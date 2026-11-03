"""Preparedness Action Planner Agent tests through the real Strands agent loop (LLM replaced by ScriptedModel)."""

from __future__ import annotations

import json

from backend.agents.planner_agent import AUDIENCE_SKILLS, ActionPlannerAgent, deterministic_intro
from backend.guidance.catalog import PHASES, REQUIRED_TOPICS, catalog_for
from backend.models.risk import CommunityProfile
from backend.services.risk_rules import classify
from backend.tests.fakes import make_weather
from backend.tests.scripted_model import ScriptedModel, text, tool_call

ALL = CommunityProfile(terrain="plains", elderly=True, outdoor_workers=True, farmers=True)
HOUSEHOLD = CommunityProfile(terrain="plains")
AUDIENCES = ("household", "outdoor_worker", "farmer")


def weather():
    return make_weather(44.2, 21, [44, 45, 46], apparent_c=46.0)


def risk_for(profile):
    return classify(weather(), profile, 2)


def intro(s):
    return tool_call("PlanIntro", intro=s)


def full_script(category, audiences=AUDIENCES, intro_text="This plan helps the community prepare for the heat."):
    return [
        [tool_call("skills", skill_name=AUDIENCE_SKILLS[a]) for a in audiences],
        [tool_call("list_guidance", audience=a, phase="all") for a in audiences],
        [tool_call("select_guidance", audience=a, phase=p,
                   guidance_ids=",".join(i.id for i in catalog_for(a, p, category)))
         for a in audiences for p in PHASES],
        [intro(intro_text)],
    ]


def make_agent(settings, turns, cls=ScriptedModel):
    model = cls(turns)
    return ActionPlannerAgent(settings, model=model), model


def test_full_selection_three_audiences_three_phases(settings):
    risk = risk_for(ALL)
    agent, model = make_agent(settings, full_script(risk.category))
    plan = agent.run(risk, ALL, weather())

    assert plan.status == "ok" and plan.risk_category == risk.category == "extreme"
    for a in AUDIENCES:
        for p in PHASES:
            expected = {i.id for i in catalog_for(a, p, risk.category)}
            got = {i.id for i in plan.items if i.audience == a and i.phase == p}
            assert got == expected
    assert all(i.added_by == "agent" and i.kind == "sourced" for i in plan.items)
    assert plan.intro_source == "model" and plan.issues == []
    assert [c.id for c in plan.checklist] == [i.id for i in plan.items]
    assert "skills" in model.calls[0]["tool_names"]
    tools_used = [t.tool for t in agent.last_trace]
    assert tools_used.count("skills") == 3 and tools_used.count("select_guidance") == 9
    skill_record = next(t for t in agent.last_trace if t.tool == "skills")
    assert skill_record.status == "success" and "list_guidance" in str(skill_record.payload)
    assert agent.last_blocked == []


def test_missing_phases_and_topics_filled_by_rules(settings):
    risk = risk_for(HOUSEHOLD)
    turns = [[tool_call("select_guidance", audience="household", phase="before", guidance_ids="hh-before-cooling-1")],
             [intro("A short plan for households.")]]
    agent, _ = make_agent(settings, turns)
    plan = agent.run(risk, HOUSEHOLD, weather())

    by_id = {i.id: i for i in plan.items}
    assert by_id["hh-before-cooling-1"].added_by == "agent"
    assert {i.audience for i in plan.items} == {"household"}
    assert {i.phase for i in plan.items} == set(PHASES)
    assert set(REQUIRED_TOPICS) <= {i.topic for i in plan.items}
    assert any(i.added_by == "rules" for i in plan.items)


def test_unknown_id_rejected(settings):
    risk = risk_for(HOUSEHOLD)
    turns = [[tool_call("select_guidance", audience="household", phase="during",
                        guidance_ids="hh-during-hydration-1,hh-made-up-9")],
             [tool_call("select_guidance", audience="household", phase="during", guidance_ids="ow-during-rest-1")],
             [intro("A short plan for households.")]]
    agent, _ = make_agent(settings, turns)
    plan = agent.run(risk, HOUSEHOLD, weather())

    records = [t for t in agent.last_trace if t.tool == "select_guidance"]
    assert [r.status for r in records] == ["error", "error"]
    assert "hh-made-up-9" in json.dumps(records[0].payload)
    ids = {i.id for i in plan.items}
    assert "hh-made-up-9" not in ids and "ow-during-rest-1" not in ids
    assert all(i.added_by == "rules" for i in plan.items)  # nothing valid was selected


