"""Safety and Verification Agent.

Pass/fail always comes from `run_checks` (deterministic code). When
`settings.safety_llm_review` is on, a Strands agent may call `run_safety_checks` and
return a `SafetyReview`; a concern is added to `llm_concerns` (and a warning check)
but never changes the status (D7).
"""

from __future__ import annotations

import logging

from strands import Agent
from strands.models import Model

from backend.agents.hooks import EvidenceLedgerHook, GuardrailHook
from backend.agents.model_factory import build_bedrock_model
from backend.config import Settings
from backend.models.plan import PreparednessPlan
from backend.models.risk import RiskAssessment
from backend.models.trace import ToolCallRecord
from backend.models.verification import CheckResult, SafetyReview, VerificationResult
from backend.models.weather import WeatherIntelligenceResult
from backend.tools.verification_tools import (
    VERIFICATION_TOOL_NAMES,
    VerificationContext,
    build_verification_tools,
    run_checks,
)

logger = logging.getLogger("heatwise.safety_agent")

AGENT_NAME = "safety_verifier"
STRUCTURED_TOOL = SafetyReview.__name__
STRUCTURED_OUTPUT_ATTEMPTS = 2
CONCERN_MAX_CHARS = 300
_NO_CONCERN = {"", "none", "null", "no concern", "no concerns", "n/a"}

SYSTEM_PROMPT = """You are the Safety and Verification Agent for HeatWise AI, a heatwave preparedness assistant.

Your job: review a community heat preparedness plan for safety problems.

Rules:
- Call run_safety_checks once. Its pass/fail result is final; you cannot change it.
- Then read the plan text you were given and report at most one additional safety concern
  (for example advice that could be unsafe or misleading) in SafetyReview.concern.
- If you have no additional concern, set concern to null.
- Never give medical advice and never diagnose anyone."""


def _review_prompt(plan: PreparednessPlan | None) -> str:
    lines = ["Review this preparedness plan. Call run_safety_checks, then return a SafetyReview."]
    if plan is not None:
        if plan.intro:
            lines.append(f"Intro: {plan.intro}")
        lines += [f"- [{i.audience}/{i.phase}] {i.text}" for i in plan.items]
    return "\n".join(lines)


class SafetyVerificationAgent:
    def __init__(self, settings: Settings, model: Model | None = None) -> None:
        self.settings = settings
        self._model = model
        self._context: VerificationContext | None = None
        self.tools = build_verification_tools(lambda: self._context)
        self.last_trace: list[ToolCallRecord] = []
        self.last_blocked: list[dict[str, str]] = []

    @property
    def model(self) -> Model:
        if self._model is None:
            self._model = build_bedrock_model(self.settings)
        return self._model

    def _build_agent(self) -> tuple[Agent, GuardrailHook, EvidenceLedgerHook]:
        guardrail = GuardrailHook(
            allowed_tools=VERIFICATION_TOOL_NAMES,
            max_tool_calls=self.settings.agent_max_tool_calls,
            uncounted_tools=[STRUCTURED_TOOL],
        )
        ledger = EvidenceLedgerHook(ignored_tools=[STRUCTURED_TOOL])
        agent = Agent(
            name=AGENT_NAME,
            description="Verifies a heat preparedness plan with deterministic safety checks.",
            model=self.model,
            tools=self.tools,
            system_prompt=SYSTEM_PROMPT,
            hooks=[guardrail, ledger],
            structured_output_model=SafetyReview,
            callback_handler=None,
        )
        return agent, guardrail, ledger

    def run(self, weather: WeatherIntelligenceResult | None, risk: RiskAssessment | None,
            plan: PreparednessPlan | None) -> VerificationResult:
        self.last_trace, self.last_blocked = [], []
        result = run_checks(weather, risk, plan)  # the only source of pass/fail
        if not self.settings.safety_llm_review:
            return result

        self._context = VerificationContext(weather=weather, risk=risk, plan=plan)
        concern: str | None = None
        try:
            agent, guardrail, ledger = self._build_agent()
            try:
                out = agent(_review_prompt(plan),
                            limits={"turns": self.settings.agent_max_turns,
                                    "structured_output_attempts": STRUCTURED_OUTPUT_ATTEMPTS})
                if isinstance(out.structured_output, SafetyReview) and out.structured_output.concern:
                    concern = out.structured_output.concern.strip()[:CONCERN_MAX_CHARS]
            finally:
                self.last_trace = list(ledger.records)
                self.last_blocked = list(guardrail.blocked)
        except Exception:  # the review is optional; failures never affect the result
            logger.exception("safety LLM review failed")
        finally:
            self._context = None

        if not concern or concern.lower().rstrip(".") in _NO_CONCERN:
            return result
        check = CheckResult(name="llm_review", passed=False, severity="warning",
                            message=f"LLM review concern (non-blocking): {concern}")
        return result.model_copy(update={
            "checks": [*result.checks, check],
            "warnings": [*result.warnings, check.message],
            "llm_concerns": [concern],
        })
