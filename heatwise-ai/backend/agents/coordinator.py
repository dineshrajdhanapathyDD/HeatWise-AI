"""HeatWise Coordinator Agent (agents-as-tools, workshop Module 6).

The coordinator's tools are thin closures over a `CoordinatorRun` state object. Each
one calls a specialist agent's `.run(...)` with data held in code and returns a compact
JSON summary to the model, so the model never copies large JSON between agents (D1).

Ordering weather -> risk -> plan -> safety, the single revision and finalisation are
enforced by `OrderingSteeringHandler` (Strands steering plugin) and a
`SequentialToolExecutor` (D2). After the model returns or fails, `_complete_pipeline`
runs any step it skipped under the same rules, so a report is never finalised without
safety verification (D3). The report itself is built in code by `build_report`.
"""

from __future__ import annotations

import json
import logging
import time
import uuid
from dataclasses import dataclass, field
from datetime import datetime, timezone
from typing import Any

from strands import Agent, tool
from strands.models import Model
from strands.tools.executors import SequentialToolExecutor
from strands.vended_plugins.steering import Guide, Proceed, SteeringHandler

from backend.agents.hooks import EvidenceLedgerHook, GuardrailHook
from backend.agents.model_factory import build_bedrock_model
from backend.agents.planner_agent import ActionPlannerAgent
from backend.agents.risk_agent import CommunityRiskAgent
from backend.agents.safety_agent import SafetyVerificationAgent
from backend.agents.weather_agent import WeatherIntelligenceAgent
from backend.config import Settings
from backend.models.plan import PreparednessPlan
from backend.models.report import AgentTraceEntry, PreparednessReport, WeatherSourceInfo, evidence_from
from backend.models.risk import CommunityProfile, RiskAssessment
from backend.models.trace import ToolCallRecord
from backend.models.verification import VerificationResult
from backend.models.weather import WeatherIntelligenceResult
from backend.session.sessions import build_session_manager

logger = logging.getLogger("heatwise.coordinator")

AGENT_NAME = "coordinator"
FALLBACK_AGENT = "coordinator_fallback"
WEATHER, RISK, PLAN, SAFETY, FINALIZE = (
    "weather_intelligence", "community_risk", "action_planner", "safety_verifier", "finalize_report")
COORDINATOR_TOOL_NAMES = (WEATHER, RISK, PLAN, SAFETY, FINALIZE)
MAX_REVISIONS = 1

NOTICES = (
    "HeatWise AI does not send alerts or contact anyone. Share this plan yourself if it is useful.",
    "Forecast values are not official warnings. Follow your local meteorological and disaster management "
    "authorities for official warnings.",
    "This is general preparedness guidance, not medical advice.",
)

SYSTEM_PROMPT = """You are the HeatWise AI Coordinator, a heatwave preparedness assistant for communities.

You build a preparedness report by delegating to specialist agents through your tools.
The data moves between the specialists in code; you only see short summaries.

Call the tools in this order, one at a time:
1. weather_intelligence - weather data for the requested place.
2. community_risk - the rules-based community heat risk.
3. action_planner - the preparedness plan.
4. safety_verifier - deterministic safety checks on the plan.
5. If safety_verifier fails and no revision was made yet, call action_planner once more, then safety_verifier again.
6. finalize_report - ends the run.

Rules:
- If weather_intelligence returns no usable data, call finalize_report straight away.
- If a tool call is cancelled with guidance, follow the guidance.
- Never invent weather values, risk categories or advice. Never claim to send alerts or contact anyone.
- After finalize_report, reply with one short sentence and stop."""


@dataclass
class Step:
    tool: str
    origin: str  # "model" or "fallback"
    records: list[ToolCallRecord]
    status: str = "success"
    duration_ms: float | None = None


@dataclass
class CoordinatorRun:
    location: str
    days: int
    profile: CommunityProfile
    weather: WeatherIntelligenceResult | None = None
    risk: RiskAssessment | None = None
    plans: list[PreparednessPlan] = field(default_factory=list)
    verifications: list[VerificationResult] = field(default_factory=list)
    finalized: bool = False
    steps: list[Step] = field(default_factory=list)
    fallback_steps: list[str] = field(default_factory=list)
    steering_blocks: list[dict[str, str]] = field(default_factory=list)
    notes: list[str] = field(default_factory=list)

    # -- state predicates used by steering, fallback and the report -------------------
    def weather_usable(self) -> bool:
        return self.weather is not None and self.weather.status in ("ok", "partial")

    def risk_usable(self) -> bool:
        return self.risk is not None and self.risk.category != "unknown"

    def plan_pending_verification(self) -> bool:
        return len(self.plans) > len(self.verifications)

    def last_verification_failed(self) -> bool:
        return bool(self.verifications) and self.verifications[-1].status == "failed"

    def revision_allowed(self) -> bool:
        return (len(self.plans) <= MAX_REVISIONS and not self.plan_pending_verification()
                and self.last_verification_failed())

    def can_finalize(self) -> bool:
        if self.weather is not None and not self.weather_usable():
            return True
        if self.risk is not None and not self.risk_usable():
            return True
        if not self.verifications or self.plan_pending_verification():
            return False
        return not self.revision_allowed()


