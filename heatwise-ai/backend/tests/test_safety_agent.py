"""Safety and Verification Agent tests. Pass/fail must come only from deterministic checks."""

from __future__ import annotations

from backend.agents.planner_agent import assemble_items, deterministic_intro
from backend.agents.risk_agent import deterministic_explanation
from backend.agents.safety_agent import SafetyVerificationAgent
from backend.models.plan import ChecklistItem, PlanItem, PreparednessPlan
from backend.models.risk import CommunityProfile
from backend.services.risk_rules import classify
from backend.tests.fakes import make_weather
from backend.tests.scripted_model import ScriptedModel, tool_call
from backend.tools.verification_tools import run_checks

PROFILE = CommunityProfile(terrain="plains", elderly=True, outdoor_workers=True, farmers=True)
AUDIENCES = ("household", "outdoor_worker", "farmer")


def weather(**kw):
    return make_weather(44.2, 21, [44, 45, 46], apparent_c=46.0, **kw)


def risk_for(w):
    r = classify(w, PROFILE, 2)
    return r.model_copy(update={"explanation": deterministic_explanation(r), "explanation_source": "rules"})


def clean_plan(risk, extra: list[PlanItem] = (), intro: str | None = None) -> PreparednessPlan:
    items = assemble_items([], AUDIENCES, risk.category, 3) + list(extra)
    return PreparednessPlan(status="ok", risk_category=risk.category,
                            intro=intro or deterministic_intro(risk, AUDIENCES), intro_source="rules", items=items,
                            checklist=[ChecklistItem(id=i.id, audience=i.audience, phase=i.phase, text=i.text)
                                       for i in items])


def general(text, gid="general-1"):
    return PlanItem(id=gid, audience="household", phase="during", topic="general", text=text,
                    kind="general_educational")


def failed_names(result):
    return {c.name for c in result.checks if not c.passed and c.severity == "error"}


def no_review(settings):
    return settings.model_copy(update={"safety_llm_review": False})


def test_clean_plan_passes_without_model_when_review_off(settings):
    w = weather()
    risk = risk_for(w)
    model = ScriptedModel([])
    agent = SafetyVerificationAgent(no_review(settings), model=model)
    r = agent.run(w, risk, clean_plan(risk))
    assert r.status == "passed", r.issues
    assert r.issues == [] and r.warnings == [] and r.pct_items_verified == 100.0
    assert model.calls == [] and agent.last_trace == []


def test_banned_general_advice_fails(settings):
    w = weather()
    risk = risk_for(w)
    for bad in ("Take aspirin if you feel hot.", "If you feel dizzy, you have heat stroke.",
                "There is no need to see a doctor.", "Drink less water to avoid trips outside.",
                "HeatWise will send alerts to your village.", "Give 500 mg paracetamol."):
        r = run_checks(w, risk, clean_plan(risk, [general(bad)]))
        assert r.status == "failed", bad
        assert "banned_content" in failed_names(r), bad
        assert "general-1" not in r.verified_item_ids and r.pct_items_verified < 100


def test_phone_numbers_fail_in_advice_and_intro(settings):
    w = weather()
    risk = risk_for(w)
    for bad in ("If someone collapses, call 108 for an ambulance.", "Dial 112 or 911 right away.",
                "Call the helpline at +91 98765 43210."):
        r = run_checks(w, risk, clean_plan(risk, [general(bad)]))
        assert r.status == "failed" and "banned_content" in failed_names(r), bad
        assert "general-1" not in r.verified_item_ids
    r = run_checks(w, risk, clean_plan(risk, intro="In an emergency dial 112."))
    assert r.status == "failed" and {"banned_content", "text_claims"} <= failed_names(r)


def test_broader_diagnosis_patterns_fail(settings):
    w = weather()
    risk = risk_for(w)
    for bad in ("Older people with heart disease are certainly suffering heat illness now.",
                "Your neighbour is having heat stroke.", "Many workers have heat exhaustion today."):
        r = run_checks(w, risk, clean_plan(risk, [general(bad)]))
        assert r.status == "failed" and "banned_content" in failed_names(r), bad


