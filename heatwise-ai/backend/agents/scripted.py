"""A deterministic Strands `Model` for offline agent runs (tests and AGENT_MODE=offline demos).

It replays scripted assistant turns as real Converse-style stream events, so the
actual SDK event loop, tool executor, hooks and structured output run unchanged.
Only the LLM is replaced.
"""

from __future__ import annotations

import itertools
import json
from typing import Any, AsyncGenerator

from strands.models import Model

_ids = itertools.count(1)


def tool_call(name: str, **tool_input: Any) -> dict[str, Any]:
    return {"type": "tool", "name": name, "input": tool_input}


def text(content: str) -> dict[str, Any]:
    return {"type": "text", "text": content}


class ScriptedModel(Model):
    """Each entry in `turns` is one assistant message: a list of tool_call()/text() blocks."""

    def __init__(self, turns: list[list[dict[str, Any]]]) -> None:
        self.turns = list(turns)
        self.calls: list[dict[str, Any]] = []
        self.config: dict[str, Any] = {"model_id": "scripted"}

    def update_config(self, **model_config: Any) -> None:
        self.config.update(model_config)

    def get_config(self) -> dict[str, Any]:
        return self.config

    async def structured_output(self, output_model, prompt, system_prompt=None, **kwargs):  # pragma: no cover
        raise NotImplementedError("Agent structured output uses the tool path, not this method.")
        yield  # noqa

    async def stream(self, messages, tool_specs=None, system_prompt=None, **kwargs) -> AsyncGenerator[dict, None]:
        self.calls.append({
            "tool_names": [s["name"] for s in (tool_specs or [])],
            "tool_choice": kwargs.get("tool_choice"),
            "n_messages": len(messages),
        })
        blocks = self.turns.pop(0) if self.turns else [text("Done.")]

        yield {"messageStart": {"role": "assistant"}}
        has_tool = False
        for block in blocks:
            if block["type"] == "text":
                yield {"contentBlockStart": {"start": {}}}
                yield {"contentBlockDelta": {"delta": {"text": block["text"]}}}
                yield {"contentBlockStop": {}}
            else:
                has_tool = True
                yield {"contentBlockStart": {"start": {"toolUse": {
                    "name": block["name"], "toolUseId": f"tooluse_{next(_ids)}"}}}}
                yield {"contentBlockDelta": {"delta": {"toolUse": {"input": json.dumps(block["input"])}}}}
                yield {"contentBlockStop": {}}
        yield {"messageStop": {"stopReason": "tool_use" if has_tool else "end_turn"}}
        yield {"metadata": {"usage": {"inputTokens": 1, "outputTokens": 1, "totalTokens": 2},
                            "metrics": {"latencyMs": 1}}}
