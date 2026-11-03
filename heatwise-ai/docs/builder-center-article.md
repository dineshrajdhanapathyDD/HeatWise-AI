# HeatWise AI: from weather intelligence to community action



GitHub Repo: https://github.com/dineshrajdhanapathyDD/HeatWise-AI.git

Live dashboard: https://main.dmupjpltx9cou.amplifyapp.com


## The problem

Heatwaves build over days, and the people most exposed are often the ones with the least time and information to prepare: older people, young children, people living with chronic illness, outdoor workers and farming households, and communities with limited drinking water or shade. A village volunteer or a local health worker usually has a weather app and a forecast number, but not a plan: what to do before, during and after the hot days, for which group, and when to get help.

HeatWise AI turns a place name and a short, community-level profile into a verified preparedness plan. It is an informational and preparedness tool. It does not diagnose anyone, does not send alerts, does not contact anyone, and its forecast values are never presented as official warnings.

## Who it is for

- Community volunteers, local health and anganwadi workers, farmer groups and NGOs who prepare a village or a neighbourhood for hot days.
- Households, outdoor workers and farmers, who get separate before / during / after actions.

The request takes only the place, the forecast length and yes/no community indicators (for example "older people live here", "limited water", terrain). Requests with any other field, such as a name or a phone number, are rejected before anything is stored.

## What it does

1. Fetches current conditions and a 1-7 day forecast from Open-Meteo, with provider, source URL, retrieval time and staleness on every value.
2. Classifies community heat risk with documented, deterministic rules: the NWS heat index bands, the IMD actual-maximum heat-wave criteria (as an indication only, never an official declaration) and a labelled project heuristic for vulnerability indicators.
3. Builds a plan for households, outdoor workers and farmers from a catalog of guidance items, each tied to a trusted source (WHO, NWS, Ready.gov, FAO and others listed in `backend/guidance/sources.py`).
4. Verifies the plan with deterministic safety checks before anyone sees it: data freshness, trusted sources, no medication, dose, diagnosis or unverified phone numbers, escalation advice present, consistent risk category, no unsupported numbers in free text.
5. Shows the result on a dashboard. The home page has a risk overview with a gauge, weather intelligence with a forecast trend chart, community impact, "What should the community do?", the latest assessment and the agent pipeline. A three-step form (Place, Community, Settings and review) starts an assessment. Each report has Climate, Risk, Plan and Agent activity views, and there are History and Impact pages. A Markdown checklist can be exported to print or share. Data the backend does not provide, such as hourly forecasts or per-agent live progress, is shown as unavailable with the missing field named, never filled in.

If the plan fails verification, the planner gets one revision with the issues. If it still fails, the report is marked `needs_human_review` and only the verified items are shown and exported.

## Screenshots

Taken with Playwright from the live Amplify site. The files are in [`screenshots/`](../../screenshots/) in the repo. When publishing on Builder Center, upload these images in the editor, because relative repo paths do not render there.

- Home, desktop: [`amplify-home-desktop.png`](../../screenshots/amplify-home-desktop.png) (full page: [`amplify-home-full.png`](../../screenshots/amplify-home-full.png))
- Home, mobile: [`amplify-home-mobile.png`](../../screenshots/amplify-home-mobile.png) (full page: [`amplify-home-mobile-full.png`](../../screenshots/amplify-home-mobile-full.png))
- New assessment form: [`amplify-assess-direct-link.png`](../../screenshots/amplify-assess-direct-link.png)
- Report, Climate view: [`amplify-report-climate.png`](../../screenshots/amplify-report-climate.png)
- Impact page: [`amplify-impact-full.png`](../../screenshots/amplify-impact-full.png)

## Multi-agent architecture

A coordinator agent delegates to four specialists (agents as tools): Weather Intelligence, Community Risk, Action Planner and Safety and Verification. The coordinator's tools pass data between specialists in code and return short JSON summaries to the model, so the model never copies weather or plan data by hand. Numbers come from tool results captured by a hook, not from model text. Details and diagrams: [agent-workflow.md](agent-workflow.md) and [architecture.md](architecture.md) (editable diagram: [architecture.drawio](architecture.drawio)).

## Strands Agents SDK features used

