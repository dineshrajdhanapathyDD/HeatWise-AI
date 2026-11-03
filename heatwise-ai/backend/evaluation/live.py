"""Opt-in live evaluation (task 5.2, live part; D-M5-3).

Runs selected synthetic scenarios through the real `HeatWiseCoordinator` with Amazon Bedrock
(settings.bedrock_model_id) against the synthetic weather fixtures, then scores them with the
same deterministic metrics as offline mode, plus an LLM-as-judge relevance score and a
knowledge test answered by the model. Never run by automated tests: the judge, answerer and
model are injectable, and the CLI requires --confirm-live.
"""

from __future__ import annotations

import json
from datetime import datetime, timezone
from pathlib import Path
from typing import Any, Callable

from strands.models import BedrockModel, Model

from backend.agents.coordinator import HeatWiseCoordinator
from backend.agents.weather_agent import WeatherIntelligenceAgent
from backend.config import Settings
from backend.evaluation.dataset import KnowledgeTest, ScenarioDataset, load_knowledge_test, load_scenarios
from backend.evaluation.metrics import aggregate, failures_for, not_run, ratio_metric, renderable_items
from backend.evaluation.provider import ScenarioWeatherProvider
from backend.evaluation.results import Failure, Metric, RunResult
from backend.evaluation.runner import run_adversarial, run_scenarios
from backend.models.report import PreparednessReport

LIVE_LABEL = "live (Amazon Bedrock, real model calls, synthetic weather fixtures)"
MAX_LIVE_SCENARIOS = 6
DEFAULT_LIVE_SCENARIOS = ("S01", "S04", "S08", "S14")
DEFAULT_KNOWLEDGE_SCENARIOS = ("S01", "S04")
RAW_DIR = Path(".data") / "evaluation"

# Judge: list of case dicts -> list of {case_id, score, test_pass, reason} plus usage.
Judge = Callable[[list[dict[str, Any]]], dict[str, Any]]
# Answerer: (context or None, questions) -> {"answers": {qid: letter}, "error": str | None}
Answerer = Callable[[str | None, KnowledgeTest], dict[str, Any]]


class MeteredBedrockModel(BedrockModel):
    """BedrockModel that sums `metadata.usage` tokens from its stream events."""

    def __init__(self, *args: Any, **kwargs: Any) -> None:
        super().__init__(*args, **kwargs)
        self.usage = {"inputTokens": 0, "outputTokens": 0, "totalTokens": 0, "calls": 0}

    async def stream(self, *args: Any, **kwargs: Any):  # type: ignore[override]
        self.usage["calls"] += 1
        async for event in super().stream(*args, **kwargs):
            usage = event.get("metadata", {}).get("usage") if isinstance(event, dict) else None
            if usage:
                for key in ("inputTokens", "outputTokens", "totalTokens"):
                    self.usage[key] += int(usage.get(key, 0) or 0)
            yield event


def build_metered_model(settings: Settings) -> MeteredBedrockModel:
    return MeteredBedrockModel(model_id=settings.bedrock_model_id, region_name=settings.aws_region, temperature=0.1)


def live_coordinator_factory(model: Model) -> Callable[[Settings, Any, ScenarioWeatherProvider], HeatWiseCoordinator]:
    def build(settings: Settings, sc: Any, provider: ScenarioWeatherProvider) -> HeatWiseCoordinator:
        return HeatWiseCoordinator(settings, weather_agent=WeatherIntelligenceAgent(settings, provider=provider,
                                                                                    model=model), model=model)
    return build


def judge_cases(reports: dict[str, PreparednessReport]) -> list[dict[str, Any]]:
    """Judge input: scenario summary; judge output: the plan items a user is shown."""
    cases = []
    for sid, r in reports.items():
        items = renderable_items(r)
        if not items:
            continue
        risk = r.risk
        summary = (f"Community heat risk category: {r.risk_category}. "
                   f"Community groups present: {', '.join(risk.vulnerability_indicators) if risk else 'none'}. "
                   f"Plan audiences: {', '.join(dict.fromkeys(i.audience for i in items))}.")
        output = "\n".join(f"- [{i.audience}/{i.phase}] {i.text}" for i in items)
        cases.append({"case_id": sid, "input": summary, "output": output})
    return cases


