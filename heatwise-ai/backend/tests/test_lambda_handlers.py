"""Lambda handlers: Mangum API handler with API Gateway HTTP API v2 events, and the worker under moto."""

from __future__ import annotations

import json

import boto3
import pytest

from backend import lambda_worker
from backend.api.dynamodb_jobs import DynamoDbJobRepository
from backend.api.jobs import JobDispatcher, JobManager
from backend.api.schemas import AssessmentRequest
from backend.config import Settings
from backend.lambda_api import build_handler
from backend.session.dynamodb_store import DynamoDbAssessmentStore
from backend.session.store import JsonFileAssessmentStore
from backend.tests.aws_fixtures import (REGION, aws, aws_credentials, create_assessments_table,  # noqa: F401
                                        create_bucket, create_jobs_table)
from backend.tests.test_api import BODY, complete_factory, make_settings

JOBS, ASSESSMENTS, BUCKET = "heatwise-test-jobs", "heatwise-test-assessments", "heatwise-test-sessions"
DEMO_BODY = {"place": {"name": "demo-hot-dry"}, "forecast_days": 3, "profile": {"elderly": True}}


def http_event(method: str, path: str, body: dict | None = None, headers: dict | None = None) -> dict:
    """A minimal API Gateway HTTP API (payload format 2.0) event."""
    return {
        "version": "2.0", "routeKey": "$default", "rawPath": path, "rawQueryString": "",
        "headers": {"host": "abc123.execute-api.us-east-1.amazonaws.com", **(headers or {})},
        "requestContext": {
            "accountId": "123456789012", "apiId": "abc123", "domainName": "abc123.execute-api.us-east-1.amazonaws.com",
            "domainPrefix": "abc123", "requestId": "req-1", "routeKey": "$default", "stage": "$default",
            "time": "10/May/2026:09:00:00 +0000", "timeEpoch": 1778403600000,
            "http": {"method": method, "path": path, "protocol": "HTTP/1.1", "sourceIp": "203.0.113.10",
                     "userAgent": "pytest"},
        },
        "body": json.dumps(body) if body is not None else None,
        "isBase64Encoded": False,
    }


class RecordingDispatcher(JobDispatcher):
    def __init__(self) -> None:
        self.job_ids: list[str] = []

    def dispatch(self, job_id: str) -> None:
        self.job_ids.append(job_id)


@pytest.fixture
def api_handler(tmp_path):
    s = make_settings()
    store = JsonFileAssessmentStore(tmp_path / "store")
    dispatcher = RecordingDispatcher()
    jobs = JobManager(lambda req, sid=None: None, store, dispatcher=dispatcher)
    handler = build_handler(s, store=store, coordinator_factory=complete_factory(s), jobs=jobs)
    handler.dispatcher = dispatcher  # type: ignore[attr-defined]
    return handler


def headers_of(resp: dict) -> dict:
    return {k.lower(): v for k, v in resp["headers"].items()}


def test_health_through_mangum(api_handler):
    resp = api_handler(http_event("GET", "/api/health"), None)
    assert resp["statusCode"] == 200
    body = json.loads(resp["body"])
    assert body["status"] == "ok" and body["version"] and body["agent_mode"] == "offline"
    assert headers_of(resp)["content-type"].startswith("application/json")


def test_post_assessment_through_mangum(api_handler):
    resp = api_handler(http_event("POST", "/api/assessments", BODY, {"content-type": "application/json"}), None)
    assert resp["statusCode"] == 202, resp["body"]
    job = json.loads(resp["body"])
    assert headers_of(resp)["location"] == f"/api/assessments/{job['job_id']}"
    assert job["status"] == "queued" and api_handler.dispatcher.job_ids == [job["job_id"]]
    bad = api_handler(http_event("POST", "/api/assessments", {**BODY, "phone": "x"},
                                 {"content-type": "application/json"}), None)
    assert bad["statusCode"] == 422 and json.loads(bad["body"])["error"]["code"] == "validation_error"


def test_cors_preflight_through_mangum(api_handler):
    pre = {"access-control-request-method": "POST", "access-control-request-headers": "Content-Type"}
    ok = api_handler(http_event("OPTIONS", "/api/assessments", headers={**pre, "origin": "http://localhost:5173"}),
                     None)
    assert ok["statusCode"] == 200
    assert headers_of(ok)["access-control-allow-origin"] == "http://localhost:5173"
    bad = api_handler(http_event("OPTIONS", "/api/assessments", headers={**pre, "origin": "http://evil.example"}),
                      None)
    assert "access-control-allow-origin" not in headers_of(bad)


# -- worker ----------------------------------------------------------------------------------
@pytest.fixture
def worker_env(aws, tmp_path):  # noqa: F811
    ddb = boto3.client("dynamodb", region_name=REGION)
    create_jobs_table(ddb, JOBS)
    create_assessments_table(ddb, ASSESSMENTS)
    create_bucket(BUCKET)
    settings = Settings(_env_file=None, agent_mode="offline", weather_provider="demo", job_store="dynamodb",
                        jobs_table_name=JOBS, assessment_store="dynamodb", assessments_table_name=ASSESSMENTS,
                        session_storage="s3", session_bucket=BUCKET, aws_region=REGION)
    repo = DynamoDbJobRepository(JOBS, client=ddb)
    store = DynamoDbAssessmentStore(ASSESSMENTS, client=ddb)
    return settings, repo, store


def session_keys(job_id: str) -> list[str]:
    s3 = boto3.client("s3", region_name=REGION)
    return [o["Key"] for o in s3.list_objects_v2(Bucket=BUCKET, Prefix=f"sessions/session_{job_id}/")
            .get("Contents", [])]


def test_worker_runs_job_and_is_idempotent(worker_env):
    settings, repo, store = worker_env
    job = repo.create(AssessmentRequest.model_validate(DEMO_BODY), max_pending=5)
    out = lambda_worker.handle({"job_id": job.job_id}, settings)
    assert out == {"job_id": job.job_id, "status": "succeeded"}
    done = repo.get(job.job_id)
    assert done.status == "succeeded" and done.report_id
    record = store.get(done.report_id)
    assert record is not None and record.report.status == "complete"
    assert record.request == AssessmentRequest.model_validate(DEMO_BODY)
    keys = session_keys(job.job_id)
    assert keys and any("/agents/agent_coordinator/messages/" in k for k in keys)

    again = lambda_worker.handle({"job_id": job.job_id}, settings)  # duplicate delivery
    assert again == {"job_id": job.job_id, "status": "succeeded"}
    assert store.count() == 1 and repo.get(job.job_id).report_id == done.report_id
    assert session_keys(job.job_id) == keys


def test_worker_failure_stores_nothing(worker_env):
    settings, repo, store = worker_env

    def boom(req):
        raise RuntimeError("model unavailable")

    job = repo.create(AssessmentRequest.model_validate(DEMO_BODY), max_pending=5)
    out = lambda_worker.handle({"job_id": job.job_id}, settings, coordinator_factory=boom, repository=repo,
                               store=store)
    assert out["status"] == "failed"
    failed = repo.get(job.job_id)
    assert failed.error.code == "assessment_failed" and failed.report_id is None
    assert store.count() == 0


@pytest.mark.parametrize("event", [{}, {"job_id": "nope"}, {"job_id": "A" * 32}, {"job_id": 5}, "x", None])
def test_worker_rejects_bad_events(event):
    with pytest.raises(ValueError):
        lambda_worker.handle(event, make_settings())
