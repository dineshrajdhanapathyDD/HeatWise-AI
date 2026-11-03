"""Offline evaluation runner (task 5.2, offline part).

Runs every synthetic scenario through the shipped offline coordinator (scripted models,
real Strands loop, D-M5-2) against `ScenarioWeatherProvider`, then scores the reports with
the deterministic metrics and runs the adversarial safety cases. No network, AWS or Bedrock.
"""

from __future__ import annotations

import time
from datetime import datetime, timezone
from typing import Any, Callable

from backend.agents.coordinator import HeatWiseCoordinator
from backend.agents.offline import build_offline_coordinator
from backend.config import Settings
from backend.evaluation.adversarial import run_direct_cases, run_end_to_end
from backend.evaluation.dataset import Scenario, ScenarioDataset, load_adversarial, load_scenarios
from backend.evaluation.metrics import aggregate, failures_for, not_run, ratio_metric, score_scenario
from backend.evaluation.provider import ScenarioWeatherProvider
from backend.evaluation.results import Failure, Metric, RunResult
from backend.models.report import PreparednessReport

OFFLINE_COMMAND = r".venv\Scripts\python.exe -m backend.evaluation run --mode offline"
OFFLINE_LABEL = "offline (scripted models, real Strands loop, synthetic weather fixtures)"


def offline_settings() -> Settings:
    return Settings(_env_file=None, weather_provider="demo", agent_mode="offline")


def evaluate_scenario(scenario: Scenario, run: Callable[[], tuple[PreparednessReport, HeatWiseCoordinator]],
                      provider: ScenarioWeatherProvider) -> tuple[dict[str, Any], PreparednessReport | None,
                                                                   HeatWiseCoordinator | None]:
    row: dict[str, Any] = {"id": scenario.id, "title": scenario.title, "tags": scenario.tags,
                           "expected": scenario.expected.model_dump(exclude_none=True)}
    start = time.perf_counter()
    try:
        report, coord = run()
    except Exception as exc:  # recorded as a workflow failure, never hidden
        row.update(error=f"{type(exc).__name__}: {exc}", duration_ms=round((time.perf_counter() - start) * 1000, 1),
                   provider_calls=list(provider.calls))
        return row, None, None
    row["duration_ms"] = round((time.perf_counter() - start) * 1000, 1)
    row.update(score_scenario(report, scenario))
    row["provider_calls"] = list(provider.calls)
    row["report_id"] = report.report_id
    row["error"] = None
    return row, report, coord


def run_scenarios(settings: Settings, scenarios: list[Scenario],
                  build: Callable[[Settings, Scenario, ScenarioWeatherProvider], HeatWiseCoordinator],
                  all_scenarios: list[Scenario]):
    rows, reports, coords = [], {}, {}
    for sc in scenarios:
        provider = ScenarioWeatherProvider(all_scenarios, settings.weather_stale_after_minutes)

        def go(sc=sc, provider=provider):
            coord = build(settings, sc, provider)
            return coord.run(sc.location, sc.profile, sc.forecast_days), coord

        row, report, coord = evaluate_scenario(sc, go, provider)
        rows.append(row)
        if report is not None:
            reports[sc.id], coords[sc.id] = report, coord
    return rows, reports, coords


def _offline_build(settings: Settings, sc: Scenario, provider: ScenarioWeatherProvider) -> HeatWiseCoordinator:
    return build_offline_coordinator(settings, sc.location, sc.forecast_days, sc.profile, provider=provider)


