"""Input validation shared by tools and hooks.

Location names may be in any script (e.g. Devanagari, Tamil), so validation works
on Unicode categories rather than an ASCII allowlist.
"""

from __future__ import annotations

import unicodedata

MAX_LOCATION_LENGTH = 120
MIN_FORECAST_DAYS = 1
MAX_FORECAST_DAYS = 7
_ALLOWED_PUNCTUATION = set(" ,.-'()")


class ValidationError(ValueError):
    """Raised when user or model supplied input fails validation."""


def normalize_location(raw: object) -> str:
    """Return a cleaned location string or raise ValidationError."""
    if not isinstance(raw, str):
        raise ValidationError("Location must be text.")
    if any(unicodedata.category(ch) == "Cc" for ch in raw):
        raise ValidationError("Location contains control characters such as line breaks.")
    cleaned = " ".join(raw.split())
    if not cleaned:
        raise ValidationError("Location is empty.")
    if len(cleaned) > MAX_LOCATION_LENGTH:
        raise ValidationError(f"Location is longer than {MAX_LOCATION_LENGTH} characters.")
    for ch in cleaned:
        if ch in _ALLOWED_PUNCTUATION:
            continue
        category = unicodedata.category(ch)
        if category[0] in ("L", "M", "N"):
            continue
        raise ValidationError(f"Location contains a disallowed character: {ch!r}.")
    if not any(unicodedata.category(ch)[0] == "L" for ch in cleaned):
        raise ValidationError("Location must contain at least one letter.")
    return cleaned


def validate_forecast_days(raw: object) -> int:
    """Return forecast days as int within range, or raise ValidationError."""
    if isinstance(raw, bool):
        raise ValidationError("Forecast days must be a whole number.")
    try:
        days = int(raw)  # type: ignore[arg-type]
    except (TypeError, ValueError) as exc:
        raise ValidationError("Forecast days must be a whole number.") from exc
    if isinstance(raw, float) and not raw.is_integer():
        raise ValidationError("Forecast days must be a whole number.")
    if not MIN_FORECAST_DAYS <= days <= MAX_FORECAST_DAYS:
        raise ValidationError(
            f"Forecast days must be between {MIN_FORECAST_DAYS} and {MAX_FORECAST_DAYS}."
        )
    return days
