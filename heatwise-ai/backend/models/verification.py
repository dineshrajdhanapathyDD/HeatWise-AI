"""Safety and verification models.

Pass/fail is decided only by deterministic checks (`run_checks`). The optional LLM
review (`SafetyReview`) can only add non-blocking concerns.
"""

from __future__ import annotations

from typing import Literal

from pydantic import BaseModel, Field


class CheckResult(BaseModel):
    name: str
    passed: bool
    severity: Literal["error", "warning"] = "error"
    message: str
    item_id: str | None = None


class VerificationResult(BaseModel):
    status: Literal["passed", "failed"]
    checks: list[CheckResult] = Field(default_factory=list)
    issues: list[str] = Field(default_factory=list, description="Messages of failed error-severity checks")
    warnings: list[str] = Field(default_factory=list, description="Messages of failed warning-severity checks")
    llm_concerns: list[str] = Field(default_factory=list, description="Non-blocking concerns from the LLM review")
    verified_item_ids: list[str] = Field(default_factory=list)
    pct_items_verified: float = 0.0


class SafetyReview(BaseModel):
    """Structured output for the Safety Agent's optional LLM review. Kept flat on purpose."""

    concern: str | None = Field(
        default=None,
        description="One sentence describing a safety concern with the plan, or null if there is none",
    )
