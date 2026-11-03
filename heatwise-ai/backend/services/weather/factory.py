"""Build the configured weather provider. There is deliberately no fallback chain."""

from __future__ import annotations

from backend.config import Settings
from backend.services.weather.base import WeatherProvider
from backend.services.weather.demo import DemoWeatherProvider
from backend.services.weather.open_meteo import OpenMeteoProvider


def build_weather_provider(settings: Settings) -> WeatherProvider:
    if settings.weather_provider == "open_meteo":
        return OpenMeteoProvider(
            timeout_seconds=settings.http_timeout_seconds,
            stale_after_minutes=settings.weather_stale_after_minutes,
            country_code=settings.geocode_country_code or None,
        )
    if settings.weather_provider == "demo":
        return DemoWeatherProvider()
    raise ValueError(f"Unknown WEATHER_PROVIDER: {settings.weather_provider!r}")
