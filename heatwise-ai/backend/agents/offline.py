"""Offline coordinator for AGENT_MODE=offline: scripted agents, no Bedrock.

For offline demos and tests only. Every agent runs the real Strands loop with a
`ScriptedModel` whose turns are generated from the job's location and days, against
the configured weather provider (use WEATHER_PROVIDER=demo). The scripts only choose
which tools to call; the deterministic risk rules, the verified guidance catalog, the
safety checks and `build_report` still decide every value in the report.
"""

from __future__ import annotations

from backend.agents.coordinator import COORDINATOR_TOOL_NAMES, HeatWiseCoordinator
from backend.agents.planner_agent import ActionPlannerAgent, plan_audiences
from backend.agents.risk_agent import CommunityRiskAgent
from backend.agents.safety_agent import SafetyVerificationAgent
from backend.agents.scripted import ScriptedModel, text, tool_call
from backend.agents.weather_agent import WeatherIntelligenceAgent
from backend.config import Settings
from backend.models.risk import CommunityProfile
from backend.services.weather.base import WeatherProvider
from backend.services.weather.factory import build_weather_provider

PLAN_AUDIENCES = ("household", "outdoor_worker", "farmer")


def _weather_turns(location: str, days: int) -> list:
    return [
        [tool_call("get_weather", location=location), tool_call("get_forecast", location=location, days=days),
         tool_call("get_weather_alerts", location=location)],
        [tool_call("WeatherSummary", location_name=location,
                   summary="Weather data was retrieved for this location.",
                   claimed_temperature_c=None, claimed_apparent_temperature_c=None, claimed_humidity_pct=None,
                   claimed_max_forecast_temperature_c=None)],
    ]


def _risk_turns() -> list:
    return [
        [tool_call("classify_heat_risk")],
        [tool_call("RiskExplanation", explanation="The community heat risk category was set by the HeatWise "
                                                  "rules from the retrieved weather and the community profile.")],
    ]


def _planner_turns(audiences: tuple[str, ...]) -> list:
    return ([[tool_call("list_guidance", audience=a, phase="all")] for a in audiences]
            + [[tool_call("PlanIntro", intro="This plan lists verified preparedness actions for the community.")]])


def _safety_turns() -> list:
    return [[tool_call("run_safety_checks")], [tool_call("SafetyReview", concern=None)]]


def _coordinator_turns() -> list:
    return [[tool_call(name)] for name in COORDINATOR_TOOL_NAMES] + [[text("The report is ready.")]]


def build_offline_coordinator(settings: Settings, location: str, forecast_days: int,
                              profile: CommunityProfile | None = None,
                              provider: WeatherProvider | None = None) -> HeatWiseCoordinator:
    """A fresh coordinator with scripted models for one run (a ScriptedModel is consumed by one run).

    With a profile, the planner script lists guidance only for that profile's plan audiences
    (the planning tools reject other audiences); without one it lists all three. `provider`
    replaces the configured weather provider (the evaluation passes its synthetic fixtures).
    """
    audiences = plan_audiences(profile) if profile is not None else PLAN_AUDIENCES
    return HeatWiseCoordinator(
        settings,
        weather_agent=WeatherIntelligenceAgent(settings, provider=provider or build_weather_provider(settings),
                                               model=ScriptedModel(_weather_turns(location, forecast_days))),
        risk_agent=CommunityRiskAgent(settings, model=ScriptedModel(_risk_turns())),
        planner_agent=ActionPlannerAgent(settings, model=ScriptedModel(_planner_turns(audiences))),
        safety_agent=SafetyVerificationAgent(settings, model=ScriptedModel(_safety_turns())),
        model=ScriptedModel(_coordinator_turns()),
    )
