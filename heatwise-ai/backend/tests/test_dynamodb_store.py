"""DynamoDB assessment store under moto, compared with the JSON-file store (offline)."""

from __future__ import annotations

import json
import uuid

import boto3
import pytest

from backend.api.summaries import compute_metrics, history_items, location_key
from backend.config import Settings
from backend.session import dynamodb_schema as schema
from backend.session.dynamodb_store import DynamoDbAssessmentStore
from backend.session.factory import build_assessment_store
from backend.session.store import JsonFileAssessmentStore
from backend.tests.aws_fixtures import REGION, aws, aws_credentials, create_assessments_table  # noqa: F401
from backend.tests.test_store import record, reports  # noqa: F401

TABLE = "heatwise-test-assessments"


@pytest.fixture
def client(aws):  # noqa: F811
    c = boto3.client("dynamodb", region_name=REGION)
    create_assessments_table(c, TABLE)
    return c


@pytest.fixture
def store(client):
    return DynamoDbAssessmentStore(TABLE, client=client)


def nagpur(rep):
    return {"location": rep.location.model_copy(update={"name": "Nagpur"})}


def test_round_trip(store, reports):  # noqa: F811
    for kind in ("complete", "needs_human_review", "incomplete"):
        rec = record(reports[kind])
        store.save(rec)
        assert store.get(rec.report_id) == rec
    review = record(reports["needs_human_review"])
    store.save(review)
    back = store.get(review.report_id)
    assert back.report.verification.verified_item_ids == review.report.verification.verified_item_ids
    assert back.report.checklist_markdown == review.report.checklist_markdown
    no_duration = record(reports["complete"], duration_ms=None)
    store.save(no_duration)
    assert store.get(no_duration.report_id).duration_ms is None


def test_list_offset_count_newest_first(store, reports):  # noqa: F811
    assert store.all() == [] and store.count() == 0 and store.list() == []
    recs = [record(reports["complete"], minutes=m) for m in (0, 10, 5)]
    for r in recs:
        store.save(r)
    newest_first = [recs[1].report_id, recs[2].report_id, recs[0].report_id]
    assert [r.report_id for r in store.all()] == newest_first
    assert [r.report_id for r in store.list()] == newest_first
    assert [r.report_id for r in store.list(limit=1, offset=1)] == [recs[2].report_id]
    assert [r.report_id for r in store.list(limit=5, offset=2)] == [recs[0].report_id]
    assert store.list(limit=2, offset=5) == []
    assert store.count() == 3


def test_history_for_location_matches_json_store(store, reports, tmp_path):  # noqa: F811
    base = reports["complete"]
    recs = [record(base, 0), record(base, 10), record(base, 5, **nagpur(base)), record(base, 3)]
    json_store = JsonFileAssessmentStore(tmp_path / "json")
    for r in recs:
        store.save(r)
        json_store.save(r)
    key = location_key(base)
    got = store.history_for_location(key)
    assert [r.report_id for r in got] == [recs[1].report_id, recs[3].report_id, recs[0].report_id]
    assert got == json_store.history_for_location(key)
    assert [r.report_id for r in store.history_for_location(key, limit=2)] == [recs[1].report_id,
                                                                               recs[3].report_id]
    assert store.history_for_location(key, limit=2) == json_store.history_for_location(key, limit=2)
    other = location_key(recs[2].report)
    assert [r.report_id for r in store.history_for_location(other)] == [recs[2].report_id]
    assert store.history_for_location("nowhere") == json_store.history_for_location("nowhere") == []


def test_bad_or_missing_id_returns_none(store):
    assert store.get(uuid.uuid4().hex) is None
    assert store.get("../../etc/passwd") is None


def test_save_rejects_bad_report_id(store, reports):  # noqa: F811
    rec = record(reports["complete"]).model_copy(update={"report_id": "../x"})
    with pytest.raises(ValueError):
        store.save(rec)


