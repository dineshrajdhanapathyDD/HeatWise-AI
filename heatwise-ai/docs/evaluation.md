# HeatWise AI evaluation

> Status: synthetic test scenarios; no real-world health outcome is measured or claimed. Every number below is generated from `backend/evaluation/results/evaluation-results.json` by `python -m backend.evaluation report` and carries the mode it was measured in.

## Runs

- offline: offline (scripted models, real Strands loop, synthetic weather fixtures); started 2026-11-03 06:00 UTC; scenarios S01, S02, S03, S04, S05, S06, S07, S08, S09, S10, S11, S12, S13, S14, S15, S16, S17, S18.
- live: live (Amazon Bedrock, real model calls, synthetic weather fixtures); started 2026-11-03 06:03 UTC; scenarios S01, S04, S08, S14, model `us.amazon.nova-2-lite-v1:0` in `us-east-1`.

## How to reproduce

From `heatwise-ai`:

```powershell
.venv\Scripts\python.exe -m backend.evaluation run --mode offline
.venv\Scripts\python.exe -m backend.evaluation run --mode live --confirm-live --scenarios S01,S04,S08,S14 --knowledge S01,S04
.venv\Scripts\python.exe -m backend.evaluation report
```

Offline mode needs no network or AWS access and also runs inside `pytest`. Live mode calls Amazon Bedrock (it refuses to start without `--confirm-live` and is capped at 6 scenarios).

## Methodology

- Weather comes from `ScenarioWeatherProvider`, which serves synthetic fixtures from the dataset (provider `HeatWise evaluation fixtures (synthetic)`, data mode `demo`) in both modes, so field extraction has exact ground truth. Fixtures can inject missing fields, stale observations and provider errors.
- Offline mode runs the shipped offline coordinator: the real Strands agent loop, hooks, steering and deterministic fallback, with scripted models instead of an LLM. Live mode runs the same coordinator and specialists with the Bedrock model.
- Expected risk categories are derived by hand from the documented rules (design.md 8.2: NWS heat index bands, IMD actual-maximum criteria, the project vulnerability heuristic) and re-checked by an independent implementation in `backend/tests/test_evaluation_dataset.py`.
- Delegation order is a deterministic check over the report trace: successful coordinator and fallback delegations in step order must equal the expected path.
- Adversarial cases inject one unsafe item into a real plan and call the deterministic safety checks; the end-to-end case scripts a planner that adds unsafe text on both attempts.
- Recommendation relevance (live only) uses `strands_evals` `OutputEvaluator` as an LLM judge on the plan items a user is shown. The knowledge test (live only) is answered by the model, first with the questions only, then with the scenario's exported checklist.

## Dataset

| Dataset | Version | Size |
| --- | --- | --- |
| Scenarios | `heatwise-eval-v1` | 18 scenarios |
| Knowledge test | `heatwise-knowledge-v1` | 10 questions |
| Adversarial | `heatwise-adversarial-v1` | 9 unsafe, 3 controls |

Synthetic test scenarios. Not observations, not real communities. Tags covered: coastal, heuristic_raise, hilly, hot_dry, humid, imd_only, invalid_location, language, mild, missing_data, plains, provider_error, severe, stale, terrain_unknown, vulnerable_groups.

## Metrics

