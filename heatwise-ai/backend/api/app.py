"""FastAPI application factory for the HeatWise API (Milestones 3 and 4)."""

from __future__ import annotations

from collections.abc import Callable
from contextlib import asynccontextmanager

from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware

from backend.agents.coordinator import HeatWiseCoordinator
from backend.api.errors import install_error_handlers
from backend.api.jobs import JobManager, RunFn, build_job_manager
from backend.api.routes import APP_VERSION, router
from backend.api.schemas import AssessmentRequest
from backend.config import Settings, get_settings
from backend.models.report import PreparednessReport
from backend.session.factory import build_assessment_store
from backend.session.store import AssessmentStore

# Builds a fresh coordinator (anything with .run(location, profile, forecast_days, session_id=...)) for one job.
CoordinatorFactory = Callable[[AssessmentRequest], HeatWiseCoordinator]


def default_coordinator_factory(settings: Settings) -> CoordinatorFactory:
    if settings.agent_mode == "offline":
        from backend.agents.offline import build_offline_coordinator

        return lambda req: build_offline_coordinator(settings, req.location, req.forecast_days,
                                                     req.profile_as_community())
    return lambda req: HeatWiseCoordinator(settings)


def make_run_fn(settings: Settings, coordinator_factory: CoordinatorFactory | None = None) -> RunFn:
    """The job body shared by the thread pool and the worker Lambda: one fresh coordinator per job."""
    factory = coordinator_factory or default_coordinator_factory(settings)

    def run_fn(req: AssessmentRequest, session_id: str | None = None) -> PreparednessReport:
        return factory(req).run(req.location, req.profile_as_community(), req.forecast_days,
                                session_id=session_id)

    return run_fn


def create_app(settings: Settings | None = None, store: AssessmentStore | None = None,
               coordinator_factory: CoordinatorFactory | None = None, jobs: JobManager | None = None) -> FastAPI:
    settings = settings or get_settings()
    store = store or build_assessment_store(settings)
    jobs = jobs or build_job_manager(settings, make_run_fn(settings, coordinator_factory), store)

    @asynccontextmanager
    async def lifespan(_: FastAPI):
        yield
        jobs.shutdown(wait=False)

    app = FastAPI(title="HeatWise AI API", version=APP_VERSION, lifespan=lifespan)
    app.state.settings, app.state.store, app.state.jobs = settings, store, jobs
    app.add_middleware(CORSMiddleware, allow_origins=settings.api_cors_origins, allow_methods=["GET", "POST"],
                       allow_headers=["Content-Type"])
    install_error_handlers(app)
    # FastAPI 0.162 wraps include_router() routes in one nested entry; adding the router's routes
    # (already prefixed with /api) keeps app.routes a flat list of the six API paths.
    app.router.routes.extend(router.routes)
    return app
