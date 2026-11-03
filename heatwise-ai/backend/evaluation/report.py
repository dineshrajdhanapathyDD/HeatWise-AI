"""Render docs/evaluation.md from the results file. Deterministic: same results, same bytes."""

from __future__ import annotations

from backend.evaluation.dataset import load_adversarial, load_knowledge_test, load_scenarios
from backend.evaluation.results import EvaluationResults, Metric, RunResult

METRIC_ORDER = (
    "workflow_completion", "risk_agreement", "safety_pass", "weather_extraction", "source_verification",
    "items_verified", "delegation_order_effective", "delegation_order_model_driven", "language_notice",
    "adversarial_direct_rejection", "adversarial_controls_pass", "adversarial_end_to_end",
    "recommendation_relevance", "knowledge_test_baseline", "knowledge_test_with_checklist", "timing_ms",
)
TITLES = {
    "workflow_completion": "Workflow completion (expected status)",
    "risk_agreement": "Risk category agreement with documented rules",
    "safety_pass": "Verification status as expected",
    "weather_extraction": "Weather field extraction accuracy",
    "source_verification": "Plan items with trusted sources",
    "items_verified": "Plan items passing safety checks",
    "delegation_order_effective": "Delegation order correct (fallback allowed)",
    "delegation_order_model_driven": "Delegation order driven by the model alone",
    "language_notice": "Non-English request: English plan with notice",
    "adversarial_direct_rejection": "Unsafe injected items rejected",
    "adversarial_controls_pass": "Safe control items accepted",
    "adversarial_end_to_end": "End-to-end unsafe planner held for review",
    "recommendation_relevance": "Recommendation relevance (LLM judge)",
    "knowledge_test_baseline": "Knowledge test, questions only (model)",
    "knowledge_test_with_checklist": "Knowledge test, with the checklist (model)",
    "timing_ms": "Time per scenario (mean)",
}


def _fmt(m: Metric) -> tuple[str, str]:
    if m.status != "measured" or m.value is None:
        return "not run", "-"
    if m.unit.startswith("ms"):
        d = m.details
        return f"{m.value:g} ms", f"median {d.get('median')} ms, max {d.get('max')} ms, n={m.denominator}"
    return f"{m.value * 100:.1f}%", f"{m.numerator}/{m.denominator} {m.unit}"


def _ts(run: RunResult) -> str:
    return run.started_at.strftime("%Y-%m-%d %H:%M UTC")


def _metrics_table(results: EvaluationResults) -> list[str]:
    runs = [r for r in (results.runs.offline, results.runs.live) if r is not None and r.status == "ok"]
    lines = ["| Metric | Mode | Value | Count | Note |", "| --- | --- | --- | --- | --- |"]
    for key in METRIC_ORDER:
        for run in runs:
            m = run.metrics.get(key)
            if m is None:
                continue
            value, count = _fmt(m)
            note = m.note.replace("|", "/") if m.status == "measured" else f"Not run: {m.note}"
            lines.append(f"| {TITLES.get(key, key)} | {m.mode} | {value} | {count} | {note} |")
    return lines


def _run_section(name: str, run: RunResult | None) -> list[str]:
    if run is None:
        return [f"- {name}: not run. No {name} numbers are reported."]
    if run.status != "ok":
        return [f"- {name}: FAILED at {_ts(run)}. Error: `{run.error}`. No {name} metrics are reported."]
    extra = ""
    if run.settings.get("bedrock_model_id"):
        extra = f", model `{run.settings['bedrock_model_id']}` in `{run.settings.get('aws_region')}`"
    return [f"- {name}: {run.mode_label}; started {_ts(run)}; scenarios {', '.join(run.scenario_ids)}{extra}."]


