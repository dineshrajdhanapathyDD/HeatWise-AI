"""Weather provider that serves the synthetic evaluation fixtures (D-M5-1).

Used by both evaluation modes, so weather extraction has exact ground truth and no run
touches the network for weather. Every result is labelled `data_mode="demo"` with the
provider name `HeatWise evaluation fixtures (synthetic)`.
"""

from __future__ import annotations

from datetime import date, timedelta

from backend.evaluation.dataset import Scenario
from backend.models.weather import (
    AlertsResult,
    CurrentConditions,
    DailyForecast,
    DataProvenance,
    ForecastResult,
    ResolvedLocation,
)
from backend.services.weather.base import (
    LocationNotFoundError,
    ProviderTimeoutError,
    ProviderUnavailableError,
    WeatherError,
    WeatherProvider,
    is_stale,
    utc_now,
)

PROVIDER_NAME = "HeatWise evaluation fixtures (synthetic)"
SOURCE_URL = "synthetic://heatwise/evaluation"

_ERRORS: dict[str, type[WeatherError]] = {
    "provider_unavailable": ProviderUnavailableError,
    "provider_timeout": ProviderTimeoutError,
    "location_not_found": LocationNotFoundError,
}


def _key(text: str) -> str:
    return text.split(",")[0].strip().casefold()


def _raise(code: str | None, what: str) -> None:
    if code:
        raise _ERRORS[code](f"Synthetic {code.replace('_', ' ')} injected for {what}.")


class ScenarioWeatherProvider(WeatherProvider):
    name = PROVIDER_NAME
    supports_alerts = False

    def __init__(self, scenarios: list[Scenario], stale_after_minutes: int = 90) -> None:
        self._by_key = {_key(s.location): s for s in scenarios}
        self.stale_after_minutes = stale_after_minutes
        self.calls: list[str] = []

    def _scenario(self, location: ResolvedLocation) -> Scenario:
        s = self._by_key.get(_key(location.query))
        if s is None:
            raise LocationNotFoundError(f"No synthetic fixture for '{location.query}'.")
        return s

    def _provenance(self, minutes_ago: int | None) -> DataProvenance:
        now = utc_now()
        observed = now - timedelta(minutes=minutes_ago) if minutes_ago is not None else now
        stale = is_stale(observed, now, self.stale_after_minutes) if minutes_ago is not None else False
        return DataProvenance(provider=PROVIDER_NAME, source_url=SOURCE_URL, retrieved_at=now,
                              observed_at=observed, data_mode="demo", is_stale=stale)

    def geocode(self, query: str) -> ResolvedLocation:
        self.calls.append(f"geocode:{query}")
        s = self._by_key.get(_key(query))
        if s is None:
            raise LocationNotFoundError(f"No synthetic fixture for '{query}'.")
        _raise(s.weather.geocode_error, "geocoding")
        return ResolvedLocation(query=query, **s.weather.location.model_dump())

    def current(self, location: ResolvedLocation) -> CurrentConditions:
        self.calls.append("current")
        s = self._scenario(location)
        _raise(s.weather.current_error, "current conditions")
        if s.weather.current is None:
            raise ProviderUnavailableError("The synthetic fixture has no current conditions.")
        values = s.weather.current.model_dump()
        missing = [k for k, v in values.items() if v is None]
        return CurrentConditions(location=location, **values, missing_fields=missing,
                                 provenance=self._provenance(s.weather.observed_minutes_ago))

    def forecast(self, location: ResolvedLocation, days: int) -> ForecastResult:
        self.calls.append(f"forecast:{days}")
        s = self._scenario(location)
        _raise(s.weather.forecast_error, "the forecast")
        if s.weather.forecast_days is None:
            raise ProviderUnavailableError("The synthetic fixture has no forecast.")
        today = date.today()
        out = []
        for i, d in enumerate(s.weather.forecast_days[:days]):
            values = d.model_dump()
            out.append(DailyForecast(date=today + timedelta(days=i), **values,
                                     missing_fields=[k for k, v in values.items() if v is None]))
        return ForecastResult(location=location, days=out, provenance=self._provenance(None),
                              note="Synthetic evaluation forecast fixtures. Not real data and not official warnings.")

    def alerts(self, location: ResolvedLocation) -> AlertsResult:
        self.calls.append("alerts")
        self._scenario(location)
        return AlertsResult(location=location, alerts_supported=False, alerts=[],
                            explanation="Synthetic evaluation fixtures have no official warnings. "
                                        "No alerts are generated.",
                            provenance=self._provenance(None))
