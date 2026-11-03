"""Weather Intelligence Agent tests through the real Strands agent loop.

The LLM is replaced by ScriptedModel; tools, hooks and structured output are the
real SDK code paths.
"""

from __future__ import annotations

import json

from backend.agents.weather_agent import WeatherIntelligenceAgent, build_result
from backend.services.weather.base import ProviderTimeoutError
from backend.services.weather.demo import DemoWeatherProvider
from backend.tests.fakes import FakeProvider
from backend.tests.scripted_model import ScriptedModel, text, tool_call

ALL_TOOLS = [
    tool_call("get_weather", location="Wardha"),
    tool_call("get_forecast", location="Wardha", days=3),
    tool_call("get_weather_alerts", location="Wardha"),
]


def summary_call(**overrides):
    args = dict(location_name="Wardha", summary="Very hot and dry in Wardha.", claimed_temperature_c=44.2,
                claimed_apparent_temperature_c=46.0, claimed_humidity_pct=21.0,
                claimed_max_forecast_temperature_c=46.0)
    args.update(overrides)
    return tool_call("WeatherSummary", **args)


def make_agent(settings, turns, provider=None):
    model = ScriptedModel(turns)
    return WeatherIntelligenceAgent(settings, provider=provider or FakeProvider(), model=model), model


def test_happy_path_ledger_backed_result(settings):
    agent, model = make_agent(settings, [ALL_TOOLS, [summary_call()]])
    res = agent.run("Wardha", 3)

    assert res.status == "ok"
    assert res.current.temperature_c == 44.2
    assert len(res.forecast.days) == 3
    assert res.alerts.alerts_supported is False
    assert res.summary == "Very hot and dry in Wardha."
    assert res.data_mode == "live" and res.sources == ["https://fake.example/api"]
    assert res.consistency_issues == []
    # The SDK's default executor runs tools concurrently, so the trace is in completion order.
    assert sorted(res.tools_called) == ["get_forecast", "get_weather", "get_weather_alerts"]
    assert "Official warnings are not available from this provider." in res.missing_information
    # The SDK offered our three tools plus the structured output tool to the model.
    assert set(model.calls[0]["tool_names"]) >= {"get_weather", "get_forecast", "get_weather_alerts", "WeatherSummary"}
    # Trace has durations and redacted inputs.
    assert all(r.duration_ms is not None for r in agent.last_trace)
    weather_rec = next(r for r in agent.last_trace if r.tool == "get_weather")
    assert weather_rec.input_summary == {"location": "Wardha"}


def test_fabricated_numbers_are_replaced_by_tool_data(settings):
    agent, _ = make_agent(settings, [ALL_TOOLS, [summary_call(
        summary="Pleasant 30°C in Wardha with an official red heat warning.",
        claimed_temperature_c=30.0)]])
    res = agent.run("Wardha", 3)

    assert res.current.temperature_c == 44.2  # value from tool, not model
    fields = {i.field for i in res.consistency_issues}
    assert "temperature_c" in fields
    assert "red heat warning" not in res.summary  # model text discarded
    assert "44.2°C" in res.summary


def test_unsupported_free_text_claims_replace_summary(settings):
    # Structured claimed_* fields are correct, but the prose adds a sky claim and a °F value
    # no tool returned. The ledger wins: the deterministic summary is used.
    agent, _ = make_agent(settings, [ALL_TOOLS, [summary_call(
        summary="Wardha is 44.2°C under clear skies, about 120°F in the afternoon.")]])
    res = agent.run("Wardha", 3)

    problems = [i.message for i in res.consistency_issues if i.field == "summary_text"]
    assert any("clear skies" in p for p in problems)
    assert any("120°F" in p for p in problems)
    assert "clear skies" not in res.summary
    assert res.summary.startswith("Current conditions in Wardha: 44.2°C")


