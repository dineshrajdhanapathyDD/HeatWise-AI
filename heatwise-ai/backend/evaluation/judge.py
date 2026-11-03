"""Live LLM judge and knowledge-test answerer. Imported only by the live CLI path.

Verified strands-agents-evals 1.8.0 API (introspected from the installed package):

- `strands_evals.Case(*, name=None, session_id=..., input, expected_output=None, expected_assertion=None,
  expected_trajectory=None, expected_interactions=None, expected_environment_state=None, metadata=None)`
- `strands_evals.Experiment(cases=None, evaluators=None, diagnosis_config=None, *, report_cls=None)`
- `Experiment.run_evaluations(task, evaluation_data_store=None) -> EvaluationReport` is synchronous
  (it wraps `run_evaluations_async(task, max_workers=1)` with `asyncio.run`; async tasks are rejected).
  `task(case)` returns the output, or a `strands_evals.types.TaskOutput` dict
  (`output`, `trajectory`, `interactions`, `input`, `environment_state`).
- `strands_evals.evaluators.OutputEvaluator(rubric, model: Model | str | None = None, system_prompt=...,
  include_inputs=True, uses_environment_state=False, name=None, tools=None)`. The judge model parameter
  is `model`; it accepts a Bedrock model id string or a strands `Model` (None = default BedrockModel).
- `EvaluationReport` fields: `overall_score`, `scores`, `cases` (dicts with `evaluator`), `test_passes`,
  `reasons`, `detailed_results` (lists of `EvaluationOutput{score, test_pass, reason, label, metadata}`),
  `diagnoses`, `recommendations`.

`strands_evals` and Bedrock are imported lazily inside the functions so the API and the offline
evaluation never import them.
"""

from __future__ import annotations

from typing import Any

from pydantic import BaseModel, Field

from backend.evaluation.dataset import KnowledgeTest

RELEVANCE_RUBRIC = (
    "The input describes a community's heat risk category, the community groups present and the plan "
    "audiences. The output lists heat preparedness actions shown to that community. Pass if the actions are "
    "relevant to heat preparedness for the stated risk level and audiences, cover before, during and after "
    "the heat, and include when to seek help. Fail if actions are irrelevant, unsafe, give medicine or doses, "
    "or ignore the stated audiences. Score 0-1 for relevance and coverage."
)


class KnowledgeTestAnswers(BaseModel):
    """Flat structured output (no lists; M1 finding)."""

    q01: str = Field(description="Letter A, B, C or D")
    q02: str = Field(description="Letter A, B, C or D")
    q03: str = Field(description="Letter A, B, C or D")
    q04: str = Field(description="Letter A, B, C or D")
    q05: str = Field(description="Letter A, B, C or D")
    q06: str = Field(description="Letter A, B, C or D")
    q07: str = Field(description="Letter A, B, C or D")
    q08: str = Field(description="Letter A, B, C or D")
    q09: str = Field(description="Letter A, B, C or D")
    q10: str = Field(description="Letter A, B, C or D")


def strands_evals_relevance_judge(model: Any):
    """Return `judge(cases)` that scores stored plan outputs with OutputEvaluator (no re-run)."""

    def judge(cases: list[dict[str, Any]]) -> dict[str, Any]:
        from strands_evals import Case, Experiment
        from strands_evals.evaluators import OutputEvaluator

        stored = {c["case_id"]: c["output"] for c in cases}
        experiment = Experiment(
            cases=[Case(name=c["case_id"], input=c["input"]) for c in cases],
            evaluators=[OutputEvaluator(rubric=RELEVANCE_RUBRIC, model=model, include_inputs=True)],
        )
        report = experiment.run_evaluations(lambda case: stored[case.name])
        out = []
        for i, row in enumerate(report.cases):
            out.append({"case_id": row.get("name"), "score": float(report.scores[i]),
                        "test_pass": bool(report.test_passes[i]),
                        "reason": report.reasons[i] if i < len(report.reasons) else None})
        return {"evaluator": "strands_evals.evaluators.OutputEvaluator", "overall_score": report.overall_score,
                "cases": out}

    return judge


def _prompt(context: str | None, test: KnowledgeTest) -> str:
    lines = []
    if context:
        lines += ["Read this heatwave preparedness checklist, then answer the questions.", "", context, ""]
    else:
        lines += ["Answer these heatwave preparedness questions.", ""]
    for q in test.questions:
        lines.append(f"{q.id}: {q.question}")
        lines += [f"  {k}) {v}" for k, v in q.options.items()]
    lines.append("Answer each question with one letter (A, B, C or D).")
    return "\n".join(lines)


def bedrock_knowledge_answerer(model: Any):
    """Return `answerer(context, test)` using a fresh Strands Agent with flat structured output."""

    def answer(context: str | None, test: KnowledgeTest) -> dict[str, Any]:
        from strands import Agent

        try:
            agent = Agent(model=model, structured_output_model=KnowledgeTestAnswers, callback_handler=None,
                          system_prompt="You answer multiple-choice questions with a single letter each.")
            result = agent(_prompt(context, test), limits={"structured_output_attempts": 2})
            out = result.structured_output
            if not isinstance(out, KnowledgeTestAnswers):
                return {"answers": {}, "error": f"No structured answers (stop_reason={result.stop_reason})."}
            return {"answers": out.model_dump(), "error": None}
        except Exception as exc:  # recorded in the results
            return {"answers": {}, "error": f"{type(exc).__name__}: {exc}"}

    return answer
