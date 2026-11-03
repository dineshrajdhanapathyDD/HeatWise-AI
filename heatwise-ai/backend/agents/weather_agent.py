"""Weather Intelligence Agent.

The Strands agent decides which weather tools to call and writes a short summary
(structured output `WeatherSummary`). The final `WeatherIntelligenceResult` is
then assembled from the evidence ledger, i.e. from what the tools actually
returned. Numbers the model states are diffed against the ledger; if they
disagree, the model's summary is replaced by a deterministic one.
"""

from __future__ import annotations

import logging
from typing import Any

from pydantic import ValidationError as PydanticValidationError
from strands import Agent, tool
from strands.models import Model

from backend.agents.hooks import EvidenceLedgerHook, GuardrailHook
from backend.agents.model_factory import build_bedrock_model
from backend.config import Settings
from backend.models.trace import ToolCallRecord
from backend.models.weather import (
    AlertsResult,
    ConsistencyIssue,
    CurrentConditions,
    ForecastResult,
    ToolErrorPayload,
    WeatherIntelligenceResult,
    WeatherSummary,
)
from backend.services.claims import check_text_claims
from backend.services.risk_rules import c_to_f
from backend.services.validation import ValidationError, normalize_location, validate_forecast_days
from backend.services.weather.base import WeatherProvider
from backend.services.weather.factory import build_weather_provider
from backend.tools.weather_tools import WEATHER_TOOL_NAMES, build_weather_tools

logger = logging.getLogger("heatwise.weather_agent")

AGENT_NAME = "weather_intelligence"
STRUCTURED_TOOL = WeatherSummary.__name__
NUMERIC_TOLERANCE = 0.5
STRUCTURED_OUTPUT_ATTEMPTS = 2  # fail fast to the deterministic summary

SYSTEM_PROMPT = """You are the Weather Intelligence Agent for HeatWise AI, a heatwave preparedness assistant.

Your job: retrieve weather data for the requested place using your tools, then report it.

Rules:
- Call get_weather, get_forecast and get_weather_alerts for the requested location. Call each once.
  Use the location text exactly as given to you.
- Only report values that appear in tool results. Never estimate, round loosely, or invent values.
- Do not describe anything the tools do not return, such as sky, cloud cover or rain chances.
- If a tool returns an error or a field is null, say the data is unavailable and set that claimed_* field to null.
- When you call WeatherSummary, copy claimed_* numbers exactly from the tool results.
- Forecast values are not official warnings. If get_weather_alerts reports alerts_supported=false,
  say that no official warnings are available from this provider. Never describe a warning that a tool did not return.
- If the data is labelled data_mode "demo", say clearly that it is demonstration data.
- Do not give medical advice. Keep the summary to two or three plain sentences."""


def _validate_location_input(tool_input: Any) -> None:
    normalize_location(tool_input.get("location"))


def _validate_forecast_input(tool_input: Any) -> None:
    normalize_location(tool_input.get("location"))
    if "days" in tool_input:
        validate_forecast_days(tool_input["days"])


class WeatherIntelligenceAgent:
    def __init__(
        self,
        settings: Settings,
        provider: WeatherProvider | None = None,
        model: Model | None = None,
    ) -> None:
        self.settings = settings
        self.provider = provider or build_weather_provider(settings)
        self._model = model
        self.tools = build_weather_tools(self.provider)
        self.last_trace: list[ToolCallRecord] = []
        self.last_blocked: list[dict[str, str]] = []

    @property
    def model(self) -> Model:
        if self._model is None:
            self._model = build_bedrock_model(self.settings)
        return self._model

    def _build_agent(self) -> tuple[Agent, GuardrailHook, EvidenceLedgerHook]:
        guardrail = GuardrailHook(
            allowed_tools=WEATHER_TOOL_NAMES,
            max_tool_calls=self.settings.agent_max_tool_calls,
            validators={
                "get_weather": _validate_location_input,
                "get_weather_alerts": _validate_location_input,
                "get_forecast": _validate_forecast_input,
            },
            uncounted_tools=[STRUCTURED_TOOL],
        )
        ledger = EvidenceLedgerHook(ignored_tools=[STRUCTURED_TOOL])
        agent = Agent(
            name=AGENT_NAME,
            description="Retrieves current weather, forecast and official alert availability for a place.",
            model=self.model,
            tools=self.tools,
            system_prompt=SYSTEM_PROMPT,
            hooks=[guardrail, ledger],
            structured_output_model=WeatherSummary,
            callback_handler=None,
        )
        return agent, guardrail, ledger

    def run(self, location: str, forecast_days: int = 3) -> WeatherIntelligenceResult:
        try:
            query = normalize_location(location)
            days = validate_forecast_days(forecast_days)
        except ValidationError as exc:
            code = "invalid_argument" if "days" in str(exc).lower() else "invalid_location"
            return WeatherIntelligenceResult(
                status="error", query=str(location)[:120],
                errors=[ToolErrorPayload(error_code=code, message=str(exc))],  # type: ignore[arg-type]
                missing_information=["No weather data retrieved because the request was invalid."],
            )

        agent, guardrail, ledger = self._build_agent()
        prompt = f"Location: {query}\nForecast days: {days}\nRetrieve the weather data and report it."
        summary: WeatherSummary | None = None
        agent_error: str | None = None
        try:
            result = agent(
                prompt,
                limits={
                    "turns": self.settings.agent_max_turns,
                    "structured_output_attempts": STRUCTURED_OUTPUT_ATTEMPTS,
                },
            )
            summary = result.structured_output if isinstance(result.structured_output, WeatherSummary) else None
            if summary is None:
                agent_error = f"Agent stopped without a structured summary (stop_reason={result.stop_reason})."
        except Exception as exc:  # model/service failures must not crash the workflow
            logger.exception("weather agent invocation failed")
            agent_error = f"Weather agent failed: {type(exc).__name__}"

        self.last_trace = list(ledger.records)
        self.last_blocked = list(guardrail.blocked)
        return build_result(query, ledger.records, summary, agent_error)

    def as_tool(self):
        """Agents-as-tools wrapper (workshop Module 6) for the coordinator."""
        specialist = self

        @tool
        def weather_intelligence(location: str, forecast_days: int = 3) -> str:
            """Delegate to the Weather Intelligence Agent. Returns verified, source-attributed
            current weather, forecast and official-alert availability for a location as JSON.

            Args:
                location: Village, town, city or district, optionally with state or country.
                forecast_days: Number of forecast days, 1 to 7.
            """
            return specialist.run(location, forecast_days).model_dump_json()

        return weather_intelligence


