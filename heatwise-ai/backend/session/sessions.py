"""Strands session managers for the coordinator conversation (Milestone 4, D-M4-5).

A session holds only the coordinator agent's conversation: the place, the community-level
indicators from the prompt, and the compact JSON step summaries returned by its tools.
Raw weather payloads stay inside the specialist agents (they have no session manager), and
no personal data is ever stored. Storage is a local directory (`file`, default) or an S3
prefix (`s3`); `none` disables sessions.
"""

from __future__ import annotations

from strands.session import FileSessionManager, S3SessionManager, SessionManager

from backend.config import Settings


def build_session_manager(settings: Settings, session_id: str) -> SessionManager | None:
    """Return the configured session manager for `session_id`, or None when disabled.

    Constructing a Strands session manager reads (or creates) the session straight away.
    """
    if settings.session_storage == "none":
        return None
    if settings.session_storage == "s3":
        if not settings.session_bucket:
            raise ValueError("SESSION_BUCKET is required when SESSION_STORAGE=s3.")
        return S3SessionManager(session_id=session_id, bucket=settings.session_bucket,
                                prefix=settings.session_prefix, region_name=settings.aws_region)
    return FileSessionManager(session_id=session_id, storage_dir=settings.session_dir)
