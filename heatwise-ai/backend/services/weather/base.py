"""Weather provider abstraction.

Providers fetch and map data. They never invent values, and they never fall back
to another provider. Callers decide how to report failures.
"""

from __future__ import annotations

from abc import ABC, abstractmethod
from datetime import datetime, timedelta, timezone

from backend.models.weather import AlertsResult, CurrentConditions, ForecastResult, ResolvedLocation


class WeatherError(Exception):
    error_code = "provider_unavailable"
    retryable = False


class InvalidLocationError(WeatherError):
    error_code = "invalid_location"


class InvalidArgumentError(WeatherError):
    error_code = "invalid_argument"


class LocationNotFoundError(WeatherError):
    error_code = "location_not_found"


class ProviderTimeoutError(WeatherError):
    error_code = "provider_timeout"
    retryable = True


class ProviderUnavailableError(WeatherError):
    error_code = "provider_unavailable"
    retryable = True


class ProviderDataError(WeatherError):
    """The provider answered, but the response could not be used."""

    error_code = "provider_data_error"


def utc_now() -> datetime:
    return datetime.now(timezone.utc)


def is_stale(observed_at: datetime | None, retrieved_at: datetime, stale_after_minutes: int) -> bool:
    """Data with no provider timestamp cannot be shown to be fresh, so it counts as stale."""
    if observed_at is None:
        return True
    return retrieved_at - observed_at > timedelta(minutes=stale_after_minutes)


class WeatherProvider(ABC):
    name: str
    supports_alerts: bool = False

    @abstractmethod
    def geocode(self, query: str) -> ResolvedLocation:
        """Resolve a place name to a location or raise LocationNotFoundError."""

    @abstractmethod
    def current(self, location: ResolvedLocation) -> CurrentConditions: ...

    @abstractmethod
    def forecast(self, location: ResolvedLocation, days: int) -> ForecastResult: ...

    @abstractmethod
    def alerts(self, location: ResolvedLocation) -> AlertsResult: ...