class OrderingSteeringHandler(SteeringHandler):
    """Deterministic steering: weather -> risk -> plan -> safety, one revision, finalize last."""

    name = "heatwise-ordering"

    def __init__(self, get_state) -> None:
        super().__init__()
        self._get_state = get_state

    def decide(self, tool_name: str) -> str | None:
        """Return a guidance reason if the call must be cancelled, else None."""
        s: CoordinatorRun | None = self._get_state()
        if s is None or tool_name not in COORDINATOR_TOOL_NAMES:
            return None  # unknown tools are handled by the guardrail allowlist
        if s.finalized:
            return "The report is already finalized. Do not call more tools; reply with one short sentence."
        if tool_name == WEATHER:
            if s.weather is not None:
                return "Weather data was already retrieved. Do not call weather_intelligence again; " \
                       + _next_hint(s)
            return None
        if s.weather is None:
            return "Call weather_intelligence first; every other step needs the weather data."
        if tool_name == FINALIZE and s.can_finalize():
            return None  # includes the early exits (no usable weather, unknown risk)
        if tool_name != FINALIZE and not s.weather_usable():
            return "No usable weather data was retrieved, so the assessment cannot continue. Call finalize_report."
        if tool_name == RISK:
            if s.risk is not None:
                return "The risk was already assessed. Do not call community_risk again; " + _next_hint(s)
            return None
        if s.risk is None:
            return "Call community_risk next; the plan needs the risk assessment."
        if tool_name != FINALIZE and not s.risk_usable():
            return "The risk category is unknown, so no plan can be built. Call finalize_report."
        if tool_name == PLAN:
            if not s.plans:
                return None
            if s.revision_allowed():
                return None
            if s.plan_pending_verification():
                return "A plan is waiting for verification. Call safety_verifier next."
            if s.verifications and s.verifications[-1].status == "passed":
                return "The plan passed verification. Call finalize_report."
            return "Only one plan revision is allowed. Call finalize_report."
        if tool_name == SAFETY:
            if not s.plans:
                return "Call action_planner first; there is no plan to verify yet."
            if not s.plan_pending_verification():
                return "The latest plan was already verified. " + _next_hint(s)
            return None
        # FINALIZE
        if s.can_finalize():
            return None
        return "The report cannot be finalized yet. " + _next_hint(s)

    async def steer_before_tool(self, *, agent: Any, tool_use: Any, **kwargs: Any):
        name = tool_use.get("name", "")
        reason = self.decide(name)
        if reason is None:
            return Proceed(reason="Order respected")
        state = self._get_state()
        if state is not None:
            state.steering_blocks.append({"tool": name, "reason": reason})
        logger.info("steering blocked tool=%s reason=%s", name, reason)
        return Guide(reason=reason)


def _next_hint(s: CoordinatorRun) -> str:
    if s.weather is None:
        return "Call weather_intelligence."
    if not s.weather_usable():
        return "Call finalize_report."
    if s.risk is None:
        return "Call community_risk."
    if not s.risk_usable():
        return "Call finalize_report."
    if not s.plans:
        return "Call action_planner."
    if s.plan_pending_verification():
        return "Call safety_verifier."
    if s.revision_allowed():
        return "The plan failed verification; call action_planner once to revise it."
    return "Call finalize_report."


def _compact(obj: dict[str, Any]) -> str:
    return json.dumps(obj, ensure_ascii=False, separators=(",", ":"))