def test_unsupported_intro_claims_fail(settings):
    w = weather()
    risk = risk_for(w)
    for bad in ("Expect clear skies this week.", "Temperatures will reach 52°C."):
        r = run_checks(w, risk, clean_plan(risk, intro=bad))
        assert r.status == "failed" and "text_claims" in failed_names(r), bad
    ok = run_checks(w, risk, clean_plan(risk, intro="The forecast reaches 46°C, so plan ahead."))
    assert ok.status == "passed"


def test_unknown_source_id_fails(settings):
    w = weather()
    risk = risk_for(w)
    plan = clean_plan(risk)
    plan.items[0] = plan.items[0].model_copy(update={"source_ids": ["made_up_source"]})
    r = run_checks(w, risk, plan)
    assert r.status == "failed" and "item_sources" in failed_names(r)
    assert plan.items[0].id not in r.verified_item_ids


def test_stale_weather_fails_and_demo_is_warning(settings):
    stale = weather(stale=True)
    r = run_checks(stale, risk_for(stale), clean_plan(risk_for(stale)))
    assert r.status == "failed" and "weather_freshness" in failed_names(r)

    demo = weather(data_mode="demo")
    r = run_checks(demo, risk_for(demo), clean_plan(risk_for(demo)))
    assert r.status == "passed" and any("demo" in w for w in r.warnings)


def test_weather_agent_and_safety_accept_forecast_fahrenheit():
    # Seam between the Weather Agent and the safety text_claims check: a summary the
    # Weather Agent keeps (correct forecast °F conversion) must not fail safety.
    w = weather().model_copy(update={"summary": "Highs reach 46°C (about 115°F)."})
    risk = risk_for(w)
    r = run_checks(w, risk, clean_plan(risk))
    assert "text_claims" not in failed_names(r), r.issues


def test_missing_escalation_and_category_mismatch_fail(settings):
    w = weather()
    risk = risk_for(w)
    plan = clean_plan(risk)
    no_esc = plan.model_copy(update={"items": [i for i in plan.items
                                               if not (i.audience == "farmer" and i.topic == "escalation")]})
    assert "escalation_present" in failed_names(run_checks(w, risk, no_esc))
    mismatch = plan.model_copy(update={"risk_category": "low"})
    assert "risk_category_match" in failed_names(run_checks(w, risk, mismatch))
    skipped = PreparednessPlan(status="skipped", risk_category=risk.category)
    assert "plan_present" in failed_names(run_checks(w, risk, skipped))


def review(concern):
    return [[tool_call("run_safety_checks")], [tool_call("SafetyReview", concern=concern)]]


def test_llm_concern_on_passing_plan_stays_passed(settings):
    w = weather()
    risk = risk_for(w)
    model = ScriptedModel(review("The intro could mention checking on neighbours."))
    agent = SafetyVerificationAgent(settings, model=model)
    r = agent.run(w, risk, clean_plan(risk))
    assert r.status == "passed"
    assert r.llm_concerns == ["The intro could mention checking on neighbours."]
    assert any("non-blocking" in x for x in r.warnings)
    assert [t.tool for t in agent.last_trace] == ["run_safety_checks"]
    assert set(model.calls[0]["tool_names"]) >= {"run_safety_checks", "SafetyReview"}


def test_llm_no_concern_on_failing_plan_stays_failed(settings):
    w = weather()
    risk = risk_for(w)
    agent = SafetyVerificationAgent(settings, model=ScriptedModel(review(None)))
    r = agent.run(w, risk, clean_plan(risk, [general("Take aspirin if you feel hot.")]))
    assert r.status == "failed" and r.llm_concerns == []


def test_llm_failure_does_not_change_result(settings):
    class Boom(ScriptedModel):
        async def stream(self, *a, **k):
            raise RuntimeError("bedrock down")
            yield  # noqa

    w = weather()
    risk = risk_for(w)
    plan = clean_plan(risk)
    r = SafetyVerificationAgent(settings, model=Boom([])).run(w, risk, plan)
    assert r == run_checks(w, risk, plan)