def run_adversarial(settings: Settings, dataset: ScenarioDataset, reports: dict, coords: dict,
                    mode: str, include_end_to_end: bool = True
                    ) -> tuple[dict[str, Any], dict[str, dict[str, Any]], list[Failure]]:
    """Direct cases on the first complete scenario's real plan, plus one end-to-end run."""
    adv = load_adversarial()
    failures: list[Failure] = []
    base_id = next((sid for sid, r in reports.items() if r.status == "complete" and coords[sid].last_state.plans),
                   None)
    metrics: dict[str, dict[str, Any]] = {}
    out: dict[str, Any] = {"dataset_version": adv.dataset_version, "base_scenario_id": base_id}
    if base_id is None:
        note = "No complete scenario plan was available to inject into."
        metrics["adversarial_direct_rejection"] = not_run("unsafe cases", mode, note)
        metrics["adversarial_controls_pass"] = not_run("control cases", mode, note)
    else:
        st = coords[base_id].last_state
        direct = run_direct_cases(st.plans[-1], st.weather, st.risk, adv)
        out["direct"] = direct
        metrics["adversarial_direct_rejection"] = ratio_metric(
            direct["rejected"], direct["unsafe_total"], "unsafe cases", mode,
            "Unsafe item injected into a real plan: verification fails, the item is not verified and the "
            "original items stay verified (deterministic run_checks).")
        metrics["adversarial_controls_pass"] = ratio_metric(
            direct["controls_passed"], direct["controls_total"], "control cases", mode,
            "Safe control item injected into the same plan: verification still passes.")
        failures += [Failure(scenario_id=r["id"], metric="adversarial_direct_rejection",
                             detail=f"not rejected (status {r['status']})") for r in direct["unsafe"] if not r["rejected"]]
        failures += [Failure(scenario_id=r["id"], metric="adversarial_controls_pass",
                             detail=f"control failed (status {r['status']})") for r in direct["controls"]
                     if not r["passed"]]
    if not include_end_to_end:
        metrics["adversarial_end_to_end"] = not_run("runs", mode, "offline only (scripted unsafe planner)")
        return out, metrics, failures
    e2e_scenario = next(s for s in dataset.scenarios if s.expected.status == "complete")
    e2e = run_end_to_end(settings, e2e_scenario,
                         ScenarioWeatherProvider(dataset.scenarios, settings.weather_stale_after_minutes))
    out["end_to_end"] = e2e
    metrics["adversarial_end_to_end"] = ratio_metric(
        1 if e2e["passed"] else 0, 1, "runs", "offline",
        "Planner model adds unsafe text on both attempts (scripted): report ends needs_human_review after one "
        "revision and the unsafe text is absent from the exported checklist.")
    if not e2e["passed"]:
        failures.append(Failure(scenario_id=e2e["scenario_id"], metric="adversarial_end_to_end",
                                detail=f"status {e2e['status']}, in checklist {e2e['unsafe_text_in_checklist']}"))
    return out, metrics, failures


def run_offline(settings: Settings | None = None, dataset: ScenarioDataset | None = None) -> RunResult:
    settings = settings or offline_settings()
    dataset = dataset or load_scenarios()
    started = datetime.now(timezone.utc)
    rows, reports, coords = run_scenarios(settings, dataset.scenarios, _offline_build, dataset.scenarios)
    metrics = aggregate(rows, "offline")
    failures = [Failure(**f) for r in rows for f in failures_for(r)]
    adversarial, adv_metrics, adv_failures = run_adversarial(settings, dataset, reports, coords, "offline")
    metrics.update(adv_metrics)
    failures += adv_failures
    metrics["recommendation_relevance"] = not_run("cases", "offline", "live only (LLM judge)")
    metrics["knowledge_test_baseline"] = not_run("questions", "offline", "live only (model answers)")
    metrics["knowledge_test_with_checklist"] = not_run("questions", "offline", "live only (model answers)")
    return RunResult(
        mode="offline", mode_label=OFFLINE_LABEL, status="ok", command=OFFLINE_COMMAND, started_at=started,
        finished_at=datetime.now(timezone.utc), dataset_version=dataset.dataset_version,
        settings={"agent_mode": settings.agent_mode, "weather": "ScenarioWeatherProvider (synthetic)",
                  "weather_stale_after_minutes": settings.weather_stale_after_minutes,
                  "risk_vulnerability_min_indicators": settings.risk_vulnerability_min_indicators},
        scenario_ids=[s.id for s in dataset.scenarios],
        metrics={k: Metric(**v) for k, v in metrics.items()},
        scenarios=rows, adversarial=adversarial, failures=failures,
    )
