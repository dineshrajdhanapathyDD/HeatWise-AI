# Requirements Document: HeatWise AI

## Introduction

HeatWise AI is a multi-agent heatwave preparedness assistant built on the Strands Agents SDK and Amazon Bedrock. It gathers weather data from a documented provider, applies transparent risk rules to a community profile, generates preparedness plans, and verifies them before display.

It is an informational and preparedness tool. It is not a medical diagnosis tool, an emergency dispatch system, or a substitute for official warnings.

Scope legend: **[M1]** = implemented in Milestone 1 (backend foundation + Weather Intelligence Agent). **[M2]** = implemented in Milestone 2 (risk, planner, safety, coordinator, report). **[M4]** = implemented in Milestone 4 (sessions, DynamoDB persistence, CDK infrastructure; `HeatWiseData` and `HeatWiseApi` deployed to us-east-1 on 2026-11-03). **[M5]** = implemented in Milestone 5 (evaluation suite, Impact screen, submission docs; the M5 API changes need a redeploy). Other requirements are scheduled in `tasks.md`.

## Glossary

- **Provider**: a weather data source behind the `WeatherProvider` interface (e.g. Open-Meteo, demo fixtures).
- **Live data**: data fetched from a real provider during the request.
- **Demo data**: fixture data, explicitly selected by configuration, always labelled `data_mode="demo"`.
- **Evidence ledger**: the record of actual tool results captured by hooks during an agent invocation.
- **Official warning**: an alert issued by a national meteorological authority. Forecast values are never presented as warnings.

## Requirements

### Requirement 1: Weather Intelligence [M1]

**User Story:** As a community volunteer, I want current weather and a short forecast for my village or town, so that I know whether heat conditions are building.

#### Acceptance Criteria

1. WHEN a user supplies a location name THEN the system SHALL resolve it to coordinates using the configured provider's geocoding service and return the resolved name, admin region, country, latitude and longitude.
2. WHEN a location is resolved THEN the system SHALL return current temperature, relative humidity, apparent temperature, wind speed and precipitation as reported by the provider.
3. WHEN a forecast is requested THEN the system SHALL return daily max/min temperature, max apparent temperature, precipitation sum, max UV index and max relative humidity for 1 to 7 days.
4. EVERY weather result SHALL include provider name, source URL, retrieval timestamp (UTC), provider observation time, and `data_mode` (`live` or `demo`).
5. IF a location cannot be resolved THEN the system SHALL return a structured `location_not_found` error and SHALL NOT return weather values.
6. IF the location input is empty, longer than 120 characters, or contains disallowed characters THEN the system SHALL reject it with `invalid_location` before any network call.
7. IF the provider times out or returns an error THEN the system SHALL return a structured `provider_timeout` or `provider_unavailable` error, and SHALL NOT substitute demo data.
8. IF the provider response is missing a required field THEN that field SHALL be reported as missing (null plus an entry in `missing_fields`) and SHALL NOT be estimated.
9. WHEN official alerts are requested and the configured provider does not support alerts THEN the system SHALL return `alerts_supported=false` with an explanation, and SHALL NOT generate alerts.
10. WHEN data is older than the configured freshness threshold THEN the result SHALL be flagged `is_stale=true`.

### Requirement 2: Anti-fabrication of weather data [M1]

**User Story:** As a user, I want to trust that every number shown came from a real source, so that I don't act on invented data.

#### Acceptance Criteria

1. The final weather measurements SHALL be built from the evidence ledger (actual tool outputs), not from model-generated text.
2. WHEN the model's structured summary states a measurement that differs from the ledger beyond tolerance THEN the system SHALL flag `consistency_issues` and use the ledger value.
3. IF no successful weather tool call is in the ledger THEN the result SHALL have status `no_data` and contain no measurements.
4. The system SHALL use demo data only when `WEATHER_PROVIDER=demo` is configured explicitly, and the result SHALL carry `data_mode="demo"`.

### Requirement 3: Guardrail hooks [M1 for weather agent]

**User Story:** As an operator, I want deterministic controls on agent tool use, so that a model error can't trigger unapproved calls or loops.

#### Acceptance Criteria

1. Before each tool call, a hook SHALL cancel calls to tools not on the agent's allowlist.
2. Before each tool call, a hook SHALL validate tool inputs (location rules, `days` range 1-7) and cancel invalid calls with a reason.
3. A hook SHALL cap tool calls per invocation (configurable) and cancel calls over the cap.
4. Each agent invocation SHALL run with SDK `Limits` (max turns) set from configuration.
5. After each tool call, a hook SHALL record tool name, status, duration and a redacted input summary to the execution trace and log. Secrets SHALL NOT be logged.
6. The MVP SHALL NOT send emergency alerts or contact third parties. Any future external action SHALL require explicit user confirmation.

### Requirement 4: Community Risk Assessment [M2]

1. The system SHALL classify heat risk using deterministic, documented rules (heat index / apparent temperature bands, exposure, water, shade, vulnerable groups).
2. The result SHALL include risk category, contributing factors, confidence, and missing data.
3. The system SHALL NOT infer medical conditions or make predictions about individuals.

### Requirement 5: Preparedness Action Planning [M2]

1. The system SHALL generate separate guidance for households, outdoor workers and farmers, organised as before / during / after a heatwave.
2. Plans SHALL include hydration, rest and shade guidance and escalation to official emergency services where appropriate.
3. Plans SHALL use the user's preferred language where supported, and fall back to English with a notice otherwise.
   - M2 note: only English is supported (`SUPPORTED_PLAN_LANGUAGES=("en",)`), because translated guidance cannot be verified against its sources. Other languages get English plus `language_notice`. Localised guidance is an open gap.
4. The system SHALL produce a downloadable checklist.

