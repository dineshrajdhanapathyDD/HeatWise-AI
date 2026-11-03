# HeatWise M5: synthetic evaluation suite, checklist progress, Impact screen and submission docs

M5 adds a synthetic evaluation harness (`backend/evaluation/`) that runs the real coordinator over 18 fixture scenarios offline (scripted models, inside pytest) and once live on Nova 2 Lite with a `strands_evals` judge and a model-answered knowledge test, writing one results JSON and a generated `docs/evaluation.md`. It adds community-level checklist progress (`POST /api/reports/{id}/checklist`, renderable ids only) stored in both stores, extends `/api/metrics`, serves the results at `GET /api/evaluation`, and surfaces both on a new `/impact` screen and Plan-tab checkboxes. The submission docs (article, demo script, checklist, workflow, architecture, deployment, README) and the three spec files were brought up to date. The review is file-based (no git diff): files were identified from FEAT steps and write times, and verification results were read from the FEAT findings, not re-run.

Watch for: live adversarial numbers (9/9, 3/3) are deterministic `run_checks` on a live plan but sit under the "Live (Nova 2 Lite)" column in the article and as "Live Nova" on the Impact panel (minor, confirmed); the new checklist write path will be publicly writable on the unauthenticated deployed API after redeploy, which the docs do not state (minor, likely); the live CLI prints an unverified cost estimate "well under 1 USD" (minor, confirmed); two qualifying conditions in `submission-checklist.md` are not covered by the recorded fetch evidence (minor, likely).

**Verdict**: APPROVED

## High-level view

The evaluation is honest by construction. Every number in `docs/evaluation.md`, the README, the article and tasks.md matches `backend/evaluation/results/evaluation-results.json` (checked field by field: offline 18/18, 326/326, 322/322, 13/18, 9/9, 3/3, 1/1, 130.7 ms; live 4/4, 71/71, 101/101, 4/4, 3/3, 20/20, 16267.2 ms; tokens 53 calls 120010/4283, judge 3 calls 9412/434, knowledge 4 calls 9382/464). The live section has a 2026-11-03 06:03:22 UTC start, and the four raw reports exist under `.data/evaluation/live-20261103T060322Z/`. Cost stays "price not verified; tokens only" with no dollar figure in any doc. Weaknesses are stated, not hidden: 13/18 model-driven delegation offline, the knowledge test showing no difference (20/20 both ways), "LLM in test scenarios, not people", and rules-derived expectations described as "not clinical validation".

The checklist API is gated by `renderable_item_ids`, a line-for-line twin of `renderablePlanItems` in `safety.ts`. On `needs_human_review` a withheld item 404s before the store is touched. The verification rules themselves (`verification_tools.py`, `claims.py`, `safety.ts`) were not modified in M5, and the adversarial run shows the phone (`Call 108`), diagnosis, medication, dose, alcohol, water-limiting, external-action and discourage-help cases still rejected by `banned_content`/`text_claims`. Pins are exact (`strands-agents-evals==1.8.0` in `dev` and `eval` only, not in `lambda-requirements.txt`), and the CDK change adds one `dynamodb:UpdateItem` statement on the assessments table ARN only, with a template test. Nothing was deployed; the AWS calls were read-only `describe-stacks`/`list-stack-resources` plus the opt-in live Bedrock run.

The gaps are about how the numbers and the new write path are presented. The live adversarial rows measure deterministic checks on a model-built plan, but they sit in the live column without that qualifier in the article and on the Impact panel. Once the API is redeployed, the checklist endpoint is a new unauthenticated mutation, and `/api/history` lists every report id. The docs note that the API is public, but they don't say that checklist progress (and so the Impact counts) can be changed by anyone.

<details>
<summary>Issues (4)</summary>

