"""Evaluation CLI.

    python -m backend.evaluation run --mode offline [--out PATH]
    python -m backend.evaluation run --mode live --confirm-live [--scenarios S01,S04,S08,S14]
                                     [--knowledge S01,S04] [--max-scenarios N] [--out PATH]
    python -m backend.evaluation report [--results PATH] [--out docs/evaluation.md]
"""

from __future__ import annotations

import argparse
import logging
import sys
from pathlib import Path

from backend.evaluation.results import DEFAULT_RESULTS_PATH, load_results, save_run

DEFAULT_DOC = Path("docs") / "evaluation.md"
REFUSAL = ("Refusing to run live evaluation without --confirm-live. Live mode calls Amazon Bedrock and costs "
           "money. Re-run with --confirm-live to proceed.")


def _quiet_logs() -> None:
    """CLI runs only: agent fallbacks log stack traces that would bury the summary."""
    logging.basicConfig(level=logging.WARNING)
    logging.getLogger("heatwise").setLevel(logging.CRITICAL)


def _ids(text: str) -> list[str]:
    return [s.strip().upper() for s in text.split(",") if s.strip()]


def _run_offline(args) -> int:
    from backend.evaluation.runner import run_offline

    _quiet_logs()
    run = run_offline()
    save_run(args.out, run)
    print(f"Offline run written to {args.out}")
    for k, m in run.metrics.items():
        print(f"  {k}: {m.value} ({m.numerator}/{m.denominator}) [{m.status}, {m.mode}]")
    print(f"  failures: {len(run.failures)}")
    return 0


def _run_live(args) -> int:
    from backend.evaluation.live import (
        DEFAULT_KNOWLEDGE_SCENARIOS,
        DEFAULT_LIVE_SCENARIOS,
        MAX_LIVE_SCENARIOS,
        build_metered_model,
        failed_run,
        run_live,
    )

    if not args.confirm_live:
        print(REFUSAL, file=sys.stderr)
        return 2
    scenarios = _ids(args.scenarios) if args.scenarios else list(DEFAULT_LIVE_SCENARIOS)
    knowledge = _ids(args.knowledge) if args.knowledge else list(DEFAULT_KNOWLEDGE_SCENARIOS)
    cap = min(args.max_scenarios or MAX_LIVE_SCENARIOS, MAX_LIVE_SCENARIOS)
    if len(scenarios) > cap:
        print(f"Too many scenarios ({len(scenarios)}); the cap is {cap}.", file=sys.stderr)
        return 1
    if any(k not in scenarios for k in knowledge):
        print("--knowledge scenarios must be a subset of --scenarios.", file=sys.stderr)
        return 1

    _quiet_logs()
    from backend.config import Settings
    from backend.evaluation.judge import bedrock_knowledge_answerer, strands_evals_relevance_judge

    settings = Settings(_env_file=None, weather_provider="demo", agent_mode="bedrock")
    command = " ".join(["python -m backend.evaluation", *sys.argv[1:]])
    print(f"Live evaluation: {len(scenarios)} coordinator runs ({', '.join(scenarios)}), 1 judge pass over the "
          f"plans, {2 * len(knowledge)} knowledge-test calls; model {settings.bedrock_model_id} in "
          f"{settings.aws_region}. This calls Amazon Bedrock and costs money (price not verified; check Bedrock pricing).")
    try:
        import boto3

        identity = boto3.client("sts", region_name=settings.aws_region).get_caller_identity()
        print(f"AWS credentials found (account ending {identity['Account'][-4:]}).")
    except Exception as exc:
        msg = f"AWS credentials unavailable: {type(exc).__name__}: {exc}"
        print(msg, file=sys.stderr)
        return 1
    agents_model = build_metered_model(settings)
    judge_model = build_metered_model(settings)
    answer_model = build_metered_model(settings)
    try:
        run = run_live(settings, scenarios, knowledge, judge=strands_evals_relevance_judge(judge_model),
                       answerer=bedrock_knowledge_answerer(answer_model), model=agents_model, command=command,
                       aux_models={"judge": judge_model, "knowledge_test": answer_model})
    except Exception as exc:
        run = failed_run(command, f"{type(exc).__name__}: {exc}", scenarios, settings)
    save_run(args.out, run)
    print(f"Live run ({run.status}) written to {args.out}")
    if run.error:
        print(f"  error: {run.error}", file=sys.stderr)
    for k, m in run.metrics.items():
        print(f"  {k}: {m.value} ({m.numerator}/{m.denominator}) [{m.status}, {m.mode}]")
    print(f"  usage: {run.usage}")
    return 0 if run.status == "ok" else 1


def _report(args) -> int:
    from backend.evaluation.report import render_markdown

    text = render_markdown(load_results(args.results))
    out = Path(args.out)
    out.parent.mkdir(parents=True, exist_ok=True)
    out.write_text(text, encoding="utf-8", newline="\n")
    print(f"Report written to {out}")
    return 0


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(prog="python -m backend.evaluation")
    sub = parser.add_subparsers(dest="command", required=True)
    run = sub.add_parser("run", help="Run the evaluation")
    run.add_argument("--mode", choices=("offline", "live"), required=True)
    run.add_argument("--confirm-live", action="store_true", help="Required for live mode (calls Bedrock)")
    run.add_argument("--scenarios", help="Comma-separated scenario ids (live)")
    run.add_argument("--knowledge", help="Comma-separated scenario ids for the knowledge test (live)")
    run.add_argument("--max-scenarios", type=int, default=None)
    run.add_argument("--out", default=str(DEFAULT_RESULTS_PATH))
    rep = sub.add_parser("report", help="Render docs/evaluation.md from the results file")
    rep.add_argument("--results", default=str(DEFAULT_RESULTS_PATH))
    rep.add_argument("--out", default=str(DEFAULT_DOC))
    args = parser.parse_args(argv)
    if args.command == "report":
        return _report(args)
    return _run_offline(args) if args.mode == "offline" else _run_live(args)


if __name__ == "__main__":
    sys.exit(main())
