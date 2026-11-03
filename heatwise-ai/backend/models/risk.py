"""Community risk models.

The profile describes a community, not individuals: each indicator means "this
group is present in the community", never a fact about a named person. No
medical inference about individuals is made anywhere in HeatWise.
"""

from __future__ import annotations

from typing import Literal

from pydantic import BaseModel, Field

RiskCategory = Literal["low", "moderate", "high", "very_high", "extreme", "unknown"]
Terrain = Literal["plains", "hilly", "coastal"]

VULNERABILITY_INDICATORS = (
    "elderly",
    "young_children",
    "pregnant_women",
    "chronic_illness_group",
    "outdoor_workers",
    "farmers",
    "limited_water_access",
    "limited_shade_or_cooling",
)


class CommunityProfile(BaseModel):
    """Community-level presence of groups and conditions. Location-free; no personal data."""

    elderly: bool = Field(default=False, description="Older people are present in the community")
    young_children: bool = Field(default=False, description="Infants or young children are present")
    pregnant_women: bool = Field(default=False, description="Pregnant women are present")
    chronic_illness_group: bool = Field(
        default=False, description="People living with chronic illness are present (community level only)"
    )
    outdoor_workers: bool = Field(default=False, description="People who work outdoors are present")
    farmers: bool = Field(default=False, description="Farming households are present")
    limited_water_access: bool = Field(default=False, description="Drinking water access is limited")
    limited_shade_or_cooling: bool = Field(default=False, description="Shade or cooling is limited")
    terrain: Terrain | None = Field(default=None, description="plains, hilly or coastal; null if unknown")
    preferred_language: str = Field(default="en")

    def indicators(self) -> list[str]:
        return [name for name in VULNERABILITY_INDICATORS if getattr(self, name)]


class RiskFactor(BaseModel):
    code: str
    description: str
    value: float | None = None
    unit: str | None = None
    source_id: str | None = None


class RiskAssessment(BaseModel):
    """Deterministic community heat-risk assessment. The category never comes from a model."""

    status: Literal["ok", "insufficient_data"]
    category: RiskCategory
    hazard_score: int | None = Field(default=None, description="0-4 from rules, before the heuristic adjustment")
    heat_index_c: float | None = None
    heat_index_f: float | None = None
    heat_index_band: str | None = None
    imd_indication: Literal["none", "threshold_met", "heat_wave", "severe_heat_wave"] | None = None
    contributing_factors: list[RiskFactor] = Field(default_factory=list)
    vulnerability_indicators: list[str] = Field(default_factory=list)
    heuristic_adjustment_applied: bool = False
    confidence: Literal["high", "medium", "low"]
    missing_data: list[str] = Field(default_factory=list)
    explanation: str | None = None
    explanation_source: Literal["model", "rules"] | None = None
    explanation_issues: list[str] = Field(
        default_factory=list, description="Why a model explanation was rejected, or agent failures"
    )
    rules_version: str
    source_ids: list[str] = Field(default_factory=list)


class RiskExplanation(BaseModel):
    """Structured output for the Community Risk Agent's model. Kept flat on purpose."""

    explanation: str = Field(
        description="Two or three plain sentences explaining the risk category returned by classify_heat_risk"
    )
