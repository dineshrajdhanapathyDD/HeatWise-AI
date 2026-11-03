"""Preparedness Action Planner Agent.

The model reads per-audience SKILL.md instructions (AgentSkills plugin), lists and
selects verified catalog items by id, may add a few short general notes, and writes a
short intro (structured output `PlanIntro`). The plan itself is assembled in code from
the evidence ledger, then completed by a deterministic fill so every audience x phase
has at least one item and every audience covers hydration, rest, shade and escalation.
"""

from __future__ import annotations

import logging
from pathlib import Path

from pydantic import ValidationError as PydanticValidationError
from strands import Agent, AgentSkills, tool
from strands.models import Model

from backend.agents.hooks import EvidenceLedgerHook, GuardrailHook
from backend.agents.model_factory import build_bedrock_model
from backend.agents.risk_agent import evidence_numbers, named_categories
from backend.config import Settings
from backend.guidance.catalog import CATALOG, PHASES, REQUIRED_TOPICS, catalog_for
from backend.models.plan import ChecklistItem, PlanIntro, PlanItem, PreparednessPlan
from backend.models.risk import CommunityProfile, RiskAssessment
from backend.models.trace import ToolCallRecord
from backend.models.weather import WeatherIntelligenceResult
from backend.services.claims import check_text_claims
from backend.tools.planning_tools import PLANNING_TOOL_NAMES, PlanningContext, build_planning_tools
from backend.tools.weather_tools import tool_error

logger = logging.getLogger("heatwise.planner_agent")

AGENT_NAME = "action_planner"
STRUCTURED_TOOL = PlanIntro.__name__
SKILLS_TOOL = "skills"
STRUCTURED_OUTPUT_ATTEMPTS = 2
SKILLS_DIR = Path(__file__).resolve().parent.parent / "skills"
SUPPORTED_PLAN_LANGUAGES = ("en",)
INTRO_MAX_CHARS = 600

AUDIENCE_SKILLS = {
    "household": "household-heat-preparedness",
    "outdoor_worker": "outdoor-worker-heat-safety",
    "farmer": "farmer-heat-preparedness",
}
_AUDIENCE_WORDS = {"household": "households", "outdoor_worker": "outdoor workers", "farmer": "farmers"}

SYSTEM_PROMPT = """You are the Preparedness Action Planner Agent for HeatWise AI, a heatwave preparedness assistant.

Your job: build a community heat preparedness plan from the verified guidance catalog.

Rules:
- For each audience in the request, load its skill with the skills tool and follow it.
- Call list_guidance(audience, phase="all") exactly once per audience; it returns every phase.
  Do not call list_guidance per phase. Then call select_guidance once per phase with
  comma-separated catalog ids. Only catalog ids are allowed. Never invent ids and never rewrite guidance text.
- Cover the before, during and after phases for every audience.
- add_general_advice is only for short general notes the catalog lacks. Use it rarely.
- Never mention medicines or doses, never diagnose anyone, never suggest limiting water,
  never give a phone number, and never say that HeatWise sends alerts or contacts anyone.
- The risk category given to you is final. Do not name any other category.
- In PlanIntro, write two or three plain sentences introducing the plan. Only use numbers given to you.
  Do not describe sky, cloud or rain, and do not mention official warnings."""


def plan_audiences(profile: CommunityProfile) -> tuple[str, ...]:
    """Households always; outdoor workers and farmers when the community includes them."""
    out = ["household"]
    if profile.outdoor_workers:
        out.append("outdoor_worker")
    if profile.farmers:
        out.append("farmer")
    return tuple(out)


def resolve_language(requested: str | None) -> tuple[str, str, str | None]:
    """Return (language, requested_language, notice). Guidance is English-only in M2 (D6)."""
    req = (requested or "en").strip().lower() or "en"
    if req in SUPPORTED_PLAN_LANGUAGES:
        return req, req, None
    return "en", req, (f"The requested language '{req}' is not available yet. This plan is in English because "
                       "translated guidance cannot be verified against its sources.")


def deterministic_intro(risk: RiskAssessment, audiences: tuple[str, ...]) -> str:
    who = ", ".join(_AUDIENCE_WORDS[a] for a in audiences)
    return (f"This plan lists heat preparedness actions for {who}, before, during and after hot days. "
            f"Community heat risk is {risk.category.replace('_', ' ')} according to the rules-based assessment. "
            "The actions are general guidance from trusted public sources, not medical advice.")


