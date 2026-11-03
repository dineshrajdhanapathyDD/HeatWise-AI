"""HTTP API tests through FastAPI's TestClient. Offline: FakeProvider/demo weather and ScriptedModels only."""

from __future__ import annotations

import threading
import time

import pytest
from fastapi.testclient import TestClient

from backend.api.app import create_app
from backend.api.jobs import JobManager
from backend.api.schemas import AssessmentRequest
from backend.config import Settings
from backend.services.weather.base import ProviderTimeoutError
from backend.services.weather.demo import DEMO_LOCATIONS
from backend.session.store import JsonFileAssessmentStore
from backend.tests.fakes import FakeProvider
from backend.tests.test_coordinator import DELEGATIONS, REVIEW, UNSAFE_PLAN, build, calls

BODY = {"place": {"name": "Wardha", "state": "Maharashtra"}, "forecast_days": 3,
        "profile": {"elderly": True, "outdoor_workers": True, "farmers": True, "terrain": "plains"}}


def make_settings(**overrides) -> Settings:
    return Settings(_env_file=None, weather_provider="demo", agent_mode="offline", **overrides)


def complete_factory(settings):
    return lambda req: build(settings, calls(*DELEGATIONS, "finalize_report"))[0]


def needs_review_factory(settings):
    turns = calls(*DELEGATIONS, "action_planner", "safety_verifier", "action_planner", "finalize_report")
    return lambda req: build(settings, turns, planner_turns=UNSAFE_PLAN + UNSAFE_PLAN,
                             safety_turns=REVIEW + REVIEW)[0]


def incomplete_factory(settings):
    def factory(req):
        provider = FakeProvider(fail={"current": ProviderTimeoutError("slow"),
                                      "forecast": ProviderTimeoutError("slow")})
        return build(settings, calls("weather_intelligence", "community_risk", "finalize_report"),
                     provider=provider)[0]
    return factory


@pytest.fixture
def api(tmp_path):
    """Yield a function that builds a started TestClient; clients are closed at teardown."""
    opened = []

    def make(factory_of=complete_factory, settings=None, default_factory=False):
        s = settings or make_settings()
        store = JsonFileAssessmentStore(tmp_path / "store")
        app = create_app(s, store=store, coordinator_factory=None if default_factory else factory_of(s))
        client = TestClient(app)
        client.__enter__()
        opened.append(client)
        client.store = store  # type: ignore[attr-defined]
        return client

    yield make
    for c in opened:
        c.__exit__(None, None, None)


def wait_for(client, job_id, timeout=15.0, statuses=("succeeded", "failed")):
    deadline = time.monotonic() + timeout
    while time.monotonic() < deadline:
        job = client.get(f"/api/assessments/{job_id}").json()
        if job["status"] in statuses:
            return job
        time.sleep(0.02)
    raise AssertionError(f"job {job_id} did not reach {statuses} in {timeout}s")


def assert_envelope(resp, status, code):
    assert resp.status_code == status, resp.text
    body = resp.json()
    assert set(body) == {"error"} and set(body["error"]) == {"code", "message", "fields"}
    assert body["error"]["code"] == code and body["error"]["message"]
    return body["error"]


def submit(client, body=BODY):
    resp = client.post("/api/assessments", json=body)
    assert resp.status_code == 202, resp.text
    return resp


def test_job_lifecycle_queued_running_succeeded(api):
    gate = threading.Event()

    def blocked(settings):
        inner = complete_factory(settings)

        def factory(req):
            assert gate.wait(10)
            return inner(req)
        return factory

    client = api(blocked, settings=make_settings(api_job_workers=1))
    first = submit(client)
    assert first.headers["location"] == f"/api/assessments/{first.json()['job_id']}"
    assert first.json()["status"] in ("queued", "running") and first.json()["report"] is None
    second = submit(client).json()
    wait_for(client, first.json()["job_id"], statuses=("running",))
    assert client.get(f"/api/assessments/{second['job_id']}").json()["status"] == "queued"
    gate.set()

    job = wait_for(client, first.json()["job_id"])
    assert job["status"] == "succeeded" and job["error"] is None
    assert job["report"]["status"] == "complete" and job["report_id"] == job["report"]["report_id"]
    assert job["duration_ms"] >= 0 and job["started_at"] and job["finished_at"]
    assert job["request"]["place"] == {"name": "Wardha", "district": None, "state": "Maharashtra"}
    wait_for(client, second["job_id"])

    record = client.get(f"/api/reports/{job['report_id']}").json()
    assert set(record) == {"report_id", "created_at", "duration_ms", "request", "report"}
    assert set(record["request"]) == {"place", "forecast_days", "profile"}
    assert record["report"]["report_id"] == job["report_id"]
    assert record["request"]["profile"]["elderly"] is True
    assert client.store.count() == 2


