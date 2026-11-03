"""Open-Meteo provider tests with mocked HTTP (respx). No network access."""

from __future__ import annotations

from datetime import datetime, timezone

import httpx
import pytest
import respx

from backend.services.weather import open_meteo
from backend.services.weather.base import (
    LocationNotFoundError,
    ProviderDataError,
    ProviderTimeoutError,
    ProviderUnavailableError,
)
from backend.services.weather.open_meteo import FORECAST_URL, GEOCODING_URL, OpenMeteoProvider
from backend.tests.conftest import GEOCODE_NAGPUR, forecast_current_payload, forecast_daily_payload

FIXED_NOW = datetime(2026, 11, 2, 8, 30, tzinfo=timezone.utc)  # 15 min after 13:45 IST


@pytest.fixture
def provider(monkeypatch) -> OpenMeteoProvider:
    monkeypatch.setattr(open_meteo, "utc_now", lambda: FIXED_NOW)
    return OpenMeteoProvider(timeout_seconds=2, stale_after_minutes=90)


@respx.mock
def test_geocode_picks_first_result(provider):
    respx.get(GEOCODING_URL).mock(return_value=httpx.Response(200, json=GEOCODE_NAGPUR))
    loc = provider.geocode("Nagpur")
    assert loc.name == "Nagpur" and loc.admin1 == "Maharashtra"
    assert loc.latitude == pytest.approx(21.14631)


@respx.mock
def test_geocode_uses_qualifiers_to_disambiguate(provider):
    route = respx.get(GEOCODING_URL).mock(return_value=httpx.Response(200, json=GEOCODE_NAGPUR))
    loc = provider.geocode("Nagpur, Haryana")
    assert loc.admin1 == "Haryana"
    assert route.calls.last.request.url.params["name"] == "Nagpur"


@respx.mock
def test_geocode_unmatched_qualifier_is_not_found(provider):
    respx.get(GEOCODING_URL).mock(return_value=httpx.Response(200, json=GEOCODE_NAGPUR))
    with pytest.raises(LocationNotFoundError):
        provider.geocode("Nagpur, Kerala")


@respx.mock
def test_geocode_no_results_is_not_found(provider):
    # Open-Meteo omits "results" when nothing matches.
    respx.get(GEOCODING_URL).mock(return_value=httpx.Response(200, json={"generationtime_ms": 0.5}))
    with pytest.raises(LocationNotFoundError):
        provider.geocode("Zzqxville")


@respx.mock
def test_geocode_country_filter_is_sent():
    route = respx.get(GEOCODING_URL).mock(return_value=httpx.Response(200, json=GEOCODE_NAGPUR))
    OpenMeteoProvider(country_code="IN").geocode("Nagpur")
    assert route.calls.last.request.url.params["countryCode"] == "IN"


@respx.mock
def test_current_maps_fields_and_provenance(provider):
    respx.get(GEOCODING_URL).mock(return_value=httpx.Response(200, json=GEOCODE_NAGPUR))
    respx.get(FORECAST_URL).mock(return_value=httpx.Response(200, json=forecast_current_payload()))
    cur = provider.current(provider.geocode("Nagpur"))
    assert cur.temperature_c == 31.2
    assert cur.apparent_temperature_c == 33.0
    assert cur.relative_humidity_pct == 42
    assert cur.missing_fields == []
    p = cur.provenance
    assert p.provider == "Open-Meteo" and p.data_mode == "live"
    assert p.observed_at == datetime(2026, 11, 2, 8, 15, tzinfo=timezone.utc)
    assert p.retrieved_at == FIXED_NOW
    assert p.is_stale is False
    assert p.source_url.startswith(FORECAST_URL)


@respx.mock
def test_current_old_observation_is_stale(provider):
    respx.get(GEOCODING_URL).mock(return_value=httpx.Response(200, json=GEOCODE_NAGPUR))
    respx.get(FORECAST_URL).mock(return_value=httpx.Response(200, json=forecast_current_payload("2026-11-02T08:00")))
    cur = provider.current(provider.geocode("Nagpur"))
    assert cur.provenance.is_stale is True


@respx.mock
def test_current_missing_fields_are_null_not_estimated(provider):
    payload = forecast_current_payload()
    del payload["current"]["relative_humidity_2m"]
    payload["current"]["apparent_temperature"] = None
    respx.get(GEOCODING_URL).mock(return_value=httpx.Response(200, json=GEOCODE_NAGPUR))
    respx.get(FORECAST_URL).mock(return_value=httpx.Response(200, json=payload))
    cur = provider.current(provider.geocode("Nagpur"))
    assert cur.relative_humidity_pct is None and cur.apparent_temperature_c is None
    assert set(cur.missing_fields) == {"relative_humidity_pct", "apparent_temperature_c"}


@respx.mock
def test_current_without_block_is_data_error(provider):
    respx.get(GEOCODING_URL).mock(return_value=httpx.Response(200, json=GEOCODE_NAGPUR))
    respx.get(FORECAST_URL).mock(return_value=httpx.Response(200, json={"latitude": 1}))
    with pytest.raises(ProviderDataError):
        provider.current(provider.geocode("Nagpur"))


@respx.mock
def test_forecast_maps_days(provider):
    respx.get(GEOCODING_URL).mock(return_value=httpx.Response(200, json=GEOCODE_NAGPUR))
    route = respx.get(FORECAST_URL).mock(return_value=httpx.Response(200, json=forecast_daily_payload()))
    fc = provider.forecast(provider.geocode("Nagpur"), 3)
    assert len(fc.days) == 3
    assert fc.days[1].temperature_max_c == 32.0
    assert fc.days[2].uv_index_max == 6.65
    assert fc.kind == "forecast" and "not official warnings" in fc.note
    assert route.calls.last.request.url.params["forecast_days"] == "3"


def test_alerts_are_not_invented(provider):
    from backend.models.weather import ResolvedLocation

    loc = ResolvedLocation(query="Nagpur", name="Nagpur", country_code="IN", latitude=21.1, longitude=79.1)
    res = provider.alerts(loc)
    assert res.alerts_supported is False and res.alerts == []
    assert "https://mausam.imd.gov.in/" in res.official_sources


@respx.mock
def test_timeout_maps_to_provider_timeout(provider):
    respx.get(GEOCODING_URL).mock(side_effect=httpx.ReadTimeout("slow"))
    with pytest.raises(ProviderTimeoutError):
        provider.geocode("Nagpur")


@respx.mock
def test_server_error_maps_to_unavailable(provider):
    respx.get(GEOCODING_URL).mock(return_value=httpx.Response(503))
    with pytest.raises(ProviderUnavailableError):
        provider.geocode("Nagpur")


@respx.mock
def test_connect_error_retries_once_then_unavailable(provider):
    route = respx.get(GEOCODING_URL).mock(side_effect=httpx.ConnectError("down"))
    with pytest.raises(ProviderUnavailableError):
        provider.geocode("Nagpur")
    assert route.call_count == 2


@respx.mock
def test_bad_request_is_data_error(provider):
    respx.get(FORECAST_URL).mock(
        return_value=httpx.Response(400, json={"error": True, "reason": "Latitude must be in range"})
    )
    from backend.models.weather import ResolvedLocation

    with pytest.raises(ProviderDataError, match="Latitude"):
        provider.current(ResolvedLocation(query="x", name="x", latitude=999, longitude=0))
