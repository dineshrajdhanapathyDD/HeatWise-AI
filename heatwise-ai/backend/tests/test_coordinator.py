"""Coordinator tests through the real Strands agent loop: one ScriptedModel per agent, FakeProvider weather."""

from __future__ import annotations

from backend.agents.coordinator import (
    FALLBACK_AGENT,
    CoordinatorRun,
    HeatWiseCoordinator,
    OrderingSteeringHandler,
)
from backend.agents.planner_agent import ActionPlannerAgent
from backend.agents.risk_agent import CommunityRiskAgent
from backend.agents.safety_agent import SafetyVerificationAgent
from backend.agents.weather_agent import WeatherIntelligenceAgent
from backend.models.risk import CommunityProfile
from backend.services.weather.base import ProviderTimeoutError
from backend.tests.fakes import FakeProvider
from backend.tests.scripted_model import ScriptedModel, text, tool_call

PROFILE = CommunityProfile(terrain="plains", elderly=True, outdoor_workers=True, farmers=True)
DELEGATIONS = ["weather_intelligence", "community_risk", "action_planner", "safety_verifier"]

WEATHER_TURNS = [
    [tool_call("get_weather", location="Wardha"), tool_call("get_forecast", location="Wardha", days=3),
     tool_call("get_weather_alerts", location="Wardha")],
    [tool_call("WeatherSummary", location_name="Wardha", summary="Very hot and dry in Wardha.",
               claimed_temperature_c=44.2, claimed_apparent_temperature_c=46.0, claimed_humidity_pct=21.0,
               claimed_max_forecast_temperature_c=46.0)],
]
RISK_TURNS = [
    [tool_call("classify_heat_risk")],
    [tool_call("RiskExplanation", explanation="Community heat risk is extreme. The forecast reaches 46°C, above "
                                              "the 45°C IMD heat-wave criterion; this is an indication, not an "
                                              "official declaration.")],
]
SAFE_PLAN = [
    [tool_call("list_guidance", audience="household", phase="all")],
    [tool_call("PlanIntro", intro="This plan helps the community prepare for the heat.")],
]
UNSAFE_PLAN = [
    [tool_call("add_general_advice", audience="household", phase="during", text="Take aspirin if you feel hot.")],
    [tool_call("PlanIntro", intro="This plan helps the community prepare for the heat.")],
]
REVIEW = [[tool_call("run_safety_checks")], [tool_call("SafetyReview", concern=None)]]


def calls(*names):
    return [[tool_call(n)] for n in names] + [[text("The report is ready.")]]


def build(settings, coordinator_turns, planner_turns=SAFE_PLAN, safety_turns=REVIEW, provider=None,
          coordinator_model=None):
    models = {
        "weather": ScriptedModel(WEATHER_TURNS),
        "risk": ScriptedModel(RISK_TURNS),
        "planner": ScriptedModel(planner_turns),
        "safety": ScriptedModel(safety_turns),
        "coordinator": coordinator_model or ScriptedModel(coordinator_turns),
    }
    coord = HeatWiseCoordinator(
        settings,
        weather_agent=WeatherIntelligenceAgent(settings, provider=provider or FakeProvider(), model=models["weather"]),
        risk_agent=CommunityRiskAgent(settings, model=models["risk"]),
        planner_agent=ActionPlannerAgent(settings, model=models["planner"]),
        safety_agent=SafetyVerificationAgent(settings, model=models["safety"]),
        model=models["coordinator"],
    )
    return coord, models


def coordinator_entries(report):
    return [t for t in report.trace if t.agent == "coordinator"]


def first_seen_agents(report):
    return list(dict.fromkeys(t.agent for t in report.trace if t.agent not in ("coordinator", FALLBACK_AGENT)))


