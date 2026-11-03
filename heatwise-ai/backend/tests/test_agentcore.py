"""Optional AgentCore entrypoint: logic tested offline (scripted agents + demo weather)."""

from __future__ import annotations

import pytest
from pydantic import ValidationError

from backend.agentcore_handler import run_assessment
from backend.tests.test_api import make_settings

DEMO_BODY = {"place": {"name": "demo-hot-dry"}, "forecast_days": 3, "profile": {"elderly": True}}


def test_run_assessment_offline():
    report = run_assessment(DEMO_BODY, settings=make_settings())
    assert report["status"] == "complete" and len(report["report_id"]) == 32
    assert report["weather_source"]["data_mode"] == "demo"


def test_run_assessment_wrapped_payload():
    report = run_assessment({"request": DEMO_BODY}, settings=make_settings())
    assert report["status"] == "complete" and report["report_id"]


def test_run_assessment_rejects_personal_fields():
    with pytest.raises(ValidationError):
        run_assessment({**DEMO_BODY, "phone": "+910000000000"}, settings=make_settings())


def test_entrypoint_module():
    pytest.importorskip("bedrock_agentcore")
    from backend import agentcore_entry

    assert agentcore_entry.app is not None and callable(agentcore_entry.invoke)
