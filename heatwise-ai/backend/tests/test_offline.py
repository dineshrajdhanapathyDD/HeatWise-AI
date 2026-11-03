"""AGENT_MODE=offline coordinator against the demo weather provider (no network, no Bedrock)."""

from __future__ import annotations

from backend.agents.offline import build_offline_coordinator
from backend.config import Settings
from backend.models.risk import CommunityProfile

ORDER = ["low", "moderate", "high", "very_high", "extreme"]
PROFILE = CommunityProfile(elderly=True, outdoor_workers=True, farmers=True)


def demo_settings() -> Settings:
    return Settings(_env_file=None, weather_provider="demo")


def run(location: str, days: int = 3, profile: CommunityProfile = PROFILE):
    return build_offline_coordinator(demo_settings(), location, days, profile).run(location, profile, days)


def test_offline_planner_lists_only_plan_audiences():
    report = run("demo-hot-dry", profile=CommunityProfile(elderly=True, outdoor_workers=True))
    listed = [t for t in report.trace if t.tool == "list_guidance"]
    assert {t.input_summary["audience"] for t in listed} == {"household", "outdoor_worker"}
    assert all(t.status == "success" for t in listed)


def test_offline_demo_hot_dry_is_complete():
    report = run("demo-hot-dry")
    assert report.status == "complete", (report.missing_information, report.verification)
    assert report.weather_source.data_mode == "demo"
    assert report.forecast is not None and len(report.forecast.days) == 3
    assert report.current_conditions is not None and report.current_conditions.temperature_c == 44.0
    assert report.alerts is not None and not report.alerts.alerts_supported
    assert report.recommended_actions is not None and report.recommended_actions.items
    assert report.steering_blocks == []
    assert any("demonstration weather data" in n for n in report.notices)


def test_offline_demo_mild_is_lower_risk():
    hot, mild = run("demo-hot-dry"), run("demo-mild")
    assert hot.risk_category in ORDER and mild.risk_category in ORDER
    assert ORDER.index(mild.risk_category) < ORDER.index(hot.risk_category)
