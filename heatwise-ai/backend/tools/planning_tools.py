"""Planning tools for the Preparedness Action Planner Agent.

The model chooses catalog items by id; the plan is later assembled in code from
the evidence ledger (successful `select_guidance` / `add_general_advice` calls),
so the model cannot change verified guidance text.
"""

from __future__ import annotations

import json
from dataclasses import dataclass
from typing import Callable

from strands import tool

from backend.guidance.catalog import AUDIENCES, CATALOG, PHASES, catalog_for
from backend.tools.weather_tools import tool_error

PLANNING_TOOL_NAMES = ("list_guidance", "select_guidance", "add_general_advice")
GENERAL_ADVICE_MAX_CHARS = 300


@dataclass
class PlanningContext:
    risk_category: str
    audiences: tuple[str, ...]
    max_general_advice: int
    general_advice_count: int = 0


def _check_audience_phase(ctx: PlanningContext, audience: str, phase: str, allow_all: bool = False) -> str | None:
    if audience not in AUDIENCES:
        return f"Unknown audience '{audience}'. Use one of: {', '.join(AUDIENCES)}."
    if audience not in ctx.audiences:
        return f"Audience '{audience}' is not part of this plan. Plan audiences: {', '.join(ctx.audiences)}."
    phases = (*PHASES, "all") if allow_all else PHASES
    if phase not in phases:
        return f"Unknown phase '{phase}'. Use one of: {', '.join(phases)}."
    return None


def build_planning_tools(get_context: Callable[[], PlanningContext | None]) -> list:
    @tool
    def list_guidance(audience: str, phase: str = "all"):
        """List verified guidance items for one audience, from the HeatWise guidance catalog.

        Returns item ids, topics and texts that apply at the current risk category. Only these ids
        may be passed to select_guidance.

        Args:
            audience: household, outdoor_worker or farmer.
            phase: before, during, after, or all.
        """
        ctx = get_context()
        if ctx is None:
            return tool_error("invalid_argument", "No plan request is bound to this call.")
        problem = _check_audience_phase(ctx, audience, phase, allow_all=True)
        if problem:
            return tool_error("invalid_argument", problem)
        items = catalog_for(audience, None if phase == "all" else phase, ctx.risk_category)
        return json.dumps({"audience": audience, "phase": phase,
                           "items": [{"id": i.id, "phase": i.phase, "topic": i.topic, "text": i.text}
                                     for i in items]})

    @tool
    def select_guidance(audience: str, phase: str, guidance_ids: str):
        """Add verified catalog items to the plan for one audience and phase.

        Args:
            audience: household, outdoor_worker or farmer.
            phase: before, during or after.
            guidance_ids: Comma-separated catalog ids from list_guidance, e.g. "hh-during-hydration-1,hh-during-rest-1".
        """
        ctx = get_context()
        if ctx is None:
            return tool_error("invalid_argument", "No plan request is bound to this call.")
        problem = _check_audience_phase(ctx, audience, phase)
        if problem:
            return tool_error("invalid_argument", problem)
        ids = list(dict.fromkeys(x.strip() for x in (guidance_ids or "").split(",") if x.strip()))
        if not ids:
            return tool_error("invalid_argument", "guidance_ids is empty. Pass comma-separated ids from list_guidance.")
        allowed = {i.id for i in catalog_for(audience, phase, ctx.risk_category)}
        unknown = [x for x in ids if x not in allowed]
        if unknown:
            known_elsewhere = [x for x in unknown if x in CATALOG]
            hint = (" Some ids exist but belong to another audience/phase or do not apply at this risk level."
                    if known_elsewhere else "")
            return tool_error("invalid_argument",
                              f"Unknown guidance ids for {audience}/{phase}: {', '.join(unknown)}.{hint} "
                              "Nothing was selected; use only ids from list_guidance.")
        return json.dumps({"audience": audience, "phase": phase, "selected": ids})

    @tool
    def add_general_advice(audience: str, phase: str, text: str):
        """Add one short general educational note that is not in the catalog. Use sparingly.

        The note is marked as general educational content without a source and is checked by the
        Safety Agent. No medicines, doses, diagnoses, phone numbers or claims about alerts.

        Args:
            audience: household, outdoor_worker or farmer.
            phase: before, during or after.
            text: The note, at most 300 characters.
        """
        ctx = get_context()
        if ctx is None:
            return tool_error("invalid_argument", "No plan request is bound to this call.")
        problem = _check_audience_phase(ctx, audience, phase)
        if problem:
            return tool_error("invalid_argument", problem)
        note = (text or "").strip()
        if not note:
            return tool_error("invalid_argument", "text is empty.")
        if len(note) > GENERAL_ADVICE_MAX_CHARS:
            return tool_error("invalid_argument",
                              f"text is {len(note)} characters; the limit is {GENERAL_ADVICE_MAX_CHARS}.")
        if ctx.general_advice_count >= ctx.max_general_advice:
            return tool_error("invalid_argument",
                              f"General advice limit ({ctx.max_general_advice}) reached. Use catalog items instead.")
        ctx.general_advice_count += 1
        return json.dumps({"audience": audience, "phase": phase, "text": note})

    return [list_guidance, select_guidance, add_general_advice]
