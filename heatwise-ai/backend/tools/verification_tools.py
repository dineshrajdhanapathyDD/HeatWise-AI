"""Deterministic safety checks and the Safety Agent's tool.

`run_checks(weather, risk, plan)` decides pass/fail. No model output is consulted.
"""

from __future__ import annotations

import re
from dataclasses import dataclass
from typing import Callable

from strands import tool

from backend.agents.risk_agent import evidence_numbers
from backend.guidance.catalog import AUDIENCES
from backend.guidance.sources import TRUSTED_SOURCES
from backend.models.plan import PreparednessPlan
from backend.models.risk import RiskAssessment
from backend.models.verification import CheckResult, VerificationResult
from backend.models.weather import WeatherIntelligenceResult
from backend.services.claims import PHONE_NUMBER_RE, check_text_claims
from backend.tools.weather_tools import tool_error

VERIFICATION_TOOL_NAMES = ("run_safety_checks",)

_I = re.IGNORECASE
_ILLNESS = r"(?:heat\s*stroke|heatstroke|heat\s+exhaustion|dehydration|hyperthermia|sunstroke|heat\s+illness)"
_HELP = r"(?:a\s+|an\s+|the\s+)?(?:doctor|hospital|clinic|emergency|ambulance|health\s+(?:facility|centre|center|worker|provider)|medical\s+help)"

# (code, pattern, message). Matched against every user-facing text in the plan and report.
BANNED_PATTERNS: tuple[tuple[str, re.Pattern[str], str], ...] = (
    ("medication", re.compile(r"\b(?:aspirin|paracetamol|acetaminophen|ibuprofen|painkillers?|antipyretics?|"
                              r"salt\s+tablets?|electrolyte\s+tablets?)\b", _I),
     "names a medicine"),
    ("medication", re.compile(r"\b(?:take|give|use|swallow)\s+(?:\w+\s+){0,3}?(?:medicines?|medications?|pills?|"
                              r"tablets?|drugs?)\b", _I),
     "tells people to take medication"),
    ("dosing", re.compile(r"\b\d+(?:\.\d+)?\s*(?:mg|milligrams?|ml)\b|\bdos(?:e|es|age|ing)\b", _I),
     "gives a dose"),
    ("diagnosis", re.compile(rf"\b(?:you|he|she|they|this person|your (?:child|mother|father|neighbou?r))\s+"
                             rf"(?:have|has|are suffering from|is suffering from|(?:have|has)\s+got)\s+"
                             rf"(?:a\s+|an\s+)?{_ILLNESS}\b", _I),
     "diagnoses a person"),
    ("diagnosis", re.compile(rf"\b(?:this|it)\s+is\s+(?:definitely\s+|probably\s+)?{_ILLNESS}\b", _I),
     "diagnoses a person"),
    ("diagnosis", re.compile(rf"\b(?:is|are|am|was|were)\s+(?:\w+\s+){{0,2}}?(?:suffering|experiencing|having)\s+"
                             rf"(?:from\s+)?(?:a\s+|an\s+)?{_ILLNESS}\b", _I),
     "diagnoses a person"),
    ("diagnosis", re.compile(rf"\b(?:people|persons?|workers?|farmers?|residents?|children|child|elderly|adults?|"
                             rf"someone|everyone|many|they|we)\s+(?:\w+\s+){{0,4}}?(?:has|have|had|got|"
                             rf"(?:has|have)\s+(?:got|developed)|developed)\s+(?:a\s+|an\s+)?{_ILLNESS}\b", _I),
     "diagnoses a person"),
    ("phone_number", PHONE_NUMBER_RE, "gives a phone or emergency number, and none was verified"),
    ("discourage_help", re.compile(rf"\b(?:no\s+need|don't\s+need|do\s+not\s+need|unnecessary)\s+to\s+"
                                   rf"(?:see|call|visit|contact|go\s+to)\b", _I),
     "discourages seeking medical help"),
    ("discourage_help", re.compile(rf"\b(?:don't|do\s+not|never|avoid)\s+(?:call(?:ing)?|contact(?:ing)?|"
                                   rf"visit(?:ing)?|go(?:ing)?\s+to|seek(?:ing)?)\s+{_HELP}", _I),
     "discourages seeking medical help or emergency services"),
    ("discourage_help", re.compile(rf"\b(?:instead\s+of|rather\s+than)\s+(?:calling|seeing|visiting|going\s+to|"
                                   rf"contacting)\s+{_HELP}", _I),
     "discourages seeking medical help or emergency services"),
    ("alcohol", re.compile(r"\b(?:drink|have|try|take)\s+(?:\w+\s+){0,2}?(?:alcohol|beer|wine|liquor|toddy)\b", _I),
     "recommends alcohol"),
    ("limit_water", re.compile(r"\b(?:limit|reduce|restrict|avoid|cut\s+down\s+on|skip|stop)\s+(?:your\s+|drinking\s+)?"
                               r"(?:water|fluids?|fluid\s+intake|water\s+intake)\b", _I),
     "tells people to limit water"),
    ("limit_water", re.compile(r"\bdrink\s+less\b", _I), "tells people to limit water"),
    ("external_action", re.compile(r"\b(?:we|heatwise(?:\s+ai)?|this\s+(?:app|system|service|assistant))\s+"
                                   r"(?:will|has|have|can|did)\s+(?:also\s+)?(?:send|sent|alert|alerted|notify|"
                                   r"notified|contact|contacted|call|called|inform|informed)\b", _I),
     "claims HeatWise sends alerts or contacts people"),
    ("external_action", re.compile(r"\b(?:alerts?|sms|messages?|notifications?)\s+(?:has|have)\s+been\s+sent\b", _I),
     "claims alerts were sent"),
    ("external_action", re.compile(r"\b(?:authorities|emergency\s+services|officials|police|hospitals?)\s+"
                                   r"(?:have|has)\s+been\s+(?:notified|alerted|contacted|informed)\b", _I),
     "claims someone was contacted"),
)


