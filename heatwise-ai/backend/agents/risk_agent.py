"""Community Risk Agent.

The risk category is always computed by deterministic rules (`classify`). The
Strands agent calls the risk tools and writes a short explanation (structured
output `RiskExplanation`). The explanation is kept only if it makes no claim
outside the evidence and names no other category; otherwise a deterministic
explanation is used.
"""

from __future__ import annotations

import logging
import re

from pydantic import ValidationError as PydanticValidationError
from strands import Agent, tool
from strands.models import Model

from backend.agents.hooks import EvidenceLedgerHook, GuardrailHook
from backend.agents.model_factory import build_bedrock_model
from backend.agents.weather_agent import weather_evidence_numbers
from backend.config import Settings
from backend.models.risk import CommunityProfile, RiskAssessment, RiskExplanation
from backend.models.trace import ToolCallRecord
from backend.models.weather import WeatherIntelligenceResult
from backend.services.claims import check_text_claims
from backend.services.risk_rules import (
    HI_CAUTION_F,
    HI_DANGER_F,
    HI_EXTREME_CAUTION_F,
    HI_EXTREME_DANGER_F,
    IMD_HEAT_WAVE_C,
    IMD_PLAINS_CONSIDER_C,
    IMD_SEVERE_HEAT_WAVE_C,
    classify,
)
from backend.tools.risk_tools import RISK_TOOL_NAMES, RiskContext, build_risk_tools
from backend.tools.weather_tools import tool_error

logger = logging.getLogger("heatwise.risk_agent")

AGENT_NAME = "community_risk"
STRUCTURED_TOOL = RiskExplanation.__name__
STRUCTURED_OUTPUT_ATTEMPTS = 2

SYSTEM_PROMPT = """You are the Community Risk Agent for HeatWise AI, a heatwave preparedness assistant.

Your job: explain the community heat-risk category computed by deterministic rules.

Rules:
- Call classify_heat_risk once. You may call get_risk_rules once to explain the thresholds.
- The category returned by classify_heat_risk is final. Never change, upgrade or downgrade it,
  and never name a different risk category.
- Only use numbers that appear in tool results. Do not describe sky, cloud or rain.
- The IMD indication is computed from forecast data for one point. It is not an official heat wave
  declaration or warning. The vulnerability adjustment is a project heuristic, not an official standard.
- Describe the community in general terms. Never make medical statements about any person.
- In RiskExplanation, write two or three plain sentences."""

_CATEGORY_WORDS = r"(very[ _]high|extreme|high|moderate|low)"
_CATEGORY_PATTERNS = (
    re.compile(rf"\b{_CATEGORY_WORDS}\s+(?:heat[- ]?)?risk\b", re.IGNORECASE),
    re.compile(rf"\brisk\s+(?:category\s+|level\s+)?(?:is|of|:|=)\s*(?:an?\s+)?{_CATEGORY_WORDS}\b", re.IGNORECASE),
)


def named_categories(text: str | None) -> set[str]:
    """Risk categories a text explicitly names, e.g. 'high risk' or 'risk is very high'."""
    found: set[str] = set()
    for pat in _CATEGORY_PATTERNS:
        for m in pat.finditer(text or ""):
            found.add(m.group(1).lower().replace(" ", "_"))
    return found


def evidence_numbers(weather: WeatherIntelligenceResult | None, risk: RiskAssessment) -> set[float]:
    """Numbers an explanation may state: tool data, rule outputs and published thresholds."""
    nums: set[float] = {IMD_PLAINS_CONSIDER_C, IMD_HEAT_WAVE_C, IMD_SEVERE_HEAT_WAVE_C,
                        HI_CAUTION_F, HI_EXTREME_CAUTION_F, HI_DANGER_F, HI_EXTREME_DANGER_F}
    for x in (risk.heat_index_c, risk.heat_index_f):
        if x is not None:
            nums.add(x)
    for f in risk.contributing_factors:
        if f.value is not None:
            nums.add(f.value)
    if weather is not None:
        # Same weather numbers the Weather Agent accepts in its summary (incl. forecast °F).
        nums |= weather_evidence_numbers(weather.current, weather.forecast)
    return nums


_IMD_TEXT = {
    "none": "no IMD heat-wave threshold is met",
    "threshold_met": "the IMD heat-wave consideration threshold is met",
    "heat_wave": "IMD heat-wave conditions are indicated",
    "severe_heat_wave": "IMD severe heat-wave conditions are indicated",
}


def deterministic_explanation(risk: RiskAssessment) -> str:
    if risk.category == "unknown":
        return ("Community heat risk could not be assessed because no current conditions or forecast "
                "temperatures were available.")
    parts = [f"Community heat risk is {risk.category.replace('_', ' ')} "
             f"(rules-based assessment, {risk.confidence} confidence)."]
    if risk.heat_index_c is not None and risk.heat_index_f is not None:
        band = f"in the NWS {risk.heat_index_band} band" if risk.heat_index_band else "below the NWS Caution band"
        parts.append(f"The current heat index is about {risk.heat_index_c:g}°C ({risk.heat_index_f:g}°F), {band}.")
    fc = next((f for f in risk.contributing_factors if f.code == "forecast_max_temperature"), None)
    if fc is not None and fc.value is not None:
        if risk.imd_indication is not None:
            parts.append(f"The highest forecast maximum is {fc.value:g}°C, so {_IMD_TEXT[risk.imd_indication]}; "
                         "this is an indication from forecast data, not an official declaration.")
        else:
            parts.append(f"The highest forecast maximum is {fc.value:g}°C; the IMD actual-maximum rule was not "
                         "applied for this terrain.")
    if risk.heuristic_adjustment_applied:
        parts.append("The category was raised one step by a project heuristic (not an official standard) because "
                     "several community vulnerability indicators are present.")
    return " ".join(parts)