# ---------------------------------------------------------------------------
# Result assembly (pure functions, unit-tested without a model)
# ---------------------------------------------------------------------------


def _first_part(text: str) -> str:
    return text.split(",")[0].strip().casefold()


def build_result(
    query: str,
    records: list[ToolCallRecord],
    summary: WeatherSummary | None,
    agent_error: str | None = None,
) -> WeatherIntelligenceResult:
    issues: list[ConsistencyIssue] = []
    errors: list[ToolErrorPayload] = []
    missing: list[str] = []

    # Only evidence for the requested place counts. A tool call for a different
    # place (model drift) is flagged and ignored.
    relevant: list[ToolCallRecord] = []
    for r in records:
        loc = r.input_summary.get("location")
        if isinstance(loc, str) and _first_part(loc) != _first_part(query):
            issues.append(ConsistencyIssue(field="location", claimed=None, actual=None,
                                           message=f"{r.tool} was called for '{loc}', not '{query}'. Ignored."))
            continue
        relevant.append(r)

    def latest(tool_name: str, model_cls):
        for r in reversed(relevant):
            if r.tool == tool_name and r.status == "success" and isinstance(r.payload, dict):
                try:
                    return model_cls.model_validate(r.payload)
                except PydanticValidationError:
                    missing.append(f"{tool_name} returned data in an unexpected format.")
                    return None
        return None

    current: CurrentConditions | None = latest("get_weather", CurrentConditions)
    forecast: ForecastResult | None = latest("get_forecast", ForecastResult)
    alerts: AlertsResult | None = latest("get_weather_alerts", AlertsResult)

    for r in relevant:
        if r.status == "error" and isinstance(r.payload, dict):
            try:
                errors.append(ToolErrorPayload.model_validate(r.payload))
            except PydanticValidationError:
                missing.append(f"{r.tool} failed.")
        elif r.status == "cancelled":
            missing.append(f"{r.tool} was blocked: {r.cancel_reason}")

    for name, value in (("current conditions", current), ("forecast", forecast), ("official alerts", alerts)):
        if value is None:
            missing.append(f"No {name} retrieved.")
    if current is not None:
        missing.extend(f"Current {f} not supplied by provider." for f in current.missing_fields)
        if current.provenance.is_stale:
            missing.append("Current conditions are older than the freshness threshold.")
    if alerts is not None and not alerts.alerts_supported:
        missing.append("Official warnings are not available from this provider.")
    if agent_error:
        missing.append(agent_error)

    if current is None and forecast is None:
        return WeatherIntelligenceResult(
            status="error" if errors and all(e.error_code != "location_not_found" for e in errors) else "no_data",
            query=query, errors=errors, missing_information=_dedupe(missing),
            consistency_issues=issues, tools_called=[r.tool for r in records],
        )

    if current is not None and forecast is not None:
        a, b = current.location, forecast.location
        if abs(a.latitude - b.latitude) > 0.01 or abs(a.longitude - b.longitude) > 0.01:
            issues.append(ConsistencyIssue(field="location", claimed=None, actual=None,
                                           message="Current conditions and forecast resolved to different places."))

    if summary is not None:
        issues.extend(_check_claims(summary, current, forecast))
        # Free-text claims (numbers with units, sky/rain, warnings) must also be in the ledger.
        alerts_supported = bool(alerts and alerts.alerts_supported)
        for problem in check_text_claims(summary.summary, weather_evidence_numbers(current, forecast),
                                         alerts_supported):
            issues.append(ConsistencyIssue(field="summary_text", claimed=None, actual=None, message=problem))

    use_model_summary = summary is not None and not any(i.field != "location" for i in issues)
    text = summary.summary if use_model_summary else deterministic_summary(current, forecast, alerts)

    provenances = [x.provenance for x in (current, forecast, alerts) if x is not None]
    modes = {p.data_mode for p in provenances}
    location = (current or forecast).location  # type: ignore[union-attr]
    status = "ok" if current and forecast and alerts and not errors else "partial"

    return WeatherIntelligenceResult(
        status=status,
        query=query,
        location=location,
        current=current,
        forecast=forecast,
        alerts=alerts,
        summary=text,
        data_mode="demo" if "demo" in modes else "live",
        sources=_dedupe([p.source_url for p in provenances]),
        retrieved_at=min(p.retrieved_at for p in provenances),
        is_stale=bool(current and current.provenance.is_stale),
        missing_information=_dedupe(missing),
        errors=errors,
        consistency_issues=issues,
        tools_called=[r.tool for r in records],
    )


