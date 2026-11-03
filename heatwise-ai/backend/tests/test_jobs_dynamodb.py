"""DynamoDB job repository and Lambda dispatcher (moto and stub clients only; no real AWS)."""

from __future__ import annotations

import json
from datetime import datetime, timedelta, timezone

import boto3
import pytest
from fastapi.testclient import TestClient

from backend.api.app import create_app, make_run_fn
from backend.api.dynamodb_jobs import DynamoDbJobRepository, LambdaDispatcher
from backend.api.jobs import (FAILED_ERROR, JobDispatcher, JobManager, TooManyJobs, build_job_manager,
                              execute_job)
from backend.api.schemas import AssessmentRequest
from backend.session import dynamodb_schema as schema
from backend.session.dynamodb_store import DynamoDbAssessmentStore
from backend.session.store import JsonFileAssessmentStore
from backend.tests.aws_fixtures import REGION, aws, aws_credentials, create_assessments_table, create_jobs_table  # noqa: F401
from backend.tests.test_api import BODY, complete_factory, make_settings, wait_for

JOBS = "heatwise-test-jobs"
ASSESSMENTS = "heatwise-test-assessments"


@pytest.fixture
def ddb(aws):  # noqa: F811
    client = boto3.client("dynamodb", region_name=REGION)
    create_jobs_table(client, JOBS)
    create_assessments_table(client, ASSESSMENTS)
    return client


@pytest.fixture
def repo(ddb):
    return DynamoDbJobRepository(JOBS, stale_after_seconds=420, ttl_days=7, client=ddb)


def request() -> AssessmentRequest:
    return AssessmentRequest.model_validate(BODY)


def raw_item(ddb, job_id: str) -> dict:
    return ddb.get_item(TableName=JOBS, Key={schema.JOBS_PK: {"S": job_id}})["Item"]


def age(ddb, job_id: str, seconds: int) -> None:
    old = schema.ts(datetime.now(timezone.utc) - timedelta(seconds=seconds))
    ddb.update_item(TableName=JOBS, Key={schema.JOBS_PK: {"S": job_id}}, UpdateExpression="SET created_at = :c",
                    ExpressionAttributeValues={":c": {"S": old}})


class StubLambda:
    def __init__(self, status: int = 202) -> None:
        self.calls: list[dict] = []
        self.status = status

    def invoke(self, **kwargs):
        self.calls.append(kwargs)
        return {"StatusCode": self.status}


class InlineDispatcher(JobDispatcher):
    """Runs the job in the calling thread, like the worker Lambda would."""

    def __init__(self) -> None:
        self.execute = None

    def dispatch(self, job_id: str) -> None:
        self.execute(job_id)


class FailingDispatcher(JobDispatcher):
    def dispatch(self, job_id: str) -> None:
        raise RuntimeError("invoke failed")


def test_create_and_get_queued(repo, ddb):
    job = repo.create(request(), max_pending=5)
    got = repo.get(job.job_id)
    assert got.status == "queued" and got.request == request() and got.report is None and got.error is None
    assert got.job_id == job.job_id and len(job.job_id) == 32
    assert abs((got.created_at - job.created_at).total_seconds()) < 0.001
    item = raw_item(ddb, job.job_id)
    assert item[schema.PENDING_PK] == {"S": "pending"} and schema.TTL_ATTR in item
    assert repo.get("0" * 32) is None


def test_too_many_jobs(repo):
    repo.create(request(), max_pending=2)
    repo.create(request(), max_pending=2)
    with pytest.raises(TooManyJobs):
        repo.create(request(), max_pending=2)


def test_stale_job_not_counted_and_timed_out(repo, ddb):
    job = repo.create(request(), max_pending=1)
    age(ddb, job.job_id, 1000)
    repo.create(request(), max_pending=1)  # the stale job no longer counts as pending
    got = repo.get(job.job_id)
    assert got.status == "failed" and got.error.code == "assessment_timed_out"


def test_mark_running_once(repo):
    job = repo.create(request(), max_pending=5)
    running = repo.mark_running(job.job_id)
    assert running.status == "running" and running.started_at is not None
    assert repo.mark_running(job.job_id) is None
    assert repo.mark_running("f" * 32) is None


def test_worker_skips_stale_queued_job(repo, ddb):
    """A late async delivery must not start a job the API already reports as timed out."""
    job = repo.create(request(), max_pending=5)
    age(ddb, job.job_id, 1000)
    assert repo.mark_running(job.job_id) is None
    store = DynamoDbAssessmentStore(ASSESSMENTS, client=ddb)
    calls: list = []
    execute_job(job.job_id, repo, store, lambda req, sid=None: calls.append(req))
    assert calls == [] and store.count() == 0
    assert raw_item(ddb, job.job_id)["status"] == {"S": "queued"}
    got = repo.get(job.job_id)
    assert got.status == "failed" and got.error.code == "assessment_timed_out"


