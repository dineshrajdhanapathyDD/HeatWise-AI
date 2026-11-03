"""Which plan items may be ticked off as checklist items (D-M5-9).

Backend twin of `frontend/src/lib/safety.ts` `renderablePlanItems` (D-M3-9): only items the
dashboard may render as advice can carry checklist progress.
"""

from __future__ import annotations

from backend.models.report import PreparednessReport


def renderable_item_ids(report: PreparednessReport) -> list[str]:
    """complete: every plan item; needs_human_review: verified items only; otherwise none."""
    items = report.recommended_actions.items if report.recommended_actions is not None else []
    if report.status == "complete":
        return [i.id for i in items]
    if report.status == "needs_human_review":
        verified = set(report.verification.verified_item_ids if report.verification is not None else [])
        return [i.id for i in items if i.id in verified]
    return []