def weather_evidence_numbers(current: CurrentConditions | None, forecast: ForecastResult | None) -> set[float]:
    """Numbers free text may state about the weather: tool values plus °F forms of temperatures."""
    nums: set[float] = set()
    if current is not None:
        for x in (current.temperature_c, current.apparent_temperature_c, current.relative_humidity_pct):
            if x is not None:
                nums.add(x)
        for x in (current.temperature_c, current.apparent_temperature_c):
            if x is not None:
                nums.add(round(c_to_f(x), 1))
    if forecast is not None:
        for d in forecast.days:
            for x in (d.temperature_max_c, d.temperature_min_c, d.apparent_temperature_max_c,
                      d.relative_humidity_max_pct):
                if x is not None:
                    nums.add(x)
            for x in (d.temperature_max_c, d.temperature_min_c):
                if x is not None:
                    nums.add(round(c_to_f(x), 1))
    return nums


def _check_claims(
    summary: WeatherSummary, current: CurrentConditions | None, forecast: ForecastResult | None
) -> list[ConsistencyIssue]:
    max_fc = None
    if forecast is not None:
        vals = [d.temperature_max_c for d in forecast.days if d.temperature_max_c is not None]
        max_fc = max(vals) if vals else None
    pairs = [
        ("temperature_c", summary.claimed_temperature_c, current.temperature_c if current else None),
        ("apparent_temperature_c", summary.claimed_apparent_temperature_c,
         current.apparent_temperature_c if current else None),
        ("relative_humidity_pct", summary.claimed_humidity_pct, current.relative_humidity_pct if current else None),
        ("max_forecast_temperature_c", summary.claimed_max_forecast_temperature_c, max_fc),
    ]
    issues = []
    for field, claimed, actual in pairs:
        if claimed is None:
            continue
        if actual is None:
            issues.append(ConsistencyIssue(field=field, claimed=claimed, actual=None,
                                           message="Model stated a value that no tool returned."))
        elif abs(claimed - actual) > NUMERIC_TOLERANCE:
            issues.append(ConsistencyIssue(field=field, claimed=claimed, actual=actual,
                                           message="Model value differs from tool data. Tool value is used."))
    return issues


def deterministic_summary(
    current: CurrentConditions | None, forecast: ForecastResult | None, alerts: AlertsResult | None
) -> str:
    parts: list[str] = []
    if current is not None:
        loc = current.location.name
        bits = []
        if current.temperature_c is not None:
            bits.append(f"{current.temperature_c:g}°C")
        if current.apparent_temperature_c is not None:
            bits.append(f"feels like {current.apparent_temperature_c:g}°C")
        if current.relative_humidity_pct is not None:
            bits.append(f"humidity {current.relative_humidity_pct:g}%")
        parts.append(f"Current conditions in {loc}: {', '.join(bits) if bits else 'values unavailable'}.")
    if forecast is not None and forecast.days:
        highs = [d.temperature_max_c for d in forecast.days if d.temperature_max_c is not None]
        if highs:
            parts.append(f"Forecast highs over the next {len(forecast.days)} day(s) range "
                         f"{min(highs):g}-{max(highs):g}°C.")
    if alerts is not None and not alerts.alerts_supported:
        parts.append("No official warnings are available from this provider.")
    elif alerts is not None:
        parts.append(f"{len(alerts.alerts)} official alert(s) reported.")
    mode = next((x.provenance.data_mode for x in (current, forecast) if x is not None), None)
    if mode == "demo":
        parts.append("This is demonstration data, not real weather.")
    return " ".join(parts)


def _dedupe(items: list[str]) -> list[str]:
    seen: set[str] = set()
    out = []
    for i in items:
        if i not in seen:
            seen.add(i)
            out.append(i)
    return out
