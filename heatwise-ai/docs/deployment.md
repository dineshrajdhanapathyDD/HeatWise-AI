# Deploying HeatWise AI to AWS

This guide covers the infrastructure in `infrastructure/` (Python AWS CDK). Every `deploy`, `destroy` or delete command below is a step you run yourself, after deciding the open points in [Before you deploy](#before-you-deploy). `HeatWiseData` and `HeatWiseApi` were first deployed on 2026-11-03 (see the [Deployment log](#deployment-log)); the Milestone 5 code changes are not deployed yet ([Milestone 5 changes](#milestone-5-changes-redeploy-needed)).

All commands are PowerShell and start from the `heatwise-ai` folder unless a `cd` says otherwise.

## What gets deployed

| Stack | Resources (from `cdk synth`) |
|---|---|
| `HeatWiseData` | 2 DynamoDB tables (assessments, jobs; on-demand), 1 S3 bucket for coordinator sessions (private, SSE-S3, SSL only, `sessions/` expires after 30 days) and its bucket policy. 5 resources incl. CDK metadata. |
| `HeatWiseApi` | API Lambda (FastAPI via Mangum, 512 MB, 29 s) and worker Lambda (1024 MB, 300 s, async, 0 retries), both `python3.13` on arm64 from one zip asset; 2 IAM roles with inline least-privilege policies; 3 log groups (14 days); an HTTP API (`$default` route, access logs, throttling 5 req/s, burst 10). 16 resources. Output `ApiUrl`. |
| `HeatWiseFrontend` (optional, off by default) | Private S3 site bucket behind CloudFront with origin access control, a CloudFront Function for SPA paths, `/api/*` forwarded to the HTTP API with caching disabled, and the CDK `BucketDeployment` that uploads `frontend/dist`. 12 resources. Output `SiteUrl`. |

There is no VPC, no NAT gateway, no provisioned or reserved capacity, no customer-managed KMS key and no `AWS::ApiGateway::Account` (an HTTP API does not use the account-level API Gateway CloudWatch role). See [architecture.md](architecture.md) for the diagrams and IAM details.

## Prerequisites

- Node.js 22 (the CDK CLI runs through `npx --yes aws-cdk@2.1147.0`; do not install it globally).
- [uv](https://docs.astral.sh/uv/) and Python 3.13 (the Lambda runtime is `python3.13`).
- The dev venv from the README (`.venv`, installed with `-e ".[dev]"`).
- AWS CLI v2 and credentials from a named profile or IAM Identity Center (SSO), for example `$env:AWS_PROFILE="my-profile"; aws sso login`. Never put keys in `.env`, `cdk.json` or code.
- Amazon Bedrock model access to Amazon Nova 2 Lite. The worker calls the US cross-region inference profile `us.amazon.nova-2-lite-v1:0` from us-east-1, which can route to us-east-1, us-east-2 and us-west-2 ([model card](https://docs.aws.amazon.com/bedrock/latest/userguide/model-card-amazon-nova-2-lite.html), checked 2026-11-03), so access must be granted in all three Regions.
- us-east-1 is already CDK-bootstrapped in this account. Do not run `cdk bootstrap`.
- Docker is not needed. The Lambda asset is built with uv from prebuilt aarch64 wheels.

Check which account you are pointing at (read-only):

```powershell
aws sts get-caller-identity
```

## 1. Build the Lambda asset

```powershell
.venv\Scripts\python.exe infrastructure\scripts\build_lambda_asset.py
```

The script installs `infrastructure/lambda-requirements.txt` for `aarch64-manylinux_2_28` / Python 3.13 (binary wheels only, versions constrained to the dev venv) into `infrastructure/build/lambda` (git-ignored), copies `backend/` without `tests/` and `__pycache__`, and fails if the unzipped size exceeds 262,144,000 bytes (the Lambda limit). Last run: 4,267 files, 64,778,050 bytes (61.8 MiB) unzipped. Re-run it after any backend change.

## 2. Create the infrastructure venv

```powershell
uv venv infrastructure\.venv --python 3.13
uv pip install --python infrastructure\.venv\Scripts\python.exe -r infrastructure\requirements.txt -r infrastructure\requirements-dev.txt
infrastructure\.venv\Scripts\python.exe -m pytest infrastructure\tests -q
```

Pins: `aws-cdk-lib==2.275.0`, `constructs==10.8.1`, `pytest==9.2.0`. uv writes progress to stderr, which PowerShell shows in red; check the exit code. The infrastructure tests (15 as of Milestone 5) assert the templates offline and need no AWS access.

## 3. Synthesize and review

```powershell
cd infrastructure
.\.venv\Scripts\Activate.ps1
npx --yes aws-cdk@2.1147.0 synth --all
npx --yes aws-cdk@2.1147.0 diff
```

- `synth` writes CloudFormation templates to `infrastructure/cdk.out` (git-ignored) and needs no deployed resources. CLI 2.1147.0 prints `Unknown option(s): --all. These will be ignored` for `synth`, then synthesizes every stack anyway; plain `synth` gives the same result.
- If credentials are available, the CLI reads the account id (read-only) and the templates contain it. Without credentials the account stays an `AWS::AccountId` token.
- `diff` compares against what is deployed and only reads from AWS. It was not run in Milestone 4.

## 4. Deploy (user-approved step: creates billable resources)

Only run this after the decisions in [Before you deploy](#before-you-deploy). It creates the resources listed above in the current account and Region (us-east-1), uploads the asset zip to the existing CDK bootstrap bucket, and asks you to confirm the IAM changes.

```powershell
cd infrastructure
.\.venv\Scripts\Activate.ps1
npx --yes aws-cdk@2.1147.0 deploy HeatWiseData HeatWiseApi
```

The `HeatWiseApi.ApiUrl` output is the API base URL (`https://<api-id>.execute-api.us-east-1.amazonaws.com`).

### Context options

Set in `infrastructure/cdk.json`, or per command with `-c key=value` (the same value must be passed to every later `synth`, `diff`, `deploy` and `destroy`):

| Key | Default | Meaning |
|---|---|---|
| `heatwise:region` | `us-east-1` | Region for all stacks. |
| `heatwise:model_id` | `us.amazon.nova-2-lite-v1:0` | Bedrock model or inference profile id. Only (profile, Region) pairs listed in `infrastructure/stacks/bedrock_routes.py` synthesize; anything else fails with a pointer to the model card instead of guessing the IAM scope. |
| `heatwise:cors_origins` | `["http://localhost:5173", "http://127.0.0.1:5173"]` | Browser origins allowed by FastAPI's CORS middleware (`API_CORS_ORIGINS`). |
| `heatwise:frontend` | `false` | `true` adds the `HeatWiseFrontend` stack. |
| `heatwise:removal` | `retain` | `retain` keeps the tables and buckets on `destroy`; `destroy` deletes them (buckets must be empty). |
| `heatwise:log_retention_days` | `14` | Retention of every log group. |
| `heatwise:throttle_rate` | `5` | HTTP API default route rate limit (requests per second). |
| `heatwise:throttle_burst` | `10` | HTTP API default route burst limit. |
| `heatwise:max_pending_jobs` | `20` | `API_MAX_PENDING_JOBS`: queued plus running jobs before the API answers 429. |
| `heatwise:lambda_asset_dir` | `build/lambda` | Lambda asset folder (relative to `infrastructure/`). |
| `heatwise:frontend_dist` | `../frontend/dist` | Built web app uploaded by the frontend stack. |

## 5. Smoke test

```powershell
$api = aws cloudformation describe-stacks --stack-name HeatWiseApi --region us-east-1 --query "Stacks[0].Outputs[?OutputKey=='ApiUrl'].OutputValue" --output text
Invoke-RestMethod "$api/api/health"

$body = '{"place":{"name":"Nagpur","state":"Maharashtra"},"forecast_days":3,"profile":{"elderly":true,"outdoor_workers":true,"farmers":true}}'
$job = Invoke-RestMethod -Method Post "$api/api/assessments" -ContentType 'application/json' -Body $body
do { Start-Sleep 5; $j = Invoke-RestMethod "$api/api/assessments/$($job.job_id)" } while ($j.status -in 'queued','running')
$j | Select-Object status, duration_ms, report_id, error

$record = Invoke-RestMethod "$api/api/reports/$($j.report_id)"
$record.report | Select-Object status, risk_category, verification_status, revision_count
```

Expect `status: ok` and `agent_mode: bedrock` from health, then a `succeeded` job. A job that is still `queued` or `running` after 420 s (`JOB_STALE_AFTER_SECONDS`: worker timeout 300 s plus 120 s margin) is reported as `failed` with code `assessment_timed_out`. The worker's async event age is capped at 120 s and the worker refuses to start a queued job older than 420 s, so a late delivery never runs a job that was already reported as timed out. The same local run took about 41 s (M3 live run); Lambda timings have not been measured.

## 6. Logs

`HeatWiseApi` has three log groups with 14-day retention: the worker function, the API function, and the HTTP API access log (JSON lines with requestId, ip, requestTime, httpMethod, routeKey, status, protocol, responseLength, integrationErrorMessage). Their names are generated by CloudFormation; list them and tail one (read-only):

```powershell
aws cloudformation describe-stack-resources --stack-name HeatWiseApi --query "StackResources[?ResourceType=='AWS::Logs::LogGroup'].[LogicalResourceId,PhysicalResourceId]" --output table
aws logs tail <PhysicalResourceId> --since 30m --follow
```

Worker errors are logged with their trace; the API only returns the generic error envelope.

## 7. Optional: web app on CloudFront

The frontend stack serves the built dashboard and forwards `/api/*` to the HTTP API on the same origin, so no CORS change is needed. Build the dashboard with same-origin API calls, deploy with the flag, then restore the local build:

```powershell
cd frontend
$env:VITE_API_BASE_URL='/'
npm run build
cd ..\infrastructure
.\.venv\Scripts\Activate.ps1
npx --yes aws-cdk@2.1147.0 deploy HeatWiseData HeatWiseApi HeatWiseFrontend -c heatwise:frontend=true
cd ..\frontend
Remove-Item Env:VITE_API_BASE_URL
npm run build
```

`HeatWiseFrontend.SiteUrl` is the CloudFront URL. Keep passing `-c heatwise:frontend=true` to later `diff`, `deploy` and `destroy` commands; without it the stack is not part of the app and is neither updated nor destroyed. The `BucketDeployment` construct creates its own Lambda, layer and role with CDK-generated grants (`s3:GetObject*`, `s3:List*`, `s3:PutObject`, `s3:DeleteObject*` and similar on the bootstrap assets bucket and the site bucket only, plus the AWS managed `AWSLambdaBasicExecutionRole`).

## 8. Cost

No prices are quoted here; check the official pricing pages for your Region.

Idle (no traffic):

- Lambda, HTTP API and CloudFront: charged per request and compute time, so nothing while idle.
- DynamoDB on-demand, S3 (sessions bucket, site bucket, the asset zip in the CDK bootstrap bucket) and CloudWatch Logs: storage only.
- No NAT gateway, no VPC, no provisioned or reserved capacity, no customer-managed KMS keys (DynamoDB uses AWS-owned keys, S3 uses SSE-S3).

Per assessment:

- Bedrock input and output tokens for Nova 2 Lite: the coordinator and four specialists each call the model, so this is the main variable cost.
- Worker Lambda duration: 1024 MB (1 GB) on arm64 for the length of the run. At the M3 local live run of about 41 s that is about 41 GB-seconds; Lambda runs have not been measured.
- API Lambda (512 MB) and HTTP API requests: one POST, the polls and the report read. The dashboard polls every 1.5 s, and every 3 s after 30 s, so a 41 s run means about 24 polls.
- DynamoDB on-demand reads and writes for the job and the stored record, S3 requests for the coordinator session, CloudWatch Logs ingestion.

Pricing pages: [Amazon Bedrock](https://aws.amazon.com/bedrock/pricing/), [AWS Lambda](https://aws.amazon.com/lambda/pricing/), [Amazon API Gateway](https://aws.amazon.com/api-gateway/pricing/), [Amazon DynamoDB](https://aws.amazon.com/dynamodb/pricing/), [Amazon S3](https://aws.amazon.com/s3/pricing/), [Amazon CloudWatch](https://aws.amazon.com/cloudwatch/pricing/), [Amazon CloudFront](https://aws.amazon.com/cloudfront/pricing/). The HTTP API is public and has no authorizer (see below), so an AWS Budgets alarm is recommended before deploying.

## 9. Destroy

Before destroying, note the physical names of the retained data resources (read-only):

```powershell
aws cloudformation describe-stack-resources --stack-name HeatWiseData --query "StackResources[?ResourceType=='AWS::DynamoDB::Table' || ResourceType=='AWS::S3::Bucket'].[LogicalResourceId,PhysicalResourceId]" --output table
aws cloudformation describe-stack-resources --stack-name HeatWiseFrontend --query "StackResources[?ResourceType=='AWS::S3::Bucket'].[LogicalResourceId,PhysicalResourceId]" --output table
```

(The second command only applies if the frontend stack was deployed.) Then remove the stacks with exactly one of the two commands below:

```powershell
cd infrastructure
.\.venv\Scripts\Activate.ps1
# frontend stack NOT deployed:
npx --yes aws-cdk@2.1147.0 destroy --all
```

```powershell
cd infrastructure
.\.venv\Scripts\Activate.ps1
# frontend stack deployed: run this one instead of the plain command
npx --yes aws-cdk@2.1147.0 destroy --all -c heatwise:frontend=true
```

Use the flagged command whenever `HeatWiseFrontend` exists. `HeatWiseFrontend` imports the HTTP API id exported by `HeatWiseApi`; without the flag the frontend stack is not part of the app, so CDK would try to delete `HeatWiseApi` first and CloudFormation refuses while the export is still in use. With the flag, CDK deletes `HeatWiseFrontend` first, then `HeatWiseApi` and `HeatWiseData`.

With the default `heatwise:removal=retain`, the two tables, the sessions bucket and the site bucket stay in the account after `destroy`, and keep costing storage. Find leftovers later with read-only list commands:

```powershell
aws dynamodb list-tables --query "TableNames[?starts_with(@, 'HeatWiseData')]"
aws s3api list-buckets --query "Buckets[?starts_with(Name, 'heatwise')].Name"
```

Destructive and irreversible: the commands below delete every stored assessment, job and coordinator session. There is no backup (PITR is off and the bucket is unversioned). Replace the placeholders with the names found above and double-check them first.

```powershell
aws dynamodb delete-table --table-name <assessments-table-name>
aws dynamodb delete-table --table-name <jobs-table-name>
aws s3 rm s3://<sessions-bucket-name> --recursive
aws s3api delete-bucket --bucket <sessions-bucket-name>
# site bucket, if the frontend stack was deployed:
aws s3 rm s3://<site-bucket-name> --recursive
aws s3api delete-bucket --bucket <site-bucket-name>
```

Alternative: deploy with `-c heatwise:removal=destroy` from the start (and pass it to `destroy` too). The tables and buckets then use `DeletionPolicy: Delete`. There is no auto-delete custom resource, so empty the buckets with `aws s3 rm s3://<bucket> --recursive` before `destroy`, or CloudFormation cannot delete them.

The three log groups use `RemovalPolicy.DESTROY` and are deleted with the stack.

## 10. Optional: Amazon Bedrock AgentCore Runtime

`backend/agentcore_entry.py` wraps the coordinator with `BedrockAgentCoreApp` and `@app.entrypoint` (the workshop pattern in `_reference/strands-workshop/samples/05-deploy`). The logic lives in `backend/agentcore_handler.py` `run_assessment(payload, session_id)`: it validates the payload (`{"place", "forecast_days", "profile"}` or the same inside `{"request": ...}`) as an `AssessmentRequest`, runs the coordinator and returns the report JSON. It stores nothing. AgentCore Runtime was not deployed in Milestone 4, and this path is an alternative to the Lambda stacks, not part of them.

Prerequisites: Node.js 20 or later, uv, AWS credentials with AgentCore access, Bedrock model access as above. Do not install the old `bedrock-agentcore-starter-toolkit`; it conflicts with the current CLI. Steps, following the workshop README:

```powershell
npm install -g @aws/agentcore --ignore-scripts
agentcore --version

agentcore create        # interactive: enter a name, then choose "Skip"
cd <project-name>
agentcore add           # agent -> name -> "Bring my own code" -> Enter (code location) -> Enter (entrypoint)
                        # -> "Direct Code Deploy" -> "Amazon Bedrock" -> Enter (advanced) -> confirm
```

Copy the backend into the app folder the CLI created (`app\<AgentName>`). `backend/agentcore_entry.py` imports `backend.agentcore_handler`, so the folder that contains `backend\` must be on the import path. Running `backend\agentcore_entry.py` directly as a script would not put it there. Keep the default entrypoint (`main.py`) and make it a two-line shim that points at `backend/agentcore_entry.py`:

```powershell
Copy-Item -Recurse <path-to>\heatwise-ai\backend app\<AgentName>\backend
Remove-Item -Recurse app\<AgentName>\backend\tests
Set-Content app\<AgentName>\main.py "from backend.agentcore_entry import app`n`nif __name__ == '__main__':`n    app.run()"
cd app\<AgentName>
uv init --bare --python 3.13
uv add strands-agents==1.63.0 fastapi==0.162.0 pydantic==2.14.2 pydantic-settings==2.16.2 httpx==0.28.1 boto3==1.43.123 bedrock-agentcore==1.25.2
cd ..\..
```

Configure the runtime environment with `SESSION_STORAGE=none` (AgentCore keeps its own session; the file store would write into the runtime's local disk), and `AWS_REGION` / `BEDROCK_MODEL_ID` if they differ from the defaults. Then:

```powershell
agentcore dev       # local server for testing
agentcore deploy    # packages to S3 and provisions the runtime (creates billable resources)
agentcore invoke --session-id heatwise-assessment-session-000000001 '{"place":{"name":"Nagpur","state":"Maharashtra"},"forecast_days":3,"profile":{"elderly":true}}'
```

A `--session-id` must be at least 33 characters. The workshop invokes with a text prompt; how `agentcore invoke` wraps a JSON argument was not verified in Milestone 4. If the entrypoint answers with a validation error, call the runtime with boto3 instead, which sends the body unchanged (ARN from `agentcore status`):

```python
import json, uuid, boto3

client = boto3.client("bedrock-agentcore", region_name="us-east-1")
body = {"place": {"name": "Nagpur", "state": "Maharashtra"}, "forecast_days": 3, "profile": {"elderly": True}}
response = client.invoke_agent_runtime(
    agentRuntimeArn="<ARN from agentcore status>",
    runtimeSessionId=str(uuid.uuid4()),
    payload=json.dumps(body).encode(),
    qualifier="DEFAULT",
)
print("".join(chunk.decode("utf-8") for chunk in response.get("response", [])))
```

Cleanup is two steps: `agentcore remove all -y` resets the local config only, and the following `agentcore deploy` removes the runtime and its CloudFormation stack from AWS.

```powershell
agentcore remove all -y
agentcore deploy
```

## Before you deploy

These were left open in Milestone 4 and need your decision:

1. API auth. The HTTP API is public and unauthenticated; anyone with the URL can start Bedrock runs, bounded only by throttling (5 req/s, burst 10) and 20 pending jobs. Options: keep it for a short demo, IAM auth, a Cognito JWT authorizer, or only exposing it through CloudFront.
2. Removal policy: `retain` (default) or `destroy` for the tables and buckets.
3. Bedrock model access for Nova 2 Lite in us-east-1, us-east-2 and us-west-2, and the model id.
4. Throttle limits, `heatwise:max_pending_jobs`, optional reserved concurrency for the worker (not set, because new accounts can have a low concurrency quota), and an AWS Budgets alarm.
5. Frontend hosting on CloudFront or local only, and the CORS origins.
6. Log retention (14 days) and DynamoDB point-in-time recovery (off).
7. Client IP addresses in the HTTP API access log. The access log format records `$context.identity.sourceIp` for every request and keeps it for 14 days; IP addresses are commonly treated as personal data. Options: keep it (useful to spot abuse of the public API), drop the `ip` field from `_ACCESS_LOG_FORMAT` in `infrastructure/stacks/api_stack.py`, or shorten `heatwise:log_retention_days`.

## Milestone 5 changes (redeploy needed)

Milestone 5 changed the backend and one IAM statement. None of it is deployed: a read-only `describe-stacks` on 2026-11-03 shows `HeatWiseApi` at `UPDATE_COMPLETE` from the Milestone 4 deploy (last update 04:26 UTC), before these changes.

- New routes in the Lambda code: `POST /api/reports/{report_id}/checklist` and `GET /api/evaluation`, plus new `GET /api/metrics` fields. The deployed API Lambda does not have them, so the Impact screen and the Plan checkboxes only work against a local API until you redeploy.
- IAM: the API role gets a new statement, `dynamodb:UpdateItem` on the assessments table ARN only (no index ARN), in `infrastructure/stacks/api_stack.py` (test `test_api_role_checklist_update`). Without it, a checklist update on the deployed API would fail with a 500 even after a code-only update.
- The evaluation results file (`backend/evaluation/results/evaluation-results.json`) is copied into the asset with `backend/`. `strands-agents-evals` is a dev/eval extra and is not in `infrastructure/lambda-requirements.txt`.

To roll it out (a user-approved step: it changes live resources and asks you to confirm the IAM change):

```powershell
.venv\Scripts\python.exe infrastructure\scripts\build_lambda_asset.py
cd infrastructure
.\.venv\Scripts\Activate.ps1
npx --yes aws-cdk@2.1147.0 diff HeatWiseApi -c heatwise:removal=destroy
npx --yes aws-cdk@2.1147.0 deploy HeatWiseApi -c heatwise:removal=destroy
```

Pass the same `-c heatwise:removal=destroy` the first deploy used (see the log below). Only `HeatWiseApi` changes; `HeatWiseData` has no Milestone 5 change.

Integrity warning: the deployed API has no authentication, and `/api/history` lists report ids. After this redeploy, anyone with the URL can tick or untick checklist items on any listed report. Treat the Impact screen's "checklist items completed" count on the deployed API as untrustworthy until auth is added (decision 1). Throttling limits volume, not integrity.

## Deployment log

**2026-11-03, first deploy (us-east-1)**
- Stacks: `HeatWiseData` and `HeatWiseApi`, deployed with `-c heatwise:removal=destroy`. Tables and the sessions bucket are deleted with the stack, so pass the same flag to `destroy`. `HeatWiseFrontend` is not deployed; the dashboard runs locally.
- API URL: `https://pwnenvmo71.execute-api.us-east-1.amazonaws.com`. It is public and unauthenticated (decision 1: demo window, then destroy).
- Other open decisions taken as recommended: Nova 2 Lite; default throttles (5 req/s, burst 10, 20 pending jobs); 14-day log retention; PITR off; client IPs kept in the access log.
- Smoke test: `GET /api/health` returned ok (agent_mode bedrock, open_meteo). A live Nagpur assessment succeeded in 16.4 s worker time (23 s wall-clock): status complete, risk high, verification passed, 0 revisions, live Open-Meteo data. `/api/history` listed it.
- Incident: on the first deploy both Lambdas got a partial 1,400-file zip (no `fastapi`/`mangum`), and every route returned 500 (`Runtime.ImportModuleError: No module named 'mangum'`). An earlier interrupted `cdk diff` had staged a partial copy under the full asset's hash. CDK uploaded it, and later deploys skipped the upload as "no changes". Fix: `build_lambda_asset.py` now writes a `BUILD_ID.txt` marker on every build, so every build gets a new asset hash. Don't interrupt `synth`/`diff`/`deploy` while they stage assets.
- Not done yet: AWS Budgets alarm (it needs a notification email).
