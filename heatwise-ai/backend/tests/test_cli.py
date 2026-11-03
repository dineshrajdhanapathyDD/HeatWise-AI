"""Offline tests for `heatwise assess`: the coordinator is replaced by one that returns prepared reports."""

from __future__ import annotations

import json

import pytest

from backend import cli
from backend.tests.scripted_model import text, tool_call
from backend.tests.test_coordinator import DELEGATIONS, PROFILE, UNSAFE_PLAN, REVIEW, build, calls


def scripted_report(settings, kind: str):
    if kind == "complete":
        coord, _ = build(settings, calls(*DELEGATIONS, "finalize_report"))
    elif kind == "needs_human_review":
        coord, _ = build(settings, [[tool_call("weather_intelligence")], [text("Stop.")]],
                         planner_turns=UNSAFE_PLAN + UNSAFE_PLAN, safety_turns=REVIEW + REVIEW)
    else:
        from backend.services.weather.base import ProviderTimeoutError
        from backend.tests.fakes import FakeProvider
        provider = FakeProvider(fail={"current": ProviderTimeoutError("slow"),
                                      "forecast": ProviderTimeoutError("slow")})
        coord, _ = build(settings, calls("weather_intelligence", "finalize_report"), provider=provider)
    return coord.run("Wardha", PROFILE, 3)


@pytest.fixture
def fake_coordinator(monkeypatch, settings):
    seen: dict = {}

    def install(report):
        class FakeCoordinator:
            def __init__(self, s):
                seen["settings"] = s

            def run(self, location, profile, days):
                seen.update(location=location, profile=profile, days=days)
                return report

        monkeypatch.setattr(cli, "HeatWiseCoordinator", FakeCoordinator)
        monkeypatch.setattr(cli, "get_settings", lambda: settings)
        return seen

    return install


@pytest.mark.parametrize("kind,code", [("complete", 0), ("needs_human_review", 2), ("incomplete", 1)])
def test_assess_exit_codes_and_json(settings, fake_coordinator, capsys, kind, code):
    report = scripted_report(settings, kind)
    assert report.status == kind
    fake_coordinator(report)
    assert cli.main(["assess", "Wardha"]) == code
    out, err = capsys.readouterr()
    assert json.loads(out)["status"] == kind
    assert "=== trace" in err and f"status:              {kind}" in err


def test_assess_flags_and_checklist_out(settings, fake_coordinator, capsys, tmp_path):
    report = scripted_report(settings, "complete")
    seen = fake_coordinator(report)
    path = tmp_path / "checklist.md"
    argv = ["assess", "Nagpur, Maharashtra", "--days", "2", "--elderly", "--outdoor-workers", "--farmers",
            "--limited-water", "--terrain", "plains", "--language", "hi", "--checklist-out", str(path)]
    assert cli.main(argv) == 0
    profile = seen["profile"]
    assert seen["location"] == "Nagpur, Maharashtra" and seen["days"] == 2
    assert profile.indicators() == ["elderly", "outdoor_workers", "farmers", "limited_water_access"]
    assert profile.terrain == "plains" and profile.preferred_language == "hi"
    assert path.read_text(encoding="utf-8") == report.recommended_actions.checklist_markdown()
    assert "checklist written" in capsys.readouterr().err


def test_assess_needs_review_exports_only_verified_items(settings, fake_coordinator, capsys, tmp_path):
    report = scripted_report(settings, "needs_human_review")
    fake_coordinator(report)
    path = tmp_path / "checklist.md"
    assert cli.main(["assess", "Wardha", "--checklist-out", str(path)]) == 2
    md = path.read_text(encoding="utf-8")
    assert md == report.checklist_markdown
    assert "Not verified - needs human review" in md and "aspirin" not in md.lower()
    assert "verified items only" in capsys.readouterr().err


def test_assess_incomplete_does_not_write_checklist(settings, fake_coordinator, capsys, tmp_path):
    fake_coordinator(scripted_report(settings, "incomplete"))
    path = tmp_path / "checklist.md"
    assert cli.main(["assess", "Wardha", "--checklist-out", str(path)]) == 1
    assert not path.exists()
    assert "checklist not written" in capsys.readouterr().err