1. **Live adversarial rows read as model behaviour** (minor, confirmed). In `docs/builder-center-article.md` the measured-results table and in `frontend/src/routes/Impact.tsx` (via `lib/evaluation.ts`), mark the live "Unsafe injected items rejected" and "Safe control items accepted" values as deterministic `run_checks` on a live plan. Adding that to the article's "What the numbers say" bullets is enough.
2. **Public checklist writes after redeploy** (minor, likely). State in `docs/deployment.md` "Milestone 5 changes" (and the submission checklist's hygiene section) that on the unauthenticated API anyone can tick or untick items on any listed report, so Impact checklist counts are not trustworthy there until auth is added.
3. **Unverified cost claim in the live CLI** (minor, confirmed). `backend/evaluation/__main__.py` prints "expected well under 1 USD" even though the price was not verified. Drop the figure or say "price not verified".
4. **Qualifying conditions not traced to the fetch** (minor, likely). In `docs/submission-checklist.md`, "Entrants must be 18 or older with a Builder Center profile" and "climate resilience is one of the listed focus areas" are not in the recorded fetch evidence (FEAT-003 lists the five items, workshop window, due date and rubric). Confirm them against the page or mark them TODO like the Rules.

</details>

<details>
<summary>Details</summary>

## Live-column labelling and cost wording

The live adversarial metrics come from `run_adversarial(..., "live", include_end_to_end=False)`, which injects items into `st.plans[-1]` of the first complete live scenario and calls `run_checks`. That is labelled correctly in evaluation.md's note column ("deterministic run_checks"). The article table, however, places 9/9 and 3/3 under "Live (Nova 2 Lite, 2026-11-03 06:03 UTC)", and the Impact panel shows "Live Nova" beside them. The article's caveat bullet covers only offline safety numbers, so a reader can take 9/9 as the model refusing unsafe content (confirmed).

The live CLI preamble in `__main__.py` says "This calls Amazon Bedrock and costs money (expected well under 1 USD)". That is an unverified price assertion in the same run whose results correctly say "price not verified". It only reaches stdout, not any doc (confirmed).

## Checklist write path and the safety rendering rule

```
POST /api/reports/{id}/checklist
  -> store.get(id)                 404 if missing
  -> renderable_item_ids(report)   complete: all | needs_human_review: verified_item_ids | else: none
  -> item_id not in renderable     404, nothing stored
  -> store.set_checklist_item      JSON: under lock | DynamoDB: get_item + update_item(attribute_exists)
```

The deployed HTTP API is public and unauthenticated (documented decision 1), and `/api/history` returns report ids. After the redeploy, anyone can tick or untick any report's checklist, and the Impact "Checklist items completed" figure changes with it. Throttling (5 req/s) limits volume but not integrity. Earlier, the only public write was job submission. The deployment and submission docs mention the public API but not this new mutable state (likely).

## Submission checklist facts

Two statements in `submission-checklist.md` are not covered by the recorded fetch summary in FEAT-003: the "18 or older with a Builder Center profile" eligibility line and "climate resilience is one of the listed focus areas" (likely). The section reads as if both came from the fetched page, but the recorded evidence doesn't cover them.

</details>

<details>
<summary>File map</summary>

- `pyproject.toml`: `strands-agents-evals==1.8.0` in `dev`, new `eval` extra.
- `backend/evaluation/{dataset,provider,metrics,adversarial,results,runner,live,judge,report,__main__}.py`: harness, live runner, judge, report generator, CLI.
- `backend/evaluation/datasets/{scenarios,knowledge-test,adversarial}-v1.json`: synthetic datasets.
- `backend/evaluation/results/evaluation-results.json`, `docs/evaluation.md`: generated results and report.
- `backend/agents/offline.py`: `provider=` keyword on `build_offline_coordinator`.
- `backend/session/{store,dynamodb_store,dynamodb_schema}.py`: `checklist_completed`, `set_checklist_item`, `checklist_json`.
- `backend/api/{checklist,schemas,routes,summaries}.py`, `backend/config.py`: checklist and evaluation endpoints, metrics fields, `evaluation_results_path`.
- `infrastructure/stacks/api_stack.py`, `infrastructure/tests/test_stacks.py`: API-role `dynamodb:UpdateItem` on the assessments table, plus a test.
- `backend/tests/{test_evaluation_dataset,test_evaluation_harness,test_evaluation_live,test_api,test_store,test_dynamodb_store}.py`: new and extended tests.
- `frontend/src/{api/types.ts,api/client.ts,App.tsx,components/AppShell.tsx,lib/evaluation.ts,routes/Impact.tsx,routes/Impact.test.tsx,routes/report/PlanView.tsx,routes/report/report.test.tsx}`: checkboxes, Impact screen, tests.
- `.gitignore`: `.agents/`, `*.log`.
- `docs/{agent-workflow,architecture,builder-center-article,demo-script,submission-checklist,deployment}.md`, `README.md`: submission docs.
- `.kiro/specs/heatwise-ai/{tasks,design,requirements}.md`: M5 spec sync.

No git repository, so there is no diff. Files were identified from the FEAT steps, the plan and write times after 2026-11-03 10:50.

</details>
