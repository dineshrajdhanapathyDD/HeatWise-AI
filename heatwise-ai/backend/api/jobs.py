"""Assessment jobs: a repository for job state plus a dispatcher that runs them (D-M4-1).

Local default: `InMemoryJobRepository` (jobs live only in this process and are lost on
restart) and `ThreadDispatcher` (a small thread pool). On AWS: `DynamoDbJobRepository`
and `LambdaDispatcher` (backend/api/dynamodb_jobs.py), where the worker Lambda calls the
same `execute_job`. Each job runs `run_fn(request, session_id)`, which must build its own
coordinator (the coordinator keeps per-run state and is not shared between threads).
"""

from __future__ import annotations

import logging
import threading
import time
import uuid
from abc import ABC, abstractmethod
from collections.abc import Callable
from concurrent.futures import ThreadPoolExecutor
from dataclasses import dataclass, field, replace
from datetime import datetime, timezone
from typing import TYPE_CHECKING

from backend.api.schemas import AssessmentRequest, JobError, JobStatus
from backend.models.report import PreparednessReport
from backend.session.store import AssessmentRecord, AssessmentStore

if TYPE_CHECKING:
    from backend.config import Settings

logger = logging.getLogger("heatwise.jobs")

FAILED_ERROR = JobError(code="assessment_failed",
                        message="The assessment could not be completed. Check the server log.")
DISPATCH_FAILED_ERROR = JobError(code="dispatch_failed",
                                 message="The assessment could not be started. Try again shortly.")

# run_fn(request, session_id) -> report; session_id is the job id (one coordinator session per job).
RunFn = Callable[[AssessmentRequest, str | None], PreparednessReport]


class TooManyJobs(Exception):
    """Raised when queued plus running jobs reach the configured limit."""


def _now() -> datetime:
    return datetime.now(timezone.utc)


@dataclass
class Job:
    request: AssessmentRequest
    job_id: str = field(default_factory=lambda: uuid.uuid4().hex)
    status: JobStatus = "queued"
    created_at: datetime = field(default_factory=_now)
    started_at: datetime | None = None
    finished_at: datetime | None = None
    duration_ms: float | None = None
    report_id: str | None = None
    report: PreparednessReport | None = None
    error: JobError | None = None

    @property
    def finished(self) -> bool:
        return self.status in ("succeeded", "failed")


# -- repositories ------------------------------------------------------------------------------
class JobRepository(ABC):
    """Job state. Every method returns a snapshot copy, never a live object."""

    @abstractmethod
    def create(self, request: AssessmentRequest, max_pending: int) -> Job:
        """Store a new queued job; raise TooManyJobs when `max_pending` jobs are queued or running."""

    @abstractmethod
    def get(self, job_id: str) -> Job | None: ...

    @abstractmethod
    def mark_running(self, job_id: str) -> Job | None:
        """Move a queued job to running; None when the job is missing or not queued."""

    @abstractmethod
    def mark_succeeded(self, job_id: str, report_id: str, report: PreparednessReport | None,
                       duration_ms: float | None) -> None: ...

    @abstractmethod
    def mark_failed(self, job_id: str, error: JobError, duration_ms: float | None) -> None: ...


class InMemoryJobRepository(JobRepository):
    def __init__(self, max_retained: int = 200) -> None:
        self._max_retained = max_retained
        self._jobs: dict[str, Job] = {}  # insertion order = creation order
        self._lock = threading.Lock()

    def create(self, request: AssessmentRequest, max_pending: int) -> Job:
        with self._lock:
            pending = sum(1 for j in self._jobs.values() if not j.finished)
            if pending >= max_pending:
                raise TooManyJobs(f"{pending} assessments are already queued or running.")
            job = Job(request=request)
            self._jobs[job.job_id] = job
            return replace(job)

    def get(self, job_id: str) -> Job | None:
        """A copy taken under the lock, so readers never see a half-applied update."""
        with self._lock:
            job = self._jobs.get(job_id)
            return replace(job) if job is not None else None

    def _update(self, job_id: str, **changes) -> Job | None:
        with self._lock:
            job = self._jobs.get(job_id)
            if job is None:
                return None
            for k, v in changes.items():
                setattr(job, k, v)
            return replace(job)

    def mark_running(self, job_id: str) -> Job | None:
        with self._lock:
            job = self._jobs.get(job_id)
            if job is None or job.status != "queued":
                return None
            job.status, job.started_at = "running", _now()
            return replace(job)

    def mark_succeeded(self, job_id: str, report_id: str, report: PreparednessReport | None,
                       duration_ms: float | None) -> None:
        self._update(job_id, status="succeeded", finished_at=_now(), duration_ms=duration_ms,
                     report_id=report_id, report=report)
        self._evict()

    def mark_failed(self, job_id: str, error: JobError, duration_ms: float | None) -> None:
        self._update(job_id, status="failed", finished_at=_now(), error=error, duration_ms=duration_ms)
        self._evict()

    def _evict(self) -> None:
        with self._lock:
            excess = len(self._jobs) - self._max_retained
            if excess <= 0:
                return
            for jid in [j.job_id for j in self._jobs.values() if j.finished][:excess]:
                del self._jobs[jid]