def test_job_reads_are_snapshots(tmp_path):
    gate = threading.Event()
    s = make_settings(api_job_workers=1)
    inner = complete_factory(s)
    def run_fn(req, session_id=None):
        assert gate.wait(10)
        return inner(req).run(req.location, req.profile_as_community(), req.forecast_days, session_id=session_id)

    manager = JobManager(run_fn, JsonFileAssessmentStore(tmp_path / "store"), max_workers=1)
    try:
        job = manager.submit(AssessmentRequest.model_validate(BODY))
        before = manager.get(job.job_id)
        gate.set()
        deadline = time.monotonic() + 15
        while manager.get(job.job_id).status != "succeeded":
            assert time.monotonic() < deadline
            time.sleep(0.02)
        after = manager.get(job.job_id)
        # Earlier reads are copies: a later update never half-applies to them.
        assert before.status in ("queued", "running") and before.report_id is None and before.report is None
        assert after.report_id and after.report is not None and after.report_id == after.report.report_id
    finally:
        manager.shutdown(wait=True)


@pytest.mark.parametrize("body,field", [
    ({**BODY, "place": {"name": ""}}, "place.name"),
    ({**BODY, "place": {"name": "Wardha\nx"}}, "place.name"),
    ({**BODY, "place": {"name": "Wardha", "state": "<script>"}}, "place.state"),
    ({**BODY, "forecast_days": 0}, "forecast_days"),
    ({**BODY, "forecast_days": 8}, "forecast_days"),
    ({**BODY, "forecast_days": True}, "forecast_days"),
    ({**BODY, "profile": {"name": "A person"}}, "profile.name"),
    ({**BODY, "phone": "+910000000000"}, "phone"),
    ({**BODY, "profile": {"preferred_language": "english!"}}, "profile.preferred_language"),
    ({"forecast_days": 3}, "place"),
])
def test_validation_errors(api, body, field):
    client = api()
    err = assert_envelope(client.post("/api/assessments", json=body), 422, "validation_error")
    assert any(f["field"] == field for f in err["fields"]), err["fields"]
    assert all(not f["message"].startswith("Value error") for f in err["fields"])
    assert client.store.count() == 0


def test_validation_message_is_readable(api):
    err = assert_envelope(api().post("/api/assessments", json={**BODY, "forecast_days": 8}), 422, "validation_error")
    assert err["fields"] == [{"field": "forecast_days", "message": "Forecast days must be between 1 and 7."}]


def test_history_limit_is_validated(api):
    assert_envelope(api().get("/api/history?limit=0"), 422, "validation_error")


def test_unknown_job_and_report_are_404(api):
    client = api()
    assert_envelope(client.get("/api/assessments/nope"), 404, "not_found")
    assert_envelope(client.get("/api/reports/" + "0" * 32), 404, "not_found")
    assert_envelope(client.get("/api/reports/not-a-hex-id"), 404, "not_found")
    assert_envelope(client.get("/api/nothing-here"), 404, "not_found")
    assert_envelope(client.delete("/api/metrics"), 405, "http_405")


def test_too_many_jobs_is_429(api):
    gate = threading.Event()

    def blocked(settings):
        inner = complete_factory(settings)
        return lambda req: (gate.wait(10), inner(req))[1]

    client = api(blocked, settings=make_settings(api_job_workers=1, api_max_pending_jobs=1))
    job = submit(client).json()
    assert_envelope(client.post("/api/assessments", json=BODY), 429, "too_many_jobs")
    gate.set()
    assert wait_for(client, job["job_id"])["status"] == "succeeded"
    submit(client)  # capacity is back


def test_factory_failure_marks_job_failed(api):
    def boom(settings):
        def factory(req):
            raise RuntimeError("secret internal detail")
        return factory

    client = api(boom)
    job = wait_for(client, submit(client).json()["job_id"])
    assert job["status"] == "failed" and job["report"] is None and job["report_id"] is None
    assert job["error"]["code"] == "assessment_failed" and "secret" not in job["error"]["message"]
    assert client.store.count() == 0


def test_needs_human_review_payload(api):
    client = api(needs_review_factory)
    job = wait_for(client, submit(client).json()["job_id"])
    report = client.get(f"/api/reports/{job['report_id']}").json()["report"]
    assert report["status"] == "needs_human_review"
    verified = report["verification"]["verified_item_ids"]
    assert verified
    md = report["checklist_markdown"]
    assert "Not verified - needs human review" in md and "aspirin" not in md.lower()
    # The rejected item stays in the JSON for the human reviewer; the UI must not render it.
    rejected = [i for i in report["recommended_actions"]["items"] if "aspirin" in i["text"]]
    assert rejected and all(i["id"] not in verified for i in rejected)


