"""Live tests against real services. Opt-in:  pytest -m live

- Open-Meteo: no credentials needed.
- Bedrock: needs AWS credentials with bedrock:InvokeModel on BEDROCK_MODEL_ID.
"""

from __future__ import annotations

import pytest

from backend.agents.coordinator import HeatWiseCoordinator
from backend.agents.weather_agent import WeatherIntelligenceAgent
from backend.config import Settings
from backend.models.risk import CommunityProfile
from backend.models.weather import CurrentConditions, ForecastResult
from backend.services.weather.open_meteo import OpenMeteoProvider
from backend.tools.weather_tools import build_weather_tools

pytestmark = pytest.mark.live


def test_open_meteo_live_tools():
    get_weather, get_forecast, get_weather_alerts = build_weather_tools(OpenMeteoProvider(timeout_seconds=15))
    cur = get_weather(location="Nagpur, Maharashtra")
    assert isinstance(cur, CurrentConditions), cur
    assert cur.location.admin1 == "Maharashtra"
    assert cur.temperature_c is not None and -10 < cur.temperature_c < 55
    assert cur.provenance.data_mode == "live" and cur.provenance.observed_at is not None
    fc = get_forecast(location="Nagpur, Maharashtra", days=3)
    assert isinstance(fc, ForecastResult) and len(fc.days) == 3
    assert get_weather_alerts(location="Nagpur, Maharashtra").alerts_supported is False


def test_open_meteo_live_unknown_place():
    get_weather, *_ = build_weather_tools(OpenMeteoProvider(timeout_seconds=15))
    res = get_weather(location="Qwxzvillezzq")
    assert res["status"] == "error" and "location_not_found" in res["content"][0]["text"]


def test_bedrock_weather_agent_end_to_end():
    settings = Settings(weather_provider="open_meteo")
    agent = WeatherIntelligenceAgent(settings)
    res = agent.run("Nagpur, Maharashtra", 3)
    assert res.status in ("ok", "partial"), res.model_dump_json(indent=2)
    assert res.current is not None and res.current.provenance.provider == "Open-Meteo"
    assert res.summary
    assert "get_weather" in res.tools_called
    print(res.model_dump_json(indent=2))
    print("consistency issues:", res.consistency_issues)


def test_bedrock_coordinator_end_to_end():
    settings = Settings(weather_provider="open_meteo")
    profile = CommunityProfile(elderly=True, outdoor_workers=True, farmers=True)
    report = HeatWiseCoordinator(settings).run("Nagpur, Maharashtra", profile, 3)
    assert report.status in ("complete", "needs_human_review"), report.model_dump_json(indent=2)
    assert report.risk_category != "unknown"
    assert report.verification_status in ("passed", "failed")
    assert report.recommended_actions is not None and report.checklist_markdown
    assert report.weather_source.provider == "Open-Meteo"
    print(report.model_dump_json(indent=2))
    print("steering blocks:", report.steering_blocks)
    print("fallback trace:", [t.tool for t in report.trace if t.agent == "coordinator_fallback"])