class HeatWiseCoordinator:
    def __init__(
        self,
        settings: Settings,
        weather_agent: WeatherIntelligenceAgent | None = None,
        risk_agent: CommunityRiskAgent | None = None,
        planner_agent: ActionPlannerAgent | None = None,
        safety_agent: SafetyVerificationAgent | None = None,
        model: Model | None = None,
    ) -> None:
        self.settings = settings
        self._model = model
        # Specialists share the coordinator's Bedrock model unless given their own.
        self.weather_agent = weather_agent or WeatherIntelligenceAgent(settings, model=model)
        self.risk_agent = risk_agent or CommunityRiskAgent(settings, model=model)
        self.planner_agent = planner_agent or ActionPlannerAgent(settings, model=model)
        self.safety_agent = safety_agent or SafetyVerificationAgent(settings, model=model)
        self._state: CoordinatorRun | None = None
        self.tools = self._build_tools()
        self.last_state: CoordinatorRun | None = None
        self.last_trace: list[ToolCallRecord] = []
        self.last_blocked: list[dict[str, str]] = []

    @property
    def model(self) -> Model:
        if self._model is None:
            self._model = build_bedrock_model(self.settings)
        return self._model

    # -- specialist steps (shared by tools and the deterministic fallback) ---------------
    def _timed(self, state: CoordinatorRun, tool_name: str, origin: str, fn, records_of) -> None:
        start = time.perf_counter()
        fn()
        state.steps.append(Step(tool=tool_name, origin=origin, records=list(records_of()),
                                duration_ms=round((time.perf_counter() - start) * 1000, 1)))

    def _do_weather(self, s: CoordinatorRun, origin: str) -> None:
        def go():
            s.weather = self.weather_agent.run(s.location, s.days)
        self._timed(s, WEATHER, origin, go, lambda: self.weather_agent.last_trace)

    def _do_risk(self, s: CoordinatorRun, origin: str) -> None:
        def go():
            s.risk = self.risk_agent.run(s.weather, s.profile)
        self._timed(s, RISK, origin, go, lambda: self.risk_agent.last_trace)

    def _do_plan(self, s: CoordinatorRun, origin: str) -> None:
        revision = len(s.plans)
        notes = list(s.verifications[-1].issues) if revision and s.verifications else None

        def go():
            s.plans.append(self.planner_agent.run(s.risk, s.profile, s.weather,  # type: ignore[arg-type]
                                                  revision_notes=notes, revision=revision))
        self._timed(s, PLAN, origin, go, lambda: self.planner_agent.last_trace)

    def _do_safety(self, s: CoordinatorRun, origin: str) -> None:
        def go():
            s.verifications.append(self.safety_agent.run(s.weather, s.risk, s.plans[-1]))
        self._timed(s, SAFETY, origin, go, lambda: self.safety_agent.last_trace)

    def _build_tools(self) -> list:
        coord = self

        def state() -> CoordinatorRun:
            if coord._state is None:
                raise RuntimeError("No coordinator run is active.")
            return coord._state

        @tool
        def weather_intelligence(location: str = "", forecast_days: int = 3) -> str:
            """Delegate to the Weather Intelligence Agent for the requested place. Returns a short summary.
            The requested location and forecast days are already bound to this run.

            Args:
                location: Optional; the run's requested location is always used.
                forecast_days: Optional; the run's requested forecast days are always used.
            """
            s = state()
            coord._do_weather(s, "model")
            w = s.weather
            return _compact({
                "status": w.status, "location": w.location.name if w.location else None,
                "data_mode": w.data_mode, "is_stale": w.is_stale,
                "errors": sorted({e.error_code for e in w.errors}),
                "next": "community_risk" if s.weather_usable() else "finalize_report",
            })

        @tool
        def community_risk() -> str:
            """Delegate to the Community Risk Agent. Classifies community heat risk with deterministic
            rules from the retrieved weather and the community profile. Returns a short summary."""
            s = state()
            coord._do_risk(s, "model")
            r = s.risk
            return _compact({"status": r.status, "category": r.category, "confidence": r.confidence,
                             "next": "action_planner" if s.risk_usable() else "finalize_report"})

        @tool
        def action_planner(revision_notes: str = "") -> str:
            """Delegate to the Preparedness Action Planner Agent. Builds the plan from verified guidance.
            On a revision, the Safety Agent's issues are passed to the planner automatically.

            Args:
                revision_notes: Optional; the latest safety issues are always used.
            """
            s = state()
            coord._do_plan(s, "model")
            p = s.plans[-1]
            return _compact({"status": p.status, "revision": p.revision, "items": len(p.items),
                             "language": p.language, "next": "safety_verifier"})

        @tool
        def safety_verifier() -> str:
            """Delegate to the Safety and Verification Agent. Runs deterministic safety checks on the
            latest plan. Returns pass/fail and the issues found."""
            s = state()
            coord._do_safety(s, "model")
            v = s.verifications[-1]
            return _compact({"status": v.status, "issues": v.issues[:5], "revision_allowed": s.revision_allowed(),
                             "next": _next_hint(s)})

        @tool
        def finalize_report() -> str:
            """Finalize the preparedness report. Call this last."""
            s = state()
            s.finalized = True
            return _compact({"finalized": True, "status": preview_status(s)})

        return [weather_intelligence, community_risk, action_planner, safety_verifier, finalize_report]

    def _build_agent(self, session_id: str | None = None) -> tuple[Agent, GuardrailHook, EvidenceLedgerHook]:
        guardrail = GuardrailHook(allowed_tools=COORDINATOR_TOOL_NAMES,
                                  max_tool_calls=self.settings.coordinator_max_tool_calls)
        ledger = EvidenceLedgerHook()
        agent = Agent(
            name=AGENT_NAME,
            agent_id=AGENT_NAME,
            session_manager=build_session_manager(self.settings, session_id) if session_id else None,
            description="Coordinates the HeatWise specialists into a verified preparedness report.",
            model=self.model,
            tools=self.tools,
            system_prompt=SYSTEM_PROMPT,
            hooks=[guardrail, ledger],
            plugins=[OrderingSteeringHandler(lambda: self._state)],
            tool_executor=SequentialToolExecutor(),
            callback_handler=None,
        )
        return agent, guardrail, ledger

    def run(self, location: str, profile: CommunityProfile | None = None, forecast_days: int = 3,
            session_id: str | None = None) -> PreparednessReport:
        s = CoordinatorRun(location=location, days=forecast_days, profile=profile or CommunityProfile())
        self._state = s
        records: list[ToolCallRecord] = []
        blocked: list[dict[str, str]] = []
        try:
            agent, guardrail, ledger = self._build_agent(session_id)
            try:
                agent(_prompt(s), limits={"turns": self.settings.coordinator_max_turns})
            finally:
                records = list(ledger.records)
                blocked = list(guardrail.blocked)
        except Exception as exc:  # model/service failures must not crash the workflow
            logger.exception("coordinator invocation failed")
            s.notes.append(f"Coordinator agent failed ({type(exc).__name__}); remaining steps ran deterministically.")
        self._complete_pipeline(s)
        self._state = None
        self.last_state, self.last_trace, self.last_blocked = s, records, blocked
        return build_report(s, records, blocked)

    def _complete_pipeline(self, s: CoordinatorRun) -> None:
        """Run any step the model skipped, under the same rules as the steering handler (D3)."""
        def fallback(name: str, fn) -> None:
            s.fallback_steps.append(name)
            fn(s, "fallback")

        if s.weather is None:
            fallback(WEATHER, self._do_weather)
        if not s.weather_usable():
            return
        if s.risk is None:
            fallback(RISK, self._do_risk)
        if not s.risk_usable():
            return
        if not s.plans:
            fallback(PLAN, self._do_plan)
        if s.plan_pending_verification():
            fallback(SAFETY, self._do_safety)
        if s.revision_allowed():
            fallback(PLAN, self._do_plan)
            fallback(SAFETY, self._do_safety)
        if s.fallback_steps:
            s.notes.append("The coordinator model skipped step(s) " + ", ".join(s.fallback_steps)
                           + "; they were run deterministically.")


