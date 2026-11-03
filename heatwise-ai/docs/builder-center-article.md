# HeatWise AI: from weather intelligence to community action

Draft for the AWS Builder Center project article. Not published yet. Publishing URL: TODO (add after the article is posted on Builder Center).

Repository: TODO (public GitHub URL). Demo video: TODO (public link, under three minutes; script in [demo-script.md](demo-script.md)).

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
5. Shows the report on a dashboard (Climate, Risk, Plan, Agent activity, History, Impact) and exports a Markdown checklist that a volunteer can print or share.

If the plan fails verification, the planner gets one revision with the issues. If it still fails, the report is marked `needs_human_review` and only the verified items are shown and exported.

## Multi-agent architecture

A coordinator agent delegates to four specialists (agents as tools): Weather Intelligence, Community Risk, Action Planner and Safety and Verification. The coordinator's tools pass data between specialists in code and return short JSON summaries to the model, so the model never copies weather or plan data by hand. Numbers come from tool results captured by a hook, not from model text. Details and diagrams: [agent-workflow.md](agent-workflow.md) and [architecture.md](architecture.md).

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
- **AWS Lambda and Amazon API Gateway** (HTTP API) carry the dashboard's job API. The API Lambda creates the job. A worker Lambda calls `invoke_agent_runtime` once and stores the report. It runs no agents, and its only AgentCore permission is to invoke that runtime. It exists because an HTTP API request times out at 30 s, which is too close to an agent run.
- **Amazon DynamoDB** stores jobs and reports (on-demand). **Amazon CloudWatch Logs** holds the API, worker and runtime logs. **AWS IAM** roles are scoped per function. **AWS CloudFormation** (CDK and the AgentCore CLI) defines all of it.

The runtime's execution role is the AgentCore CLI default. It allows Bedrock model invocation on any model in the account, which is wider than the Lambda roles. A custom `executionRoleArn` would narrow it to Nova 2 Lite. An optional CloudFront stack for the dashboard is in the code but not deployed.

## How we evaluated it

The evaluation suite (`backend/evaluation/`, report in [evaluation.md](evaluation.md)) runs the real coordinator over 18 synthetic scenarios: hot-dry plains, humid coast, mild hills, missing humidity, a stale observation, provider errors, an invalid location and a Hindi request. Weather comes from labelled synthetic fixtures, so every extracted value has exact ground truth. Expected risk categories were derived by hand from the documented rules and re-checked by an independent implementation in the tests. It has two modes:

- Offline: scripted models through the real Strands loop, hooks, steering and fallback. It needs no AWS and also runs inside `pytest`.
- Live: Amazon Bedrock (Nova 2 Lite, us-east-1) on 4 scenarios, plus an LLM judge (`strands_evals` `OutputEvaluator`) for recommendation relevance and a 10-question knowledge test answered by the model.

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
- The live run used 53 agent model calls (120010 input and 4283 output tokens), 3 judge calls and 4 knowledge-test calls. The Bedrock price was not verified in that session, so no cost is given.

## What we learned

- Let code own the numbers. The evidence ledger hook made it easy to keep model text out of weather values and risk categories, and to replace a summary when it disagreed with the data.
- Steering plus a deterministic fallback gives a predictable workflow without a rigid graph: the model drives when it gets the order right, and the run still finishes safely when it does not.
- Small, flat structured-output schemas and a cap of two attempts worked better with Nova 2 Lite than larger schemas with retries.
- Making the evaluation run offline, with the same code path as production, turned it into a regression test.

## Limitations and future work

- Weather comes from Open-Meteo, which publishes no government warnings. An adapter for the IMD API is future work (its endpoint schemas were not verified).
- IMD departure-from-normal and coastal criteria are not implemented (they need climatological normals).
- Plans are English only; other languages get English with a notice. Localized guidance is the next step.
- The deployed HTTP API is public and unauthenticated (demo window); IAM or Cognito auth is needed before wider use.
- The evaluation is synthetic. A field study with community partners would be needed before any claim about real-world use.

## Try it

Offline quickstart, live mode and the evaluation commands are in the [README](../../README.md). The code is MIT licensed ([LICENSE](../../LICENSE)).