def build_prompt(risk: RiskAssessment, audiences: tuple[str, ...], revision_notes: list[str] | None) -> str:
    lines = [
        f"Community heat risk category: {risk.category} (final, from deterministic rules).",
        f"Plan audiences: {', '.join(audiences)}.",
        "Skills to load: " + ", ".join(AUDIENCE_SKILLS[a] for a in audiences) + ".",
    ]
    if risk.heat_index_c is not None:
        lines.append(f"Current heat index: {risk.heat_index_c:g}°C.")
    if revision_notes:
        lines.append("This is a revision. The Safety Agent rejected the previous plan for these reasons; fix them:")
        lines += [f"- {n}" for n in revision_notes]
    lines.append("Build the plan with the planning tools, then write the PlanIntro.")
    return "\n".join(lines)


def assemble_items(records: list[ToolCallRecord], audiences: tuple[str, ...], category: str,
                   max_general_advice: int) -> list[PlanItem]:
    """Plan items from successful tool calls in the ledger, then the deterministic fill (D5)."""
    items: dict[str, PlanItem] = {}
    general = 0
    for r in records:
        if r.status != "success" or not isinstance(r.payload, dict):
            continue
        if r.tool == "select_guidance":
            for gid in r.payload.get("selected") or []:
                g = CATALOG.get(gid)
                if g is not None and g.audience in audiences and gid not in items:
                    items[gid] = PlanItem(id=g.id, audience=g.audience, phase=g.phase, topic=g.topic, text=g.text,
                                          source_ids=list(g.source_ids), kind="sourced", added_by="agent")
        elif r.tool == "add_general_advice" and general < max_general_advice:
            aud, phase, text = r.payload.get("audience"), r.payload.get("phase"), r.payload.get("text")
            if aud in audiences and phase in PHASES and isinstance(text, str) and text.strip():
                general += 1
                gid = f"general-{general}"
                items[gid] = PlanItem(id=gid, audience=aud, phase=phase, topic="general", text=text.strip(),
                                      source_ids=[], kind="general_educational", added_by="agent")

    def add_rule(g) -> None:
        if g.id not in items:
            items[g.id] = PlanItem(id=g.id, audience=g.audience, phase=g.phase, topic=g.topic, text=g.text,
                                   source_ids=list(g.source_ids), kind="sourced", added_by="rules")

    if not any(i.kind == "sourced" for i in items.values()):
        # Nothing usable was selected (model failure or no selection): full deterministic plan.
        for aud in audiences:
            for g in catalog_for(aud, None, category):
                add_rule(g)
    for aud in audiences:
        for phase in PHASES:
            if not any(i.audience == aud and i.phase == phase and i.kind == "sourced" for i in items.values()):
                options = catalog_for(aud, phase, category)
                pick = next((g for g in options if g.topic in REQUIRED_TOPICS), options[0] if options else None)
                if pick is not None:
                    add_rule(pick)
        for topic in REQUIRED_TOPICS:
            if not any(i.audience == aud and i.topic == topic for i in items.values()):
                options = [g for g in catalog_for(aud, None, category) if g.topic == topic]
                options.sort(key=lambda g: 0 if g.phase == "during" else 1)
                if options:
                    add_rule(options[0])

    order = {a: n for n, a in enumerate(audiences)}
    phase_order = {p: n for n, p in enumerate(PHASES)}
    return sorted(items.values(), key=lambda i: (order[i.audience], phase_order[i.phase]))


def check_intro(intro: str, risk: RiskAssessment, weather: WeatherIntelligenceResult | None) -> list[str]:
    problems: list[str] = []
    if not intro:
        return ["Model intro was empty."]
    if len(intro) > INTRO_MAX_CHARS:
        problems.append(f"Model intro is longer than {INTRO_MAX_CHARS} characters.")
    alerts_supported = bool(weather and weather.alerts and weather.alerts.alerts_supported)
    problems += check_text_claims(intro, evidence_numbers(weather, risk), alerts_supported)
    others = named_categories(intro) - {risk.category}
    if others:
        problems.append(f"Model intro named a different risk category ({', '.join(sorted(others))}).")
    return problems


