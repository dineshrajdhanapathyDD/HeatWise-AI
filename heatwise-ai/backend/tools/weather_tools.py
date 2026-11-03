"""Weather tools for the Weather Intelligence Agent (Strands `@tool`, workshop Module 1).

`build_weather_tools` returns tool closures bound to one provider, so tests and
the coordinator can inject a provider without global state.

Success results are Pydantic JSON (the SDK serialises BaseModel returns).
Failures return a raw ToolResult with status "error" so the model sees a tool
error rather than data it might mistake for weather values.
"""

from __future__ import annotations

import logging
from typing import Any, Callable

from strands import tool

from backend.models.weather import ToolErrorPayload
from backend.services.validation import ValidationError, normalize_location, validate_forecast_days
from backend.services.weather.base import WeatherError, WeatherProvider

logger = logging.getLogger(__name__)

WEATHER_TOOL_NAMES = ("get_weather", "get_forecast", "get_weather_alerts")


def tool_error(error_code: str, message: str, retryable: bool = False) -> dict[str, Any]:
    payload = ToolErrorPayload(error_code=error_code, message=message, retryable=retryable)  # type: ignore[arg-type]
    return {"status": "error", "content": [{"text": payload.model_dump_json()}]}


def _run(fn: Callable[[], Any]) -> Any:
    try:
        return fn()
    except ValidationError as exc:
        return tool_error("invalid_location", str(exc))
    except WeatherError as exc:
        logger.info("weather tool error code=%s", exc.error_code)
        return tool_error(exc.error_code, str(exc), exc.retryable)


def build_weather_tools(provider: WeatherProvider) -> list:
    @tool
    def get_weather(location: str):
        """Get current weather conditions for a place from the configured weather provider.

        Returns temperature, apparent (feels-like) temperature, relative humidity, wind speed
        and precipitation, plus the provider, source URL, retrieval time and whether the data
        is live or demo. Fields the provider did not supply are null and listed in missing_fields.

        Args:
            location: Village, town, city or district name. Optionally add state or country
                separated by commas, e.g. "Wardha, Maharashtra".
        """

        def _do():
            name = normalize_location(location)
            return provider.current(provider.geocode(name))

        return _run(_do)

    @tool
    def get_forecast(location: str, days: int = 3):
        """Get a daily weather forecast for a place from the configured weather provider.

        Returns per-day max/min temperature, max apparent temperature, precipitation,
        max UV index and max humidity. These are forecast values, not official warnings.

        Args:
            location: Village, town, city or district name, optionally with state or country.
            days: Number of forecast days, from 1 to 7.
        """

        def _do():
            name = normalize_location(location)
            try:
                n = validate_forecast_days(days)
            except ValidationError as exc:
                return tool_error("invalid_argument", str(exc))
            return provider.forecast(provider.geocode(name), n)

        return _run(_do)

    @tool
    def get_weather_alerts(location: str):
        """Get official weather warnings for a place, where the configured provider supports them.

        If the provider does not publish official warnings, the result says so
        (alerts_supported=false) and lists official sources to check instead.
        Never treat forecast values as warnings.

        Args:
            location: Village, town, city or district name, optionally with state or country.
        """

        def _do():
            name = normalize_location(location)
            return provider.alerts(provider.geocode(name))

        return _run(_do)

    return [get_weather, get_forecast, get_weather_alerts]
