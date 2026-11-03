"""AGENT_MODE=agentcore: the worker invokes AgentCore Runtime. Offline, with a stub client."""

from __future__ import annotations

import io
import json

import pytest

from backend.agents.agentcore_client import AgentCoreCoordinator, AgentCoreInvocationError, runtime_session_id
from backend.agentcore_handler import run_assessment
from backend.api.app import default_coordinator_factory, make_run_fn
from backend.api.schemas import AssessmentRequest
from backend.config import Settings

ARN = "arn:aws:bedrock-agentcore:us-east-1:111122223333:runtime/HeatWiseAC_heatwise_agent-abc123"
REQ = AssessmentRequest.model_validate(
    {"place": {"name": "demo-hot-dry"}, "forecast_days": 3, "profile": {"elderly": True, "farmers": True}})


def offline_report() -> dict:
    """A real report produced by the runtime entrypoint logic (scripted agents, demo weather)."""
    s = Settings(_env_file=None, agent_mode="offline", weather_provider="demo", session_storage="none")
    return run_assessment(REQ.model_dump(mode="json"), None, settings=s)


class StubClient:
    def __init__(self, body: bytes | None = None, status: int = 200, exc: Exception | None = None):
        self.body, self.status, self.exc, self.calls = body, status, exc, []

    def invoke_agent_runtime(self, **kwargs):
        self.calls.append(kwargs)
        if self.exc:
            raise self.exc
        return {"statusCode": self.status, "response": io.BytesIO(self.body or b"")}


def settings(**kw) -> Settings:
    return Settings(_env_file=None, agent_mode="agentcore", agentcore_runtime_arn=ARN, **kw)


def test_run_sends_request_and_parses_report():
    report = offline_report()
    stub = StubClient(json.dumps(report).encode())
    out = AgentCoreCoordinator(settings(), REQ, client=stub).run(REQ.location, session_id="a" * 32)
    assert out.report_id == report["report_id"] and out.status == report["status"]
    call = stub.calls[0]
    assert call["agentRuntimeArn"] == ARN
    assert json.loads(call["payload"]) == REQ.model_dump(mode="json")
    assert call["runtimeSessionId"] == "heatwise-job-" + "a" * 32 and len(call["runtimeSessionId"]) >= 33


def test_session_id_is_long_enough():
    assert runtime_session_id(None) is None
    assert len(runtime_session_id("x")) >= 33
    assert runtime_session_id("heatwise-job-" + "b" * 32) == "heatwise-job-" + "b" * 32


@pytest.mark.parametrize("stub, msg", [
    (StubClient(exc=TimeoutError("read timed out")), "invocation failed"),
    (StubClient(b"{}", status=500), "HTTP 500"),
    (StubClient(b"not json"), "non-JSON"),
    (StubClient(json.dumps({"error": "validation"}).encode()), "no report"),
])
def test_failures_raise(stub, msg):
    with pytest.raises(AgentCoreInvocationError, match=msg):
        AgentCoreCoordinator(settings(), REQ, client=stub).run(REQ.location, session_id="c" * 32)


def test_requires_runtime_arn():
    with pytest.raises(ValueError, match="AGENTCORE_RUNTIME_ARN"):
        AgentCoreCoordinator(Settings(_env_file=None, agent_mode="agentcore"), REQ)


def test_factory_and_run_fn_use_agentcore(monkeypatch):
    report = offline_report()
    stub = StubClient(json.dumps(report).encode())
    monkeypatch.setattr(AgentCoreCoordinator, "client", property(lambda self: stub))
    s = settings()
    assert isinstance(default_coordinator_factory(s)(REQ), AgentCoreCoordinator)
    out = make_run_fn(s)(REQ, "d" * 32)
    assert out.report_id == report["report_id"]
    assert len(stub.calls) == 1  # exactly one runtime invocation per job (no retries)
