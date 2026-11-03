"""Scenario provider, metrics, adversarial cases and the offline runner (no network, AWS or Bedrock)."""

from __future__ import annotations

from datetime import datetime, timezone

import pytest

from backend.agents.offline import build_offline_coordinator
from backend.evaluation.dataset import load_scenarios
from backend.evaluation.metrics import delegation, weather_extraction
from backend.evaluation.provider import PROVIDER_NAME, ScenarioWeatherProvider
from backend.evaluation.results import RunResult, load_results, save_run
from backend.evaluation.runner import offline_settings, run_offline
from backend.models.report import AgentTraceEntry
from backend.services.weather.base import LocationNotFoundError, ProviderTimeoutError, ProviderUnavailableError

DATA = load_scenarios()
BY_ID = {s.id: s for s in DATA.scenarios}


@pytest.fixture(scope="module")
def offline_run() -> RunResult:
    return run_offline()


def provider() -> ScenarioWeatherProvider:
    return ScenarioWeatherProvider(DATA.scenarios, stale_after_minutes=90)


def test_provider_round_trip_and_labels():
    p = provider()
    loc = p.geocode("eval dryfield, Synthetic State")  # first comma part, casefolded
    cur = p.current(loc)
    fc = p.forecast(loc, 3)
    alerts = p.alerts(loc)
    assert cur.temperature_c == 43.0 and cur.relative_humidity_pct == 15.0 and cur.missing_fields == []
    assert [d.temperature_max_c for d in fc.days] == [45.0, 46.0, 44.5]
    assert cur.provenance.provider == PROVIDER_NAME and cur.provenance.data_mode == "demo"
    assert cur.provenance.source_url == "synthetic://heatwise/evaluation" and not cur.provenance.is_stale
    assert alerts.alerts_supported is False
    assert p.calls == ["geocode:eval dryfield, Synthetic State", "current", "forecast:3", "alerts"]


def test_provider_missing_field_and_stale():
    p = provider()
    cur = p.current(p.geocode("Eval Brickfield"))
    assert cur.relative_humidity_pct is None and cur.missing_fields == ["relative_humidity_pct"]
    assert p.current(p.geocode("Eval Oldmill")).provenance.is_stale is True


def test_provider_injected_errors():
    p = provider()
    with pytest.raises(ProviderTimeoutError):
        p.geocode("Eval Fogbank")
    with pytest.raises(LocationNotFoundError):
        p.geocode("Eval Nowhere")
    with pytest.raises(LocationNotFoundError):
        p.geocode("Somewhere Else")
    loc = p.geocode("Eval Quietwell")
    with pytest.raises(ProviderUnavailableError):
        p.current(loc)
    with pytest.raises(ProviderUnavailableError):
        p.forecast(loc, 3)


def test_invalid_location_never_calls_provider():
    sc = BY_ID["S16"]
    p = provider()
    report = build_offline_coordinator(offline_settings(), sc.location, 3, sc.profile, provider=p).run(
        sc.location, sc.profile, 3)
    assert report.status == "incomplete" and p.calls == []
    assert any("invalid_location" in m for m in report.missing_information)


def test_offline_run_covers_all_scenarios(offline_run):
    m = offline_run.metrics
    assert len(offline_run.scenarios) == len(DATA.scenarios) == 18
    assert all(not r["error"] for r in offline_run.scenarios)
    assert m["risk_agreement"].numerator == m["risk_agreement"].denominator == 18
    assert m["workflow_completion"].value == 1.0 and m["safety_pass"].value == 1.0
    assert m["weather_extraction"].value == 1.0
    assert m["delegation_order_effective"].value == 1.0
    assert all(x.mode == "offline" for x in m.values())
    assert m["recommendation_relevance"].status == "not_run" and "live only" in m["recommendation_relevance"].note
    assert m["knowledge_test_baseline"].status == "not_run"
    s16 = next(r for r in offline_run.scenarios if r["id"] == "S16")
    assert s16["provider_calls"] == []


def test_offline_adversarial(offline_run):
    m = offline_run.metrics
    assert (m["adversarial_direct_rejection"].numerator, m["adversarial_direct_rejection"].denominator) == (9, 9)
    assert (m["adversarial_controls_pass"].numerator, m["adversarial_controls_pass"].denominator) == (3, 3)
    e2e = offline_run.adversarial["end_to_end"]
    assert e2e["status"] == "needs_human_review" and e2e["revision_count"] == 1
    assert e2e["unsafe_text_in_checklist"] is False and e2e["passed"] is True


def test_save_run_keeps_other_mode(tmp_path, offline_run):
    path = tmp_path / "results.json"
    live = RunResult(mode="live", mode_label="live", status="failed", error="no credentials", command="x",
                     started_at=datetime.now(timezone.utc), dataset_version="v")
    save_run(path, live)
    save_run(path, offline_run)
    res = load_results(path)
    assert res.runs.live is not None and res.runs.live.error == "no credentials"
    assert res.runs.offline is not None and res.runs.offline.metrics["risk_agreement"].value == 1.0
    assert load_results(tmp_path / "missing.json").runs.offline is None


def _report_for(sid: str):
    sc = BY_ID[sid]
    return build_offline_coordinator(offline_settings(), sc.location, 3, sc.profile, provider=provider()).run(
        sc.location, sc.profile, 3), sc


def test_wrong_field_lowers_extraction():
    report, sc = _report_for("S01")
    good = weather_extraction(report, sc)
    assert good["matched"] == good["total"]
    bad = report.model_copy(update={"current_conditions": report.current_conditions.model_copy(
        update={"temperature_c": 40.0})})
    out = weather_extraction(bad, sc)
    assert out["matched"] == good["total"] - 1 and "current.temperature_c" in out["mismatches"][0]


def test_fallback_step_makes_model_driven_false():
    report, sc = _report_for("S01")
    assert delegation(report, sc.expected.path)["model_driven"] is True
    trace = [t for t in report.trace if not (t.agent == "coordinator" and t.tool == "safety_verifier")]
    trace.append(AgentTraceEntry(agent="coordinator_fallback", tool="safety_verifier", status="success",
                                 step_index=4))
    d = delegation(report.model_copy(update={"trace": trace}), sc.expected.path)
    assert d["effective"] is True and d["model_driven"] is False and d["fallback_used"] is True