def banned_hits(text: str | None) -> list[str]:
    return [f"{code}: {msg}" for code, pat, msg in BANNED_PATTERNS if pat.search(text or "")]


def _texts(weather: WeatherIntelligenceResult | None, risk: RiskAssessment | None,
           plan: PreparednessPlan | None) -> list[tuple[str, str | None, str]]:
    """(label, item_id, text) for every user-facing text."""
    out: list[tuple[str, str | None, str]] = []
    if weather is not None and weather.summary:
        out.append(("weather summary", None, weather.summary))
    if risk is not None and risk.explanation:
        out.append(("risk explanation", None, risk.explanation))
    if plan is not None:
        if plan.intro:
            out.append(("plan intro", None, plan.intro))
        out += [(f"plan item {i.id}", i.id, i.text) for i in plan.items]
    return out


def run_checks(weather: WeatherIntelligenceResult | None, risk: RiskAssessment | None,
               plan: PreparednessPlan | None) -> VerificationResult:
    checks: list[CheckResult] = []

    def add(name: str, passed: bool, message: str, severity: str = "error", item_id: str | None = None) -> None:
        checks.append(CheckResult(name=name, passed=passed, severity=severity, message=message,  # type: ignore[arg-type]
                                  item_id=item_id))

    # Weather freshness and sources.
    if weather is None or weather.status in ("no_data", "error"):
        add("weather_data", False, "No usable weather data was retrieved.")
    else:
        add("weather_data", True, f"Weather status is {weather.status}.")
        add("weather_freshness", not weather.is_stale,
            "Weather data is stale." if weather.is_stale else "Weather data is fresh.")
        demo = weather.data_mode == "demo"
        add("weather_live", not demo, "Weather data is demo data, not live observations." if demo
            else "Weather data is live.", severity="warning")
        add("weather_sources", bool(weather.sources),
            "Weather sources are listed." if weather.sources else "Weather result lists no source.")

    # Risk and plan consistency.
    if risk is None:
        add("risk_present", False, "No risk assessment is available.")
    if plan is None or plan.status != "ok":
        add("plan_present", False, "No preparedness plan was built.")
    elif not plan.items:
        add("plan_present", False, "The preparedness plan has no items.")
    else:
        add("plan_present", True, f"The plan has {len(plan.items)} items.")
    if risk is not None and plan is not None:
        same = plan.risk_category == risk.category
        add("risk_category_match", same,
            f"Plan risk category ({plan.risk_category}) matches the assessment." if same else
            f"Plan risk category ({plan.risk_category}) differs from the assessment ({risk.category}).")

    item_failed: set[str] = set()
    if plan is not None:
        for item in plan.items:
            if item.kind == "sourced":
                unknown = [s for s in item.source_ids if s not in TRUSTED_SOURCES]
                if not item.source_ids:
                    add("item_sources", False, f"Item {item.id} has no source.", item_id=item.id)
                    item_failed.add(item.id)
                elif unknown:
                    add("item_sources", False, f"Item {item.id} cites unknown source(s): {', '.join(unknown)}.",
                        item_id=item.id)
                    item_failed.add(item.id)
            elif item.source_ids:
                bad = [s for s in item.source_ids if s not in TRUSTED_SOURCES]
                if bad:
                    add("item_sources", False, f"Item {item.id} cites unknown source(s): {', '.join(bad)}.",
                        item_id=item.id)
                    item_failed.add(item.id)
        audiences = [a for a in AUDIENCES if any(i.audience == a for i in plan.items)]
        for aud in audiences:
            ok = any(i.audience == aud and i.topic == "escalation" for i in plan.items)
            add("escalation_present", ok, f"Escalation guidance is present for {aud}." if ok else
                f"No escalation guidance for {aud}.")

    # Banned content in every text.
    for label, item_id, text in _texts(weather, risk, plan):
        for hit in banned_hits(text):
            add("banned_content", False, f"The {label} {hit.split(': ', 1)[1]}.", item_id=item_id)
            if item_id:
                item_failed.add(item_id)

    # Free-text claims (model-writable texts) against the evidence numbers.
    if risk is not None:
        allowed = evidence_numbers(weather, risk)
        alerts_supported = bool(weather and weather.alerts and weather.alerts.alerts_supported)
        free: list[tuple[str, str | None, str]] = []
        if weather is not None and weather.summary:
            free.append(("weather summary", None, weather.summary))
        if risk.explanation:
            free.append(("risk explanation", None, risk.explanation))
        if plan is not None:
            if plan.intro:
                free.append(("plan intro", None, plan.intro))
            free += [(f"plan item {i.id}", i.id, i.text) for i in plan.items if i.kind == "general_educational"]
        for label, item_id, text in free:
            for problem in check_text_claims(text, allowed, alerts_supported):
                add("text_claims", False, f"The {label}: {problem}", item_id=item_id)
                if item_id:
                    item_failed.add(item_id)

    issues = [c.message for c in checks if not c.passed and c.severity == "error"]
    warnings = [c.message for c in checks if not c.passed and c.severity == "warning"]
    verified = [i.id for i in plan.items if i.id not in item_failed] if plan is not None else []
    total = len(plan.items) if plan is not None else 0
    return VerificationResult(
        status="failed" if issues else "passed",
        checks=checks,
        issues=issues,
        warnings=warnings,
        verified_item_ids=verified,
        pct_items_verified=round(100.0 * len(verified) / total, 1) if total else 0.0,
    )


@dataclass
class VerificationContext:
    weather: WeatherIntelligenceResult | None
    risk: RiskAssessment | None
    plan: PreparednessPlan | None


def build_verification_tools(get_context: Callable[[], VerificationContext | None]) -> list:
    @tool
    def run_safety_checks():
        """Run the deterministic safety checks on the current plan: weather freshness and sources,
        item sources, banned content (medication, diagnosis, discouraging help, alcohol, limiting water,
        claims of sending alerts, phone or emergency numbers), escalation guidance per audience, risk category consistency and
        unsupported numbers or claims in free text. Returns the pass/fail result, which is final."""
        ctx = get_context()
        if ctx is None:
            return tool_error("invalid_argument", "No plan is bound to this request.")
        return run_checks(ctx.weather, ctx.risk, ctx.plan)

    return [run_safety_checks]
