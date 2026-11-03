"""A deterministic Strands `Model` for offline agent tests.

The implementation lives in `backend.agents.scripted` (also used by AGENT_MODE=offline);
this module re-exports it so existing test imports keep working.
"""

from backend.agents.scripted import ScriptedModel, text, tool_call  # noqa: F401
