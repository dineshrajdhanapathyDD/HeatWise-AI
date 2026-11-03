"""Deterministic risk rule tests. Expected heat index values come from the formula, not by hand."""

from __future__ import annotations

import re
from pathlib import Path

import pytest

from backend.guidance.sources import TRUSTED_SOURCES
from backend.models.risk import CommunityProfile
from backend.services import risk_rules
from backend.services.risk_rules import c_to_f, classify, f_to_c, heat_index_f, imd_indication, nws_band
from backend.tests.fakes import make_weather

PLAINS = CommunityProfile(terrain="plains")
VULNERABLE = CommunityProfile(terrain="plains", elderly=True, outdoor_workers=True)


def test_nws_chart_anchors():
    # https://www.weather.gov/ama/heatindex: 100°F/55% -> 124°F, 100°F/15% -> 96°F, error ±1.3°F.
    assert heat_index_f(100, 55) == pytest.approx(124, abs=1.3)
    assert heat_index_f(100, 15) == pytest.approx(96, abs=1.3)


def test_simple_formula_below_80f():
    t, rh = 70.0, 40.0
    simple = 0.5 * (t + 61.0 + (t - 68.0) * 1.2 + rh * 0.094)
    assert heat_index_f(t, rh) == pytest.approx((simple + t) / 2)


def test_low_humidity_adjustment_lowers_value():
    t, rh = 100.0, 10.0
    unadjusted = (-42.379 + 2.04901523 * t + 10.14333127 * rh - 0.22475541 * t * rh - 0.00683783 * t * t
                  - 0.05481717 * rh * rh + 0.00122874 * t * t * rh + 0.00085282 * t * rh * rh
                  - 0.00000199 * t * t * rh * rh)
    assert heat_index_f(t, rh) < unadjusted


def test_conversions_round_trip():
    assert c_to_f(40) == pytest.approx(104) and f_to_c(c_to_f(33.3)) == pytest.approx(33.3)


@pytest.mark.parametrize("hi,band,score", [
    (79.9, None, 0), (80, "Caution", 1), (89.9, "Caution", 1), (90, "Extreme Caution", 2),
    (102.9, "Extreme Caution", 2), (103, "Danger", 3), (124.9, "Danger", 3), (125, "Extreme Danger", 4),
])
def test_nws_band_edges(hi, band, score):
    assert nws_band(hi) == (band, score)


@pytest.mark.parametrize("max_c,expected", [
    (39.9, "none"), (40, "threshold_met"), (44.9, "threshold_met"), (45, "heat_wave"),
    (46.9, "heat_wave"), (47, "severe_heat_wave"), (None, None),
])
def test_imd_edges(max_c, expected):
    assert imd_indication(max_c, "plains") == expected
    assert imd_indication(max_c, None) == expected  # unknown terrain: plains assumed


@pytest.mark.parametrize("terrain", ["hilly", "coastal"])
def test_imd_not_applied_for_hilly_or_coastal(terrain):
    assert imd_indication(48, terrain) is None


def test_scenario_mild_no_vulnerability_is_low():
    r = classify(make_weather(25, 40, [30, 31, 32]), PLAINS)
    assert heat_index_f(c_to_f(25), 40) < 80
    assert r.category == "low" and r.hazard_score == 0 and r.confidence == "high"
    assert r.heat_index_band is None and r.imd_indication == "none"


def test_scenario_caution_band_is_moderate_and_vulnerability_raises_it():
    hi = heat_index_f(c_to_f(29), 50)
    assert nws_band(hi) == ("Caution", 1)
    r = classify(make_weather(29, 50, [36, 37, 38]), PLAINS)
    assert r.category == "moderate" and r.heat_index_band == "Caution"
    assert r.heat_index_f == round(hi, 1)
    r2 = classify(make_weather(29, 50, [36, 37, 38]), VULNERABLE, min_indicators=2)
    assert r2.category == "high" and r2.heuristic_adjustment_applied is True
    assert r2.vulnerability_indicators == ["elderly", "outdoor_workers"]
    heuristic = next(f for f in r2.contributing_factors if f.code == "vulnerability_heuristic")
    assert "project heuristic" in heuristic.description.lower()
    assert "who_heat_health_factsheet" in r2.source_ids