def test_incomplete_payload(api):
    client = api(incomplete_factory)
    job = wait_for(client, submit(client).json()["job_id"])
    assert job["status"] == "succeeded"
    report = job["report"]
    assert report["status"] == "incomplete"
    assert report["recommended_actions"] is None and report["checklist_markdown"] is None
    assert any("provider_timeout" in m for m in report["missing_information"])


def test_history_newest_first_with_changes(api):
    client = api()
    empty = client.get("/api/history").json()
    assert empty == {"items": [], "total": 0, "limit": 20, "offset": 0}
    first = wait_for(client, submit(client).json()["job_id"])
    second_body = {**BODY, "profile": {**BODY["profile"], "limited_water_access": True}}
    second = wait_for(client, submit(client, second_body).json()["job_id"])

    page = client.get("/api/history").json()
    assert page["total"] == 2
    assert [i["report_id"] for i in page["items"]] == [second["report_id"], first["report_id"]]
    changes = page["items"][0]["changes"]
    assert changes["previous_report_id"] == first["report_id"]
    assert changes["indicators_added"] == ["limited_water_access"]
    assert changes["risk_category_from"] and changes["risk_category_to"]
    assert page["items"][1]["changes"] is None
    paged = client.get("/api/history?limit=1&offset=1").json()
    assert paged["total"] == 2 and [i["report_id"] for i in paged["items"]] == [first["report_id"]]
    assert paged["items"][0]["changes"] is None


def test_metrics_zero_and_counts(api):
    client = api()
    zero = client.get("/api/metrics").json()
    assert zero["total"] == 0 and zero["plans_generated"] == 0
    assert zero["mean_pct_items_verified"] is None and zero["mean_duration_ms"] is None
    for _ in range(2):
        wait_for(client, submit(client).json()["job_id"])
    m = client.get("/api/metrics").json()
    records = client.store.all()
    assert m["total"] == len(records) == 2
    assert m["by_status"]["complete"] == 2 and m["plans_generated"] == 2
    assert m["verification"] == {"passed": 2, "failed": 0, "not_run": 0}
    assert m["by_data_mode"]["live"] == 2
    assert m["by_risk_category"][records[0].report.risk_category] == 2
    assert m["mean_duration_ms"] == round(sum(r.duration_ms for r in records) / 2, 1)


def stored_record(client, body=BODY):
    job = wait_for(client, submit(client, body).json()["job_id"])
    assert job["status"] == "succeeded", job
    return client.get(f"/api/reports/{job['report_id']}").json()


def tick(client, report_id, item_id, completed=True):
    return client.post(f"/api/reports/{report_id}/checklist", json={"item_id": item_id, "completed": completed})


def test_metrics_zero_state_new_keys(api):
    zero = api().get("/api/metrics").json()
    assert zero["assessments_completed"] == 0 and zero["pct_recommendations_verified"] is None
    assert zero["checklist"] == {"items_completed": 0, "items_available": 0, "reports_with_progress": 0}
    assert zero["localized_guidance"] == {"served_in_requested_language": 0, "english_fallback": 0,
                                          "by_requested_language": {}}


def test_checklist_round_trip_and_metrics(api):
    client = api()
    rec = stored_record(client)
    rid = rec["report_id"]
    items = [i["id"] for i in rec["report"]["recommended_actions"]["items"]]
    assert items and "checklist_completed" not in rec

    resp = tick(client, rid, items[0])
    assert resp.status_code == 200, resp.text
    assert resp.json() == {"report_id": rid, "completed_item_ids": [items[0]], "completed_count": 1,
                           "available_count": len(items)}
    first_at = client.get(f"/api/reports/{rid}").json()["checklist_completed"]
    assert set(first_at) == {items[0]}
    assert tick(client, rid, items[0]).json()["completed_count"] == 1  # idempotent, keeps the first time
    assert client.get(f"/api/reports/{rid}").json()["checklist_completed"] == first_at

    m = client.get("/api/metrics").json()
    assert m["checklist"] == {"items_completed": 1, "items_available": len(items), "reports_with_progress": 1}
    assert m["assessments_completed"] == 1 and m["pct_recommendations_verified"] == 100.0
    assert m["localized_guidance"] == {"served_in_requested_language": 1, "english_fallback": 0,
                                       "by_requested_language": {"en": 1}}

    undo = tick(client, rid, items[0], completed=False).json()
    assert undo["completed_item_ids"] == [] and undo["completed_count"] == 0
    assert "checklist_completed" not in client.get(f"/api/reports/{rid}").json()
    assert client.get("/api/metrics").json()["checklist"]["items_completed"] == 0