### Requirement 6: Safety and Verification [M2]

1. The safety agent SHALL check weather freshness, source presence, and that each recommendation maps to a trusted-source reference or is labelled general educational advice.
2. It SHALL reject unsafe or medical-diagnostic instructions.
3. WHEN verification fails THEN the coordinator SHALL request one revision, then mark the report `needs_human_review` if it still fails.

### Requirement 7: Coordinator and workflow [M2]

1. The coordinator SHALL run weather → risk → plan → safety in that order and SHALL NOT finalise a report before safety verification.
2. Every report SHALL contain location, retrieval timestamp, weather source, risk category, evidence, recommended actions, missing/uncertain information and verification status.
3. The coordinator SHALL keep a trace of contributing agents and tools.

### Requirement 8: Sessions and history [M4]

1. Each session SHALL have a unique ID and conversation continuity via a Strands session manager (file locally, S3 on AWS).
   - M4 note: `backend/session/sessions.py` gives the coordinator agent a `FileSessionManager` (`SESSION_DIR`) or `S3SessionManager` (`SESSION_BUCKET`/`SESSION_PREFIX`), or none (`SESSION_STORAGE=none`). The API uses the job id as the session id, so each assessment has its own conversation; the CLI `assess --session-id` continues one.
2. Assessment records SHALL be stored in DynamoDB when configured, and in a local store otherwise.
   - M4 note: `ASSESSMENT_STORE=dynamodb` selects `DynamoDbAssessmentStore` (same interface, indexes for get-by-id, history by place and newest-first listing); the JSON-file store stays the default. Jobs can also live in DynamoDB (`JOB_STORE=dynamodb`).
3. Personal profile data SHALL be stored separately from public weather data; no unnecessary sensitive data SHALL be stored.
   - M4 note: the community profile is stored in `request_json`, apart from the report (`report_json`) with its weather data; the session holds only the coordinator conversation (raw weather payloads stay in the specialists). Requests still reject unknown keys such as `name` or `phone`, so no personal data is stored.

### Requirement 9: API and dashboard

1. A FastAPI backend SHALL expose assessment, history, health and metrics endpoints.
2. A React + TypeScript dashboard SHALL provide the screens A-G from the project brief, be keyboard-navigable, responsive, and meet accessible contrast.

### Requirement 10: Impact and evaluation [M5]

1. The system SHALL track assessments completed, plans generated, % recommendations verified, average completion time, checklist items completed and users receiving localized guidance.
   - M5 note: `GET /api/metrics` computes these only from stored records (`backend/api/summaries.py`), with no user or person counts. Assessments completed = records with status `complete`; plans generated = records with a plan; % recommendations verified = pooled plan items in `verification.verified_item_ids` over pooled plan items (null with none); average completion time = mean `duration_ms`; checklist items completed = item ids marked done through `POST /api/reports/{id}/checklist` that are still shown (community-level progress, no personal data); localized guidance = plans whose `language` equals the `requested_language`, reported as "plans in the requested language" with English fallbacks counted separately. Plans are English only (D6), so a non-English request counts as an English fallback. Shown on the Impact screen (`/impact`).
2. An evaluation suite SHALL report measured results on a synthetic scenario dataset, including baseline vs post-intervention knowledge test scores in test scenarios.
   - M5 note: `backend/evaluation/` runs the coordinator over 18 synthetic scenarios with synthetic weather fixtures, offline (scripted models, part of `pytest`) and once live (Bedrock Nova 2 Lite, 4 scenarios). Metrics: workflow completion, risk agreement with the documented rules, verification status, weather field extraction, trusted sources, delegation order, language notice, adversarial rejection, an LLM-judge relevance score (`strands_evals` `OutputEvaluator`) and timing. The knowledge test (10 questions) is answered by the model with the questions only (baseline) and with the scenario's checklist (post), in test scenarios, not by people. Results with mode labels: `heatwise-ai/backend/evaluation/results/evaluation-results.json` and the generated `heatwise-ai/docs/evaluation.md`.
3. The project SHALL NOT claim real-world health outcomes.
   - M5 note: the Impact screen shows "These are counts of assessments stored by this HeatWise instance. HeatWise does not measure or claim real-world health outcomes." in every state and keeps synthetic evaluation results in a separate, labelled panel. The evaluation report, README and article state that results are on synthetic scenarios and make no health-outcome or user-count claims.

### Requirement 11: Deployment [M4]

1. AWS CDK SHALL define Lambda (or container) backend, DynamoDB, S3, CloudWatch logging and least-privilege IAM including scoped Bedrock invoke permission.
   - M4 note: `infrastructure/` (Python CDK) defines `HeatWiseData`, `HeatWiseApi` and an optional `HeatWiseFrontend`; Bedrock invoke is scoped to the Nova 2 Lite US inference profile and its three destination-Region model ARNs. Verified with `cdk synth` and template tests only; not deployed.
   - M5 note: `HeatWiseData` (`CREATE_COMPLETE`) and `HeatWiseApi` (`UPDATE_COMPLETE`) are deployed in us-east-1 (read-only `describe-stacks`, 2026-11-03). M5 adds one API-role statement, `dynamodb:UpdateItem` on the assessments table ARN only; it is not deployed yet.
2. AgentCore Runtime deployment SHALL be optional and documented with prerequisites.
   - M4 note: `backend/agentcore_entry.py` (`BedrockAgentCoreApp`) over `backend/agentcore_handler.py` is documented in `docs/deployment.md` with the workshop CLI steps; it was not deployed.
3. Documentation SHALL include deploy and cleanup steps. No credentials SHALL be committed.
   - M4 note: `docs/deployment.md` has synth, deploy, smoke-test, cost and destroy steps (incl. the retained tables and buckets); credentials come from an AWS profile or SSO, never from files in the repo.