| Feature | Where |
|---|---|
| `Agent` (system prompt, tools, hooks, plugins, structured output) | `backend/agents/coordinator.py`, `weather_agent.py`, `risk_agent.py`, `planner_agent.py`, `safety_agent.py` |
| `@tool` | `backend/tools/*.py` and the coordinator's delegation tools |
| `BedrockModel` (Amazon Nova 2 Lite, `us.amazon.nova-2-lite-v1:0`) | `backend/agents/model_factory.py` |
| Hooks: `GuardrailHook` (allowlist, input validation, call cap) and `EvidenceLedgerHook` (records every tool result) | `backend/agents/hooks.py` |
| Per-invocation limits (`turns`, `structured_output_attempts`) | every agent's `run` |
| `AgentSkills` plugin with three `SKILL.md` files | `backend/agents/planner_agent.py`, `backend/skills/` |
| Steering plugin: `OrderingSteeringHandler` (`SteeringHandler`, `Proceed`, `Guide`) keeps weather -> risk -> plan -> safety and one revision | `backend/agents/coordinator.py` |
| `SequentialToolExecutor` on the coordinator | `backend/agents/coordinator.py` |
| `FileSessionManager` for the coordinator conversation locally. On AgentCore Runtime the session is keyed by `runtimeSessionId`, and `S3SessionManager` remains for the Lambda-hosted mode | `backend/session/sessions.py` |
| Deployment on Amazon Bedrock AgentCore Runtime: `BedrockAgentCoreApp` and `@app.entrypoint` wrap the coordinator; the worker calls `invoke_agent_runtime` | `backend/agentcore_entry.py`, `backend/agentcore_handler.py`, `backend/agents/agentcore_client.py`, `HeatWiseAC/` |
| `strands_evals` `Case`, `Experiment`, `OutputEvaluator` (LLM-as-judge in the live evaluation) | `backend/evaluation/judge.py` |
| A scripted Strands `Model` for offline runs and tests | `backend/agents/scripted.py`, `backend/agents/offline.py` |

## AWS services

Deployed in us-east-1 on 2026-11-03 (deploy outputs and live checks in [deployment.md](deployment.md)):

- **Amazon Bedrock AgentCore Runtime** hosts the agents. The coordinator and its four specialists are deployed as the runtime `HeatWiseAC_heatwise_agent` with the `agentcore` CLI, as in the workshop's deploy module. The code is a CodeZip bundle built without Docker, and the entrypoint is `BedrockAgentCoreApp` with `@app.entrypoint`. One live assessment invoked directly took 24.0 s. Through the public API, one took 19.5 s. Both produced complete, verified reports.
- **Amazon Bedrock** (Nova 2 Lite, `us.amazon.nova-2-lite-v1:0`) is the model for every agent, called from inside the runtime.
- **AWS Lambda and Amazon API Gateway** (HTTP API) carry the dashboard's job API. The API Lambda creates the job. A worker Lambda (arm64, 1024 MB) calls `invoke_agent_runtime` once and stores the report. It runs no agents, and its only AgentCore permission is to invoke that runtime. It exists because an HTTP API request times out at 30 s, which is too close to an agent run.
- **Amazon DynamoDB** stores jobs and reports (on-demand). **Amazon CloudWatch Logs** holds the API, worker and runtime logs. **AWS IAM** roles are scoped per function. **AWS CloudFormation** (CDK and the AgentCore CLI) defines all of it.
- **AWS Amplify Hosting** serves the React dashboard at https://main.dmupjpltx9cou.amplifyapp.com, built from the GitHub repo with `amplify.yml`. The API allows this origin through CORS.

The runtime's execution role is the AgentCore CLI default. It allows Bedrock model invocation on any model in the account, which is wider than the Lambda roles. A custom `executionRoleArn` would narrow it to Nova 2 Lite. An optional CloudFront stack for the dashboard is still in the code, but it is not deployed and is not used. Amplify replaced it.

## How we evaluated it

The evaluation suite (`backend/evaluation/`, report in [evaluation.md](evaluation.md)) runs the real coordinator over 18 synthetic scenarios: hot-dry plains, humid coast, mild hills, missing humidity, a stale observation, provider errors, an invalid location and a Hindi request. Weather comes from labelled synthetic fixtures, so every extracted value has exact ground truth. Expected risk categories were derived by hand from the documented rules and re-checked by an independent implementation in the tests. It has two modes:

- Offline: scripted models through the real Strands loop, hooks, steering and fallback. It needs no AWS and also runs inside `pytest`.
- Live: Amazon Bedrock (Nova 2 Lite, us-east-1) on 4 scenarios, plus an LLM judge (`strands_evals` `OutputEvaluator`) for recommendation relevance and a 10-question knowledge test answered by the model.

The test suites cover the rest: 338 backend tests (4 live tests deselected by default), 73 frontend tests in 10 files and 16 infrastructure tests.

## Measured results

All values below are quoted from [docs/evaluation.md](evaluation.md), generated from `backend/evaluation/results/evaluation-results.json`. They are results on synthetic test scenarios, labelled with the mode they were measured in. They are not observations of real communities, and no real-world health outcome is measured or claimed.