def test_finished_job_leaves_pending_index(repo, ddb):
    ok, bad = repo.create(request(), 5), repo.create(request(), 5)
    for j in (ok, bad):
        repo.mark_running(j.job_id)
    repo.mark_succeeded(ok.job_id, "a" * 32, None, 12.5)
    repo.mark_failed(bad.job_id, FAILED_ERROR, 3.0)
    for j in (ok, bad):
        item = raw_item(ddb, j.job_id)
        assert schema.PENDING_PK not in item and schema.TTL_ATTR in item
    s = repo.get(ok.job_id)
    assert s.status == "succeeded" and s.report_id == "a" * 32 and s.duration_ms == 12.5 and s.finished_at
    f = repo.get(bad.job_id)
    assert f.status == "failed" and f.error.code == "assessment_failed"
    assert int(raw_item(ddb, ok.job_id)[schema.TTL_ATTR]["N"]) > datetime.now(timezone.utc).timestamp() + 6 * 86400


def test_lambda_dispatcher_payload():
    stub = StubLambda()
    LambdaDispatcher("heatwise-worker", client=stub).dispatch("b" * 32)
    assert stub.calls == [{"FunctionName": "heatwise-worker", "InvocationType": "Event",
                           "Payload": json.dumps({"job_id": "b" * 32}).encode()}]
    assert json.loads(stub.calls[0]["Payload"]) == {"job_id": "b" * 32}
    with pytest.raises(RuntimeError):
        LambdaDispatcher("heatwise-worker", client=StubLambda(status=500)).dispatch("b" * 32)


def test_api_with_dynamodb_matches_memory_path(ddb, repo, tmp_path):
    s = make_settings()
    store = DynamoDbAssessmentStore(ASSESSMENTS, client=ddb)
    run_fn = make_run_fn(s, complete_factory(s))
    dispatcher = InlineDispatcher()
    dispatcher.execute = lambda jid: execute_job(jid, repo, store, run_fn)
    manager = JobManager(run_fn, store, repository=repo, dispatcher=dispatcher)
    with TestClient(create_app(s, store=store, jobs=manager)) as client:
        resp = client.post("/api/assessments", json=BODY)
        assert resp.status_code == 202 and resp.headers["location"] == f"/api/assessments/{resp.json()['job_id']}"
        job = client.get(f"/api/assessments/{resp.json()['job_id']}").json()
        assert job["status"] == "succeeded" and job["report"]["report_id"] == job["report_id"]
        assert client.get(f"/api/reports/{job['report_id']}").status_code == 200
        assert client.get("/api/assessments/nope").status_code == 404

    mem_app = create_app(s, store=JsonFileAssessmentStore(tmp_path / "store"), coordinator_factory=complete_factory(s))
    with TestClient(mem_app) as mem:
        mem_job = wait_for(mem, mem.post("/api/assessments", json=BODY).json()["job_id"])
    assert set(job) == set(mem_job)
    assert set(resp.json()) == set(mem_job)


def test_dispatch_failure_marks_job_failed(ddb, repo):
    s = make_settings()
    store = DynamoDbAssessmentStore(ASSESSMENTS, client=ddb)
    manager = JobManager(make_run_fn(s, complete_factory(s)), store, repository=repo, dispatcher=FailingDispatcher())
    with TestClient(create_app(s, store=store, jobs=manager)) as client:
        resp = client.post("/api/assessments", json=BODY)
        assert resp.status_code == 202
        assert resp.json()["status"] == "failed" and resp.json()["error"]["code"] == "dispatch_failed"
        again = client.get(f"/api/assessments/{resp.json()['job_id']}").json()
        assert again["status"] == "failed" and again["error"]["code"] == "dispatch_failed"
    assert store.count() == 0


def test_build_job_manager_selection(aws, tmp_path):  # noqa: F811
    s = make_settings()
    store = JsonFileAssessmentStore(tmp_path / "store")
    default = build_job_manager(s, lambda req, sid=None: None, store)
    assert type(default.repository).__name__ == "InMemoryJobRepository"
    assert type(default.dispatcher).__name__ == "ThreadDispatcher"
    default.shutdown(wait=True)
    aws_mgr = build_job_manager(make_settings(job_store="dynamodb", jobs_table_name=JOBS, job_dispatch="lambda",
                                              worker_function_name="heatwise-worker", aws_region=REGION),
                                lambda req, sid=None: None, store)
    assert isinstance(aws_mgr.repository, DynamoDbJobRepository)
    assert isinstance(aws_mgr.dispatcher, LambdaDispatcher)
    with pytest.raises(ValueError, match="JOBS_TABLE_NAME"):
        build_job_manager(make_settings(job_store="dynamodb"), lambda req, sid=None: None, store)
    with pytest.raises(ValueError, match="WORKER_FUNCTION_NAME"):
        build_job_manager(make_settings(job_dispatch="lambda"), lambda req, sid=None: None, store)
