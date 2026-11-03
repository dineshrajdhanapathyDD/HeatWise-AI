"""Strands hooks for HeatWise AI (workshop Module 2 pattern).

GuardrailHook   - deterministic pre-tool checks: allowlist, input validation, call cap.
EvidenceLedgerHook - records what every tool actually returned. Agent results are
                     built from this ledger, so the model cannot invent measurements.

Both hooks reset at the start of each invocation (BeforeInvocationEvent).
"""

from __future__ import annotations

import json
import logging
import time
from typing import Any, Callable, Iterable, Mapping

from strands.hooks import (
    AfterToolCallEvent,
    BeforeInvocationEvent,
    BeforeToolCallEvent,
    HookProvider,
    HookRegistry,
)

from backend.models.trace import ToolCallRecord
from backend.services.validation import ValidationError

logger = logging.getLogger("heatwise.hooks")

InputValidator = Callable[[Mapping[str, Any]], None]

# Input keys that are safe to log verbatim. Everything else is logged by type only.
_LOGGABLE_KEYS = {"location", "days", "forecast_days", "audience", "phase", "revision"}


def summarize_input(tool_input: Any) -> dict[str, Any]:
    if not isinstance(tool_input, Mapping):
        return {"_type": type(tool_input).__name__}
    out: dict[str, Any] = {}
    for k, v in tool_input.items():
        if k in _LOGGABLE_KEYS and isinstance(v, (str, int, float)):
            out[k] = v if not isinstance(v, str) else v[:120]
        else:
            out[k] = f"<{type(v).__name__}>"
    return out


class GuardrailHook(HookProvider):
    def __init__(
        self,
        allowed_tools: Iterable[str],
        max_tool_calls: int,
        validators: Mapping[str, InputValidator] | None = None,
        uncounted_tools: Iterable[str] = (),
    ) -> None:
        self.allowed_tools = set(allowed_tools) | set(uncounted_tools)
        self.uncounted_tools = set(uncounted_tools)
        self.max_tool_calls = max_tool_calls
        self.validators = dict(validators or {})
        self.calls = 0
        self.blocked: list[dict[str, str]] = []

    def register_hooks(self, registry: HookRegistry, **kwargs: Any) -> None:
        registry.add_callback(BeforeInvocationEvent, self.reset)
        registry.add_callback(BeforeToolCallEvent, self.check)

    def reset(self, event: BeforeInvocationEvent) -> None:
        self.calls = 0
        self.blocked = []

    def _block(self, event: BeforeToolCallEvent, name: str, reason: str) -> None:
        event.cancel_tool = reason
        self.blocked.append({"tool": name, "reason": reason})
        logger.warning("tool blocked tool=%s reason=%s", name, reason)

    def check(self, event: BeforeToolCallEvent) -> None:
        name = event.tool_use.get("name", "")
        if name not in self.allowed_tools:
            self._block(event, name, f"Tool '{name}' is not approved for this agent. Do not call it.")
            return
        if name not in self.uncounted_tools:
            self.calls += 1
            if self.calls > self.max_tool_calls:
                self._block(
                    event, name,
                    f"Tool call limit ({self.max_tool_calls}) reached for this request. "
                    "Do not call more tools; report with the data you have.",
                )
                return
        validator = self.validators.get(name)
        if validator is not None:
            try:
                validator(event.tool_use.get("input") or {})
            except ValidationError as exc:
                self._block(event, name, f"Invalid input for '{name}': {exc} Fix the input or report the gap.")


class EvidenceLedgerHook(HookProvider):
    """Captures each tool call and its parsed result for evidence and the activity trace."""

    def __init__(self, ignored_tools: Iterable[str] = ()) -> None:
        self.ignored_tools = set(ignored_tools)
        self.records: list[ToolCallRecord] = []
        self._starts: dict[str, float] = {}

    def register_hooks(self, registry: HookRegistry, **kwargs: Any) -> None:
        registry.add_callback(BeforeInvocationEvent, self.reset)
        registry.add_callback(BeforeToolCallEvent, self.start)
        registry.add_callback(AfterToolCallEvent, self.finish)

    def reset(self, event: BeforeInvocationEvent) -> None:
        self.records = []
        self._starts = {}

    def start(self, event: BeforeToolCallEvent) -> None:
        self._starts[event.tool_use.get("toolUseId", "")] = time.perf_counter()

    def finish(self, event: AfterToolCallEvent) -> None:
        tool_use = event.tool_use
        name = tool_use.get("name", "")
        if name in self.ignored_tools:
            return
        tool_use_id = tool_use.get("toolUseId", "")
        started = self._starts.pop(tool_use_id, None)
        duration_ms = (time.perf_counter() - started) * 1000 if started is not None else None

        result = event.result or {}
        cancel_reason = getattr(event, "cancel_message", None)
        if cancel_reason:
            status = "cancelled"
        else:
            status = "success" if result.get("status") == "success" else "error"

        record = ToolCallRecord(
            agent=getattr(event.agent, "name", None) or "agent",
            tool=name,
            tool_use_id=tool_use_id,
            input_summary=summarize_input(tool_use.get("input")),
            status=status,  # type: ignore[arg-type]
            duration_ms=round(duration_ms, 1) if duration_ms is not None else None,
            cancel_reason=cancel_reason,
            payload=_parse_result_payload(result),
        )
        self.records.append(record)
        logger.info(
            "tool call agent=%s tool=%s status=%s duration_ms=%s input=%s",
            record.agent, name, status, record.duration_ms, record.input_summary,
        )

    def successful(self, tool: str) -> list[ToolCallRecord]:
        return [r for r in self.records if r.tool == tool and r.status == "success"]


def _parse_result_payload(result: Mapping[str, Any]) -> Any:
    content = result.get("content") or []
    for block in content:
        if not isinstance(block, Mapping):
            continue
        if "json" in block:
            return block["json"]
        if "text" in block:
            text = block["text"]
            try:
                return json.loads(text)
            except (TypeError, ValueError):
                return text
    return None