def test_scenario_forecast_heat_wave_very_high_then_extreme():
    r = classify(make_weather(25, 40, [44, 45, 46]), PLAINS)
    assert r.imd_indication == "heat_wave" and r.category == "very_high"
    r2 = classify(make_weather(25, 40, [44, 45, 46]), VULNERABLE)
    assert r2.category == "extreme"


def test_scenario_severe_heat_wave_is_extreme_and_capped():
    r = classify(make_weather(25, 40, [46, 47.5]), PLAINS)
    assert r.imd_indication == "severe_heat_wave" and r.category == "extreme"
    r2 = classify(make_weather(25, 40, [46, 47.5]), VULNERABLE)
    assert r2.category == "extreme" and r2.heuristic_adjustment_applied is False


def test_scenario_wardha_dry_heat():
    hi = heat_index_f(c_to_f(44.2), 21)
    band, score = nws_band(hi)
    r = classify(make_weather(44.2, 21, [44, 45, 46]), PLAINS)
    assert r.heat_index_band == band and r.hazard_score == max(score, 3)


def test_scenario_forecast_only_has_low_confidence():
    r = classify(make_weather(None, None, [41, 42], current=False), PLAINS)
    assert r.status == "ok" and r.category == "moderate" and r.confidence == "low"
    assert r.heat_index_f is None
    assert any("heat index not computed" in m for m in r.missing_data)


def test_scenario_no_weather_is_unknown():
    for weather in (None, make_weather(None, None, current=False, forecast=False)):
        r = classify(weather, PLAINS)
        assert r.status == "insufficient_data" and r.category == "unknown" and r.confidence == "low"


def test_scenario_hilly_terrain_skips_imd_rule():
    r = classify(make_weather(25, 40, [46, 47.5]), CommunityProfile(terrain="hilly"))
    assert r.imd_indication is None and r.category == "low"
    assert any("not applied for hilly terrain" in m for m in r.missing_data)


def test_scenario_unknown_terrain_assumes_plains_with_medium_confidence():
    r = classify(make_weather(25, 40, [45.5]), CommunityProfile())
    assert r.imd_indication == "heat_wave" and r.confidence == "medium"
    assert any("Terrain not provided" in m for m in r.missing_data)


def test_scenario_stale_and_demo_noted():
    r = classify(make_weather(29, 50, [38], stale=True, data_mode="demo"), PLAINS)
    assert r.confidence == "medium"
    assert any("freshness" in m for m in r.missing_data) and any("Demonstration" in m for m in r.missing_data)


def test_vulnerability_without_hazard_or_below_threshold_does_not_raise():
    assert classify(make_weather(25, 40, [30]), VULNERABLE).category == "low"
    one = CommunityProfile(terrain="plains", farmers=True)
    assert classify(make_weather(29, 50, [38]), one, min_indicators=2).category == "moderate"
    assert classify(make_weather(29, 50, [38]), one, min_indicators=1).category == "high"


def test_departure_from_normal_reported_missing():
    r = classify(make_weather(29, 50, [38]), PLAINS)
    assert any("Departure-from-normal" in m for m in r.missing_data)


def test_every_threshold_url_is_a_trusted_source():
    source = Path(risk_rules.__file__).read_text(encoding="utf-8")
    urls = set(re.findall(r"https://[^\s\"')]+", source))
    trusted = {s.url for s in TRUSTED_SOURCES.values()}
    assert urls and urls <= trusted
    # Every numeric threshold constant line carries a URL comment.
    for line in source.splitlines():
        if re.match(r"^(HI|IMD)_[A-Z_]+_[CF] = ", line):
            assert "https://" in line, line


def test_sources_are_https_and_dated():
    for s in TRUSTED_SOURCES.values():
        assert s.url.startswith("https://") and re.fullmatch(r"\d{4}-\d{2}-\d{2}", s.verified_on)
