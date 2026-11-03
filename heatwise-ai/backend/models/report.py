"""Preparedness report produced by the HeatWise Coordinator.

Everything in the report is assembled in code from specialist results: weather
values from the weather ledger, the risk category from deterministic rules, plan
items from the verified catalog and pass/fail from deterministic safety checks.
"""

from __future__ import annotations

from datetime import datetime
from typing import Any, Literal

from pydantic import BaseModel, Field

from backend.guidance.sources import TRUSTED_SOURCES
from backend.models.plan import PreparednessPlan
from backend.models.risk import RiskAssessment
from backend.models.verification import VerificationResult
from backend.models.weather import (
    AlertsResult,
    CurrentConditions,
    ForecastResult,
    ResolvedLocation,
    WeatherIntelligenceResult,
)

ReportStatus = Literal["complete", "needs_human_review", "incomplete"]


class EvidenceItem(BaseModel):
    kind: str
    description: str
    value: float | str | None = None
    unit: str | None = None
    source_url: str | None = None
    retrieved_at: datetime | None = None


class WeatherSourceInfo(BaseModel):
    provider: str | None = None
    source_urls: list[str] = Field(default_factory=list)
    data_mode: Literal["live", "demo"] | None = None


class AgentTraceEntry(BaseModel):
    agent: str
    tool: str
    status: Literal["success", "error", "cancelled"]
    duration_ms: float | None = None
    cancel_reason: str | None = None
    input_summary: dict[str, Any] = Field(default_factory=dict)
    step_index: int


class PreparednessReport(BaseModel):
    report_id: str
    created_at: datetime
    status: ReportStatus
    query: str
    location: ResolvedLocation | None = None
    data_retrieved_at: datetime | None = None
    weather_source: WeatherSourceInfo = Field(default_factory=WeatherSourceInfo)
    weather_summary: str | None = None
    risk_category: str = "unknown"
    risk: RiskAssessment | None = None
    evidence: list[EvidenceItem] = Field(default_factory=list)
    recommended_actions: PreparednessPlan | None = None
    checklist_markdown: str | None = None
    missing_information: list[str] = Field(default_factory=list)
    verification_status: Literal["passed", "failed", "not_run"] = "not_run"
    verification: VerificationResult | None = None
    revision_count: int = 0
    consistency_issues: list[str] = Field(default_factory=list)
    steering_blocks: list[dict[str, str]] = Field(default_factory=list)
    trace: list[AgentTraceEntry] = Field(default_factory=list)
    notices: list[str] = Field(default_factory=list)
    # Tool-returned weather detail for the dashboard (M3). Optional so older stored reports still parse.
    current_conditions: CurrentConditions | None = None
    forecast: ForecastResult | None = None
    alerts: AlertsResult | None = None


def evidence_from(weather: WeatherIntelligenceResult | None, risk: RiskAssessment | None) -> list[EvidenceItem]:
    """Evidence list: tool-returned weather values plus rule outputs, each with its source."""
    out: list[EvidenceItem] = []
    if weather is not None and weather.current is not None:
        c = weather.current
        url, at = c.provenance.source_url, c.provenance.retrieved_at
        for kind, desc, value, unit in (
            ("current_temperature", "Current air temperature", c.temperature_c, "°C"),
            ("current_apparent_temperature", "Current apparent temperature (provider metric)",
             c.apparent_temperature_c, "°C"),
            ("current_relative_humidity", "Current relative humidity", c.relative_humidity_pct, "%"),
        ):
            if value is not None:
                out.append(EvidenceItem(kind=kind, description=desc, value=value, unit=unit,
                                        source_url=url, retrieved_at=at))
    if weather is not None and weather.forecast is not None:
        f = weather.forecast
        for d in f.days:
            if d.temperature_max_c is not None:
                out.append(EvidenceItem(kind="forecast_max_temperature",
                                        description=f"Forecast maximum temperature on {d.date.isoformat()}",
                                        value=d.temperature_max_c, unit="°C", source_url=f.provenance.source_url,
                                        retrieved_at=f.provenance.retrieved_at))
    if weather is not None and weather.alerts is not None and not weather.alerts.alerts_supported:
        a = weather.alerts
        out.append(EvidenceItem(kind="official_alerts", description=a.explanation, value="not available",
                                source_url=a.provenance.source_url, retrieved_at=a.provenance.retrieved_at))
    if risk is not None:
        if risk.heat_index_c is not None:
            src = TRUSTED_SOURCES.get("wpc_heat_index_equation")
            out.append(EvidenceItem(kind="heat_index", description=f"NWS heat index ({risk.heat_index_band or 'below Caution'})",
                                    value=risk.heat_index_c, unit="°C", source_url=src.url if src else None))
        for factor in risk.contributing_factors:
            if factor.code == "heat_index":
                continue
            src = TRUSTED_SOURCES.get(factor.source_id) if factor.source_id else None
            out.append(EvidenceItem(kind=factor.code, description=factor.description, value=factor.value,
                                    unit=factor.unit, source_url=src.url if src else None))
    return out
