"""Weather data models.

Every value that reaches a user carries provenance: which provider, when it was
retrieved, when the provider observed it, and whether it is live or demo data.
Missing provider fields stay `None` and are listed in `missing_fields`; they are
never estimated.
"""

from __future__ import annotations

from datetime import date, datetime
from typing import Literal

from pydantic import BaseModel, Field

DataMode = Literal["live", "demo"]


class DataProvenance(BaseModel):
    provider: str
    source_url: str
    retrieved_at: datetime = Field(description="UTC time this service fetched the data")
    observed_at: datetime | None = Field(
        default=None, description="Provider's own timestamp for the data, if supplied"
    )
    data_mode: DataMode
    is_stale: bool = False


class ResolvedLocation(BaseModel):
    query: str
    name: str
    admin1: str | None = None
    admin2: str | None = None
    country: str | None = None
    country_code: str | None = None
    latitude: float
    longitude: float
    timezone: str | None = None


class CurrentConditions(BaseModel):
    location: ResolvedLocation
    temperature_c: float | None = None
    apparent_temperature_c: float | None = None
    relative_humidity_pct: float | None = None
    wind_speed_kmh: float | None = None
    precipitation_mm: float | None = None
    missing_fields: list[str] = Field(default_factory=list)
    provenance: DataProvenance


class DailyForecast(BaseModel):
    date: date
    temperature_max_c: float | None = None
    temperature_min_c: float | None = None
    apparent_temperature_max_c: float | None = None
    precipitation_sum_mm: float | None = None
    uv_index_max: float | None = None
    relative_humidity_max_pct: float | None = None
    missing_fields: list[str] = Field(default_factory=list)


class ForecastResult(BaseModel):
    location: ResolvedLocation
    days: list[DailyForecast]
    provenance: DataProvenance
    kind: Literal["forecast"] = "forecast"
    note: str = "Model forecast values. These are not official warnings."


class WeatherAlert(BaseModel):
    """An official warning from a meteorological authority. Never generated locally."""

    issuer: str
    headline: str
    severity: str | None = None
    effective: datetime | None = None
    expires: datetime | None = None
    source_url: str


class AlertsResult(BaseModel):
    location: ResolvedLocation
    alerts_supported: bool
    alerts: list[WeatherAlert] = Field(default_factory=list)
    explanation: str
    official_sources: list[str] = Field(default_factory=list)
    provenance: DataProvenance


class ToolErrorPayload(BaseModel):
    error_code: Literal[
        "invalid_location",
        "invalid_argument",
        "location_not_found",
        "provider_timeout",
        "provider_unavailable",
        "provider_data_error",
    ]
    message: str
    retryable: bool = False


# ---------------------------------------------------------------------------
# Agent-level models
# ---------------------------------------------------------------------------


class WeatherSummary(BaseModel):
    """Structured output the Weather Intelligence Agent's model must produce.

    The numeric fields are the model's claims. They are checked against the
    evidence ledger and are never shown to users directly.
    """

    location_name: str = Field(description="Resolved location name exactly as returned by the tools")
    summary: str = Field(description="Two or three plain sentences on current heat conditions and the forecast trend")
    claimed_temperature_c: float | None = Field(
        default=None, description="Current temperature copied from get_weather, or null if unavailable"
    )
    claimed_apparent_temperature_c: float | None = Field(
        default=None, description="Current apparent temperature copied from get_weather, or null"
    )
    claimed_humidity_pct: float | None = Field(
        default=None, description="Current relative humidity copied from get_weather, or null"
    )
    claimed_max_forecast_temperature_c: float | None = Field(
        default=None, description="Highest daily max temperature in the forecast, or null"
    )
    # Data gaps are deliberately not requested from the model. They are derived from
    # the evidence ledger. (Nova 2 Lite returned a number for a list field here in
    # live testing, which failed validation on every retry.)


class ConsistencyIssue(BaseModel):
    field: str
    claimed: float | None
    actual: float | None
    message: str


class WeatherIntelligenceResult(BaseModel):
    """Final Weather Intelligence Agent output. Measurements come only from tool results."""

    status: Literal["ok", "partial", "no_data", "error"]
    query: str
    location: ResolvedLocation | None = None
    current: CurrentConditions | None = None
    forecast: ForecastResult | None = None
    alerts: AlertsResult | None = None
    summary: str | None = None
    data_mode: DataMode | None = None
    sources: list[str] = Field(default_factory=list)
    retrieved_at: datetime | None = None
    is_stale: bool = False
    missing_information: list[str] = Field(default_factory=list)
    errors: list[ToolErrorPayload] = Field(default_factory=list)
    consistency_issues: list[ConsistencyIssue] = Field(default_factory=list)
    tools_called: list[str] = Field(default_factory=list)
