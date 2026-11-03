"""Demo provider with fixed, clearly labelled fixture data.

Used only when WEATHER_PROVIDER=demo is set explicitly (offline demos, tests).
It is never used as a fallback for a failing live provider. Every result carries
data_mode="demo" and provider="HeatWise demo fixtures".
"""

from __future__ import annotations

from datetime import date, timedelta

from backend.models.weather import (
    AlertsResult,
    CurrentConditions,
    DailyForecast,
    DataProvenance,
    ForecastResult,
    ResolvedLocation,
)
from backend.services.weather.base import LocationNotFoundError, WeatherProvider, utc_now

PROVIDER_NAME = "HeatWise demo fixtures"
SOURCE_URL = "demo://heatwise/fixtures"

# Synthetic values for demonstration. They are not observations.
_FIXTURES: dict[str, dict] = {
    "demo-hot-dry": {
        "location": dict(name="Demo Hot-Dry Town", admin1="Demo State", country="Demo", country_code="XX",
                         latitude=21.0, longitude=79.0, timezone="Asia/Kolkata"),
        "current": dict(temperature_c=44.0, apparent_temperature_c=46.5, relative_humidity_pct=18.0,
                        wind_speed_kmh=12.0, precipitation_mm=0.0),
        "daily": [(45.0, 30.0, 47.0, 0.0, 10.5, 30.0), (45.5, 31.0, 47.5, 0.0, 10.8, 28.0),
                  (44.0, 30.5, 46.0, 0.0, 10.2, 32.0), (43.0, 29.0, 45.0, 0.0, 9.8, 35.0),
                  (42.0, 29.0, 44.0, 0.2, 9.5, 40.0), (41.0, 28.0, 43.0, 0.0, 9.0, 42.0),
                  (40.0, 27.5, 42.0, 0.0, 9.0, 45.0)],
    },
    "demo-humid-coast": {
        "location": dict(name="Demo Humid Coast", admin1="Demo State", country="Demo", country_code="XX",
                         latitude=13.0, longitude=80.2, timezone="Asia/Kolkata"),
        "current": dict(temperature_c=36.0, apparent_temperature_c=44.0, relative_humidity_pct=70.0,
                        wind_speed_kmh=9.0, precipitation_mm=0.0),
        "daily": [(37.0, 29.0, 45.0, 0.0, 11.0, 85.0), (37.5, 29.5, 46.0, 0.0, 11.2, 88.0),
                  (36.5, 29.0, 44.5, 2.0, 10.0, 90.0), (35.0, 28.0, 42.0, 5.0, 8.0, 92.0),
                  (34.5, 27.5, 41.0, 8.0, 7.0, 93.0), (35.0, 28.0, 42.0, 1.0, 9.0, 88.0),
                  (36.0, 28.5, 43.0, 0.0, 10.0, 86.0)],
    },
    "demo-mild": {
        "location": dict(name="Demo Mild Hills", admin1="Demo State", country="Demo", country_code="XX",
                         latitude=11.4, longitude=76.7, timezone="Asia/Kolkata"),
        "current": dict(temperature_c=24.0, apparent_temperature_c=24.5, relative_humidity_pct=60.0,
                        wind_speed_kmh=6.0, precipitation_mm=0.0),
        "daily": [(26.0, 15.0, 26.0, 1.0, 7.0, 80.0)] * 7,
    },
}

# The exact location keys demo geocoding accepts (shown by /api/health in demo mode).
DEMO_LOCATIONS: tuple[str, ...] = tuple(sorted(_FIXTURES))


class DemoWeatherProvider(WeatherProvider):
    name = PROVIDER_NAME
    supports_alerts = False

    def _fixture(self, location: ResolvedLocation) -> dict:
        key = location.query.strip().lower()
        if key not in _FIXTURES:
            raise LocationNotFoundError(f"Demo data has no location '{location.query}'.")
        return _FIXTURES[key]

    def _provenance(self) -> DataProvenance:
        now = utc_now()
        return DataProvenance(provider=PROVIDER_NAME, source_url=SOURCE_URL, retrieved_at=now,
                              observed_at=now, data_mode="demo", is_stale=False)

    def geocode(self, query: str) -> ResolvedLocation:
        key = query.strip().lower()
        if key not in _FIXTURES:
            raise LocationNotFoundError(
                f"Demo data has no location '{query}'. Available: {', '.join(sorted(_FIXTURES))}."
            )
        return ResolvedLocation(query=key, **_FIXTURES[key]["location"])

    def current(self, location: ResolvedLocation) -> CurrentConditions:
        fx = self._fixture(location)
        return CurrentConditions(location=location, **fx["current"], provenance=self._provenance())

    def forecast(self, location: ResolvedLocation, days: int) -> ForecastResult:
        fx = self._fixture(location)
        today = date.today()
        out = [
            DailyForecast(date=today + timedelta(days=i), temperature_max_c=d[0], temperature_min_c=d[1],
                          apparent_temperature_max_c=d[2], precipitation_sum_mm=d[3], uv_index_max=d[4],
                          relative_humidity_max_pct=d[5])
            for i, d in enumerate(fx["daily"][:days])
        ]
        return ForecastResult(location=location, days=out, provenance=self._provenance(),
                              note="DEMO forecast fixtures. Not real data and not official warnings.")

    def alerts(self, location: ResolvedLocation) -> AlertsResult:
        self._fixture(location)
        return AlertsResult(location=location, alerts_supported=False, alerts=[],
                            explanation="Demo mode has no official warnings. No alerts are generated.",
                            provenance=self._provenance())