def test_unsupported_language_gives_english_with_notice(settings):
    profile = HOUSEHOLD.model_copy(update={"preferred_language": "hi"})
    risk = risk_for(profile)
    agent, _ = make_agent(settings, full_script(risk.category, ("household",)))
    plan = agent.run(risk, profile, weather())
    assert plan.language == "en" and plan.requested_language == "hi"
    assert plan.language_notice and "English" in plan.language_notice
    assert plan.language_notice in plan.checklist_markdown()


def test_checklist_markdown_covers_all_items(settings):
    risk = risk_for(ALL)
    agent, _ = make_agent(settings, full_script(risk.category))
    plan = agent.run(risk, ALL, weather())
    md = plan.checklist_markdown()
    for item in plan.items:
        assert f"- [ ] {item.text}" in md
    for heading in ("## Households", "## Outdoor workers", "## Farmers", "### Before the heat", "### After the heat"):
        assert heading in md


def test_model_failure_gives_deterministic_plan(settings):
    class Boom(ScriptedModel):
        async def stream(self, *a, **k):
            raise RuntimeError("bedrock down")
            yield  # noqa

    risk = risk_for(ALL)
    agent, _ = make_agent(settings, [], cls=Boom)
    plan = agent.run(risk, ALL, weather())
    assert plan.status == "ok" and plan.intro_source == "rules"
    assert plan.intro == deterministic_intro(risk, AUDIENCES)
    assert any("Planner agent failed" in i for i in plan.issues)
    for a in AUDIENCES:
        assert {i.id for i in plan.items if i.audience == a} == {i.id for i in catalog_for(a, None, risk.category)}
    assert all(i.added_by == "rules" for i in plan.items)


def test_intro_with_unsupported_claims_replaced(settings):
    risk = risk_for(HOUSEHOLD)
    for bad in ("Expect 30°C and clear skies.", "This is a low risk situation.", "In an emergency dial 112."):
        agent, _ = make_agent(settings, full_script(risk.category, ("household",), intro_text=bad))
        plan = agent.run(risk, HOUSEHOLD, weather())
        assert plan.intro_source == "rules" and plan.issues
        assert plan.intro == deterministic_intro(risk, ("household",))


def test_general_advice_cap_and_length(settings):
    risk = risk_for(HOUSEHOLD)
    s = settings.model_copy(update={"plan_max_general_advice": 1})
    turns = [[tool_call("add_general_advice", audience="household", phase="during", text="Keep a wet cloth handy.")],
             [tool_call("add_general_advice", audience="household", phase="during", text="Second note.")],
             [tool_call("add_general_advice", audience="household", phase="after", text="x" * 301)],
             [intro("A short plan for households.")]]
    agent = ActionPlannerAgent(s, model=ScriptedModel(turns))
    plan = agent.run(risk, HOUSEHOLD, weather())
    general = [i for i in plan.items if i.kind == "general_educational"]
    assert [g.text for g in general] == ["Keep a wet cloth handy."]
    assert [t.status for t in agent.last_trace] == ["success", "error", "error"]


def test_revision_notes_reach_the_model(settings):
    class Capture(ScriptedModel):
        first_messages = None

        async def stream(self, messages, *a, **k):
            if self.first_messages is None:
                self.first_messages = json.dumps(messages, default=str)
            async for event in super().stream(messages, *a, **k):
                yield event

    risk = risk_for(HOUSEHOLD)
    agent, model = make_agent(settings, [[intro("A short plan for households.")]], cls=Capture)
    plan = agent.run(risk, HOUSEHOLD, weather(), revision_notes=["The plan intro names a medicine."], revision=1)
    assert plan.revision == 1
    assert "The plan intro names a medicine." in agent.last_prompt
    assert "The plan intro names a medicine." in model.first_messages


def test_unknown_risk_skips_without_model_calls(settings):
    agent, model = make_agent(settings, [])
    risk = classify(make_weather(None, None, current=False, forecast=False), HOUSEHOLD, 2)
    plan = agent.run(risk, HOUSEHOLD, None)
    assert plan.status == "skipped" and plan.items == [] and plan.risk_category == "unknown"
    assert model.calls == []


def test_unapproved_tool_blocked_and_as_tool(settings):
    risk = risk_for(HOUSEHOLD)
    turns = [[tool_call("send_alert", to="+910000000000", body="heat")], [text("Done.")]]
    agent, _ = make_agent(settings, turns)
    agent.run(risk, HOUSEHOLD, weather())
    assert agent.last_blocked and agent.last_blocked[0]["tool"] == "send_alert"

    agent2, _ = make_agent(settings, full_script(risk.category, ("household",)))
    planner_tool = agent2.as_tool()
    assert planner_tool.tool_name == "action_planner"
    payload = json.loads(planner_tool(risk_json=risk.model_dump_json(), profile_json=HOUSEHOLD.model_dump_json(),
                                      weather_json=weather().model_dump_json()))
    assert payload["status"] == "ok" and payload["items"]
