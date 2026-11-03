"""Assessment logic for the optional AgentCore Runtime entrypoint (Milestone 4, D-M4-9).

No AgentCore import here, so it is tested offline. The payload is an AssessmentRequest
(`{"place", "forecast_days", "profile"}`), optionally wrapped as `{"request": {...}}`.
Returns the report as JSON-ready data and stores nothing.
"""

from __future__ import annotations

from typing import Any

from backend.api.app import CoordinatorFactory, default_coordinator_factory
from backend.api.schemas import AssessmentRequest
from backend.config import Settings, get_settings


def run_assessment(payload: dict[str, Any], session_id: str | None = None, settings: Settings | None = None,
                   coordinator_factory: CoordinatorFactory | None = None) -> dict[str, Any]:
    body = payload.get("request", payload)
    request = AssessmentRequest.model_validate(body)  # pydantic ValidationError propagates
    settings = settings or get_settings()
    factory = coordinator_factory or default_coordinator_factory(settings)
    report = factory(request).run(request.location, request.profile_as_community(), request.forecast_days,
                                  session_id=session_id)
    return report.model_dump(mode="json")