def _scenario_table(run: RunResult) -> list[str]:
    lines = [f"Per-scenario results ({run.mode}):", "",
             "| Scenario | Expected status / risk | Actual status / risk | Path | ms |",
             "| --- | --- | --- | --- | --- |"]
    for row in run.scenarios:
        exp = row["expected"]
        if row.get("error"):
            actual, path = f"error: {row['error']}", "-"
        else:
            a = row["actual"]
            actual = f"{a['status']} / {a['risk_category']}"
            d = row["delegation"]
            path = " > ".join(d["actual_path"]) + (" (fallback)" if d["fallback_used"] else "")
        lines.append(f"| {row['id']} | {exp['status']} / {exp['risk_category']} | {actual} | {path} | "
                     f"{row.get('duration_ms')} |")
    return lines


def render_markdown(results: EvaluationResults) -> str:
    scenarios = load_scenarios()
    knowledge = load_knowledge_test()
    adversarial = load_adversarial()
    off, live = results.runs.offline, results.runs.live
    L: list[str] = ["# HeatWise AI evaluation", "",
                    "> Status: synthetic test scenarios; no real-world health outcome is measured or claimed. "
                    "Every number below is generated from `backend/evaluation/results/evaluation-results.json` "
                    "by `python -m backend.evaluation report` and carries the mode it was measured in.", "",
                    "## Runs", ""]
    L += _run_section("offline", off) + _run_section("live", live)
    L += ["", "## How to reproduce", "", "From `heatwise-ai`:", "", "```powershell",
          r".venv\Scripts\python.exe -m backend.evaluation run --mode offline",
          r".venv\Scripts\python.exe -m backend.evaluation run --mode live --confirm-live --scenarios S01,S04,S08,S14 --knowledge S01,S04",
          r".venv\Scripts\python.exe -m backend.evaluation report", "```", "",
          "Offline mode needs no network or AWS access and also runs inside `pytest`. Live mode calls Amazon "
          "Bedrock (it refuses to start without `--confirm-live` and is capped at 6 scenarios).", "",
          "## Methodology", "",
          "- Weather comes from `ScenarioWeatherProvider`, which serves synthetic fixtures from the dataset "
          "(provider `HeatWise evaluation fixtures (synthetic)`, data mode `demo`) in both modes, so field "
          "extraction has exact ground truth. Fixtures can inject missing fields, stale observations and "
          "provider errors.",
          "- Offline mode runs the shipped offline coordinator: the real Strands agent loop, hooks, steering "
          "and deterministic fallback, with scripted models instead of an LLM. Live mode runs the same "
          "coordinator and specialists with the Bedrock model.",
          "- Expected risk categories are derived by hand from the documented rules (design.md 8.2: NWS heat "
          "index bands, IMD actual-maximum criteria, the project vulnerability heuristic) and re-checked by an "
          "independent implementation in `backend/tests/test_evaluation_dataset.py`.",
          "- Delegation order is a deterministic check over the report trace: successful coordinator and "
          "fallback delegations in step order must equal the expected path.",
          "- Adversarial cases inject one unsafe item into a real plan and call the deterministic safety "
          "checks; the end-to-end case scripts a planner that adds unsafe text on both attempts.",
          "- Recommendation relevance (live only) uses `strands_evals` `OutputEvaluator` as an LLM judge on "
          "the plan items a user is shown. The knowledge test (live only) is answered by the model, first "
          "with the questions only, then with the scenario's exported checklist.", "",
          "## Dataset", "",
          "| Dataset | Version | Size |", "| --- | --- | --- |",
          f"| Scenarios | `{scenarios.dataset_version}` | {len(scenarios.scenarios)} scenarios |",
          f"| Knowledge test | `{knowledge.dataset_version}` | {len(knowledge.questions)} questions |",
          f"| Adversarial | `{adversarial.dataset_version}` | {len(adversarial.unsafe)} unsafe, "
          f"{len(adversarial.controls)} controls |", "",
          f"{scenarios.label} Tags covered: "
          + ", ".join(sorted({t for s in scenarios.scenarios for t in s.tags})) + ".", "",
          "## Metrics", ""]
    if not any(r is not None and r.status == "ok" for r in (off, live)):
        L.append("No successful run is recorded yet.")
    else:
        L += _metrics_table(results)
    L += ["", "## Offline and live", ""]
    for run in (off, live):
        if run is not None and run.status == "ok":
            L += _scenario_table(run) + [""]
    if live is None:
        L += ["Live mode was not run, so no live numbers are reported.", ""]
    elif live.status != "ok":
        L += [f"The live run failed: `{live.error}`. No live numbers are reported.", ""]

    L += ["## Failures", ""]
    any_fail = False
    for run in (off, live):
        if run is None or run.status != "ok":
            continue
        if not run.failures:
            L.append(f"- {run.mode}: no failures.")
            continue
        any_fail = True
        for f in run.failures[:20]:
            L.append(f"- {run.mode} {f.scenario_id or '-'} `{f.metric}`: {f.detail}")
        if len(run.failures) > 20:
            L.append(f"- {run.mode}: {len(run.failures) - 20} more in the results file.")
    if not any_fail and not any(r is not None and r.status == "ok" for r in (off, live)):
        L.append("- No run recorded.")
    L += [""]

    L += ["## Knowledge test (model in test scenarios)", "",
          "The knowledge test measures whether a language model answers heat preparedness questions correctly "
          "with and without a HeatWise checklist. It is answered by a model in test scenarios, not by people, "
          "and says nothing about what real users learn.", ""]
    kt = live.knowledge_test if live is not None and live.status == "ok" else None
    if not kt:
        L += ["Not run (live only).", ""]
    else:
        L += ["| Scenario | Questions only | With checklist | Questions whose catalog item was in the plan |",
              "| --- | --- | --- | --- |"]
        for row in kt["rows"]:
            if row.get("error"):
                L.append(f"| {row['scenario_id']} | {row['error']} | - | - |")
                continue

            def cell(c: dict) -> str:
                return f"error: {c['error']}" if c.get("error") else f"{c['correct']}/{c['total']}"
            in_plan = sum(1 for v in row["items_in_plan"].values() if v)
            L.append(f"| {row['scenario_id']} | {cell(row['baseline'])} | {cell(row['with_checklist'])} | "
                     f"{in_plan}/{len(row['items_in_plan'])} |")
        L.append("")

    L += ["## Cost and tokens", ""]
    if live is None or live.status != "ok":
        L += ["No live run, so no tokens were used.", ""]
    else:
        u = live.usage or {}
        L.append(f"- Agents (coordinator and specialists): {u.get('calls', 0)} model calls, "
                 f"{u.get('inputTokens', 0)} input tokens, {u.get('outputTokens', 0)} output tokens.")
        for name, v in u.items():
            if isinstance(v, dict):
                L.append(f"- {name}: {v.get('calls', 0)} model calls, {v.get('inputTokens', 0)} input tokens, "
                         f"{v.get('outputTokens', 0)} output tokens.")
        c = live.cost or {}
        if c.get("price_verified"):
            L.append(f"- Estimated cost: {c['estimated_usd']} USD at {c['input_per_million_usd']} USD per million "
                     f"input tokens and {c['output_per_million_usd']} USD per million output tokens "
                     f"(price from {c.get('source_url')}, fetched {c.get('fetched_on')}).")
        else:
            L.append("- Price not verified in this session; tokens only.")
        L.append("")

    L += ["## Limitations", "",
          "- Expected risk categories come from the same documented rules the system implements, so agreement "
          "shows the multi-agent pipeline carries the rule output into the report. It is not clinical or "
          "meteorological validation.",
          "- All weather is synthetic; no real observations or communities are used.",
          "- Offline models are scripted, so offline delegation and safety numbers measure the pipeline and "
          "guardrails, not model behaviour.",
          "- The live sample is small and was run once; a single judge model (the same model family) scores "
          "relevance.",
          "- Plans are English only; other languages get English with a notice.",
          "- No real-world health outcome is measured or claimed.", ""]
    return "\n".join(L)
