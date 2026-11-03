"""Shared fixtures. Offline tests never touch the network or AWS."""

from __future__ import annotations

import pytest

from backend.config import Settings


@pytest.fixture(autouse=True)
def _isolate_settings_env(request: pytest.FixtureRequest, monkeypatch: pytest.MonkeyPatch) -> None:
    # Keep shell variables (e.g. AGENT_MODE=offline left over from a demo run) out of offline tests.
    if request.node.get_closest_marker("live") is None:
        for name in Settings.model_fields:
            monkeypatch.delenv(name.upper(), raising=False)
        # Session files go to the test's tmp dir, never heatwise-ai/.data/sessions.
        monkeypatch.setenv("SESSION_DIR", str(request.getfixturevalue("tmp_path") / "sessions"))


@pytest.fixture
def settings() -> Settings:
    # _env_file=None keeps a developer's local .env out of the tests.
    return Settings(_env_file=None, weather_provider="open_meteo", agent_max_tool_calls=6, agent_max_turns=8)


GEOCODE_NAGPUR = {
    "results": [
        {"id": 1262180, "name": "Nagpur", "latitude": 21.14631, "longitude": 79.08491, "country_code": "IN",
         "timezone": "Asia/Kolkata", "country": "India", "admin1": "Maharashtra", "admin2": "Nagpur"},
        {"id": 1262178, "name": "Nāgpur", "latitude": 29.65644, "longitude": 75.42146, "country_code": "IN",
         "timezone": "Asia/Kolkata", "country": "India", "admin1": "Haryana"},
    ]
}


def forecast_current_payload(time: str = "2026-11-02T13:45") -> dict:
    """Shape copied from a real Open-Meteo response (2026-11-02, Nagpur)."""
    return {
        "latitude": 21.124779, "longitude": 79.11585, "utc_offset_seconds": 19800, "timezone": "Asia/Kolkata",
        "current": {"time": time, "interval": 900, "temperature_2m": 31.2, "relative_humidity_2m": 42,
                    "apparent_temperature": 33.0, "wind_speed_10m": 8.6, "precipitation": 0.0},
    }


def forecast_daily_payload() -> dict:
    return {
        "latitude": 21.124779, "longitude": 79.11585, "utc_offset_seconds": 19800, "timezone": "Asia/Kolkata",
        "daily": {"time": ["2026-11-02", "2026-11-03", "2026-11-04"],
                  "temperature_2m_max": [31.2, 32.0, 31.7], "temperature_2m_min": [22.0, 22.8, 22.8],
                  "apparent_temperature_max": [33.3, 33.7, 33.3], "precipitation_sum": [0.0, 0.0, 0.0],
                  "uv_index_max": [6.7, 6.5, 6.65], "relative_humidity_2m_max": [77, 76, 69]},
    }