| Metric | Mode | Value | Count | Note |
| --- | --- | --- | --- | --- |
| Workflow completion (expected status) | offline | 100.0% | 18/18 scenarios | Report produced without an exception and its status equals the expected status. |
| Workflow completion (expected status) | live | 100.0% | 4/4 scenarios | Report produced without an exception and its status equals the expected status. |
| Risk category agreement with documented rules | offline | 100.0% | 18/18 scenarios | Report risk category equals the category derived by hand from the documented rules (design.md 8.2). Not clinical validation. |
| Risk category agreement with documented rules | live | 100.0% | 4/4 scenarios | Report risk category equals the category derived by hand from the documented rules (design.md 8.2). Not clinical validation. |
| Verification status as expected | offline | 100.0% | 18/18 scenarios | Report verification status (passed / failed / not_run) equals the expected status. |
| Verification status as expected | live | 100.0% | 4/4 scenarios | Report verification status (passed / failed / not_run) equals the expected status. |
| Weather field extraction accuracy | offline | 100.0% | 326/326 fields | Report weather fields equal to the synthetic fixture within 0.05; null fixture values must be null and listed as missing. |
| Weather field extraction accuracy | live | 100.0% | 71/71 fields | Report weather fields equal to the synthetic fixture within 0.05; null fixture values must be null and listed as missing. |
| Plan items with trusted sources | offline | 100.0% | 322/322 plan items | Plan items whose source ids are all in TRUSTED_SOURCES. |
| Plan items with trusted sources | live | 100.0% | 101/101 plan items | Plan items whose source ids are all in TRUSTED_SOURCES. |
| Plan items passing safety checks | offline | 100.0% | 322/322 plan items | Plan items that passed the deterministic safety checks. |
| Plan items passing safety checks | live | 100.0% | 101/101 plan items | Plan items that passed the deterministic safety checks. |
| Delegation order correct (fallback allowed) | offline | 100.0% | 18/18 scenarios | Successful coordinator and deterministic-fallback delegations, in step order, equal the expected path (fallback allowed). |
| Delegation order correct (fallback allowed) | live | 100.0% | 4/4 scenarios | Successful coordinator and deterministic-fallback delegations, in step order, equal the expected path (fallback allowed). |
| Delegation order driven by the model alone | offline | 72.2% | 13/18 scenarios | Expected order reached by the coordinator model alone: no fallback step, no steering block, finalize_report called by the model. |
| Delegation order driven by the model alone | live | 100.0% | 4/4 scenarios | Expected order reached by the coordinator model alone: no fallback step, no steering block, finalize_report called by the model. |
| Non-English request: English plan with notice | offline | 100.0% | 1/1 scenarios | Non-English request returns an English plan with a language notice. |
| Non-English request: English plan with notice | live | not run | - | Not run: Non-English request returns an English plan with a language notice. |
| Unsafe injected items rejected | offline | 100.0% | 9/9 unsafe cases | Unsafe item injected into a real plan: verification fails, the item is not verified and the original items stay verified (deterministic run_checks). |
| Unsafe injected items rejected | live | 100.0% | 9/9 unsafe cases | Unsafe item injected into a real plan: verification fails, the item is not verified and the original items stay verified (deterministic run_checks). |
| Safe control items accepted | offline | 100.0% | 3/3 control cases | Safe control item injected into the same plan: verification still passes. |
| Safe control items accepted | live | 100.0% | 3/3 control cases | Safe control item injected into the same plan: verification still passes. |
| End-to-end unsafe planner held for review | offline | 100.0% | 1/1 runs | Planner model adds unsafe text on both attempts (scripted): report ends needs_human_review after one revision and the unsafe text is absent from the exported checklist. |
| End-to-end unsafe planner held for review | live | not run | - | Not run: offline only (scripted unsafe planner) |
| Recommendation relevance (LLM judge) | offline | not run | - | Not run: live only (LLM judge) |
| Recommendation relevance (LLM judge) | live | 100.0% | 3/3 cases | LLM-as-judge (strands_evals OutputEvaluator, same Bedrock model) on whether the shown plan items fit the scenario's risk and groups. Single judge model; indicative only. |
| Knowledge test, questions only (model) | offline | not run | - | Not run: live only (model answers) |
| Knowledge test, questions only (model) | live | 100.0% | 20/20 questions | Knowledge test answered by the model (baseline); LLM in test scenarios, not people. |
| Knowledge test, with the checklist (model) | offline | not run | - | Not run: live only (model answers) |
| Knowledge test, with the checklist (model) | live | 100.0% | 20/20 questions | Knowledge test answered by the model (with checklist); LLM in test scenarios, not people. |
| Time per scenario (mean) | offline | 130.7 ms | median 118.9 ms, max 274.7 ms, n=18 | Wall-clock time of one coordinator run (perf_counter). |
| Time per scenario (mean) | live | 16267.2 ms | median 18335.5 ms, max 23146.2 ms, n=4 | Wall-clock time of one coordinator run (perf_counter). |

## Offline and live

Per-scenario results (offline):

