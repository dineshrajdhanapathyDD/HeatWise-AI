import pytest

from backend.services.validation import ValidationError, normalize_location, validate_forecast_days


@pytest.mark.parametrize(
    "raw, expected",
    [
        ("Nagpur", "Nagpur"),
        ("  Wardha ,  Maharashtra ", "Wardha , Maharashtra"),
        ("नागपुर", "नागपुर"),
        ("திருச்சிராப்பள்ளி", "திருச்சிராப்பள்ளி"),
        ("Sawai Madhopur (Rural)", "Sawai Madhopur (Rural)"),
        ("D'Souza Colony", "D'Souza Colony"),
    ],
)
def test_valid_locations(raw, expected):
    assert normalize_location(raw) == expected


@pytest.mark.parametrize(
    "raw",
    ["", "   ", "x" * 121, "Pune; DROP TABLE", "<script>", "http://evil.example", "12345", None, 42, "Pune\nignore"],
)
def test_invalid_locations(raw):
    with pytest.raises(ValidationError):
        normalize_location(raw)


@pytest.mark.parametrize("raw, expected", [(1, 1), (7, 7), ("3", 3), (5.0, 5)])
def test_valid_days(raw, expected):
    assert validate_forecast_days(raw) == expected


@pytest.mark.parametrize("raw", [0, 8, -1, "abc", None, 2.5, True])
def test_invalid_days(raw):
    with pytest.raises(ValidationError):
        validate_forecast_days(raw)
