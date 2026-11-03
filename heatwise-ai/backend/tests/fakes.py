"""In-memory provider for tool and agent tests."""

from __future__ import annotations

from datetime import date, datetime, timedelta, timezone

from backend.models.weather import (
    AlertsResult,
    CurrentConditions,
    DailyForecast,
    DataProvenance,
    ForecastResult,
    ResolvedLocation,
    WeatherIntelligenceResult,
)
from backend.services.weather.base import LocationNotFoundError, WeatherError, WeatherProvider

NOW = datetime(2026, 5, 10, 9, 0, tzinfo=timezone.utc)


def _prov(stale: bool = False) -> DataProvenance:
    return DataProvenance(provider="FakeProvider", source_url="https://fake.example/api", retrieved_at=NOW,
                          observed_at=NOW - timedelta(minutes=10), data_mode="live", is_stale=stale)


class FakeProvider(WeatherProvider):
    name = "FakeProvider"

    def __init__(self, fail: dict[str, WeatherError] | None = None, stale: bool = False,
                 known: tuple[str, ...] = ("wardha",)) -> None:
        self.fail = fail or {}
        self.stale = stale
        self.known = known
        self.calls: list[str] = []

    def geocode(self, query: str) -> ResolvedLocation:
        self.calls.append(f"geocode:{query}")
        if "geocode" in self.fail:
            raise self.fail["geocode"]
        if query.split(",")[0].strip().lower() not in self.known:
            raise LocationNotFoundError(f"No place named '{query}'.")
        return ResolvedLocation(query=query, name="Wardha", admin1="Maharashtra", country="India",
                                country_code="IN", latitude=20.74, longitude=78.6, timezone="Asia/Kolkata")

    def current(self, location: ResolvedLocation) -> CurrentConditions:
        self.calls.append("current")
        if "current" in self.fail:
            raise self.fail["current"]
        return CurrentConditions(location=location, temperature_c=44.2, apparent_temperature_c=46.0,
                                 relative_humidity_pct=21.0, wind_speed_kmh=11.0, precipitation_mm=0.0,
                                 provenance=_prov(self.stale))

    def forecast(self, location: ResolvedLocation, days: int) -> ForecastResult:
        self.calls.append(f"forecast:{days}")
        if "forecast" in self.fail:
            raise self.fail["forecast"]
        out = [DailyForecast(date=date(2026, 5, 10) + timedelta(days=i), temperature_max_c=44.0 + i,
                             temperature_min_c=29.0, apparent_temperature_max_c=46.0 + i,
                             precipitation_sum_mm=0.0, uv_index_max=10.0, relative_humidity_max_pct=35.0)
               for i in range(days)]
        return ForecastResult(location=location, days=out, provenance=_prov())

    def alerts(self, location: ResolvedLocation) -> AlertsResult:
        self.calls.append("alerts")
        return AlertsResult(location=location, alerts_supported=False, explanation="Fake has no alerts.",
                            provenance=_prov())


WARDHA = ResolvedLocation(query="Wardha", name="Wardha", admin1="Maharashtra", country="India",
                          country_code="IN", latitude=20.74, longitude=78.6, timezone="Asia/Kolkata")


def make_weather(temp_c: float | None, rh: float | None, fc_max: list[float] | None = None,
                 stale: bool = False, current: bool = True, forecast: bool = True,
                 data_mode: str = "live", apparent_c: float | None = None) -> WeatherIntelligenceResult:
    """A WeatherIntelligenceResult built from FakeProvider-shaped objects, for risk tests."""
    prov = _prov(stale).model_copy(update={"data_mode": data_mode})
    cur = None
    if current:
        cur = CurrentConditions(location=WARDHA, temperature_c=temp_c, apparent_temperature_c=apparent_c,
                                relative_humidity_pct=rh, provenance=prov)
    fc = None
    if forecast:
        days = [DailyForecast(date=date(2026, 5, 10) + timedelta(days=i), temperature_max_c=v)
                for i, v in enumerate(fc_max or [])]
        fc = ForecastResult(location=WARDHA, days=days, provenance=prov.model_copy(update={"is_stale": False}))
    alerts = AlertsResult(location=WARDHA, alerts_supported=False, explanation="Fake has no alerts.",
                          provenance=prov)
    if cur is None and fc is None:
        return WeatherIntelligenceResult(status="no_data", query="Wardha",
                                         missing_information=["No weather data retrieved."])
    return WeatherIntelligenceResult(
        status="ok" if cur is not None and fc is not None else "partial", query="Wardha", location=WARDHA,
        current=cur, forecast=fc, alerts=alerts, summary="Test weather.", data_mode=data_mode,  # type: ignore[arg-type]
        sources=[prov.source_url], retrieved_at=NOW, is_stale=bool(cur is not None and stale),
    )
