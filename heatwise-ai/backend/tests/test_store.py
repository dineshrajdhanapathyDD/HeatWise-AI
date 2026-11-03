"""JSON-file assessment store, history changes and metrics (offline)."""

from __future__ import annotations

import json
import uuid
from datetime import datetime, timedelta, timezone

import pytest

from backend.api.schemas import AssessmentRequest
from backend.api.summaries import compute_metrics, history_items, location_key
from backend.models.risk import CommunityProfile
from backend.session.store import AssessmentRecord, JsonFileAssessmentStore
from backend.tests.test_cli import scripted_report

T0 = datetime(2026, 5, 10, 9, 0, tzinfo=timezone.utc)


@pytest.fixture(scope="module")
def reports():
    from backend.config import Settings
    s = Settings(_env_file=None, weather_provider="open_meteo")
    return {k: scripted_report(s, k) for k in ("complete", "needs_human_review", "incomplete")}


def record(report, minutes=0, duration_ms=1200.0, profile=None, **report_update):
    rid = uuid.uuid4().hex
    rep = report.model_copy(update={"report_id": rid, **report_update})
    req = AssessmentRequest(place={"name": "Wardha"}, profile=profile or {"elderly": True})
    return AssessmentRecord(report_id=rid, created_at=T0 + timedelta(minutes=minutes), duration_ms=duration_ms,
                            request=req, report=rep)


def test_save_get_list_order_count(tmp_path, reports):
    store = JsonFileAssessmentStore(tmp_path / "a")
    assert store.all() == [] and store.count() == 0  # directory not created yet
    older, newer = record(reports["complete"], 0), record(reports["incomplete"], 5)
    store.save(older)
    store.save(newer)
    assert (tmp_path / "a" / f"{older.report_id}.json").is_file()
    assert not list((tmp_path / "a").glob(".tmp-*"))
    assert [r.report_id for r in store.list()] == [newer.report_id, older.report_id]
    assert [r.report_id for r in store.list(limit=1, offset=1)] == [older.report_id]
    assert store.count() == 2
    assert store.get(older.report_id) == older
    assert store.get(uuid.uuid4().hex) is None
    assert store.get("../../etc/passwd") is None


def test_record_json_holds_only_request_and_report(tmp_path, reports):
    store = JsonFileAssessmentStore(tmp_path)
    rec = record(reports["complete"])
    store.save(rec)
    data = json.loads((tmp_path / f"{rec.report_id}.json").read_text(encoding="utf-8"))
    assert set(data) == {"report_id", "created_at", "duration_ms", "request", "report"}
    assert set(data["request"]) == {"place", "forecast_days", "profile"}


def test_corrupt_file_is_skipped(tmp_path, reports, caplog):
    store = JsonFileAssessmentStore(tmp_path)
    good = record(reports["complete"])
    store.save(good)
    bad_id = uuid.uuid4().hex
    (tmp_path / f"{bad_id}.json").write_text("{not json", encoding="utf-8")
    assert [r.report_id for r in store.all()] == [good.report_id]
    assert store.get(bad_id) is None
    assert "unreadable" in caplog.text


def test_needs_review_round_trip_keeps_verified_ids(tmp_path, reports):
    store = JsonFileAssessmentStore(tmp_path)
    rec = record(reports["needs_human_review"])
    store.save(rec)
    back = store.get(rec.report_id)
    assert back.report.status == "needs_human_review"
    assert back.report.verification.verified_item_ids == rec.report.verification.verified_item_ids
    assert back.report.verification.verified_item_ids
    assert back.report.checklist_markdown == rec.report.checklist_markdown


def test_save_rejects_bad_report_id(tmp_path, reports):
    rec = record(reports["complete"]).model_copy(update={"report_id": "../x"})
    with pytest.raises(ValueError):
        JsonFileAssessmentStore(tmp_path).save(rec)


def test_checklist_progress_round_trip(tmp_path, reports):
    store = JsonFileAssessmentStore(tmp_path)
    rec = record(reports["complete"])
    store.save(rec)
    item_id = rec.report.recommended_actions.items[0].id
    updated = store.set_checklist_item(rec.report_id, item_id, True)
    assert updated is not None and set(updated.checklist_completed) == {item_id}
    assert store.get(rec.report_id) == updated
    data = json.loads((tmp_path / f"{rec.report_id}.json").read_text(encoding="utf-8"))
    assert set(data["checklist_completed"]) == {item_id}
    again = store.set_checklist_item(rec.report_id, item_id, True)
    assert again.checklist_completed == updated.checklist_completed  # first completion time kept
    cleared = store.set_checklist_item(rec.report_id, item_id, False)
    assert cleared.checklist_completed == {}
    data = json.loads((tmp_path / f"{rec.report_id}.json").read_text(encoding="utf-8"))
    assert set(data) == {"report_id", "created_at", "duration_ms", "request", "report"}
    assert store.set_checklist_item(uuid.uuid4().hex, item_id, True) is None
    assert store.set_checklist_item("../x", item_id, True) is None
    assert not list(tmp_path.glob(".tmp-*"))


