"""Request and response models for the HeatWise HTTP API (Milestone 3).

Requests use `extra="forbid"` so personal data such as a `name` or `phone` field is
rejected with 422 instead of being stored. The profile is community level only.
"""

from __future__ import annotations

from datetime import datetime
from typing import Literal

from pydantic import BaseModel, ConfigDict, Field, field_validator, model_validator

from backend.models.report import PreparednessReport, ReportStatus
from backend.models.risk import CommunityProfile
from backend.services.validation import normalize_location, validate_forecast_days

JobStatus = Literal["queued", "running", "succeeded", "failed"]


class PlaceInput(BaseModel):
    """One place name plus optional qualifiers; joined into the geocoding query."""

    model_config = ConfigDict(extra="forbid")

    name: str = Field(description="City, town or village")
    district: str | None = None
    state: str | None = None

    @field_validator("name", mode="before")
    @classmethod
    def _name(cls, v: object) -> str:
        return normalize_location(v)

    @field_validator("district", "state", mode="before")
    @classmethod
    def _qualifier(cls, v: object) -> str | None:
        if v is None or (isinstance(v, str) and not v.strip()):
            return None
        return normalize_location(v)

    @model_validator(mode="after")
    def _composed(self) -> PlaceInput:
        normalize_location(self.location)  # the joined query must also be a valid location
        return self

    @property
    def location(self) -> str:
        return ", ".join(p for p in (self.name, self.district, self.state) if p)


class ProfileInput(CommunityProfile):
    model_config = ConfigDict(extra="forbid")

    preferred_language: str = Field(default="en", pattern=r"^[a-z]{2,3}(-[A-Za-z]{2,4})?$")


class AssessmentRequest(BaseModel):
    model_config = ConfigDict(extra="forbid")

    place: PlaceInput
    forecast_days: int = 3
    profile: ProfileInput = Field(default_factory=ProfileInput)

    @field_validator("forecast_days", mode="before")
    @classmethod
    def _days(cls, v: object) -> int:
        return validate_forecast_days(v)

    @property
    def location(self) -> str:
        return self.place.location

    def profile_as_community(self) -> CommunityProfile:
        return CommunityProfile.model_validate(self.profile.model_dump())


class JobError(BaseModel):
    code: str
    message: str


class JobView(BaseModel):
    job_id: str
    status: JobStatus
    created_at: datetime
    started_at: datetime | None = None
    finished_at: datetime | None = None
    duration_ms: float | None = None
    report_id: str | None = None
    error: JobError | None = None
    request: AssessmentRequest
    report: PreparednessReport | None = None


class HistoryChanges(BaseModel):
    """Differences against the previous stored report for the same location key."""

    previous_report_id: str
    previous_created_at: datetime
    risk_category_from: str
    risk_category_to: str
    heat_index_delta_c: float | None = None
    max_forecast_delta_c: float | None = None
    indicators_added: list[str] = Field(default_factory=list)
    indicators_removed: list[str] = Field(default_factory=list)


class HistoryItem(BaseModel):
    report_id: str
    created_at: datetime
    duration_ms: float | None = None
    query: str
    location_name: str | None = None
    admin1: str | None = None
    country: str | None = None
    status: ReportStatus
    risk_category: str
    heat_index_c: float | None = None
    max_forecast_c: float | None = None
    indicators: list[str] = Field(default_factory=list)
    data_mode: Literal["live", "demo"] | None = None
    verification_status: Literal["passed", "failed", "not_run"]
    changes: HistoryChanges | None = None


class HistoryPage(BaseModel):
    items: list[HistoryItem]
    total: int
    limit: int
    offset: int


class VerificationCounts(BaseModel):
    passed: int = 0
    failed: int = 0
    not_run: int = 0


class ChecklistCounts(BaseModel):
    """Checklist progress over stored records; only items that are still renderable count."""

    items_completed: int = 0
    items_available: int = 0
    reports_with_progress: int = 0


class LocalizedGuidanceCounts(BaseModel):
    """Plans by language. Only English guidance exists (D6): "served" means the plan language
    equals the requested language; other requests get English with a notice."""

    served_in_requested_language: int = 0
    english_fallback: int = 0
    by_requested_language: dict[str, int] = Field(default_factory=dict)


class MetricsView(BaseModel):
    """Counts over stored records only. No user counts, nothing estimated."""

    total: int
    by_status: dict[str, int]
    by_risk_category: dict[str, int]
    by_data_mode: dict[str, int]
    plans_generated: int
    verification: VerificationCounts
    mean_pct_items_verified: float | None = None
    mean_duration_ms: float | None = None
    # Milestone 5 (D-M5-10)
    assessments_completed: int = 0
    pct_recommendations_verified: float | None = None
    checklist: ChecklistCounts = Field(default_factory=ChecklistCounts)
    localized_guidance: LocalizedGuidanceCounts = Field(default_factory=LocalizedGuidanceCounts)


class ChecklistUpdate(BaseModel):
    """Community-level checklist progress: an item id and a flag, nothing else."""

    model_config = ConfigDict(extra="forbid")

    item_id: str = Field(pattern=r"^[A-Za-z0-9_-]{1,64}$")
    completed: bool


class ChecklistProgress(BaseModel):
    report_id: str
    completed_item_ids: list[str]
    completed_count: int
    available_count: int


class HealthView(BaseModel):
    status: Literal["ok"] = "ok"
    version: str
    weather_provider: str
    agent_mode: str
    model_id: str | None = None
    demo_locations: list[str] | None = None


class FieldError(BaseModel):
    field: str
    message: str


class ErrorDetail(BaseModel):
    code: str
    message: str
    fields: list[FieldError] = Field(default_factory=list)


class ErrorBody(BaseModel):
    error: ErrorDetail