class ActionPlannerAgent:
    def __init__(self, settings: Settings, model: Model | None = None, skills_dir: Path = SKILLS_DIR) -> None:
        self.settings = settings
        self._model = model
        self.skills_dir = Path(skills_dir)
        self._context: PlanningContext | None = None
        self.tools = build_planning_tools(lambda: self._context)
        self.last_trace: list[ToolCallRecord] = []
        self.last_blocked: list[dict[str, str]] = []
        self.last_prompt: str | None = None

    @property
    def model(self) -> Model:
        if self._model is None:
            self._model = build_bedrock_model(self.settings)
        return self._model

    def _build_agent(self) -> tuple[Agent, GuardrailHook, EvidenceLedgerHook]:
        guardrail = GuardrailHook(
            allowed_tools=PLANNING_TOOL_NAMES,
            max_tool_calls=self.settings.planner_max_tool_calls,
            uncounted_tools=[SKILLS_TOOL, STRUCTURED_TOOL],
        )
        ledger = EvidenceLedgerHook(ignored_tools=[STRUCTURED_TOOL])
        agent = Agent(
            name=AGENT_NAME,
            description="Builds a heat preparedness plan from verified guidance for households, workers and farmers.",
            model=self.model,
            tools=self.tools,
            system_prompt=SYSTEM_PROMPT,
            hooks=[guardrail, ledger],
            plugins=[AgentSkills(skills=[self.skills_dir.as_posix()])],
            structured_output_model=PlanIntro,
            callback_handler=None,
        )
        return agent, guardrail, ledger

    def run(self, risk: RiskAssessment, profile: CommunityProfile | None = None,
            weather: WeatherIntelligenceResult | None = None, revision_notes: list[str] | None = None,
            revision: int = 0) -> PreparednessPlan:
        profile = profile or CommunityProfile()
        language, requested, notice = resolve_language(profile.preferred_language)
        self.last_trace, self.last_blocked, self.last_prompt = [], [], None
        base = dict(language=language, requested_language=requested, language_notice=notice,
                    risk_category=risk.category, revision=revision)
        if risk.category == "unknown":
            return PreparednessPlan(status="skipped", issues=["Risk category is unknown; no plan was built."], **base)

        audiences = plan_audiences(profile)
        self._context = PlanningContext(risk_category=risk.category, audiences=audiences,
                                        max_general_advice=self.settings.plan_max_general_advice)
        issues: list[str] = []
        intro: PlanIntro | None = None
        records: list[ToolCallRecord] = []
        self.last_prompt = build_prompt(risk, audiences, revision_notes)
        try:
            agent, guardrail, ledger = self._build_agent()
            try:
                result = agent(
                    self.last_prompt,
                    limits={"turns": self.settings.planner_max_tool_calls + 2,
                            "structured_output_attempts": STRUCTURED_OUTPUT_ATTEMPTS},
                )
                if isinstance(result.structured_output, PlanIntro):
                    intro = result.structured_output
                else:
                    issues.append(f"Agent stopped without a structured intro (stop_reason={result.stop_reason}).")
            finally:
                records = list(ledger.records)
                self.last_trace = records
                self.last_blocked = list(guardrail.blocked)
        except Exception as exc:  # model/service failures must not crash the workflow
            logger.exception("planner agent invocation failed")
            issues.append(f"Planner agent failed: {type(exc).__name__}")
        finally:
            self._context = None

        items = assemble_items(records, audiences, risk.category, self.settings.plan_max_general_advice)
        text = intro.intro.strip() if intro is not None else ""
        if intro is not None:
            issues += check_intro(text, risk, weather)
        use_model = intro is not None and not issues
        return PreparednessPlan(
            status="ok",
            intro=text if use_model else deterministic_intro(risk, audiences),
            intro_source="model" if use_model else "rules",
            items=items,
            checklist=[ChecklistItem(id=i.id, audience=i.audience, phase=i.phase, text=i.text) for i in items],
            issues=issues,
            **base,
        )

    def as_tool(self):
        """Agents-as-tools wrapper (workshop Module 6)."""
        specialist = self

        @tool
        def action_planner(risk_json: str, profile_json: str = "{}", weather_json: str = "",
                           revision_notes: str = ""):
            """Delegate to the Preparedness Action Planner Agent. Builds a heat preparedness plan from
            verified guidance for households, outdoor workers and farmers, and returns it as JSON.

            Args:
                risk_json: RiskAssessment JSON from the Community Risk Agent.
                profile_json: CommunityProfile JSON (community-level indicators, terrain, language).
                weather_json: Optional WeatherIntelligenceResult JSON, used to check numbers in the intro.
                revision_notes: Optional newline-separated Safety Agent issues to fix in a revision.
            """
            try:
                risk = RiskAssessment.model_validate_json(risk_json)
                profile = CommunityProfile.model_validate_json(profile_json or "{}")
                weather = WeatherIntelligenceResult.model_validate_json(weather_json) if weather_json else None
            except PydanticValidationError as exc:
                return tool_error("invalid_argument", f"Invalid input: {exc.error_count()} validation error(s).")
            notes = [n.strip() for n in (revision_notes or "").splitlines() if n.strip()]
            return specialist.run(risk, profile, weather, notes or None, revision=1 if notes else 0).model_dump_json()

        return action_planner