def score_knowledge(test: KnowledgeTest, answers: dict[str, str]) -> dict[str, Any]:
    per = {q.id: (str(answers.get(q.id, "")).strip().upper()[:1] == q.answer) for q in test.questions}
    return {"correct": sum(per.values()), "total": len(per), "per_question": per}


def run_knowledge(test: KnowledgeTest, reports: dict[str, PreparednessReport], scenario_ids: list[str],
                  answerer: Answerer) -> dict[str, Any]:
    """Baseline (questions only) and post (questions + the scenario's exported checklist), per scenario."""
    rows = []
    for sid in scenario_ids:
        r = reports.get(sid)
        if r is None or not r.checklist_markdown:
            rows.append({"scenario_id": sid, "error": "No checklist was produced for this scenario."})
            continue
        plan_ids = {i.id for i in renderable_items(r)}
        base = answerer(None, test)
        post = answerer(r.checklist_markdown, test)
        row: dict[str, Any] = {"scenario_id": sid,
                               "items_in_plan": {q.id: q.catalog_item_id in plan_ids for q in test.questions}}
        for name, out in (("baseline", base), ("with_checklist", post)):
            row[name] = {"error": out.get("error"), **score_knowledge(test, out.get("answers") or {})}
        rows.append(row)
    return {"dataset_version": test.dataset_version, "framing": "Answered by a language model in test scenarios, "
            "not by people.", "rows": rows}


