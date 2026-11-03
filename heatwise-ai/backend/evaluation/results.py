"""Evaluation results file (D-M5-8): one JSON with `runs.offline` and `runs.live`.

Each run replaces only its own section. `docs/evaluation.md` is generated from this file by
`python -m backend.evaluation report`; numbers are never edited by hand.
"""

from __future__ import annotations

import os
import tempfile
from datetime import datetime
from pathlib import Path
from typing import Any, Literal

from pydantic import BaseModel, Field

DEFAULT_RESULTS_PATH = Path(__file__).parent / "results" / "evaluation-results.json"
SCHEMA_VERSION = "heatwise-eval-results-v1"
LABEL = ("Synthetic test scenarios. No real-world health outcome is measured or claimed. Every metric carries "
         "the mode it was measured in.")


class Metric(BaseModel):
    value: float | None = None
    numerator: int | None = None
    denominator: int | None = None
    unit: str
    mode: Literal["offline", "live"]
    status: Literal["measured", "not_run"]
    note: str = ""
    details: dict[str, Any] = Field(default_factory=dict)


class Failure(BaseModel):
    scenario_id: str | None = None
    metric: str
    detail: str


class RunResult(BaseModel):
    mode: Literal["offline", "live"]
    mode_label: str
    status: Literal["ok", "failed"]
    error: str | None = None
    command: str
    started_at: datetime
    finished_at: datetime | None = None
    dataset_version: str
    settings: dict[str, Any] = Field(default_factory=dict)
    scenario_ids: list[str] = Field(default_factory=list)
    metrics: dict[str, Metric] = Field(default_factory=dict)
    scenarios: list[dict[str, Any]] = Field(default_factory=list)
    adversarial: dict[str, Any] | None = None
    relevance: dict[str, Any] | None = None
    knowledge_test: dict[str, Any] | None = None
    usage: dict[str, Any] | None = None
    cost: dict[str, Any] | None = None
    failures: list[Failure] = Field(default_factory=list)
    raw_reports_dir: str | None = None


class Runs(BaseModel):
    offline: RunResult | None = None
    live: RunResult | None = None


class EvaluationResults(BaseModel):
    schema_version: str = SCHEMA_VERSION
    synthetic: bool = True
    label: str = LABEL
    runs: Runs = Field(default_factory=Runs)


def load_results(path: str | os.PathLike[str] = DEFAULT_RESULTS_PATH) -> EvaluationResults:
    p = Path(path)
    if not p.is_file():
        return EvaluationResults()
    return EvaluationResults.model_validate_json(p.read_text(encoding="utf-8"))


def save_run(path: str | os.PathLike[str], run: RunResult) -> EvaluationResults:
    """Replace only `run.mode`'s section and write atomically (temp file + os.replace)."""
    p = Path(path)
    results = load_results(p)
    setattr(results.runs, run.mode, run)
    data = results.model_dump_json(indent=2) + "\n"
    p.parent.mkdir(parents=True, exist_ok=True)
    fd, tmp = tempfile.mkstemp(dir=p.parent, prefix=".tmp-", suffix=".json")
    try:
        with os.fdopen(fd, "w", encoding="utf-8", newline="\n") as f:
            f.write(data)
        os.replace(tmp, p)
    except BaseException:
        Path(tmp).unlink(missing_ok=True)
        raise
    return results
