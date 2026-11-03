"""DynamoDB job repository and async Lambda dispatcher (Milestone 4, D-M4-1, D-M4-5).

Jobs table item: job_id, status, created_at, started_at, finished_at, duration_ms, report_id,
error_code, error_message, request_json, pending_pk (only while queued or running, so the
sparse `pending` index counts open jobs) and expires_at (epoch seconds, DynamoDB TTL).
The report itself is not stored here; `JobManager.get` reads it from the assessment store.
"""

from __future__ import annotations

import json
import logging
from dataclasses import replace
from datetime import datetime, timedelta, timezone
from typing import Any

import boto3
from botocore.exceptions import ClientError

from backend.api.jobs import Job, JobDispatcher, JobRepository, TooManyJobs
from backend.api.schemas import AssessmentRequest, JobError
from backend.models.report import PreparednessReport
from backend.session import dynamodb_schema as schema

logger = logging.getLogger("heatwise.jobs.dynamodb")

TIMED_OUT_ERROR = JobError(code="assessment_timed_out",
                           message="The assessment did not finish in time. Try again.")


def _s(value: str) -> dict[str, str]:
    return {"S": value}


def _n(value: float) -> dict[str, str]:
    return {"N": repr(float(value))}


class DynamoDbJobRepository(JobRepository):
    def __init__(self, table_name: str, stale_after_seconds: int = 420, ttl_days: int = 7, client: Any = None,
                 region_name: str | None = None) -> None:
        self.table_name = table_name
        self.stale_after = timedelta(seconds=stale_after_seconds)
        self.ttl = timedelta(days=ttl_days)
        self.client = client or boto3.client("dynamodb", region_name=region_name)

    # -- helpers ---------------------------------------------------------------------------
    def _count_pending(self, now: datetime) -> int:
        params: dict[str, Any] = {
            "TableName": self.table_name, "IndexName": schema.PENDING_INDEX, "Select": "COUNT",
            "KeyConditionExpression": "#p = :p AND #c >= :cutoff",
            "ExpressionAttributeNames": {"#p": schema.PENDING_PK, "#c": schema.CREATED_AT},
            "ExpressionAttributeValues": {":p": _s(schema.PENDING_VALUE),
                                          ":cutoff": _s(schema.ts(now - self.stale_after))},
        }
        total = 0
        while True:
            page = self.client.query(**params)
            total += page["Count"]
            if "LastEvaluatedKey" not in page:
                return total
            params["ExclusiveStartKey"] = page["LastEvaluatedKey"]

    @staticmethod
    def _to_job(item: dict[str, dict[str, Any]]) -> Job:
        def opt(name: str) -> str | None:
            v = item.get(name)
            return v["S"] if v and "S" in v else None

        def when(name: str) -> datetime | None:
            v = opt(name)
            return schema.parse_ts(v) if v else None

        duration = item.get("duration_ms")
        error = (JobError(code=item["error_code"]["S"], message=item["error_message"]["S"])
                 if "error_code" in item else None)
        return Job(request=AssessmentRequest.model_validate_json(item["request_json"]["S"]),
                   job_id=item[schema.JOBS_PK]["S"], status=item["status"]["S"],
                   created_at=schema.parse_ts(item[schema.CREATED_AT]["S"]), started_at=when("started_at"),
                   finished_at=when("finished_at"),
                   duration_ms=float(duration["N"]) if duration and "N" in duration else None,
                   report_id=opt("report_id"), error=error)

    def _finish(self, job_id: str, values: dict[str, dict[str, Any]]) -> None:
        names = {f"#a{i}": k for i, k in enumerate(values)}
        sets = ", ".join(f"#a{i} = :v{i}" for i in range(len(values)))
        self.client.update_item(
            TableName=self.table_name, Key={schema.JOBS_PK: _s(job_id)},
            UpdateExpression=f"SET {sets} REMOVE #pp",
            ConditionExpression=f"attribute_exists({schema.JOBS_PK})",
            ExpressionAttributeNames={**names, "#pp": schema.PENDING_PK},
            ExpressionAttributeValues={f":v{i}": v for i, v in enumerate(values.values())},
        )

    # -- JobRepository ---------------------------------------------------------------------
    def create(self, request: AssessmentRequest, max_pending: int) -> Job:
        now = datetime.now(timezone.utc)
        pending = self._count_pending(now)
        if pending >= max_pending:
            raise TooManyJobs(f"{pending} assessments are already queued or running.")
        job = Job(request=request, created_at=now)
        self.client.put_item(
            TableName=self.table_name,
            Item={
                schema.JOBS_PK: _s(job.job_id), "status": _s(job.status), schema.CREATED_AT: _s(schema.ts(now)),
                "request_json": _s(request.model_dump_json()), schema.PENDING_PK: _s(schema.PENDING_VALUE),
                schema.TTL_ATTR: {"N": str(int((now + self.ttl).timestamp()))},
            },
            ConditionExpression=f"attribute_not_exists({schema.JOBS_PK})",
        )
        return replace(job)

    def get(self, job_id: str) -> Job | None:
        item = self.client.get_item(TableName=self.table_name, Key={schema.JOBS_PK: _s(job_id)},
                                    ConsistentRead=True).get("Item")
        if not item:
            return None
        job = self._to_job(item)
        if not job.finished and datetime.now(timezone.utc) - job.created_at > self.stale_after:
            return replace(job, status="failed", error=TIMED_OUT_ERROR)
        return job

    def mark_running(self, job_id: str) -> Job | None:
        # A queued job older than the stale window is already reported as timed out by `get`,
        # so a late async delivery must not start it (no Bedrock spend, no status flip).
        now = datetime.now(timezone.utc)
        try:
            resp = self.client.update_item(
                TableName=self.table_name, Key={schema.JOBS_PK: _s(job_id)},
                UpdateExpression="SET #s = :running, started_at = :now",
                ConditionExpression="#s = :queued AND #c >= :cutoff",
                ExpressionAttributeNames={"#s": "status", "#c": schema.CREATED_AT},
                ExpressionAttributeValues={":running": _s("running"), ":queued": _s("queued"),
                                           ":now": _s(schema.ts(now)),
                                           ":cutoff": _s(schema.ts(now - self.stale_after))},
                ReturnValues="ALL_NEW",
            )
        except ClientError as exc:
            if exc.response.get("Error", {}).get("Code") == "ConditionalCheckFailedException":
                return None
            raise
        return self._to_job(resp["Attributes"])

    def mark_succeeded(self, job_id: str, report_id: str, report: PreparednessReport | None,
                       duration_ms: float | None) -> None:
        values = {"status": _s("succeeded"), "finished_at": _s(schema.ts()), "report_id": _s(report_id)}
        if duration_ms is not None:
            values["duration_ms"] = _n(duration_ms)
        self._finish(job_id, values)

    def mark_failed(self, job_id: str, error: JobError, duration_ms: float | None) -> None:
        values = {"status": _s("failed"), "finished_at": _s(schema.ts()), "error_code": _s(error.code),
                  "error_message": _s(error.message)}
        if duration_ms is not None:
            values["duration_ms"] = _n(duration_ms)
        self._finish(job_id, values)


class LambdaDispatcher(JobDispatcher):
    """Start the worker Lambda asynchronously with {"job_id": ...}; the API returns 202 at once."""

    def __init__(self, function_name: str, client: Any = None, region_name: str | None = None) -> None:
        self.function_name = function_name
        self.client = client or boto3.client("lambda", region_name=region_name)

    def dispatch(self, job_id: str) -> None:
        resp = self.client.invoke(FunctionName=self.function_name, InvocationType="Event",
                                  Payload=json.dumps({"job_id": job_id}).encode())
        if resp.get("StatusCode") != 202:
            raise RuntimeError(f"worker invoke returned status {resp.get('StatusCode')}")
