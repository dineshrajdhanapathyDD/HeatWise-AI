# HeatWise M4 - integration verification (iteration 2)

Date: 2026-11-03. Project dir: `d:\github work\SDK workshop\heatwise-ai`. No git, no commits. No AWS resource created, modified or deleted (no deploy/bootstrap/destroy, no AWS write call; synth read the account id from local credentials, read-only).

## Review findings fixed (review.md, 4 issues)

1. Conditional `s3:ListBucket` (blocking): `infrastructure/stacks/api_stack.py` worker statement is now `s3:ListBucket` on the sessions bucket ARN with no condition (comment explains the 404-vs-403 reason). New infra test `test_list_bucket_unconditioned`. IAM text updated in docs/architecture.md (IAM summary), design.md §10.5, tasks.md M4 findings.
2. Async event age vs stale window: worker `max_event_age` 900 s -> 120 s (120 + 300 s timeout = 420 s `JOB_STALE_AFTER_SECONDS`), and `DynamoDbJobRepository.mark_running` now conditions on `#s = :queued AND created_at >= now - stale_after`, so a late delivery for a job already shown as `assessment_timed_out` is skipped (no run, no record, no status flip; the `max_pending` cap holds). New moto test `test_worker_skips_stale_queued_job`; `test_functions` asserts `MaximumEventAgeInSeconds 120` and event age + timeout <= stale window. design.md §10.2/§10.5/§10.7, docs/architecture.md sequence note, docs/deployment.md §5 updated. User-visible behaviour unchanged (the API already reported such jobs as timed out; now they stay that way).
3. Destroy order: docs/deployment.md §9 now gives two separate blocks, "run exactly one", and explains that with `HeatWiseFrontend` deployed only `destroy --all -c heatwise:frontend=true` works (export of the HTTP API id).
4. Client IPs in access logs (documented, not dropped, to keep behaviour): docs/architecture.md data classification row + sentence; docs/deployment.md "Before you deploy" item 7; design.md §10.5; tasks.md decision 7.

Test/size counts updated in README.md, docs/deployment.md, design.md §10.6/§10.7, tasks.md (265 backend, test_jobs_dynamodb 10, infra 14, asset 64,778,050 bytes).

Housekeeping: a stray `frontend/README.md` (40 bytes, created by a failed shell command in this iteration) was deleted.

## Commands and results

| Command (cwd) | Result |
|---|---|
| `.venv\Scripts\python.exe -m pytest -q` (heatwise-ai) | 265 passed, 4 deselected, 1 warning (Mangum `asyncio.get_event_loop()` DeprecationWarning), 30 s. 223 pre-M4 + 42 new; offline. |
| `infrastructure\.venv\Scripts\python.exe -m pytest infrastructure\tests -q` | 14 passed |
| `npm run typecheck` (frontend) | exit 0 |
| `npm run lint` (frontend) | exit 0 |
| `npm test` (frontend) | 7 files, 46 tests passed |
| `npm run build` (frontend) | exit 0 |
| `.venv\Scripts\python.exe infrastructure\scripts\build_lambda_asset.py` | exit 0; 4,267 files, 64,778,050 bytes (61.8 MiB) unzipped < 262,144,000 |
| `npx --yes aws-cdk@2.1147.0 synth --all` (infrastructure, venv activated) | exit 0; HeatWiseData 5 resources, HeatWiseApi 16; "Unknown option(s): --all" notice as documented. `AWS::ApiGateway::Account` count 0. (cdk.out also still holds HeatWiseFrontend.template.json, 12 resources, from the iteration-1 flagged synth at 03:08; the frontend stack code was not changed.) |

Synthesized checks (cdk.out/HeatWiseApi.template.json):
- `AWS::Lambda::EventInvokeConfig`: `MaximumEventAgeInSeconds 120`, `MaximumRetryAttempts 0`.
- Worker ListBucket statement: `{"Action":"s3:ListBucket","Effect":"Allow","Resource":<import of sessions bucket ARN>}`, no Condition.
- Other IAM statements unchanged from iteration 1: Bedrock scoped to the US profile ARN + 3 foundation-model ARNs; no wildcard actions, no `Resource: "*"` on data stores (asserted by `test_iam_least_privilege`, `test_bedrock_scope`).

## Brief Done check

- Backend pytest offline with tests for DynamoDB store, job repository + worker handler (now incl. stale skip), session selection/continuity, Lambda adapters: yes (265 passed).
- Frontend checks pass: yes.
- `cdk synth` all stacks: yes; resources, IAM, no ApiGateway::Account, asset size as above.
- docs/deployment.md: deploy, smoke-test, destroy (now order-safe) commands, idle-cost statement: present.
- tasks.md 4.1-4.4 checked with findings (incl. review fixes), design.md §10, README: updated.
- Decisions for the user before deploying: API auth, removal policy, Bedrock model access in 3 regions, throttle/max pending/budget alarm, frontend hosting + CORS, log retention + PITR, client IPs in access logs.