class CommunityRiskAgent:
    def __init__(self, settings: Settings, model: Model | None = None) -> None:
        self.settings = settings
        self._model = model
        self._context: RiskContext | None = None
        self.tools = build_risk_tools(lambda: self._context)
        self.last_trace: list[ToolCallRecord] = []
        self.last_blocked: list[dict[str, str]] = []

    @property
    def model(self) -> Model:
        if self._model is None:
            self._model = build_bedrock_model(self.settings)
        return self._model

    def _build_agent(self) -> tuple[Agent, GuardrailHook, EvidenceLedgerHook]:
        guardrail = GuardrailHook(
            allowed_tools=RISK_TOOL_NAMES,
            max_tool_calls=self.settings.agent_max_tool_calls,
            uncounted_tools=[STRUCTURED_TOOL],
        )
        ledger = EvidenceLedgerHook(ignored_tools=[STRUCTURED_TOOL])
        agent = Agent(
            name=AGENT_NAME,
            description="Classifies community heat risk with deterministic rules and explains it.",
            model=self.model,
            tools=self.tools,
            system_prompt=SYSTEM_PROMPT,
            hooks=[guardrail, ledger],
            structured_output_model=RiskExplanation,
            callback_handler=None,
        )
        return agent, guardrail, ledger

    def run(self, weather: WeatherIntelligenceResult | None, profile: CommunityProfile | None = None) -> RiskAssessment:
        profile = profile or CommunityProfile()
        assessment = classify(weather, profile, self.settings.risk_vulnerability_min_indicators)
        self.last_trace, self.last_blocked = [], []
        if assessment.status == "insufficient_data":
            # Nothing to explain; do not spend a model call.
            return assessment.model_copy(update={"explanation": deterministic_explanation(assessment),
                                                 "explanation_source": "rules"})

        self._context = RiskContext(weather=weather, profile=profile,
                                    min_indicators=self.settings.risk_vulnerability_min_indicators)
        agent, guardrail, ledger = self._build_agent()
        issues: list[str] = []
        explanation: RiskExplanation | None = None
        try:
            result = agent(
                "Classify the community heat risk for this request with classify_heat_risk, then explain it.",
                limits={"turns": self.settings.agent_max_turns,
                        "structured_output_attempts": STRUCTURED_OUTPUT_ATTEMPTS},
            )
            if isinstance(result.structured_output, RiskExplanation):
                explanation = result.structured_output
            else:
                issues.append(f"Agent stopped without a structured explanation (stop_reason={result.stop_reason}).")
        except Exception as exc:  # model/service failures must not crash the workflow
            logger.exception("risk agent invocation failed")
            issues.append(f"Risk agent failed: {type(exc).__name__}")
        finally:
            self._context = None

        self.last_trace = list(ledger.records)
        self.last_blocked = list(guardrail.blocked)
        return finalize_assessment(assessment, weather, explanation, ledger.records, issues)

    def as_tool(self):
        """Agents-as-tools wrapper (workshop Module 6)."""
        specialist = self

        @tool
        def community_risk(weather_json: str, profile_json: str = "{}"):
            """Delegate to the Community Risk Agent. Classifies community heat risk with deterministic
            rules (NWS heat index bands, IMD actual-maximum indication, project vulnerability heuristic)
            and returns the assessment as JSON.

            Args:
                weather_json: WeatherIntelligenceResult JSON from the Weather Intelligence Agent.
                profile_json: CommunityProfile JSON (community-level indicators and terrain).
            """
            try:
                weather = WeatherIntelligenceResult.model_validate_json(weather_json)
                profile = CommunityProfile.model_validate_json(profile_json or "{}")
            except PydanticValidationError as exc:
                return tool_error("invalid_argument", f"Invalid input: {exc.error_count()} validation error(s).")
            return specialist.run(weather, profile).model_dump_json()

        return community_risk


def finalize_assessment(
    assessment: RiskAssessment,
    weather: WeatherIntelligenceResult | None,
    explanation: RiskExplanation | None,
    records: list[ToolCallRecord],
    issues: list[str] | None = None,
) -> RiskAssessment:
    """Attach an explanation. The category always stays the rules' category."""
    issues = list(issues or [])
    text = explanation.explanation.strip() if explanation is not None else ""
    if explanation is not None:
        if not any(r.tool == "classify_heat_risk" and r.status == "success" for r in records):
            issues.append("Model explained the risk without calling classify_heat_risk.")
        alerts_supported = bool(weather and weather.alerts and weather.alerts.alerts_supported)
        issues.extend(check_text_claims(text, evidence_numbers(weather, assessment), alerts_supported))
        others = named_categories(text) - {assessment.category}
        if others:
            issues.append(f"Model named a different risk category ({', '.join(sorted(others))}); "
                          f"the rules category is {assessment.category}.")
        if not text:
            issues.append("Model explanation was empty.")
    use_model = explanation is not None and not issues
    return assessment.model_copy(update={
        "explanation": text if use_model else deterministic_explanation(assessment),
        "explanation_source": "model" if use_model else "rules",
        "explanation_issues": issues,
    })
