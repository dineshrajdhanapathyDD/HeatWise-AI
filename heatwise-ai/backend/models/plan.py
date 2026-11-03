"""Preparedness plan models.

Plans are assembled in code from catalog items the planner model selected (or the
deterministic fill). The model only writes the short intro (`PlanIntro`).
"""

from __future__ import annotations

from typing import Literal

from pydantic import BaseModel, Field

_AUDIENCE_TITLES = {"household": "Households", "outdoor_worker": "Outdoor workers", "farmer": "Farmers"}
_PHASE_TITLES = {"before": "Before the heat", "during": "During the heat", "after": "After the heat"}


class PlanItem(BaseModel):
    id: str
    audience: str
    phase: str
    topic: str
    text: str
    source_ids: list[str] = Field(default_factory=list)
    kind: Literal["sourced", "general_educational"] = "sourced"
    added_by: Literal["agent", "rules"] = "agent"


class ChecklistItem(BaseModel):
    id: str
    audience: str
    phase: str
    text: str
    done: bool = False


class PreparednessPlan(BaseModel):
    status: Literal["ok", "skipped"]
    language: str = "en"
    requested_language: str = "en"
    language_notice: str | None = None
    risk_category: str
    intro: str | None = None
    intro_source: Literal["model", "rules"] | None = None
    items: list[PlanItem] = Field(default_factory=list)
    checklist: list[ChecklistItem] = Field(default_factory=list)
    revision: int = 0
    issues: list[str] = Field(default_factory=list, description="Rejected model output or agent failures")

    def checklist_markdown(self, verified_item_ids: list[str] | None = None,
                           review_notices: list[str] | None = None) -> str:
        """Markdown checklist. When `verified_item_ids` is given (plan failed verification),
        only those items are listed, under a "Not verified - needs human review" banner."""
        lines = ["# Heatwave preparedness checklist", ""]
        checklist = self.checklist
        if verified_item_ids is not None:
            keep = set(verified_item_ids)
            checklist = [c for c in self.checklist if c.id in keep]
            lines += ["**Not verified - needs human review.** Only items that passed automated safety checks "
                      "are listed.", ""]
            lines += [f"_{n}_" for n in (review_notices or [])]
            if review_notices:
                lines.append("")
        if self.language_notice:
            lines += [f"_{self.language_notice}_", ""]
        audiences = list(dict.fromkeys(c.audience for c in checklist))
        for audience in audiences:
            lines += [f"## {_AUDIENCE_TITLES.get(audience, audience)}", ""]
            for phase in _PHASE_TITLES:
                entries = [c for c in checklist if c.audience == audience and c.phase == phase]
                if not entries:
                    continue
                lines.append(f"### {_PHASE_TITLES[phase]}")
                lines += [f"- [{'x' if c.done else ' '}] {c.text}" for c in entries]
                lines.append("")
        return "\n".join(lines).rstrip() + "\n"


class PlanIntro(BaseModel):
    """Structured output for the planner model. Kept flat on purpose."""

    intro: str = Field(description="Two or three plain sentences introducing the preparedness plan")