def test_item_attributes(store, client, reports):  # noqa: F811
    rec = record(reports["complete"])
    store.save(rec)
    item = client.get_item(TableName=TABLE, Key={"report_id": {"S": rec.report_id}})["Item"]
    assert set(item) == {"report_id", "entity", "created_at", "location_key", "request_json", "report_json",
                         "duration_ms"}
    assert item["entity"] == {"S": schema.ENTITY}
    assert item["created_at"] == {"S": schema.ts(rec.created_at)}
    assert item["location_key"] == {"S": location_key(rec.report)}
    assert item["duration_ms"] == {"N": "1200.0"}
    assert set(json.loads(item["request_json"]["S"])) == {"place", "forecast_days", "profile"}


def test_checklist_progress_round_trip(store, client, reports):  # noqa: F811
    rec = record(reports["complete"])
    store.save(rec)
    item_id = rec.report.recommended_actions.items[0].id
    updated = store.set_checklist_item(rec.report_id, item_id, True)
    assert updated is not None and set(updated.checklist_completed) == {item_id}
    assert store.get(rec.report_id) == updated
    item = client.get_item(TableName=TABLE, Key={"report_id": {"S": rec.report_id}})["Item"]
    assert schema.ATTR_CHECKLIST in item
    assert json.loads(item[schema.ATTR_CHECKLIST]["S"]) == {item_id: schema.ts(updated.checklist_completed[item_id])}
    assert store.all()[0] == updated
    again = store.set_checklist_item(rec.report_id, item_id, True)
    assert again.checklist_completed == updated.checklist_completed
    cleared = store.set_checklist_item(rec.report_id, item_id, False)
    assert cleared.checklist_completed == {} and store.get(rec.report_id) == rec
    item = client.get_item(TableName=TABLE, Key={"report_id": {"S": rec.report_id}})["Item"]
    assert schema.ATTR_CHECKLIST not in item
    # save() writes the attribute only while there is progress
    store.save(updated)
    item = client.get_item(TableName=TABLE, Key={"report_id": {"S": rec.report_id}})["Item"]
    assert schema.ATTR_CHECKLIST in item and store.get(rec.report_id) == updated


def test_checklist_missing_report_returns_none(store):
    assert store.set_checklist_item(uuid.uuid4().hex, "hh-during-cooling-1", True) is None
    assert store.set_checklist_item("../x", "hh-during-cooling-1", True) is None
    assert store.all() == []  # no item created


def test_oversized_item_is_rejected(store, reports):  # noqa: F811
    rec = record(reports["complete"], query="x" * (schema.MAX_ITEM_BYTES + 1))
    with pytest.raises(ValueError, match="larger"):
        store.save(rec)
    assert store.get(rec.report_id) is None


def test_summaries_match_json_store(store, reports, tmp_path):  # noqa: F811
    base = reports["complete"]
    recs = [record(base, 0, profile={"elderly": True}),
            record(reports["needs_human_review"], 4, duration_ms=3000.0),
            record(reports["incomplete"], 6, duration_ms=None),
            record(base, 8, profile={"elderly": True, "limited_water_access": True}, risk_category="very_high"),
            record(base, 2, **nagpur(base))]
    json_store = JsonFileAssessmentStore(tmp_path / "json")
    for r in recs:
        store.save(r)
        json_store.save(r)
    assert history_items(store.all()) == history_items(json_store.all())
    assert compute_metrics(store.all()) == compute_metrics(json_store.all())


def test_factory_selection(aws, tmp_path):  # noqa: F811
    default = build_assessment_store(Settings(_env_file=None, assessment_store_dir=str(tmp_path)))
    assert isinstance(default, JsonFileAssessmentStore)
    dyn = build_assessment_store(Settings(_env_file=None, assessment_store="dynamodb",
                                          assessments_table_name=TABLE, aws_region=REGION))
    assert isinstance(dyn, DynamoDbAssessmentStore) and dyn.table_name == TABLE
    with pytest.raises(ValueError, match="ASSESSMENTS_TABLE_NAME"):
        build_assessment_store(Settings(_env_file=None, assessment_store="dynamodb"))