def test_happy_path_complete_and_ordered(settings):
    coord, models = build(settings, calls(*DELEGATIONS, "finalize_report"))
    report = coord.run("Wardha", PROFILE, 3)

    assert report.status == "complete" and report.verification_status == "passed", report.verification
    assert report.risk_category == "extreme" and report.revision_count == 0
    assert [t.tool for t in coordinator_entries(report)] == [*DELEGATIONS, "finalize_report"]
    assert all(t.status == "success" for t in coordinator_entries(report))
    assert first_seen_agents(report) == DELEGATIONS
    assert report.steering_blocks == [] and coord.last_state.fallback_steps == []
    assert report.recommended_actions is not None and report.checklist_markdown.startswith("# Heatwave")
    assert report.weather_source.provider == "FakeProvider" and report.location.name == "Wardha"
    assert any(e.kind == "heat_index" for e in report.evidence)
    assert any("does not send alerts" in n for n in report.notices)
    # Step indexes rise with the coordinator's calls; specialist calls share their delegation's index.
    indexes = [t.step_index for t in report.trace]
    assert indexes == sorted(indexes)
    weather_step = next(t.step_index for t in coordinator_entries(report) if t.tool == "weather_intelligence")
    assert {t.tool for t in report.trace if t.step_index == weather_step and t.agent == "weather_intelligence"} == {
        "get_weather", "get_forecast", "get_weather_alerts"}
    # The coordinator model saw its five tools and the sequential executor ran one call per turn.
    assert set(models["coordinator"].calls[0]["tool_names"]) == {*DELEGATIONS, "finalize_report"}


def test_planner_first_is_cancelled_by_steering(settings):
    coord, _ = build(settings, calls("action_planner", *DELEGATIONS, "finalize_report"))
    report = coord.run("Wardha", PROFILE, 3)

    first = coordinator_entries(report)[0]
    assert first.tool == "action_planner" and first.status == "cancelled"
    assert "weather_intelligence first" in first.cancel_reason
    assert report.steering_blocks[0]["tool"] == "action_planner"
    assert first_seen_agents(report) == DELEGATIONS
    assert report.status == "complete"


def test_finalize_before_safety_is_blocked(settings):
    coord, _ = build(settings, calls("weather_intelligence", "community_risk", "action_planner",
                                     "finalize_report", "safety_verifier", "finalize_report"))
    report = coord.run("Wardha", PROFILE, 3)

    finals = [t for t in coordinator_entries(report) if t.tool == "finalize_report"]
    assert [t.status for t in finals] == ["cancelled", "success"]
    assert "safety_verifier" in finals[0].cancel_reason
    assert report.status == "complete" and coord.last_state.fallback_steps == []


def test_unsafe_plan_twice_needs_human_review(settings):
    turns = calls(*DELEGATIONS, "action_planner", "safety_verifier", "action_planner", "finalize_report")
    coord, _ = build(settings, turns, planner_turns=UNSAFE_PLAN + UNSAFE_PLAN, safety_turns=REVIEW + REVIEW)
    report = coord.run("Wardha", PROFILE, 3)

    assert report.status == "needs_human_review" and report.verification_status == "failed"
    assert report.revision_count == 1
    planner_calls = [t for t in coordinator_entries(report) if t.tool == "action_planner"]
    assert [t.status for t in planner_calls] == ["success", "success", "cancelled"]  # third call blocked
    assert len(coord.last_state.plans) == 2 and coord.last_state.plans[1].revision == 1
    assert any("medicine" in n for n in report.verification.issues)
    assert any("person should review" in n for n in report.notices)
    assert coord.last_state.fallback_steps == []
    # The full failing plan stays in the JSON for the reviewer; the exported checklist does not.
    assert any("aspirin" in i.text for i in report.recommended_actions.items)
    md = report.checklist_markdown
    assert "Not verified - needs human review" in md and "person should review" in md
    assert "aspirin" not in md.lower()
    verified = set(report.verification.verified_item_ids)
    assert verified and "general-1" not in verified
    for item in report.recommended_actions.items:
        assert (f"- [ ] {item.text}" in md) == (item.id in verified)


def test_unsafe_then_safe_revision_completes(settings):
    turns = calls(*DELEGATIONS, "action_planner", "safety_verifier", "finalize_report")
    coord, _ = build(settings, turns, planner_turns=UNSAFE_PLAN + SAFE_PLAN, safety_turns=REVIEW + REVIEW)
    report = coord.run("Wardha", PROFILE, 3)

    assert report.status == "complete" and report.verification_status == "passed"
    assert report.revision_count == 1
    assert [v.status for v in coord.last_state.verifications] == ["failed", "passed"]
    assert coord.planner_agent.last_prompt and "revision" in coord.planner_agent.last_prompt


