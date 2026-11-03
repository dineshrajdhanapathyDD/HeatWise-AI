"""Worker Lambda: runs one assessment job (Milestone 4, D-M4-1).

The API Lambda invokes this function asynchronously with `{"job_id": "<32 hex>"}`. The job
moves queued -> running with a conditional update, so a duplicate delivery is a no-op.
The coordinator conversation is stored with session id = job id (S3 on AWS). A failed run
marks the job failed and stores no record.

Handler path: `backend.lambda_worker.handler`.
"""

from __future__ import annotations

import logging
import re
from typing import Any

from backend.api.app import CoordinatorFactory, make_run_fn
from backend.api.jobs import JobRepository, execute_job
from backend.config import Settings, get_settings
from backend.session.factory import build_assessment_store
from backend.session.store import AssessmentStore

logger = logging.getLogger("heatwise.worker")

_JOB_ID = re.compile(r"^[0-9a-f]{32}$")
_settings: Settings | None = None


def _repository(settings: Settings) -> JobRepository:
    if not settings.jobs_table_name:
        raise ValueError("JOBS_TABLE_NAME is required for the worker.")
    from backend.api.dynamodb_jobs import DynamoDbJobRepository

    return DynamoDbJobRepository(settings.jobs_table_name, stale_after_seconds=settings.job_stale_after_seconds,
                                 ttl_days=settings.job_ttl_days, region_name=settings.aws_region)


def handle(event: Any, settings: Settings | None = None, coordinator_factory: CoordinatorFactory | None = None,
           repository: JobRepository | None = None, store: AssessmentStore | None = None) -> dict[str, Any]:
    job_id = event.get("job_id") if isinstance(event, dict) else None
    if not isinstance(job_id, str) or not _JOB_ID.match(job_id):
        raise ValueError("The worker event must be {\"job_id\": \"<32 lowercase hex characters>\"}.")
    settings = settings or get_settings()
    repository = repository or _repository(settings)
    store = store or build_assessment_store(settings)
    execute_job(job_id, repository, store, make_run_fn(settings, coordinator_factory))
    job = repository.get(job_id)
    return {"job_id": job_id, "status": job.status if job else None}


def handler(event: Any, context: Any) -> dict[str, Any]:
    global _settings
    if _settings is None:
        _settings = get_settings()
        logging.basicConfig(level=_settings.log_level, format="%(levelname)s %(name)s: %(message)s", force=True)
    return handle(event, _settings)
