"""Write PreparednessReport JSON fixtures for the frontend tests (offline, no network).

Usage (from heatwise-ai/): .venv\\Scripts\\python.exe -m backend.tests.export_fixtures <out_dir>
"""

from __future__ import annotations

import sys
from pathlib import Path

from backend.agents.offline import build_offline_coordinator
from backend.config import Settings
from backend.models.risk import CommunityProfile
from backend.tests.test_cli import scripted_report

SCRIPTED = {"report-complete.json": "complete", "report-needs-review.json": "needs_human_review",
            "report-incomplete.json": "incomplete"}


def export(out_dir: Path) -> list[Path]:
    out_dir.mkdir(parents=True, exist_ok=True)
    settings = Settings(_env_file=None, weather_provider="open_meteo")  # FakeProvider is injected; no network
    reports = {name: scripted_report(settings, kind) for name, kind in SCRIPTED.items()}
    demo = Settings(_env_file=None, weather_provider="demo")
    reports["report-demo-complete.json"] = build_offline_coordinator(demo, "demo-hot-dry", 3).run(
        "demo-hot-dry", CommunityProfile(elderly=True, outdoor_workers=True, farmers=True), 3)
    written = []
    for name, report in reports.items():
        path = out_dir / name
        path.write_text(report.model_dump_json(indent=2) + "\n", encoding="utf-8")
        written.append(path)
    return written


def main(argv: list[str] | None = None) -> int:
    args = sys.argv[1:] if argv is None else argv
    if len(args) != 1:
        print("usage: python -m backend.tests.export_fixtures <out_dir>", file=sys.stderr)
        return 2
    for path in export(Path(args[0])):
        print(path)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