def test_provider_timeout_is_incomplete(settings):
    provider = FakeProvider(fail={"current": ProviderTimeoutError("slow"), "forecast": ProviderTimeoutError("slow")})
    coord, models = build(settings, calls("weather_intelligence", "community_risk", "finalize_report"),
                          provider=provider)
    report = coord.run("Wardha", PROFILE, 3)

    assert report.status == "incomplete" and report.verification_status == "not_run"
    assert report.recommended_actions is None and report.checklist_markdown is None
    assert any("provider_timeout" in m for m in report.missing_information)
    assert report.steering_blocks and report.steering_blocks[0]["tool"] == "community_risk"
    assert models["risk"].calls == [] and models["planner"].calls == [] and models["safety"].calls == []
    assert coord.last_state.fallback_steps == []
    assert [b["tool"] for b in report.steering_blocks] == ["community_risk"]  # finalize_report was allowed


def test_finalize_allowed_when_weather_unusable(settings):
    # Live 503 run: finalize_report must not be told to call community_risk while community_risk is told
    # to finalize. A model that finalizes straight after unusable weather is not blocked.
    provider = FakeProvider(fail={"current": ProviderTimeoutError("slow"), "forecast": ProviderTimeoutError("slow")})
    coord, _ = build(settings, calls("weather_intelligence", "finalize_report"), provider=provider)
    report = coord.run("Wardha", PROFILE, 3)

    assert report.status == "incomplete" and report.steering_blocks == []
    finals = [t for t in coordinator_entries(report) if t.tool == "finalize_report"]
    assert [t.status for t in finals] == ["success"]


def test_coordinator_model_failure_falls_back(settings):
    class Boom(ScriptedModel):
        async def stream(self, *a, **k):
            raise RuntimeError("bedrock down")
            yield  # noqa

    coord, _ = build(settings, [], coordinator_model=Boom([]))
    report = coord.run("Wardha", PROFILE, 3)

    assert report.status == "complete" and report.verification_status == "passed"
    fallback = [t.tool for t in report.trace if t.agent == FALLBACK_AGENT]
    assert fallback == DELEGATIONS
    assert first_seen_agents(report) == DELEGATIONS
    assert any("Coordinator agent failed" in m for m in report.missing_information)


def test_model_stops_after_weather_fallback_completes(settings):
    coord, _ = build(settings, [[tool_call("weather_intelligence")], [text("Here is the weather.")]])
    report = coord.run("Wardha", PROFILE, 3)

    assert report.status == "complete" and report.verification_status == "passed"
    assert coord.last_state.fallback_steps == ["community_risk", "action_planner", "safety_verifier"]
    assert [t.tool for t in report.trace if t.agent == FALLBACK_AGENT] == DELEGATIONS[1:]
    assert any("skipped" in m for m in report.missing_information)


def test_fallback_runs_revision_once(settings):
    coord, _ = build(settings, [[tool_call("weather_intelligence")], [text("Stop.")]],
                     planner_turns=UNSAFE_PLAN + UNSAFE_PLAN, safety_turns=REVIEW + REVIEW)
    report = coord.run("Wardha", PROFILE, 3)
    assert report.status == "needs_human_review" and report.revision_count == 1
    assert coord.last_state.fallback_steps == ["community_risk", "action_planner", "safety_verifier",
                                               "action_planner", "safety_verifier"]


def test_steering_rules_unit():
    state = CoordinatorRun(location="Wardha", days=3, profile=PROFILE)
    handler = OrderingSteeringHandler(lambda: state)
    assert handler.decide("weather_intelligence") is None
    for name in ("community_risk", "action_planner", "safety_verifier", "finalize_report"):
        assert "weather_intelligence first" in handler.decide(name)
    assert handler.decide("send_alert") is None  # left to the guardrail allowlist