def test_metrics_checklist_counts_only_renderable_items(reports):
    review = record(reports["needs_human_review"])
    verified = review.report.verification.verified_item_ids
    rejected = [i.id for i in review.report.recommended_actions.items if i.id not in verified]
    assert verified and rejected
    now = T0 + timedelta(hours=1)
    review = review.model_copy(update={"checklist_completed": {verified[0]: now, rejected[0]: now}})
    m = compute_metrics([review, record(reports["incomplete"])])
    assert (m.checklist.items_completed, m.checklist.items_available, m.checklist.reports_with_progress) == (
        1, len(verified), 1)
    assert m.assessments_completed == 0


def test_history_changes_for_same_location(reports):
    base = reports["complete"]
    first = record(base, 0, profile={"elderly": True})
    hotter_risk = base.risk.model_copy(update={"heat_index_c": base.risk.heat_index_c + 2.0})
    second = record(base, 10, profile={"elderly": True, "limited_water_access": True},
                    risk=hotter_risk, risk_category="very_high")
    other_place = record(base, 5, location=base.location.model_copy(update={"name": "Nagpur"}))
    assert location_key(first.report) == "wardha|maharashtra|india"

    items = history_items([second, other_place, first])
    assert [i.report_id for i in items] == [second.report_id, other_place.report_id, first.report_id]
    ch = items[0].changes
    assert ch is not None and ch.previous_report_id == first.report_id
    assert (ch.risk_category_from, ch.risk_category_to) == (base.risk_category, "very_high")
    assert ch.heat_index_delta_c == 2.0 and ch.max_forecast_delta_c == 0.0
    assert ch.indicators_added == ["limited_water_access"] and ch.indicators_removed == []
    assert items[1].changes is None and items[2].changes is None
    assert items[2].max_forecast_c == max(d.temperature_max_c for d in base.forecast.days)


def test_history_uses_query_when_unresolved(reports):
    unresolved = reports["incomplete"].model_copy(update={"location": None, "query": " Wardha "})
    assert location_key(unresolved) == "wardha"


def test_metrics_counts(reports):
    recs = [record(reports["complete"], duration_ms=1000.0), record(reports["needs_human_review"], duration_ms=3000.0),
            record(reports["incomplete"], duration_ms=None)]
    m = compute_metrics(recs)
    assert m.total == 3
    assert m.by_status == {"complete": 1, "needs_human_review": 1, "incomplete": 1}
    assert m.plans_generated == 2
    assert (m.verification.passed, m.verification.failed, m.verification.not_run) == (1, 1, 1)
    modes = [r.report.weather_source.data_mode or "unknown" for r in recs]
    assert m.by_data_mode == {"live": modes.count("live"), "demo": 0,
                              **({"unknown": modes.count("unknown")} if "unknown" in modes else {})}
    assert sum(m.by_risk_category.values()) == 3
    pcts = [r.report.verification.pct_items_verified for r in recs[:2]]
    assert m.mean_pct_items_verified == round(sum(pcts) / 2, 1)
    assert m.mean_duration_ms == 2000.0


def test_metrics_zero_state():
    m = compute_metrics([])
    assert m.total == 0 and m.plans_generated == 0
    assert set(m.by_status.values()) == {0} and set(m.by_risk_category.values()) == {0}
    assert m.verification.passed == m.verification.failed == m.verification.not_run == 0
    assert m.mean_pct_items_verified is None and m.mean_duration_ms is None


def test_request_model_is_strict():
    with pytest.raises(ValueError):
        AssessmentRequest(place={"name": "Wardha"}, phone="123")
    with pytest.raises(ValueError):
        AssessmentRequest(place={"name": "Wardha"}, profile={"name": "A person"})
    req = AssessmentRequest(place={"name": " Nagpur ", "district": "", "state": "Maharashtra"})
    assert req.location == "Nagpur, Maharashtra" and req.forecast_days == 3
    assert type(req.profile_as_community()) is CommunityProfile
