"""Command-line demo for HeatWise AI.

    python -m backend.cli weather "Nagpur, Maharashtra" --days 3          # full agent (Bedrock + live weather)
    python -m backend.cli weather "Nagpur" --tools-only                    # weather tools only, no Bedrock
    WEATHER_PROVIDER=demo python -m backend.cli weather demo-hot-dry --tools-only
    python -m backend.cli assess "Nagpur, Maharashtra" --elderly --outdoor-workers --farmers --checklist-out plan.md

`weather` prints JSON; exit code 0 if status is ok/partial, 1 otherwise.
`assess` prints the PreparednessReport JSON to stdout and a trace table plus a summary to
stderr; exit code 0 complete, 2 needs_human_review, 1 incomplete.
"""

from __future__ import annotations

import argparse
import json
import logging
import sys
from pathlib import Path

from backend.agents.coordinator import HeatWiseCoordinator
from backend.agents.weather_agent import WeatherIntelligenceAgent
from backend.config import get_settings
from backend.models.risk import CommunityProfile
from backend.services.weather.factory import build_weather_provider
from backend.tools.weather_tools import build_weather_tools

ASSESS_EXIT_CODES = {"complete": 0, "needs_human_review": 2, "incomplete": 1}

# CLI flag -> CommunityProfile indicator (community-level presence, never individuals).
PROFILE_FLAGS = {
    "elderly": "elderly",
    "children": "young_children",
    "pregnant": "pregnant_women",
    "chronic_illness": "chronic_illness_group",
    "outdoor_workers": "outdoor_workers",
    "farmers": "farmers",
    "limited_water": "limited_water_access",
    "limited_shade": "limited_shade_or_cooling",
}


def _dump(obj) -> str:
    if hasattr(obj, "model_dump"):
        return obj.model_dump_json(indent=2)
    return json.dumps(obj, indent=2, ensure_ascii=False)


def _profile_from_args(args: argparse.Namespace) -> CommunityProfile:
    values = {field: bool(getattr(args, flag)) for flag, field in PROFILE_FLAGS.items()}
    return CommunityProfile(**values, terrain=args.terrain, preferred_language=args.language)


def _assess(args: argparse.Namespace, settings) -> int:
    coordinator = HeatWiseCoordinator(settings)
    session = {"session_id": args.session_id} if args.session_id else {}
    report = coordinator.run(args.location, _profile_from_args(args), args.days, **session)
    print(_dump(report))

    err = sys.stderr
    print("=== trace", file=err)
    for t in report.trace:
        line = f"  {t.step_index:>3} {t.agent:<22} {t.tool:<22} {t.status:<9} {t.duration_ms} ms"
        if t.cancel_reason:
            line += f"  ({t.cancel_reason[:100]})"
        print(line, file=err)
    print("=== summary", file=err)
    print(f"  status:              {report.status}", file=err)
    print(f"  risk category:       {report.risk_category}", file=err)
    print(f"  verification:        {report.verification_status} (revisions: {report.revision_count})", file=err)
    print(f"  steering blocks:     {len(report.steering_blocks)}", file=err)
    print(f"  consistency issues:  {len(report.consistency_issues)}", file=err)
    if report.verification and report.verification.issues:
        for issue in report.verification.issues:
            print(f"    - {issue}", file=err)

    if args.checklist_out:
        if report.checklist_markdown is not None:
            # Same text as the report: verified items only (with a review banner) unless status is complete.
            Path(args.checklist_out).write_text(report.checklist_markdown, encoding="utf-8")
            note = "" if report.status == "complete" else " (verified items only, needs human review)"
            print(f"  checklist written:   {args.checklist_out}{note}", file=err)
        else:
            print("  checklist not written: no preparedness plan in this report", file=err)
    return ASSESS_EXIT_CODES[report.status]


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(prog="heatwise")
    sub = parser.add_subparsers(dest="cmd", required=True)
    w = sub.add_parser("weather", help="Run the Weather Intelligence Agent")
    w.add_argument("location")
    w.add_argument("--days", type=int, default=3)
    w.add_argument("--tools-only", action="store_true", help="Call the weather tools directly, without the LLM")

    a = sub.add_parser("assess", help="Run the full multi-agent heat preparedness assessment")
    a.add_argument("location")
    a.add_argument("--days", type=int, default=3)
    a.add_argument("--elderly", action="store_true", help="Older people are present in the community")
    a.add_argument("--children", action="store_true", help="Infants or young children are present")
    a.add_argument("--pregnant", action="store_true", help="Pregnant women are present")
    a.add_argument("--chronic-illness", action="store_true", help="People with chronic illness are present")
    a.add_argument("--outdoor-workers", action="store_true", help="People who work outdoors are present")
    a.add_argument("--farmers", action="store_true", help="Farming households are present")
    a.add_argument("--limited-water", action="store_true", help="Drinking water access is limited")
    a.add_argument("--limited-shade", action="store_true", help="Shade or cooling is limited")
    a.add_argument("--terrain", choices=["plains", "hilly", "coastal"], default=None)
    a.add_argument("--language", default="en", help="Preferred plan language code (M2 plans are English only)")
    a.add_argument("--checklist-out", default=None, help="Write the checklist as Markdown to this path")
    a.add_argument("--session-id", default=None, help="Continue a stored coordinator conversation")
    args = parser.parse_args(argv)

    settings = get_settings()
    logging.basicConfig(level=settings.log_level, format="%(levelname)s %(name)s: %(message)s", stream=sys.stderr)

    if args.cmd == "assess":
        return _assess(args, settings)

    if args.tools_only:
        get_weather, get_forecast, get_weather_alerts = build_weather_tools(build_weather_provider(settings))
        out = {
            "current": get_weather(location=args.location),
            "forecast": get_forecast(location=args.location, days=args.days),
            "alerts": get_weather_alerts(location=args.location),
        }
        for key, value in out.items():
            print(f"=== {key}")
            print(_dump(value))
        return 0 if all(not (isinstance(v, dict) and v.get("status") == "error") for v in out.values()) else 1

    agent = WeatherIntelligenceAgent(settings)
    result = agent.run(args.location, args.days)
    print(_dump(result))
    print("=== trace", file=sys.stderr)
    for r in agent.last_trace:
        print(f"  {r.tool:<20} {r.status:<9} {r.duration_ms} ms", file=sys.stderr)
    return 0 if result.status in ("ok", "partial") else 1


if __name__ == "__main__":
    raise SystemExit(main())