# -- execution ---------------------------------------------------------------------------------
def execute_job(job_id: str, repository: JobRepository, store: AssessmentStore, run_fn: RunFn) -> None:
    """Run one job: queued -> running -> succeeded (record stored) or failed (nothing stored).

    A job that is not queued (already running, finished or unknown) is left alone, so a
    duplicate delivery to the worker is a no-op.
    """
    job = repository.mark_running(job_id)
    if job is None:
        logger.info("job %s is not queued; skipped", job_id)
        return
    start = time.perf_counter()
    try:
        report = run_fn(job.request, job.job_id)
        duration_ms = round((time.perf_counter() - start) * 1000, 1)
        store.save(AssessmentRecord(report_id=report.report_id, created_at=report.created_at,
                                    duration_ms=duration_ms, request=job.request, report=report))
    except Exception:
        logger.exception("assessment job %s failed", job_id)
        repository.mark_failed(job_id, FAILED_ERROR, round((time.perf_counter() - start) * 1000, 1))
    else:
        repository.mark_succeeded(job_id, report.report_id, report, duration_ms)


class JobDispatcher(ABC):
    @abstractmethod
    def dispatch(self, job_id: str) -> None:
        """Start running a queued job somewhere else; raise if it cannot be started."""

    def shutdown(self, wait: bool = False) -> None:  # noqa: B027 - optional hook
        """Release resources; the default has none."""


class ThreadDispatcher(JobDispatcher):
    def __init__(self, execute: Callable[[str], None], max_workers: int = 2) -> None:
        self._execute = execute
        self._executor = ThreadPoolExecutor(max_workers=max_workers, thread_name_prefix="heatwise-job")

    def dispatch(self, job_id: str) -> None:
        self._executor.submit(self._execute, job_id)

    def shutdown(self, wait: bool = False) -> None:
        self._executor.shutdown(wait=wait, cancel_futures=True)


# -- manager -----------------------------------------------------------------------------------
class JobManager:
    def __init__(self, run_fn: RunFn, store: AssessmentStore, max_workers: int = 2, max_pending: int = 20,
                 max_retained: int = 200, repository: JobRepository | None = None,
                 dispatcher: JobDispatcher | None = None) -> None:
        self._run_fn = run_fn
        self._store = store
        self._max_pending = max_pending
        self.repository = repository or InMemoryJobRepository(max_retained=max_retained)
        self.dispatcher = dispatcher or ThreadDispatcher(
            lambda job_id: execute_job(job_id, self.repository, self._store, self._run_fn), max_workers)

    def submit(self, request: AssessmentRequest) -> Job:
        job = self.repository.create(request, self._max_pending)
        try:
            self.dispatcher.dispatch(job.job_id)
        except Exception:
            logger.exception("assessment job %s could not be dispatched", job.job_id)
            self.repository.mark_failed(job.job_id, DISPATCH_FAILED_ERROR, None)
            return self.repository.get(job.job_id) or job
        return job

    def get(self, job_id: str) -> Job | None:
        job = self.repository.get(job_id)
        if job is not None and job.status == "succeeded" and job.report is None and job.report_id:
            record = self._store.get(job.report_id)
            if record is not None:
                job = replace(job, report=record.report)
        return job

    def shutdown(self, wait: bool = False) -> None:
        self.dispatcher.shutdown(wait=wait)


def build_job_manager(settings: Settings, run_fn: RunFn, store: AssessmentStore) -> JobManager:
    """Memory + thread by default; JOB_STORE=dynamodb and JOB_DISPATCH=lambda for AWS."""
    repository: JobRepository | None = None
    dispatcher: JobDispatcher | None = None
    if settings.job_store == "dynamodb":
        if not settings.jobs_table_name:
            raise ValueError("JOBS_TABLE_NAME is required when JOB_STORE=dynamodb.")
        from backend.api.dynamodb_jobs import DynamoDbJobRepository

        repository = DynamoDbJobRepository(settings.jobs_table_name,
                                           stale_after_seconds=settings.job_stale_after_seconds,
                                           ttl_days=settings.job_ttl_days, region_name=settings.aws_region)
    if settings.job_dispatch == "lambda":
        if not settings.worker_function_name:
            raise ValueError("WORKER_FUNCTION_NAME is required when JOB_DISPATCH=lambda.")
        from backend.api.dynamodb_jobs import LambdaDispatcher

        dispatcher = LambdaDispatcher(settings.worker_function_name, region_name=settings.aws_region)
    return JobManager(run_fn, store, max_workers=settings.api_job_workers,
                      max_pending=settings.api_max_pending_jobs, repository=repository, dispatcher=dispatcher)
