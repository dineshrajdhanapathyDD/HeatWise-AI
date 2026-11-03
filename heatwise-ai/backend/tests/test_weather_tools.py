"""Weather tools called directly (the @tool decorator keeps the function callable)."""

from __future__ import annotations

import json

from backend.models.weather import AlertsResult, CurrentConditions, ForecastResult
from backend.services.weather.base import ProviderTimeoutError, ProviderUnavailableError
from backend.services.weather.demo import DemoWeatherProvider
from backend.tests.fakes import FakeProvider
from backend.tools.weather_tools import build_weather_tools


def tools_for(provider):
    get_weather, get_forecast, get_weather_alerts = build_weather_tools(provider)
    return get_weather, get_forecast, get_weather_alerts


def error_of(result) -> dict:
    assert result["status"] == "error"
    return json.loads(result["content"][0]["text"])


def test_tool_names_and_specs():
    tools = build_weather_tools(FakeProvider())
    names = [t.tool_name for t in tools]
    assert names == ["get_weather", "get_forecast", "get_weather_alerts"]
    spec = tools[1].tool_spec
    props = spec["inputSchema"]["json"]["properties"]
    assert set(props) == {"location", "days"}


def test_get_weather_success():
    get_weather, *_ = tools_for(FakeProvider())
    res = get_weather(location="Wardha")
    assert isinstance(res, CurrentConditions)
    assert res.temperature_c == 44.2 and res.provenance.provider == "FakeProvider"


def test_get_forecast_success_and_days():
    p = FakeProvider()
    _, get_forecast, _ = tools_for(p)
    res = get_forecast(location="Wardha", days=5)
    assert isinstance(res, ForecastResult) and len(res.days) == 5
    assert "forecast:5" in p.calls


def test_get_forecast_rejects_bad_days_without_calling_provider():
    p = FakeProvider()
    _, get_forecast, _ = tools_for(p)
    err = error_of(get_forecast(location="Wardha", days=30))
    assert err["error_code"] == "invalid_argument"
    assert not any(c.startswith("forecast") for c in p.calls)


def test_alerts_tool_reports_unsupported():
    *_, get_weather_alerts = tools_for(FakeProvider())
    res = get_weather_alerts(location="Wardha")
    assert isinstance(res, AlertsResult) and res.alerts_supported is False and res.alerts == []


def test_invalid_location_never_reaches_provider():
    p = FakeProvider()
    get_weather, *_ = tools_for(p)
    err = error_of(get_weather(location="<script>alert(1)</script>"))
    assert err["error_code"] == "invalid_location"
    assert p.calls == []


def test_unknown_location_is_not_found():
    get_weather, *_ = tools_for(FakeProvider())
    err = error_of(get_weather(location="Atlantis"))
    assert err["error_code"] == "location_not_found"


def test_timeout_is_reported_not_substituted():
    get_weather, *_ = tools_for(FakeProvider(fail={"current": ProviderTimeoutError("slow")}))
    err = error_of(get_weather(location="Wardha"))
    assert err["error_code"] == "provider_timeout" and err["retryable"] is True


def test_unavailable_is_reported():
    _, get_forecast, _ = tools_for(FakeProvider(fail={"forecast": ProviderUnavailableError("503")}))
    assert error_of(get_forecast(location="Wardha"))["error_code"] == "provider_unavailable"


def test_demo_provider_is_labelled():
    get_weather, get_forecast, _ = tools_for(DemoWeatherProvider())
    cur = get_weather(location="demo-hot-dry")
    fc = get_forecast(location="demo-hot-dry", days=3)
    assert cur.provenance.data_mode == "demo" and fc.provenance.data_mode == "demo"
    assert "DEMO" in fc.note


def test_demo_provider_rejects_real_place_names():
    get_weather, *_ = tools_for(DemoWeatherProvider())
    assert error_of(get_weather(location="Nagpur"))["error_code"] == "location_not_found"
