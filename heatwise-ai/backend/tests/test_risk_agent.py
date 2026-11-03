"""Community Risk Agent tests through the real Strands agent loop (LLM replaced by ScriptedModel)."""

from __future__ import annotations

import json

from backend.agents.risk_agent import CommunityRiskAgent, deterministic_explanation, named_categories
from backend.models.risk import CommunityProfile
from backend.services.claims import check_text_claims
from backend.services.risk_rules import classify
from backend.tests.fakes import make_weather
from backend.tests.scripted_model import ScriptedModel, text, tool_call

PROFILE = CommunityProfile(terrain="plains", elderly=True, outdoor_workers=True)
CLASSIFY = [tool_call("classify_heat_risk")]


def weather():
    return make_weather(44.2, 21, [44, 45, 46], apparent_c=46.0)


def explain(s):
    return tool_call("RiskExplanation", explanation=s)


def make_agent(settings, turns):
    model = ScriptedModel(turns)
    return CommunityRiskAgent(settings, model=model), model


def test_happy_path_keeps_grounded_model_explanation(settings):
    w = weather()
    expected = classify(w, PROFILE, settings.risk_vulnerability_min_indicators)
    good = (f"Community heat risk is {expected.category.replace('_', ' ')}. The forecast reaches 46°C, above the "
            "45°C IMD heat-wave criterion; this is an indication, not an official declaration.")
    agent, model = make_agent(settings, [CLASSIFY, [explain(good)]])
    r = agent.run(w, PROFILE)

    assert r.category == expected.category == "extreme"
    assert r.explanation == good and r.explanation_source == "model" and r.explanation_issues == []
    assert set(model.calls[0]["tool_names"]) >= {"classify_heat_risk", "get_risk_rules", "RiskExplanation"}
    assert [t.tool for t in agent.last_trace] == ["classify_heat_risk"]
    assert agent.last_trace[0].status == "success" and agent.last_trace[0].agent == "community_risk"


def test_wrong_category_or_number_replaced(settings):
    for bad in ("This is a low risk situation.", "Temperatures near 30°C make this manageable.",
                "An official warning is in force.", "Community heat risk is extreme; call 911 if anyone collapses."):
        agent, _ = make_agent(settings, [CLASSIFY, [explain(bad)]])
        r = agent.run(weather(), PROFILE)
        assert r.category == "extreme"
        assert r.explanation_source == "rules" and r.explanation_issues
        assert r.explanation == deterministic_explanation(r)


def test_tool_never_called_still_categorised(settings):
    agent, _ = make_agent(settings, [[explain("Community heat risk is extreme.")]])
    r = agent.run(weather(), PROFILE)
    assert r.category == "extreme" and r.status == "ok"
    assert r.explanation_source == "rules"
    assert any("without calling classify_heat_risk" in i for i in r.explanation_issues)


def test_unapproved_tool_blocked(settings):
    turns = [[tool_call("send_alert", to="+910000000000", body="evacuate"), *CLASSIFY],
             [explain("Community heat risk is extreme.")]]
    agent, _ = make_agent(settings, turns)
    r = agent.run(weather(), PROFILE)
    blocked = [t for t in agent.last_trace if t.status == "cancelled"]
    assert [t.tool for t in blocked] == ["send_alert"] and "not approved" in blocked[0].cancel_reason
    assert agent.last_blocked[0]["tool"] == "send_alert"
    assert r.category == "extreme"


def test_model_exception_contained(settings):
    class Boom(ScriptedModel):
        async def stream(self, *a, **k):
            raise RuntimeError("bedrock down")
            yield  # noqa

    agent = CommunityRiskAgent(settings, model=Boom([]))
    r = agent.run(weather(), PROFILE)
    assert r.category == "extreme" and r.explanation_source == "rules"
    assert any("Risk agent failed" in i for i in r.explanation_issues)


def test_prose_only_model_falls_back(settings):
    agent, model = make_agent(settings, [CLASSIFY] + [[text("It is hot.")]] * 20)
    r = agent.run(weather(), PROFILE)
    assert r.category == "extreme" and r.explanation_source == "rules"
    assert len(model.calls) <= settings.agent_max_turns + 2


def test_no_weather_makes_no_model_calls(settings):
    agent, model = make_agent(settings, [])
    r = agent.run(make_weather(None, None, current=False, forecast=False), PROFILE)
    assert r.status == "insufficient_data" and r.category == "unknown"
    assert model.calls == [] and agent.last_trace == []
    assert r.explanation and r.explanation_source == "rules"


def test_deterministic_explanation_passes_own_checks(settings):
    from backend.agents.risk_agent import evidence_numbers

    for w, p in ((weather(), PROFILE), (make_weather(29, 50, [38]), CommunityProfile()),
                 (make_weather(25, 40, [47.5]), CommunityProfile(terrain="hilly"))):
        r = classify(w, p, 2)
        t = deterministic_explanation(r)
        assert check_text_claims(t, evidence_numbers(w, r), alerts_supported=False) == []
        assert named_categories(t) <= {r.category}


def test_as_tool_returns_json(settings):
    agent, _ = make_agent(settings, [CLASSIFY, [explain("Community heat risk is extreme.")]])
    risk_tool = agent.as_tool()
    assert risk_tool.tool_name == "community_risk"
    payload = json.loads(risk_tool(weather_json=weather().model_dump_json(), profile_json=PROFILE.model_dump_json()))
    assert payload["category"] == "extreme"