def test_checklist_needs_review_accepts_only_verified_items(api):
    client = api(needs_review_factory)
    rec = stored_record(client)
    rid, report = rec["report_id"], rec["report"]
    verified = report["verification"]["verified_item_ids"]
    items = report["recommended_actions"]["items"]
    rejected = [i["id"] for i in items if "aspirin" in i["text"].lower()]
    assert verified and rejected

    assert_envelope(tick(client, rid, rejected[0]), 404, "not_found")
    assert "checklist_completed" not in client.get(f"/api/reports/{rid}").json()  # nothing stored

    ok = tick(client, rid, verified[0])
    assert ok.status_code == 200 and ok.json()["available_count"] == len(verified)
    m = client.get("/api/metrics").json()
    assert m["checklist"] == {"items_completed": 1, "items_available": len(verified), "reports_with_progress": 1}
    assert m["assessments_completed"] == 0
    assert m["pct_recommendations_verified"] == round(100 * len(verified) / len(items), 1)


def test_checklist_errors(api):
    client = api(incomplete_factory)
    rid = stored_record(client)["report_id"]
    assert_envelope(tick(client, rid, "hh-during-cooling-1"), 404, "not_found")  # incomplete: nothing renderable
    assert_envelope(tick(client, "0" * 32, "hh-during-cooling-1"), 404, "not_found")
    extra = client.post(f"/api/reports/{rid}/checklist",
                        json={"item_id": "hh-during-cooling-1", "completed": True, "name": "A person"})
    err = assert_envelope(extra, 422, "validation_error")
    assert any(f["field"] == "name" for f in err["fields"])
    assert_envelope(tick(client, rid, "../etc"), 422, "validation_error")
    assert_envelope(client.post(f"/api/reports/{rid}/checklist", json={"item_id": "x"}), 422, "validation_error")


def test_localized_guidance_counts_hindi_request(api):
    client = api(default_factory=True)
    body = {"place": {"name": "demo-hot-dry"}, "forecast_days": 3,
            "profile": {"elderly": True, "preferred_language": "hi"}}
    plan = stored_record(client, body)["report"]["recommended_actions"]
    assert plan["language"] == "en" and plan["requested_language"] == "hi"
    assert client.get("/api/metrics").json()["localized_guidance"] == {
        "served_in_requested_language": 0, "english_fallback": 1, "by_requested_language": {"hi": 1}}


def test_evaluation_endpoint(api, tmp_path):
    from backend.evaluation.results import EvaluationResults

    path = tmp_path / "eval" / "evaluation-results.json"
    client = api(settings=make_settings(evaluation_results_path=str(path)))
    assert_envelope(client.get("/api/evaluation"), 404, "not_found")
    path.parent.mkdir()
    path.write_text(EvaluationResults().model_dump_json(), encoding="utf-8")
    body = client.get("/api/evaluation").json()
    assert body["synthetic"] is True and body["runs"] == {"offline": None, "live": None}
    packaged = api().get("/api/evaluation").json()  # default: the generated file shipped in backend/
    assert packaged["schema_version"] == "heatwise-eval-results-v1" and packaged["runs"]["offline"]["mode"] == "offline"


def test_health_demo_and_bedrock(api):
    h = api().get("/api/health").json()
    assert h["status"] == "ok" and h["agent_mode"] == "offline" and h["weather_provider"] == "demo"
    assert h["demo_locations"] == list(DEMO_LOCATIONS) and "model_id" not in h and h["version"]
    live = api(settings=Settings(_env_file=None)).get("/api/health").json()
    assert live["agent_mode"] == "bedrock" and live["model_id"] and "demo_locations" not in live


def test_cors_preflight(api):
    client = api()
    headers = {"Access-Control-Request-Method": "POST", "Access-Control-Request-Headers": "Content-Type"}
    ok = client.options("/api/assessments", headers={**headers, "Origin": "http://localhost:5173"})
    assert ok.status_code == 200 and ok.headers["access-control-allow-origin"] == "http://localhost:5173"
    bad = client.options("/api/assessments", headers={**headers, "Origin": "http://evil.example"})
    assert "access-control-allow-origin" not in bad.headers
    simple = client.get("/api/health", headers={"Origin": "http://evil.example"})
    assert "access-control-allow-origin" not in simple.headers


def test_default_offline_factory_end_to_end(api):
    client = api(default_factory=True)
    body = {"place": {"name": "demo-hot-dry"}, "forecast_days": 3, "profile": {"elderly": True}}
    job = wait_for(client, submit(client, body).json()["job_id"])
    assert job["status"] == "succeeded", job
    report = job["report"]
    assert report["status"] == "complete" and report["weather_source"]["data_mode"] == "demo"
    assert report["current_conditions"]["temperature_c"] is not None
    assert len(report["forecast"]["days"]) == 3
