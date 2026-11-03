"""Open-Meteo provider (https://open-meteo.com/en/docs).

Uses the documented forecast and geocoding endpoints, which need no API key.
Open-Meteo values are numerical weather model data, not station observations, and
Open-Meteo does not publish official government warnings. Both facts are surfaced
in the results instead of being hidden.
"""

from __future__ import annotations

import logging
from datetime import date, datetime, timedelta, timezone
from typing import Any

import httpx

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
    ProviderDataError,
    ProviderTimeoutError,
    ProviderUnavailableError,
    WeatherProvider,
    is_stale,
    utc_now,
)

logger = logging.getLogger(__name__)

GEOCODING_URL = "https://geocoding-api.open-meteo.com/v1/search"
FORECAST_URL = "https://api.open-meteo.com/v1/forecast"
PROVIDER_NAME = "Open-Meteo"
IMD_HOME = "https://mausam.imd.gov.in/"

_CURRENT_FIELDS = {
    "temperature_2m": "temperature_c",
    "apparent_temperature": "apparent_temperature_c",
    "relative_humidity_2m": "relative_humidity_pct",
    "wind_speed_10m": "wind_speed_kmh",
    "precipitation": "precipitation_mm",
}
_DAILY_FIELDS = {
    "temperature_2m_max": "temperature_max_c",
    "temperature_2m_min": "temperature_min_c",
    "apparent_temperature_max": "apparent_temperature_max_c",
    "precipitation_sum": "precipitation_sum_mm",
    "uv_index_max": "uv_index_max",
    "relative_humidity_2m_max": "relative_humidity_max_pct",
}