def test_phone_number_in_summary_replaces_summary(settings):
    agent, _ = make_agent(settings, [ALL_TOOLS, [summary_call(
        summary="Wardha is 44.2°C. If anyone collapses, call 108 for an ambulance.")]])
    res = agent.run("Wardha", 3)

    assert any("108" in i.message for i in res.consistency_issues if i.field == "summary_text")
    assert "108" not in res.summary
    assert res.summary.startswith("Current conditions in Wardha: 44.2°C")


def test_supported_free_text_with_forecast_fahrenheit_is_kept(settings):
    # 46°C forecast max is about 114.8°F, so "115°F" is a correct conversion.
    text_ok = "Wardha is 44.2°C with 21% humidity; highs reach 46°C (about 115°F). No official warnings are available."
    agent, _ = make_agent(settings, [ALL_TOOLS, [summary_call(summary=text_ok)]])
    res = agent.run("Wardha", 3)

    assert res.consistency_issues == []
    assert res.summary == text_ok


def test_claim_without_source_is_flagged(settings):
    # Model only fetched the forecast but claims a current humidity value.
    turns = [[tool_call("get_forecast", location="Wardha", days=3)],
             [summary_call(claimed_temperature_c=None, claimed_apparent_temperature_c=None, claimed_humidity_pct=55.0)]]
    agent, _ = make_agent(settings, turns)
    res = agent.run("Wardha", 3)
    assert res.status == "partial" and res.current is None
    issue = next(i for i in res.consistency_issues if i.field == "relative_humidity_pct")
    assert issue.actual is None


def test_provider_timeout_gives_no_measurements(settings):
    provider = FakeProvider(fail={"current": ProviderTimeoutError("slow"), "forecast": ProviderTimeoutError("slow")})
    agent, _ = make_agent(settings, [ALL_TOOLS, [summary_call(claimed_temperature_c=None)]], provider)
    res = agent.run("Wardha", 3)

    assert res.status == "error"
    assert res.current is None and res.forecast is None and res.summary is None
    assert {e.error_code for e in res.errors} == {"provider_timeout"}


def test_unknown_location_is_no_data(settings):
    turns = [[tool_call("get_weather", location="Atlantis")], [summary_call(location_name="Atlantis",
              claimed_temperature_c=None, claimed_apparent_temperature_c=None, claimed_humidity_pct=None,
              claimed_max_forecast_temperature_c=None)]]
    agent, _ = make_agent(settings, turns, FakeProvider())
    res = agent.run("Atlantis", 3)
    assert res.status == "no_data"
    assert res.errors[0].error_code == "location_not_found"


def test_guardrail_blocks_unapproved_tool(settings):
    turns = [[tool_call("send_emergency_sms", to="+910000000000", body="evacuate"), *ALL_TOOLS], [summary_call()]]
    agent, _ = make_agent(settings, turns)
    res = agent.run("Wardha", 3)

    blocked = [r for r in agent.last_trace if r.status == "cancelled"]
    assert [r.tool for r in blocked] == ["send_emergency_sms"]
    assert "not approved" in blocked[0].cancel_reason
    # Non-loggable inputs are redacted in the trace.
    assert blocked[0].input_summary == {"to": "<str>", "body": "<str>"}
    assert res.current is not None


def test_guardrail_blocks_invalid_model_input(settings):
    provider = FakeProvider()
    turns = [[tool_call("get_forecast", location="Wardha", days=40), *ALL_TOOLS], [summary_call()]]
    agent, _ = make_agent(settings, turns, provider)
    agent.run("Wardha", 3)
    assert agent.last_blocked[0]["tool"] == "get_forecast"
    assert "forecast:40" not in provider.calls


def test_tool_call_cap(settings):
    settings.agent_max_tool_calls = 2
    agent, _ = make_agent(settings, [ALL_TOOLS, [summary_call()]])
    res = agent.run("Wardha", 3)
    by_tool = {r.tool: r.status for r in agent.last_trace}
    # Calls are counted in start order, so the third requested tool is the one cancelled.
    assert by_tool == {"get_weather": "success", "get_forecast": "success", "get_weather_alerts": "cancelled"}
    assert res.alerts is None and res.status == "partial"


