"""Live-mode plumbing with fakes only: no Bedrock, no network, no AWS."""

from __future__ import annotations

import asyncio
import sys

from strands.models import BedrockModel

from backend.agents.offline import build_offline_coordinator
from backend.evaluation import __main__ as cli
from backend.evaluation.dataset import load_knowledge_test
from backend.evaluation.live import MeteredBedrockModel, run_live, score_knowledge
from backend.evaluation.report import render_markdown
from backend.evaluation.results import EvaluationResults
from backend.evaluation.runner import offline_settings, run_offline

KT = load_knowledge_test()
CORRECT = {q.id: q.answer for q in KT.questions}


def fake_build(settings, sc, provider):
    return build_offline_coordinator(settings, sc.location, sc.forecast_days, sc.profile, provider=provider)


def fake_judge(cases):
    return {"evaluator": "fake", "cases": [{"case_id": c["case_id"], "score": 1.0, "test_pass": True,
                                            "reason": "ok"} for c in cases]}


def fake_answerer(context, test):
    if context is None:
        return {"answers": {"q01": CORRECT["q01"]}, "error": None}
    return {"answers": dict(CORRECT), "error": None}


def test_run_live_with_fakes(tmp_path):
    run = run_live(offline_settings(), ["S01", "S14"], ["S01"], judge=fake_judge, answerer=fake_answerer,
                   model=object(), command="test", raw_dir=tmp_path, build=fake_build)
    assert run.mode == "live" and run.status == "ok"
    assert all(m.mode == "live" for m in run.metrics.values())
    assert run.metrics["risk_agreement"].numerator == 2
    rel = run.metrics["recommendation_relevance"]
    assert (rel.numerator, rel.denominator) == (1, 1)  # S14 is incomplete: nothing to judge
    assert run.metrics["knowledge_test_baseline"].numerator == 1
    assert run.metrics["knowledge_test_with_checklist"].numerator == 10
    assert run.metrics["adversarial_end_to_end"].status == "not_run"
    assert (tmp_path / run.raw_reports_dir.split("/")[-1] / "S01.json").is_file()
    assert run.cost["price_verified"] is False


def test_run_live_rejects_too_many():
    import pytest

    with pytest.raises(ValueError):
        run_live(offline_settings(), [f"S{i:02d}" for i in range(1, 8)], [], judge=fake_judge,
                 answerer=fake_answerer, model=object(), command="t", raw_dir=None, build=fake_build)


def test_knowledge_scoring():
    assert score_knowledge(KT, CORRECT)["correct"] == 10
    wrong = {k: ("A" if v != "A" else "B") for k, v in CORRECT.items()}
    assert score_knowledge(KT, wrong)["correct"] == 0
    assert score_knowledge(KT, {"q01": CORRECT["q01"].lower() + ")"})["correct"] == 1


def test_cli_refuses_live_without_confirm(capsys):
    assert cli.main(["run", "--mode", "live"]) != 0
    assert "Refusing" in capsys.readouterr().err


def test_report_without_live_run(tmp_path):
    results = EvaluationResults()
    results.runs.offline = run_offline()
    md = render_markdown(results)
    assert "Live mode was not run" in md and "| live |" not in md
    assert "no real-world health outcome is measured or claimed" in md
    assert "| Risk category agreement with documented rules | offline | 100.0% | 18/18 scenarios |" in md
    assert render_markdown(results) == md  # deterministic


def test_metered_model_sums_usage(monkeypatch):
    async def fake_stream(self, *a, **k):
        yield {"messageStart": {"role": "assistant"}}
        yield {"metadata": {"usage": {"inputTokens": 7, "outputTokens": 3, "totalTokens": 10}}}

    monkeypatch.setattr(BedrockModel, "stream", fake_stream)
    model = MeteredBedrockModel(model_id="test-model", region_name="us-east-1")

    async def consume():
        for _ in range(2):
            async for _e in model.stream([]):
                pass

    asyncio.run(consume())
    assert model.usage == {"inputTokens": 14, "outputTokens": 6, "totalTokens": 20, "calls": 2}


def test_strands_evals_not_imported_by_api_or_offline():
    import subprocess

    code = ("import sys, backend.api.app, backend.evaluation.live, backend.evaluation.runner; "
            "print('strands_evals' in sys.modules)")
    out = subprocess.run([sys.executable, "-c", code], capture_output=True, text=True, check=True)
    assert out.stdout.strip() == "False"