def run_live(settings: Settings, scenario_ids: list[str], knowledge_ids: list[str], judge: Judge,
             answerer: Answerer, model: Model, command: str, dataset: ScenarioDataset | None = None,
             knowledge: KnowledgeTest | None = None, raw_dir: Path | None = RAW_DIR,
             price: dict[str, Any] | None = None, build=None,
             aux_models: dict[str, Any] | None = None) -> RunResult:
    dataset = dataset or load_scenarios()
    knowledge = knowledge or load_knowledge_test()
    by_id = {s.id: s for s in dataset.scenarios}
    unknown = [s for s in scenario_ids if s not in by_id]
    if unknown:
        raise ValueError(f"Unknown scenario id(s): {', '.join(unknown)}")
    if len(scenario_ids) > MAX_LIVE_SCENARIOS:
        raise ValueError(f"At most {MAX_LIVE_SCENARIOS} live scenarios are allowed.")
    started = datetime.now(timezone.utc)
    selected = [by_id[s] for s in scenario_ids]
    rows, reports, coords = run_scenarios(settings, selected, build or live_coordinator_factory(model),
                                          dataset.scenarios)
    metrics = aggregate(rows, "live")
    failures = [Failure(**f) for r in rows for f in failures_for(r)]
    adversarial, adv_metrics, adv_failures = run_adversarial(settings, dataset, reports, coords, "live",
                                                             include_end_to_end=False)
    metrics.update(adv_metrics)
    failures += adv_failures

    raw_path = None
    if raw_dir is not None:
        raw_path = Path(raw_dir) / f"live-{started.strftime('%Y%m%dT%H%M%SZ')}"
        raw_path.mkdir(parents=True, exist_ok=True)
        for sid, r in reports.items():
            (raw_path / f"{sid}.json").write_text(r.model_dump_json(indent=2), encoding="utf-8")

    cases = judge_cases(reports)
    relevance: dict[str, Any] = {"cases": [], "error": None}
    if cases:
        try:
            relevance = {**judge(cases), "error": None}
        except Exception as exc:  # recorded, never hidden
            relevance = {"cases": [], "error": f"{type(exc).__name__}: {exc}"}
    judged = relevance.get("cases") or []
    if judged:
        passed = sum(1 for c in judged if c.get("test_pass"))
        m = ratio_metric(passed, len(judged), "cases", "live",
                         "LLM-as-judge (strands_evals OutputEvaluator, same Bedrock model) on whether the shown "
                         "plan items fit the scenario's risk and groups. Single judge model; indicative only.")
        m["details"] = {"mean_score": round(sum(float(c.get("score", 0)) for c in judged) / len(judged), 3)}
        metrics["recommendation_relevance"] = m
    else:
        metrics["recommendation_relevance"] = not_run("cases", "live", relevance.get("error") or "No plan to judge.")

    kt = run_knowledge(knowledge, reports, knowledge_ids, answerer)
    for cond, key in (("baseline", "knowledge_test_baseline"), ("with_checklist", "knowledge_test_with_checklist")):
        ok = [r[cond] for r in kt["rows"] if cond in r and not r[cond]["error"]]
        if ok:
            metrics[key] = ratio_metric(sum(r["correct"] for r in ok), sum(r["total"] for r in ok), "questions",
                                        "live", f"Knowledge test answered by the model ({cond.replace('_', ' ')}); "
                                                "LLM in test scenarios, not people.")
        else:
            errs = [r[cond]["error"] for r in kt["rows"] if cond in r and r[cond]["error"]]
            errs += [r["error"] for r in kt["rows"] if r.get("error")]
            metrics[key] = not_run("questions", "live", errs[0] if errs else "Not run.")

    usage = dict(getattr(model, "usage", {}) or {})
    for name, aux in (aux_models or {}).items():
        if getattr(aux, "usage", None):
            usage[name] = dict(aux.usage)
    cost: dict[str, Any] = {"price_verified": False, "note": "price not verified; tokens only"}
    if price:
        tokens_in = usage.get("inputTokens", 0) + sum(v.get("inputTokens", 0) for v in usage.values()
                                                      if isinstance(v, dict))
        tokens_out = usage.get("outputTokens", 0) + sum(v.get("outputTokens", 0) for v in usage.values()
                                                        if isinstance(v, dict))
        usd = tokens_in / 1e6 * price["input_per_million_usd"] + tokens_out / 1e6 * price["output_per_million_usd"]
        cost = {"price_verified": True, **price, "estimated_usd": round(usd, 4),
                "note": "Estimated from metered input and output tokens of all live model calls."}
    if usage.get("calls", 0) and not usage.get("totalTokens"):
        failures.append(Failure(metric="usage", detail="No token usage was reported by the model stream."))
    any_ok = any(not r.get("error") for r in rows)
    return RunResult(
        mode="live", mode_label=LIVE_LABEL, status="ok" if any_ok else "failed",
        error=None if any_ok else (rows[0].get("error") if rows else "No scenario ran."),
        command=command, started_at=started, finished_at=datetime.now(timezone.utc),
        dataset_version=dataset.dataset_version,
        settings={"agent_mode": "bedrock", "bedrock_model_id": settings.bedrock_model_id,
                  "aws_region": settings.aws_region, "weather": "ScenarioWeatherProvider (synthetic)",
                  "knowledge_scenarios": knowledge_ids},
        scenario_ids=scenario_ids, metrics={k: Metric(**v) for k, v in metrics.items()}, scenarios=rows,
        adversarial=adversarial, relevance=relevance, knowledge_test=kt, usage=usage, cost=cost,
        failures=failures, raw_reports_dir=raw_path.as_posix() if raw_path else None,
    )


def failed_run(command: str, error: str, scenario_ids: list[str], settings: Settings) -> RunResult:
    now = datetime.now(timezone.utc)
    return RunResult(mode="live", mode_label=LIVE_LABEL, status="failed", error=error, command=command,
                     started_at=now, finished_at=now, dataset_version=load_scenarios().dataset_version,
                     settings={"bedrock_model_id": settings.bedrock_model_id, "aws_region": settings.aws_region},
                     scenario_ids=scenario_ids)


def dump(obj: Any) -> str:  # pragma: no cover - debugging helper
    return json.dumps(obj, indent=2, default=str)
