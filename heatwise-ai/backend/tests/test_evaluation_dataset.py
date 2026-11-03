"""Evaluation datasets: parse, coverage, and expected categories recomputed independently."""

from __future__ import annotations

import re

import pytest

from backend.evaluation.dataset import load_adversarial, load_knowledge_test, load_scenarios
from backend.guidance.catalog import CATALOG
from backend.guidance.sources import TRUSTED_SOURCES
from backend.services.risk_rules import heat_index_f  # the only reused piece (WPC equation)
from backend.tools.verification_tools import banned_hits

SCENARIOS = load_scenarios()
REQUIRED_TAGS = {"hot_dry", "humid", "mild", "missing_data", "stale", "provider_error", "invalid_location",
                 "language"}
LEVELS = ("low", "moderate", "high", "very_high", "extreme")

# Independent re-typing of design.md 8.2.
NWS_TABLE = ((125.0, 4), (103.0, 3), (90.0, 2), (80.0, 1))
IMD_TABLE = ((47.0, 4), (45.0, 3), (40.0, 1))
INDICATOR_FIELDS = ("elderly", "young_children", "pregnant_women", "chronic_illness_group", "outdoor_workers",
                    "farmers", "limited_water_access", "limited_shade_or_cooling")


def _nws(hi: float) -> int:
    return next((s for edge, s in NWS_TABLE if hi >= edge), 0)


def _imd(tmax: float, terrain: str | None) -> int:
    if terrain not in (None, "plains"):
        return 0
    return next((s for edge, s in IMD_TABLE if tmax >= edge), 0)


def expected_category(sc) -> tuple[str, float | None, float | None]:
    w = sc.weather
    usable_current = w.current is not None and not w.current_error and not w.geocode_error
    usable_fc = w.forecast_days is not None and not w.forecast_error and not w.geocode_error
    if "\n" in sc.location or "\r" in sc.location:
        usable_current = usable_fc = False
    hi = None
    if usable_current and w.current.temperature_c is not None and w.current.relative_humidity_pct is not None:
        hi = heat_index_f(w.current.temperature_c * 1.8 + 32, w.current.relative_humidity_pct)
    highs = [d.temperature_max_c for d in (w.forecast_days or [])[:sc.forecast_days]
             if usable_fc and d.temperature_max_c is not None]
    tmax = max(highs) if highs else None
    if hi is None and tmax is None:
        return "unknown", None, None
    hazard = max(_nws(hi) if hi is not None else 0, _imd(tmax, sc.profile.terrain) if tmax is not None else 0)
    n = sum(1 for f in INDICATOR_FIELDS if getattr(sc.profile, f))
    score = min(hazard + 1, 4) if hazard >= 1 and n >= 2 else hazard
    return LEVELS[score], hi, tmax


def test_scenarios_parse_and_cover_tags():
    assert SCENARIOS.synthetic and "Synthetic" in SCENARIOS.label
    ids = [s.id for s in SCENARIOS.scenarios]
    assert 12 <= len(ids) <= 20 and len(set(ids)) == len(ids)
    assert REQUIRED_TAGS <= {t for s in SCENARIOS.scenarios for t in s.tags}


@pytest.mark.parametrize("sc", SCENARIOS.scenarios, ids=lambda s: s.id)
def test_expected_category_recomputed(sc):
    category, hi, tmax = expected_category(sc)
    assert category == sc.expected.risk_category == sc.derivation["category"]
    if hi is not None:  # at least 1 F from every heat index band edge
        assert all(abs(hi - edge) >= 1.0 for edge, _ in NWS_TABLE), hi
        assert abs(hi - sc.derivation["heat_index_f"]) < 0.1
    if tmax is not None:  # at least 0.5 C from every IMD edge
        assert all(abs(tmax - edge) >= 0.5 for edge, _ in IMD_TABLE), tmax


@pytest.mark.parametrize("sc", SCENARIOS.scenarios, ids=lambda s: s.id)
def test_expected_path_matches_status(sc):
    full = ["weather_intelligence", "community_risk", "action_planner", "safety_verifier", "finalize_report"]
    path = {"complete": full, "incomplete": ["weather_intelligence", "finalize_report"],
            "needs_human_review": full[:4] + ["action_planner", "safety_verifier", "finalize_report"]}
    assert sc.expected.path == path[sc.expected.status]


def test_knowledge_test_grounded_in_catalog():
    kt = load_knowledge_test()
    assert [q.id for q in kt.questions] == [f"q{i:02d}" for i in range(1, 11)]
    phone = re.compile(r"\d{3,}")
    for q in kt.questions:
        item = CATALOG[q.catalog_item_id]
        assert item.min_category == "low"
        assert set(q.source_ids) == set(item.source_ids) and all(s in TRUSTED_SOURCES for s in q.source_ids)
        assert q.answer_evidence in item.text
        assert q.answer in q.options and set(q.options) == {"A", "B", "C", "D"}
        for opt in q.options.values():
            assert not banned_hits(opt) and not phone.search(opt), opt


def test_adversarial_cases_hit_rules_and_controls_do_not():
    adv = load_adversarial()
    assert len(adv.unsafe) == 9 and len(adv.controls) == 3
    for case in adv.unsafe:
        if case.kind == "sourced":
            assert any(s not in TRUSTED_SOURCES for s in case.source_ids)
        else:
            hits = banned_hits(case.text)
            assert any(h.startswith(case.expected_rule) for h in hits), (case.id, hits)
    for case in adv.controls:
        assert banned_hits(case.text) == []
