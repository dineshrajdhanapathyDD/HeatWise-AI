"""Execution trace records captured by hooks."""

from __future__ import annotations

from typing import Any, Literal

from pydantic import BaseModel, Field


class ToolCallRecord(BaseModel):
    agent: str
    tool: str
    tool_use_id: str
    input_summary: dict[str, Any] = Field(default_factory=dict)
    status: Literal["success", "error", "cancelled"]
    duration_ms: float | None = None
    cancel_reason: str | None = None
    payload: Any = Field(default=None, description="Parsed tool result payload (JSON if possible)")
