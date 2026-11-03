"""Run an assessment on the deployed AgentCore Runtime instead of in-process (AGENT_MODE=agentcore).

The worker Lambda uses this so the agents (coordinator plus four specialists) run only on
Amazon Bedrock AgentCore Runtime. It sends the validated AssessmentRequest as the runtime
payload (the same contract as backend/agentcore_handler.py) and parses the PreparednessReport
it returns. Job state, storage and the HTTP API are unchanged.
"""

from __future__ import annotations

import json
import logging
from typing import Any

from botocore.config import Config

from backend.api.schemas import AssessmentRequest
from backend.config import Settings
from backend.models.report import PreparednessReport
from backend.models.risk import CommunityProfile

logger = logging.getLogger("heatwise.agentcore_client")

# runtimeSessionId must be at least 33 characters; a job id is 32 hex characters.
_SESSION_PREFIX = "heatwise-job-"


class AgentCoreInvocationError(RuntimeError):
    """The runtime call failed or returned something that is not a report."""


def runtime_session_id(job_or_session_id: str | None) -> str | None:
    if not job_or_session_id:
        return None
    sid = job_or_session_id if job_or_session_id.startswith(_SESSION_PREFIX) else _SESSION_PREFIX + job_or_session_id
    return sid if len(sid) >= 33 else sid.ljust(33, "0")


class AgentCoreCoordinator:
    """Drop-in for HeatWiseCoordinator in run_fn: `.run(...)` returns a PreparednessReport."""

    def __init__(self, settings: Settings, request: AssessmentRequest, client: Any | None = None) -> None:
        if not settings.agentcore_runtime_arn:
            raise ValueError("AGENTCORE_RUNTIME_ARN is required when AGENT_MODE=agentcore.")
        self.settings = settings
        self.request = request
        self._client = client

    @property
    def client(self) -> Any:
        if self._client is None:
            import boto3

            # One attempt: a retried invoke would start a second, billable agent run.
            self._client = boto3.client(
                "bedrock-agentcore", region_name=self.settings.aws_region,
                config=Config(read_timeout=self.settings.agentcore_timeout_seconds, connect_timeout=10,
                              retries={"max_attempts": 1, "mode": "standard"}))
        return self._client

    def run(self, location: str, profile: CommunityProfile | None = None, forecast_days: int = 3,
            session_id: str | None = None) -> PreparednessReport:
        # The request is already validated by the API; send it unchanged (location/profile/days come from it).
        payload = self.request.model_dump(mode="json")
        kwargs: dict[str, Any] = {"agentRuntimeArn": self.settings.agentcore_runtime_arn,
                                  "payload": json.dumps(payload).encode("utf-8")}
        sid = runtime_session_id(session_id)
        if sid:
            kwargs["runtimeSessionId"] = sid
        try:
            resp = self.client.invoke_agent_runtime(**kwargs)
            raw = resp["response"].read()
        except Exception as exc:  # botocore ClientError, timeouts, connection errors
            logger.error("agentcore invoke failed: %s", type(exc).__name__)
            raise AgentCoreInvocationError(f"AgentCore invocation failed: {type(exc).__name__}") from exc
        status = resp.get("statusCode", 200)
        if status != 200:
            raise AgentCoreInvocationError(f"AgentCore runtime returned HTTP {status}.")
        try:
            body = json.loads(raw)
        except (TypeError, ValueError) as exc:
            raise AgentCoreInvocationError("AgentCore runtime returned a non-JSON response.") from exc
        if not isinstance(body, dict) or "report_id" not in body:
            # The entrypoint raised (for example a validation error) or returned an error object.
            logger.error("agentcore runtime returned no report: %s", str(body)[:300])
            raise AgentCoreInvocationError("AgentCore runtime returned no report.")
        return PreparednessReport.model_validate(body)