class OpenMeteoProvider(WeatherProvider):
    name = PROVIDER_NAME
    supports_alerts = False

    def __init__(
        self,
        timeout_seconds: float = 10.0,
        stale_after_minutes: int = 90,
        country_code: str | None = None,
        client: httpx.Client | None = None,
    ) -> None:
        self._timeout = timeout_seconds
        self._stale_after = stale_after_minutes
        self._country_code = country_code
        self._client = client or httpx.Client(timeout=timeout_seconds)

    # ------------------------------------------------------------------ HTTP

    def _get(self, url: str, params: dict[str, Any]) -> tuple[dict[str, Any], str]:
        """GET JSON. Retries once on connection errors only. Returns (json, final_url)."""
        last_exc: Exception | None = None
        for attempt in range(2):
            try:
                response = self._client.get(url, params=params, timeout=self._timeout)
            except httpx.TimeoutException as exc:
                raise ProviderTimeoutError(f"{PROVIDER_NAME} did not respond within {self._timeout}s.") from exc
            except httpx.TransportError as exc:
                last_exc = exc
                logger.warning("open_meteo transport error attempt=%d: %s", attempt + 1, type(exc).__name__)
                continue
            if response.status_code >= 500:
                raise ProviderUnavailableError(f"{PROVIDER_NAME} returned HTTP {response.status_code}.")
            if response.status_code >= 400:
                reason = _safe_reason(response)
                raise ProviderDataError(f"{PROVIDER_NAME} rejected the request (HTTP {response.status_code}): {reason}")
            try:
                payload = response.json()
            except ValueError as exc:
                raise ProviderDataError(f"{PROVIDER_NAME} returned a non-JSON response.") from exc
            if not isinstance(payload, dict):
                raise ProviderDataError(f"{PROVIDER_NAME} returned an unexpected response shape.")
            return payload, str(response.request.url)
        raise ProviderUnavailableError(f"Could not connect to {PROVIDER_NAME}.") from last_exc

    # ------------------------------------------------------------- geocoding

    def geocode(self, query: str) -> ResolvedLocation:
        # Open-Meteo searches by place name only, so "Village, District, State" is
        # split: search the first part, then prefer results matching the rest.
        parts = [p.strip() for p in query.split(",") if p.strip()]
        if not parts:
            raise LocationNotFoundError("No location name supplied.")
        params: dict[str, Any] = {"name": parts[0], "count": 10, "language": "en", "format": "json"}
        if self._country_code:
            params["countryCode"] = self._country_code
        payload, _ = self._get(GEOCODING_URL, params)
        results = payload.get("results") or []
        if not results:
            raise LocationNotFoundError(f"No place named '{parts[0]}' was found by {PROVIDER_NAME} geocoding.")

        qualifiers = [p.lower() for p in parts[1:]]
        chosen = None
        if qualifiers:
            for r in results:
                haystack = " ".join(
                    str(r.get(k, "")) for k in ("admin1", "admin2", "admin3", "country", "country_code")
                ).lower()
                if all(q in haystack for q in qualifiers):
                    chosen = r
                    break
            if chosen is None:
                raise LocationNotFoundError(
                    f"Found places named '{parts[0]}', but none matched '{', '.join(parts[1:])}'."
                )
        else:
            chosen = results[0]

        try:
            return ResolvedLocation(
                query=query,
                name=chosen["name"],
                admin1=chosen.get("admin1"),
                admin2=chosen.get("admin2"),
                country=chosen.get("country"),
                country_code=chosen.get("country_code"),
                latitude=float(chosen["latitude"]),
                longitude=float(chosen["longitude"]),
                timezone=chosen.get("timezone"),
            )
        except (KeyError, TypeError, ValueError) as exc:
            raise ProviderDataError("Geocoding result was missing name or coordinates.") from exc

    # -------------------------------------------------------------- current

    def current(self, location: ResolvedLocation) -> CurrentConditions:
        params = {
            "latitude": location.latitude,
            "longitude": location.longitude,
            "current": ",".join(_CURRENT_FIELDS),
            "timezone": "auto",
        }
        payload, url = self._get(FORECAST_URL, params)
        retrieved_at = utc_now()
        current = payload.get("current")
        if not isinstance(current, dict):
            raise ProviderDataError(f"{PROVIDER_NAME} response had no current conditions block.")

        values: dict[str, float | None] = {}
        missing: list[str] = []
        for src, dst in _CURRENT_FIELDS.items():
            v = _as_float(current.get(src))
            values[dst] = v
            if v is None:
                missing.append(dst)

        observed_at = _parse_local_time(current.get("time"), payload.get("utc_offset_seconds"))
        if observed_at is None:
            missing.append("observed_at")
        return CurrentConditions(
            location=location,
            **values,
            missing_fields=missing,
            provenance=DataProvenance(
                provider=PROVIDER_NAME,
                source_url=url,
                retrieved_at=retrieved_at,
                observed_at=observed_at,
                data_mode="live",
                is_stale=is_stale(observed_at, retrieved_at, self._stale_after),
            ),
        )

    # ------------------------------------------------------------- forecast

    def forecast(self, location: ResolvedLocation, days: int) -> ForecastResult:
        params = {
            "latitude": location.latitude,
            "longitude": location.longitude,
            "daily": ",".join(_DAILY_FIELDS),
            "timezone": "auto",
            "forecast_days": days,
        }
        payload, url = self._get(FORECAST_URL, params)
        retrieved_at = utc_now()
        daily = payload.get("daily")
        if not isinstance(daily, dict) or not isinstance(daily.get("time"), list) or not daily["time"]:
            raise ProviderDataError(f"{PROVIDER_NAME} response had no daily forecast.")

        out: list[DailyForecast] = []
        for i, day_str in enumerate(daily["time"]):
            try:
                day = date.fromisoformat(day_str)
            except (TypeError, ValueError) as exc:
                raise ProviderDataError(f"Invalid forecast date: {day_str!r}") from exc
            values: dict[str, float | None] = {}
            missing: list[str] = []
            for src, dst in _DAILY_FIELDS.items():
                series = daily.get(src)
                v = _as_float(series[i]) if isinstance(series, list) and i < len(series) else None
                values[dst] = v
                if v is None:
                    missing.append(dst)
            out.append(DailyForecast(date=day, **values, missing_fields=missing))

        return ForecastResult(
            location=location,
            days=out,
            provenance=DataProvenance(
                provider=PROVIDER_NAME,
                source_url=url,
                retrieved_at=retrieved_at,
                observed_at=None,
                data_mode="live",
                is_stale=False,  # forecasts are generated on request; freshness applies to observations
            ),
        )

    # --------------------------------------------------------------- alerts

    def alerts(self, location: ResolvedLocation) -> AlertsResult:
        return AlertsResult(
            location=location,
            alerts_supported=False,
            alerts=[],
            explanation=(
                f"{PROVIDER_NAME} does not publish official government weather warnings. "
                "No alerts are shown. Check the national meteorological service for official heatwave warnings."
            ),
            official_sources=[IMD_HOME] if (location.country_code or "").upper() == "IN" else [],
            provenance=DataProvenance(
                provider=PROVIDER_NAME,
                source_url="https://open-meteo.com/en/docs",
                retrieved_at=utc_now(),
                data_mode="live",
            ),
        )


def _as_float(value: Any) -> float | None:
    if value is None or isinstance(value, bool):
        return None
    try:
        return float(value)
    except (TypeError, ValueError):
        return None


def _parse_local_time(value: Any, utc_offset_seconds: Any) -> datetime | None:
    """Open-Meteo returns local ISO times plus the UTC offset when timezone=auto."""
    if not isinstance(value, str):
        return None
    try:
        local = datetime.fromisoformat(value)
        offset = int(utc_offset_seconds or 0)
    except (TypeError, ValueError):
        return None
    if local.tzinfo is not None:
        return local.astimezone(timezone.utc)
    return local.replace(tzinfo=timezone(timedelta(seconds=offset))).astimezone(timezone.utc)


def _safe_reason(response: httpx.Response) -> str:
    try:
        body = response.json()
        if isinstance(body, dict) and isinstance(body.get("reason"), str):
            return body["reason"][:200]
    except ValueError:
        pass
    return "no reason given"
