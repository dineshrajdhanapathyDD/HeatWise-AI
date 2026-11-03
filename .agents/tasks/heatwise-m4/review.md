# Persistence and AWS infrastructure as code for HeatWise AI (M4), review pass 2

This pass checks the fixes for the four issues raised in pass 1 and looks for new problems they introduced. The worker's `s3:ListBucket` no longer has a condition. Async event age is down to 120 s. `mark_running` now refuses jobs older than the stale window. The destroy section gives two mutually exclusive commands. Client IPs in the access log are documented as a pre-deploy decision. The recorded evidence (verification.md, iteration 2) shows 265 backend tests passing (223 existing + 42 new), 4 deselected, 46 frontend tests, 14 infra tests, synth exit 0 with `AWS::ApiGateway::Account` count 0, a 61.8 MiB unzipped asset, and no AWS write calls. Spec, docs and README match the new values.

Watch for: two small leftovers that don't block shipping. A job finishing right at the 420 s edge can still flip from the reported `assessment_timed_out` to `succeeded` (**possible**). Redeploying the optional frontend doesn't invalidate CloudFront, so `index.html` can be served stale (**confirmed**, optional stack only).

**Verdict**: APPROVED

## High-level view

The two blocking items are closed in code and locked in by tests. The worker's ListBucket statement targets only the sessions bucket ARN and has no `Condition`, so a new session's missing `session.json` returns 404 and Strands treats it as new. `test_list_bucket_unconditioned` asserts this. For late events there are two independent guards: `MaximumEventAgeInSeconds 120` plus a 300 s timeout fits the 420 s stale window (asserted in `test_functions`), and the `mark_running` condition `#s = :queued AND created_at >= cutoff` makes a late delivery a no-op. The moto test `test_worker_skips_stale_queued_job` checks that nothing runs, nothing is stored and the job stays `queued`/timed out.

All brief constraints that pass 1 confirmed still hold. Bedrock is limited to the US inference profile plus the us-east-1/us-east-2/us-west-2 foundation-model ARNs. The data and API stacks have no wildcard actions and no `Resource: "*"`. There is no ApiGateway Account or RestApi. Every log group has retention set, including the `BucketDeployment` log group in the optional stack. All new dependencies are pinned exactly, tests are offline (moto and stubs), and `JobView` and the routes are unchanged. The docs have exact deploy, smoke-test and destroy commands and an idle-cost statement.

<details>
<summary>Issues (2)</summary>

1. **Stale-edge flip to succeeded** (possible, non-blocking): `mark_succeeded`/`mark_failed` only require the item to exist. An event delivered near the 120 s limit, plus cold-start init and clock skew between hosts, can finish a few seconds after `created_at + 420 s`, after the API already showed `assessment_timed_out`. Optionally add a small margin (for example `JOB_STALE_AFTER_SECONDS` 450), or accept it and note it in design.md §10.2.
2. **No CloudFront invalidation on frontend redeploy** (confirmed, optional stack): `BucketDeployment` gets no `distribution=`/`distribution_paths`, so an updated `index.html` can be cached at the edge for up to the default TTL. Pass `distribution=distribution, distribution_paths=["/index.html"]` (this adds a CloudFront invalidation permission to the CDK-generated role), or document a manual invalidation.

</details>

<details>
<summary>Details</summary>

### Stale window arithmetic at the edge

The invariant in `api_stack.py` is event age (120 s) + worker timeout (300 s) = `JOB_STALE_AFTER_SECONDS` (420 s), and `test_functions` asserts `120 + 300 <= 420`. There is no margin. The Lambda function timeout covers the handler invocation, and on a cold start the init phase runs before it. `created_at` is written by the API host's clock, and the worker's "now" comes from a different host. So a job accepted by `mark_running` at about 119 s can still be running at 420 s on the API's clock. `get` then reports `assessment_timed_out`. The dashboard stops polling, and a few seconds later `_finish` writes `succeeded` and stores a record that appears in history. The window is seconds wide and costs no extra Bedrock run, so this isn't blocking. A 30 s margin in the stale setting (both function envs and the config default) would close it, and the assertion could become a strict inequality.

### Frontend redeploys and CloudFront caching

`frontend_stack.py` deploys `frontend/dist` with `BucketDeployment(sources=..., destination_bucket=bucket, log_group=...)` and no distribution. Vite's hashed asset names make the JS and CSS safe. `index.html` keeps its name, though, and the default S3 behavior uses CloudFront's default cache policy, so edge locations can serve the old `index.html`, which points at the old hashed bundles, after a redeploy. This only affects the optional, off-by-default stack and doesn't change the API.

### Test coverage

New since pass 1: `test_list_bucket_unconditioned` (single ListBucket statement, no Condition, single resource), the `EventInvokeConfig` assertion (0 retries, 120 s age), and `test_worker_skips_stale_queued_job` (moto, aged item).

Not tested: IAM behaviour against real services (moto ignores IAM, so the ListBucket fix is only verified by template shape until the first smoke test); `count_pending` across more than one query page; the stale-edge timing above.

</details>

<details>
<summary>File map</summary>

- `infrastructure/stacks/api_stack.py`: unconditioned worker `s3:ListBucket`, `max_event_age` 120 s.
- `backend/api/dynamodb_jobs.py`: `mark_running` condition adds `created_at >= now - stale_after`.
- `backend/tests/test_jobs_dynamodb.py`: `test_worker_skips_stale_queued_job`.
- `infrastructure/tests/test_stacks.py`: `test_list_bucket_unconditioned`, event-config assertions.
- `docs/deployment.md`: §9 destroy as two exclusive commands, "Before you deploy" item 7 (client IPs).
- `docs/architecture.md`: data classification row for access logs, IAM summary text.
- `README.md`, spec `design.md` §10.2/§10.5/§10.6/§10.7, `tasks.md` M4 findings and review fixes: updated counts and wording.

Not a git repo, so there is no diff; files were read in place. The pass-1 file map still applies to the full M4 change.

</details>
