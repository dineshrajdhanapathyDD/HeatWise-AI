"""Strands session managers for the coordinator (offline: tmp dirs and moto S3 only)."""

from __future__ import annotations

import json
import uuid
from pathlib import Path

import boto3
import pytest
from strands.session import FileSessionManager, S3SessionManager

from backend.config import Settings
from backend.session.sessions import build_session_manager
from backend.tests.aws_fixtures import REGION, aws, aws_credentials, create_bucket  # noqa: F401
from backend.tests.test_coordinator import DELEGATIONS, PROFILE, build, calls

BUCKET = "heatwise-test-sessions"


def run_once(settings: Settings, session_id: str | None):
    coord, _ = build(settings, calls(*DELEGATIONS, "finalize_report"))
    return coord.run("Wardha", PROFILE, 3, session_id=session_id)


def messages(settings: Settings, sid: str) -> list[dict]:
    mgr = FileSessionManager(session_id=sid, storage_dir=settings.session_dir)
    return [m.message for m in mgr.list_messages(sid, "coordinator")]


def tool_uses(msgs: list[dict]) -> list[str]:
    return [c["toolUse"]["name"] for m in msgs for c in m.get("content", []) if "toolUse" in c]


def test_session_dir_points_at_tmp(settings, tmp_path):
    assert Path(settings.session_dir) == tmp_path / "sessions"


def test_file_selection_writes_under_session_dir(settings):
    sid = uuid.uuid4().hex
    mgr = build_session_manager(settings, sid)
    assert isinstance(mgr, FileSessionManager)
    assert (Path(settings.session_dir) / f"session_{sid}").is_dir()


def test_none_selection():
    s = Settings(_env_file=None, session_storage="none")
    assert build_session_manager(s, uuid.uuid4().hex) is None


def test_s3_without_bucket_is_rejected():
    s = Settings(_env_file=None, session_storage="s3")
    with pytest.raises(ValueError, match="SESSION_BUCKET"):
        build_session_manager(s, uuid.uuid4().hex)


def test_s3_selection(aws):  # noqa: F811
    create_bucket(BUCKET)
    s = Settings(_env_file=None, session_storage="s3", session_bucket=BUCKET, aws_region=REGION)
    assert isinstance(build_session_manager(s, uuid.uuid4().hex), S3SessionManager)


def test_file_session_continuity(settings):
    sid, other = uuid.uuid4().hex, uuid.uuid4().hex
    first = run_once(settings, sid)
    assert first.status == "complete"
    after_first = messages(settings, sid)
    assert after_first and after_first[0]["role"] == "user"
    assert "Location: Wardha" in after_first[0]["content"][0]["text"]

    second = run_once(settings, sid)  # fresh coordinator, same session id: history is restored
    assert second.status == "complete"
    after_second = messages(settings, sid)
    assert len(after_second) > len(after_first)
    assert after_second[:len(after_first)] == after_first
    assert after_second[0] == after_first[0]

    assert not (Path(settings.session_dir) / f"session_{other}").exists()
    run_once(settings, other)  # another id starts empty: it holds one run only
    assert len(messages(settings, other)) == len(after_first)
    # Only the coordinator's delegations are stored; raw weather tool calls stay in the specialists.
    used = tool_uses(after_second)
    assert set(used) == {*DELEGATIONS, "finalize_report"}
    assert "get_weather" not in used and "get_forecast" not in used
    assert "temperature_2m" not in json.dumps(after_second)


def test_no_session_id_writes_nothing(settings):
    run_once(settings, None)
    root = Path(settings.session_dir)
    assert not root.exists() or not any(root.iterdir())


def test_s3_session_continuity(aws):  # noqa: F811
    create_bucket(BUCKET)
    s = Settings(_env_file=None, session_storage="s3", session_bucket=BUCKET, aws_region=REGION)
    sid = uuid.uuid4().hex
    run_once(s, sid)
    prefix = f"sessions/session_{sid}/agents/agent_coordinator/messages/"
    s3 = boto3.client("s3", region_name=REGION)

    def keys() -> list[str]:
        return [o["Key"] for o in s3.list_objects_v2(Bucket=BUCKET, Prefix=prefix).get("Contents", [])]

    first = len(keys())
    assert first > 0
    run_once(s, sid)
    assert len(keys()) > first
    mgr = S3SessionManager(session_id=sid, bucket=BUCKET, prefix="sessions", region_name=REGION)
    msgs = [m.message for m in mgr.list_messages(sid, "coordinator")]
    assert "Location: Wardha" in msgs[0]["content"][0]["text"]