| Metric | Offline (scripted, 2026-11-03 06:00 UTC) | Live (Nova 2 Lite, 2026-11-03 06:03 UTC) |
|---|---|---|
| Workflow completed with the expected status | 18/18 scenarios | 4/4 scenarios |
| Risk category agrees with the documented rules | 18/18 | 4/4 |
| Weather fields extracted exactly | 326/326 fields | 71/71 fields |
| Plan items with trusted sources | 322/322 items | 101/101 items |
| Delegation order correct (fallback allowed) | 18/18 | 4/4 |
| Delegation order driven by the model alone | 13/18 (72.2%) | 4/4 |
| Unsafe injected items rejected | 9/9 | 9/9 |
| Safe control items accepted | 3/3 | 3/3 |
| Unsafe planner held for review end to end | 1/1 | not run (offline only) |
| Recommendation relevance (LLM judge) | not run (live only) | 3/3 cases passed |
| Knowledge test, questions only / with the checklist (model) | not run (live only) | 20/20 / 20/20 questions |
| Mean time per scenario | 130.7 ms | 16267.2 ms |

What the numbers say, and what they do not:

- Risk agreement shows that the multi-agent pipeline carries the documented rule output into the report. It is not clinical or meteorological validation.
- The "unsafe injected items rejected" (9/9) and "safe control items accepted" (3/3) rows in the live column come from the deterministic `run_checks` applied to a plan produced live. They measure the guardrail code, not the model refusing unsafe content.
- Offline delegation and safety numbers measure the pipeline and guardrails, not model behaviour. 13/18 is lower because the offline script does not plan the revision or the early finalize, so steering or the deterministic fallback finishes those runs.
- The knowledge test was answered by a language model in test scenarios, not by people. Both conditions scored 20/20, so it shows no measurable difference.
- The live sample is small (4 scenarios, one run) and a single judge model scored relevance.
- The live run used 53 agent model calls (120010 input and 4283 output tokens), 3 judge calls and 4 knowledge-test calls. The token cost of the agent calls is worked out in [Pricing](#pricing).

## What we learned

- Let code own the numbers. The evidence ledger hook made it easy to keep model text out of weather values and risk categories, and to replace a summary when it disagreed with the data.
- Steering plus a deterministic fallback gives a predictable workflow without a rigid graph: the model drives when it gets the order right, and the run still finishes safely when it does not.
- Small, flat structured-output schemas and a cap of two attempts worked better with Nova 2 Lite than larger schemas with retries.
- Making the evaluation run offline, with the same code path as production, turned it into a regression test.
- Put the agents on AgentCore Runtime from the start. Our first deploy ran the agents inside Lambda. Moving them to AgentCore left the worker Lambda with one job: call `invoke_agent_runtime` and store the report.
- Check the installed `agentcore` CLI version against the docs. The CLI version we installed did not match the commands in the workshop README, so the installed CLI's own help was the reliable reference.
- Design around the 30 s HTTP API timeout. An assessment takes about 20-25 s, so the API returns a job id at once and an async worker does the run. The dashboard polls the job.
- Check the UI in a real browser. Unit tests passed, but Playwright screenshots of the live site found a horizontal overflow on mobile (from screen-reader-only tables), wrong page titles on trailing-slash URLs and a cloud drawn when no rain was reported.

## Limitations

- **Weather data.** Open-Meteo provides model data, not observations, and publishes no government warnings. There is no adapter for the India Meteorological Department (IMD) API yet.
- **Risk rules.** Risk uses one forecast point per place. The IMD departure-from-normal and coastal heat-wave criteria are not implemented because they need climatological normals. The IMD result is an indication only, never an official declaration.
- **Forecast detail.** The backend fetches daily values only. Hourly forecasts and cloud cover are not available, and the dashboard says so.
- **Progress reporting.** The job API reports one overall status per job. It does not stream per-agent progress, so the agent pipeline on the dashboard shows the final activity, not live steps.
- **Language.** Plans are English only. Requests in other languages get the English plan with a notice.
- **Access control.** The deployed HTTP API is public and has no authentication, for the demo window. Anyone with the URL can start assessments and add checklist items.
- **Runtime permissions.** The AgentCore runtime uses the CLI's default execution role, which allows Bedrock invocation on any model in the account.
- **Evaluation.** The scenarios are synthetic, and the live sample is small (4 scenarios, one run, one judge model). Nothing here measures real-world use or health outcomes.
- **Region.** Everything runs in us-east-1 only.
- **Hosting.** Deep links such as `/assess` and `/history` return HTTP 404 on Amplify until the single-page-app rewrite rule is added in the console. The page still loads and renders.

## Future work

- An IMD API adapter, once its endpoint schemas are verified, so official warnings can sit next to the forecast.
- Cognito or IAM authorization on the API before wider use.
- Localized plans, starting with the languages of the pilot communities, with guidance reviewed by local health workers.
- Hourly forecast data for peak-heat timing in the plan.
- Per-agent progress streamed to the dashboard while a run is in progress.
- A custom `executionRoleArn` for the runtime, scoped to Nova 2 Lite.
- Lower idle cost by ending each session after the report is stored, with the `StopRuntimeSession` API, or by setting a shorter idle timeout (the CLI accepts `--idle-timeout` from 60 to 28800 seconds).
- A field study with community partners before making any claim about real-world use.

## Pricing

All unit prices are on-demand prices for us-east-1. They come from the AWS Price List API and the [AgentCore pricing page](https://aws.amazon.com/bedrock/agentcore/pricing/), read on 2026-11-03. AWS prices change, so check the current pages before relying on these numbers. Free tier is ignored.

### Unit prices

| Service | Price | Source |
|---|---|---|
| Amazon Bedrock, Nova 2 Lite, input tokens | $0.00033 per 1K tokens | Price List API (`USE1-Nova2.0Lite-input-tokens`) |
| Amazon Bedrock, Nova 2 Lite, output tokens | $0.00275 per 1K tokens | Price List API |
| AgentCore Runtime, CPU | $0.0895 per vCPU-hour (v1 microVM) to $0.1276 (v2) | AgentCore pricing page |
| AgentCore Runtime, memory | $0.00945 per GB-hour (v1) to $0.0169 (v2) | AgentCore pricing page |
| AWS Lambda, arm64 compute | $0.0000133334 per GB-second | Price List API |
| AWS Lambda, requests | $0.20 per million | Price List API |
| Amazon API Gateway, HTTP API | $1.00 per million requests (first 300 million) | Price List API |
| Amazon DynamoDB, on-demand | $0.625 per million writes, $0.125 per million reads | Price List API |
| AWS Amplify Hosting | $0.01 per build minute, $0.15 per GB served, $0.023 per GB stored | Price List API |

Notes on the prices:

- The app calls Nova 2 Lite through the `us.` cross-region inference profile. A geographic profile bills at the on-demand rate of the source region, with no extra charge.
- We could not confirm whether our runtime runs on v1 or v2 microVMs, so AgentCore costs are shown as a range.
- AgentCore does not bill CPU while the agent waits on I/O, such as a model call. Model tokens are billed separately by Bedrock.

### What one assessment costs (estimate)

These are estimates from measured usage, not a bill.

| Part | Measured usage | Estimated cost |
|---|---|---|
| Nova 2 Lite tokens | 120,010 input and 4,283 output tokens over the 4 live evaluation scenarios ($0.0514 in total) | about $0.0128 |
| AgentCore Runtime | 0.019177 vCPU-hours and 1.08249 GB-hours over 5 invocations (CloudWatch, 2 days), so about 0.0038 vCPU-hours and 0.2165 GB-hours each | about $0.0024 (v1) to $0.0041 (v2) |
| Worker Lambda | 1024 MB for about 20 s (about 20 GB-seconds) | about $0.0003 |
| API Gateway | about 20 requests (create the job, then poll it) | about $0.00002 |
| DynamoDB | a few reads and writes | under $0.00001 |
| **Total** | | **about $0.016 to $0.017** |

That is about $16 to $17 per 1,000 assessments. Model tokens are about three quarters of it. The judge and knowledge-test calls only run in the evaluation, so they are not included.

When nobody uses the app, the cost is close to zero. AgentCore, Lambda, API Gateway and DynamoDB on-demand bill per use. What remains is DynamoDB storage ($0.25 per GB-month after the first 25 GB), CloudWatch Logs storage and Amplify artifact storage, all small at this scale.

Caveats:

- The token count comes from the 4-scenario live evaluation, not from the AgentCore runs. A real place with a longer plan or a revision uses more tokens.
- Memory is most of the AgentCore cost. The measured GB-hours are much larger than a 20 s run would use, which suggests that billing continues while the session stays open after the reply. We have not confirmed this. Ending the session early (see [Future work](#future-work)) is how we would test it.
- The AgentCore figures come from only 5 invocations.

## Conclusion

HeatWise AI uses Strands Agents to turn a forecast into a community preparedness plan. A coordinator delegates to four specialists. Hooks keep the numbers tied to tool results, steering keeps the order, and deterministic safety checks gate every plan. The agents run on Amazon Bedrock AgentCore Runtime with Amazon Nova 2 Lite, behind a small job API and an Amplify dashboard. By our estimate, an assessment costs a couple of cents.

The evaluation shows that the pipeline carries the documented rules into the report and that the guardrails reject the unsafe items we injected. It does not show anything about real communities. The next steps are official warning data, authentication, local languages and a field study with partners.

## Try it

- Live dashboard: https://main.dmupjpltx9cou.amplifyapp.com
- Offline quickstart, live mode and the evaluation commands are in the [README](../../README.md).

The code is MIT licensed ([LICENSE](../../LICENSE)).