def test_evidence_for_other_location_is_ignored(settings):
    provider = FakeProvider(known=("wardha", "nagpur"))
    turns = [[tool_call("get_weather", location="Nagpur"), *ALL_TOOLS[1:]], [summary_call(claimed_temperature_c=None,
              claimed_apparent_temperature_c=None, claimed_humidity_pct=None)]]
    agent, _ = make_agent(settings, turns, provider)
    res = agent.run("Wardha", 3)
    assert res.current is None
    assert any("not 'Wardha'" in i.message for i in res.consistency_issues)


def test_invalid_user_input_skips_model(settings):
    agent, model = make_agent(settings, [])
    res = agent.run("   ", 3)
    assert res.status == "error" and res.errors[0].error_code == "invalid_location"
    assert model.calls == []
    res = agent.run("Wardha", 9)
    assert res.errors[0].error_code == "invalid_argument"


def test_model_failure_is_contained(settings):
    class Boom(ScriptedModel):
        async def stream(self, *a, **k):
            raise RuntimeError("bedrock down")
            yield  # noqa

    agent = WeatherIntelligenceAgent(settings, provider=FakeProvider(), model=Boom([]))
    res = agent.run("Wardha", 3)
    assert res.status == "no_data"
    assert any("Weather agent failed" in m for m in res.missing_information)


def test_missing_structured_output_uses_deterministic_summary(settings):
    # Model fetches data then only ever answers in prose; turn limit stops the loop.
    turns = [ALL_TOOLS] + [[text("It is hot.")]] * 20
    agent, _ = make_agent(settings, turns)
    res = agent.run("Wardha", 3)
    assert res.current.temperature_c == 44.2
    assert res.summary.startswith("Current conditions in Wardha")
    assert any("structured summary" in m or "Weather agent failed" in m for m in res.missing_information)


def test_invalid_structured_output_fails_fast(settings):
    # Regression from a live Nova run: the model kept sending a number for a string field
    # and retried until the turn limit. The attempt cap should stop it early.
    bad = tool_call("WeatherSummary", location_name="Wardha", summary=403.0)
    agent, model = make_agent(settings, [ALL_TOOLS] + [[bad]] * 20)
    res = agent.run("Wardha", 3)
    assert len(model.calls) <= 4  # tools turn + at most a couple of structured output attempts
    assert res.current.temperature_c == 44.2
    assert res.summary.startswith("Current conditions in Wardha")


def test_demo_mode_is_labelled(settings):
    turns = [[tool_call("get_weather", location="demo-hot-dry"),
              tool_call("get_forecast", location="demo-hot-dry", days=3),
              tool_call("get_weather_alerts", location="demo-hot-dry")],
             [summary_call(location_name="Demo Hot-Dry Town", claimed_temperature_c=44.0,
                           claimed_apparent_temperature_c=46.5, claimed_humidity_pct=18.0,
                           claimed_max_forecast_temperature_c=45.5, summary="Demo data: very hot.")]]
    agent, _ = make_agent(settings, turns, DemoWeatherProvider())
    res = agent.run("demo-hot-dry", 3)
    assert res.data_mode == "demo" and res.sources == ["demo://heatwise/fixtures"]


def test_stale_data_flagged(settings):
    agent, _ = make_agent(settings, [ALL_TOOLS, [summary_call()]], FakeProvider(stale=True))
    res = agent.run("Wardha", 3)
    assert res.is_stale is True
    assert any("freshness" in m for m in res.missing_information)


def test_as_tool_returns_json(settings):
    agent, _ = make_agent(settings, [ALL_TOOLS, [summary_call()]])
    weather_tool = agent.as_tool()
    assert weather_tool.tool_name == "weather_intelligence"
    payload = json.loads(weather_tool(location="Wardha", forecast_days=3))
    assert payload["status"] == "ok" and payload["current"]["temperature_c"] == 44.2


def test_build_result_with_no_records():
    res = build_result("Wardha", [], None, None)
    assert res.status == "no_data" and res.current is None