def _prompt(s: CoordinatorRun) -> str:
    groups = ", ".join(i.replace("_", " ") for i in s.profile.indicators()) or "none specified"
    return (f"Location: {s.location}\nForecast days: {s.days}\n"
            f"Community groups present: {groups}\nTerrain: {s.profile.terrain or 'unknown'}\n"
            "Build the heat preparedness report by calling your tools in order.")


def preview_status(s: CoordinatorRun) -> str:
    if not s.weather_usable() or not s.risk_usable():
        return "incomplete"
    if not s.verifications:
        return "incomplete"
    return "complete" if s.verifications[-1].status == "passed" else "needs_human_review"


def build_trace(s: CoordinatorRun, records: list[ToolCallRecord]) -> list[AgentTraceEntry]:
    """Coordinator ledger in call order, each delegation followed by its specialist's tool calls."""
    out: list[AgentTraceEntry] = []
    model_steps = [st for st in s.steps if st.origin == "model"]
    step_index = 0

    def add_specialist(step: Step, index: int) -> None:
        for r in step.records:
            out.append(AgentTraceEntry(agent=r.agent, tool=r.tool, status=r.status, duration_ms=r.duration_ms,
                                       cancel_reason=r.cancel_reason, input_summary=r.input_summary,
                                       step_index=index))

    for r in records:
        step_index += 1
        out.append(AgentTraceEntry(agent=r.agent, tool=r.tool, status=r.status, duration_ms=r.duration_ms,
                                   cancel_reason=r.cancel_reason, input_summary=r.input_summary,
                                   step_index=step_index))
        if r.status == "success":
            match = next((st for st in model_steps if st.tool == r.tool), None)
            if match is not None:
                model_steps.remove(match)
                add_specialist(match, step_index)
    for st in s.steps:
        if st.origin != "fallback":
            continue
        step_index += 1
        out.append(AgentTraceEntry(agent=FALLBACK_AGENT, tool=st.tool, status="success",
                                   duration_ms=st.duration_ms, step_index=step_index))
        add_specialist(st, step_index)
    return out


