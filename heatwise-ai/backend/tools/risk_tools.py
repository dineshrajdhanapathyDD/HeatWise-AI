"""Risk tools for the Community Risk Agent.

The tools take no model-supplied arguments: they read the weather result and
community profile bound by the agent for this request, so the model cannot
alter the inputs to the rules.
"""

from __future__ import annotations

from dataclasses import dataclass
from typing import Callable

from strands import tool

from backend.models.risk import CommunityProfile
from backend.models.weather import WeatherIntelligenceResult
from backend.services.risk_rules import classify, rules_table
from backend.tools.weather_tools import tool_error

RISK_TOOL_NAMES = ("classify_heat_risk", "get_risk_rules")


@dataclass
class RiskContext:
    weather: WeatherIntelligenceResult | None
    profile: CommunityProfile
    min_indicators: int


def build_risk_tools(get_context: Callable[[], RiskContext | None]) -> list:
    @tool
    def classify_heat_risk():
        """Classify community heat risk for the current request using deterministic rules.

        Uses the retrieved weather (current heat index and forecast maximum temperature) and the
        community profile. Returns the risk category, heat index, heat index band, IMD indication,
        contributing factors, confidence and missing data. The category is final; do not change it.
        """
        ctx = get_context()
        if ctx is None:
            return tool_error("invalid_argument", "No weather data is bound to this request.")
        return classify(ctx.weather, ctx.profile, ctx.min_indicators)

    @tool
    def get_risk_rules():
        """Get the heat-risk rule tables: NWS heat index bands, IMD actual-maximum criteria,
        the category scale, the project vulnerability heuristic and the source URLs."""
        return rules_table()

    return [classify_heat_risk, get_risk_rules]