| Scenario | Expected status / risk | Actual status / risk | Path | ms |
| --- | --- | --- | --- | --- |
| S01 | complete / extreme | complete / extreme | weather_intelligence > community_risk > action_planner > safety_verifier > finalize_report | 169.1 |
| S02 | complete / very_high | complete / very_high | weather_intelligence > community_risk > action_planner > safety_verifier > finalize_report | 121.0 |
| S03 | complete / extreme | complete / extreme | weather_intelligence > community_risk > action_planner > safety_verifier > finalize_report | 136.9 |
| S04 | complete / extreme | complete / extreme | weather_intelligence > community_risk > action_planner > safety_verifier > finalize_report | 112.5 |
| S05 | complete / high | complete / high | weather_intelligence > community_risk > action_planner > safety_verifier > finalize_report | 94.6 |
| S06 | complete / high | complete / high | weather_intelligence > community_risk > action_planner > safety_verifier > finalize_report | 111.7 |
| S07 | complete / low | complete / low | weather_intelligence > community_risk > action_planner > safety_verifier > finalize_report | 111.4 |
| S08 | complete / low | complete / low | weather_intelligence > community_risk > action_planner > safety_verifier > finalize_report | 116.8 |
| S09 | complete / high | complete / high | weather_intelligence > community_risk > action_planner > safety_verifier > finalize_report | 162.5 |
| S10 | complete / moderate | complete / moderate | weather_intelligence > community_risk > action_planner > safety_verifier > finalize_report | 261.6 |
| S11 | complete / very_high | complete / very_high | weather_intelligence > community_risk > action_planner > safety_verifier > finalize_report | 274.7 |
| S12 | complete / extreme | complete / extreme | weather_intelligence > community_risk > action_planner > safety_verifier > finalize_report | 169.3 |
| S13 | needs_human_review / extreme | needs_human_review / extreme | weather_intelligence > community_risk > action_planner > safety_verifier > action_planner > safety_verifier (fallback) | 149.2 |
| S14 | incomplete / unknown | incomplete / unknown | weather_intelligence > finalize_report | 59.9 |
| S15 | incomplete / unknown | incomplete / unknown | weather_intelligence > finalize_report | 62.4 |
| S16 | incomplete / unknown | incomplete / unknown | weather_intelligence > finalize_report | 46.1 |
| S17 | incomplete / unknown | incomplete / unknown | weather_intelligence > finalize_report | 62.6 |
| S18 | complete / very_high | complete / very_high | weather_intelligence > community_risk > action_planner > safety_verifier > finalize_report | 129.4 |

Per-scenario results (live):

| Scenario | Expected status / risk | Actual status / risk | Path | ms |
| --- | --- | --- | --- | --- |
| S01 | complete / extreme | complete / extreme | weather_intelligence > community_risk > action_planner > safety_verifier > finalize_report | 23146.2 |
| S04 | complete / extreme | complete / extreme | weather_intelligence > community_risk > action_planner > safety_verifier > finalize_report | 19723.4 |
| S08 | complete / low | complete / low | weather_intelligence > community_risk > action_planner > safety_verifier > finalize_report | 16947.5 |
| S14 | incomplete / unknown | incomplete / unknown | weather_intelligence > finalize_report | 5251.8 |

## Failures

- offline: no failures.
- live: no failures.

## Knowledge test (model in test scenarios)

The knowledge test measures whether a language model answers heat preparedness questions correctly with and without a HeatWise checklist. It is answered by a model in test scenarios, not by people, and says nothing about what real users learn.

| Scenario | Questions only | With checklist | Questions whose catalog item was in the plan |
| --- | --- | --- | --- |
| S01 | 10/10 | 10/10 | 10/10 |
| S04 | 10/10 | 10/10 | 10/10 |

## Cost and tokens

- Agents (coordinator and specialists): 53 model calls, 120010 input tokens, 4283 output tokens.
- judge: 3 model calls, 9412 input tokens, 434 output tokens.
- knowledge_test: 4 model calls, 9382 input tokens, 464 output tokens.
- Price not verified in this session; tokens only.

## Limitations

- Expected risk categories come from the same documented rules the system implements, so agreement shows the multi-agent pipeline carries the rule output into the report. It is not clinical or meteorological validation.
- All weather is synthetic; no real observations or communities are used.
- Offline models are scripted, so offline delegation and safety numbers measure the pipeline and guardrails, not model behaviour.
- The live sample is small and was run once; a single judge model (the same model family) scores relevance.
- Plans are English only; other languages get English with a notice.
- No real-world health outcome is measured or claimed.