def build_report(s: CoordinatorRun, records: list[ToolCallRecord],
                 blocked: list[dict[str, str]] | None = None) -> PreparednessReport:
    w, risk = s.weather, s.risk
    plan = s.plans[-1] if s.plans else None
    verification = s.verifications[-1] if s.verifications else None

    missing: list[str] = []
    if w is not None:
        missing += [f"Weather provider error ({e.error_code}): {e.message}" for e in w.errors]
        missing += w.missing_information
    else:
        missing.append("No weather data was retrieved.")
    if risk is not None:
        missing += risk.missing_data
    elif w is not None and not s.weather_usable():
        missing.append("Community risk was not assessed because no usable weather data was retrieved.")
    if risk is not None and not s.risk_usable():
        missing.append("No preparedness plan was built because the risk category is unknown.")
    missing += s.notes

    consistency: list[str] = []
    if w is not None:
        consistency += [f"Weather summary: {i.message} ({i.field})" for i in w.consistency_issues]
    if risk is not None:
        consistency += [f"Risk explanation: {i}" for i in risk.explanation_issues]
    for p in s.plans:
        consistency += [f"Plan revision {p.revision}: {i}" for i in p.issues]
    consistency += [f"Coordinator guardrail blocked {b['tool']}: {b['reason']}" for b in (blocked or [])]

    status = preview_status(s)
    notices = list(NOTICES)
    if plan is not None and plan.language_notice:
        notices.append(plan.language_notice)
    if w is not None and w.data_mode == "demo":
        notices.append("This report uses demonstration weather data, not real observations.")
    review_notice = None
    if status == "needs_human_review":
        review_notice = ("The plan did not pass automated safety verification after one revision. "
                         "A person should review it before it is shared.")
        notices.append(review_notice)

    provenances = [x.provenance for x in ((w.current, w.forecast, w.alerts) if w else ()) if x is not None]
    actions = plan if plan is not None and plan.status == "ok" else None
    return PreparednessReport(
        report_id=uuid.uuid4().hex,
        created_at=datetime.now(timezone.utc),
        status=status,  # type: ignore[arg-type]
        query=s.location,
        location=w.location if w else None,
        data_retrieved_at=w.retrieved_at if w else None,
        weather_source=WeatherSourceInfo(provider=provenances[0].provider if provenances else None,
                                         source_urls=list(w.sources) if w else [],
                                         data_mode=w.data_mode if w else None),
        weather_summary=w.summary if w else None,
        risk_category=risk.category if risk else "unknown",
        risk=risk,
        evidence=evidence_from(w, risk),
        recommended_actions=actions,
        checklist_markdown=checklist_for(actions, status, verification, review_notice),
        missing_information=_dedupe(missing),
        verification_status=verification.status if verification else "not_run",
        verification=verification,
        revision_count=max(len(s.plans) - 1, 0),
        consistency_issues=consistency,
        steering_blocks=list(s.steering_blocks),
        trace=build_trace(s, records),
        notices=notices,
        current_conditions=w.current if w else None,
        forecast=w.forecast if w else None,
        alerts=w.alerts if w else None,
    )


def checklist_for(actions: PreparednessPlan | None, status: str, verification: VerificationResult | None,
                  review_notice: str | None) -> str | None:
    """Exported checklist. A plan that failed verification lists only its verified items under a
    review banner; rejected items stay in the report JSON for the human reviewer only."""
    if actions is None:
        return None
    if status == "complete":
        return actions.checklist_markdown()
    verified = verification.verified_item_ids if verification is not None else []
    return actions.checklist_markdown(verified, [review_notice] if review_notice else None)


def _dedupe(items: list[str]) -> list[str]:
    return list(dict.fromkeys(items))
