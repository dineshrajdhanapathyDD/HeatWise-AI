// Hand-written mirror of the HeatWise API models (backend/models/*.py, backend/api/schemas.py).
// Dates arrive as ISO strings.

export type DataMode = "live" | "demo";
export type ReportStatus = "complete" | "needs_human_review" | "incomplete";
export type RiskCategory = "low" | "moderate" | "high" | "very_high" | "extreme" | "unknown";
export type Terrain = "plains" | "hilly" | "coastal";
export type JobStatus = "queued" | "running" | "succeeded" | "failed";

export interface DataProvenance {
  provider: string;
  source_url: string;
  retrieved_at: string;
  observed_at: string | null;
  data_mode: DataMode;
  is_stale: boolean;
}

export interface ResolvedLocation {
  query: string;
  name: string;
  admin1: string | null;
  admin2: string | null;
  country: string | null;
  country_code: string | null;
  latitude: number;
  longitude: number;
  timezone: string | null;
}

export interface CurrentConditions {
  location: ResolvedLocation;
  temperature_c: number | null;
  apparent_temperature_c: number | null;
  relative_humidity_pct: number | null;
  wind_speed_kmh: number | null;
  precipitation_mm: number | null;
  missing_fields: string[];
  provenance: DataProvenance;
}

export interface DailyForecast {
  date: string;
  temperature_max_c: number | null;
  temperature_min_c: number | null;
  apparent_temperature_max_c: number | null;
  precipitation_sum_mm: number | null;
  uv_index_max: number | null;
  relative_humidity_max_pct: number | null;
  missing_fields: string[];
}

export interface ForecastResult {
  location: ResolvedLocation;
  days: DailyForecast[];
  provenance: DataProvenance;
  kind: "forecast";
  note: string;
}

export interface WeatherAlert {
  issuer: string;
  headline: string;
  severity: string | null;
  effective: string | null;
  expires: string | null;
  source_url: string;
}

export interface AlertsResult {
  location: ResolvedLocation;
  alerts_supported: boolean;
  alerts: WeatherAlert[];
  explanation: string;
  official_sources: string[];
  provenance: DataProvenance;
}

export interface RiskFactor {
  code: string;
  description: string;
  value: number | null;
  unit: string | null;
  source_id: string | null;
}

export interface RiskAssessment {
  status: "ok" | "insufficient_data";
  category: RiskCategory;
  hazard_score: number | null;
  heat_index_c: number | null;
  heat_index_f: number | null;
  heat_index_band: string | null;
  imd_indication: "none" | "threshold_met" | "heat_wave" | "severe_heat_wave" | null;
  contributing_factors: RiskFactor[];
  vulnerability_indicators: string[];
  heuristic_adjustment_applied: boolean;
  confidence: "high" | "medium" | "low";
  missing_data: string[];
  explanation: string | null;
  explanation_source: "model" | "rules" | null;
  explanation_issues: string[];
  rules_version: string;
  source_ids: string[];
}

export interface PlanItem {
  id: string;
  audience: string;
  phase: string;
  topic: string;
  text: string;
  source_ids: string[];
  kind: "sourced" | "general_educational";
  added_by: "agent" | "rules";
}

export interface ChecklistItem {
  id: string;
  audience: string;
  phase: string;
  text: string;
  done: boolean;
}

export interface PreparednessPlan {
  status: "ok" | "skipped";
  language: string;
  requested_language: string;
  language_notice: string | null;
  risk_category: string;
  intro: string | null;
  intro_source: "model" | "rules" | null;
  items: PlanItem[];
  checklist: ChecklistItem[];
  revision: number;
  issues: string[];
}

export interface CheckResult {
  name: string;
  passed: boolean;
  severity: "error" | "warning";
  message: string;
  item_id: string | null;
}

export interface VerificationResult {
  status: "passed" | "failed";
  checks: CheckResult[];
  issues: string[];
  warnings: string[];
  llm_concerns: string[];
  verified_item_ids: string[];
  pct_items_verified: number;
}

export interface EvidenceItem {
  kind: string;
  description: string;
  value: number | string | null;
  unit: string | null;
  source_url: string | null;
  retrieved_at: string | null;
}

export interface WeatherSourceInfo {
  provider: string | null;
  source_urls: string[];
  data_mode: DataMode | null;
}

export interface AgentTraceEntry {
  agent: string;
  tool: string;
  status: "success" | "error" | "cancelled";
  duration_ms: number | null;
  cancel_reason: string | null;
  input_summary: Record<string, unknown>;
  step_index: number;
}

export interface PreparednessReport {
  report_id: string;
  created_at: string;
  status: ReportStatus;
  query: string;
  location: ResolvedLocation | null;
  data_retrieved_at: string | null;
  weather_source: WeatherSourceInfo;
  weather_summary: string | null;
  risk_category: string;
  risk: RiskAssessment | null;
  evidence: EvidenceItem[];
  recommended_actions: PreparednessPlan | null;
  checklist_markdown: string | null;
  missing_information: string[];
  verification_status: "passed" | "failed" | "not_run";
  verification: VerificationResult | null;
  revision_count: number;
  consistency_issues: string[];
  steering_blocks: Record<string, string>[];
  trace: AgentTraceEntry[];
  notices: string[];
  current_conditions: CurrentConditions | null;
  forecast: ForecastResult | null;
  alerts: AlertsResult | null;
}

// ---- API request / response shapes (backend/api/schemas.py) ----

export interface PlaceInput {
  name: string;
  district?: string | null;
  state?: string | null;
}

export interface ProfileInput {
  elderly: boolean;
  young_children: boolean;
  pregnant_women: boolean;
  chronic_illness_group: boolean;
  outdoor_workers: boolean;
  farmers: boolean;
  limited_water_access: boolean;
  limited_shade_or_cooling: boolean;
  terrain: Terrain | null;
  preferred_language: string;
}

export interface AssessmentRequest {
  place: PlaceInput;
  forecast_days: number;
  profile: ProfileInput;
}

export interface JobError {
  code: string;
  message: string;
}

export interface JobView {
  job_id: string;
  status: JobStatus;
  created_at: string;
  started_at: string | null;
  finished_at: string | null;
  duration_ms: number | null;
  report_id: string | null;
  error: JobError | null;
  request: AssessmentRequest;
  report: PreparednessReport | null;
}

export interface AssessmentRecord {
  report_id: string;
  created_at: string;
  duration_ms: number | null;
  request: AssessmentRequest;
  report: PreparednessReport;
  /** Checklist item id -> completed at; absent while nothing is ticked. */
  checklist_completed?: Record<string, string>;
}

export interface ChecklistProgress {
  report_id: string;
  completed_item_ids: string[];
  completed_count: number;
  available_count: number;
}

export interface HistoryChanges {
  previous_report_id: string;
  previous_created_at: string;
  risk_category_from: string;
  risk_category_to: string;
  heat_index_delta_c: number | null;
  max_forecast_delta_c: number | null;
  indicators_added: string[];
  indicators_removed: string[];
}

export interface HistoryItem {
  report_id: string;
  created_at: string;
  duration_ms: number | null;
  query: string;
  location_name: string | null;
  admin1: string | null;
  country: string | null;
  status: ReportStatus;
  risk_category: string;
  heat_index_c: number | null;
  max_forecast_c: number | null;
  indicators: string[];
  data_mode: DataMode | null;
  verification_status: "passed" | "failed" | "not_run";
  changes: HistoryChanges | null;
}

export interface HistoryPage {
  items: HistoryItem[];
  total: number;
  limit: number;
  offset: number;
}

export interface MetricsView {
  total: number;
  by_status: Record<string, number>;
  by_risk_category: Record<string, number>;
  by_data_mode: Record<string, number>;
  plans_generated: number;
  verification: { passed: number; failed: number; not_run: number };
  mean_pct_items_verified: number | null;
  mean_duration_ms: number | null;
  // Milestone 5 (D-M5-10). Optional so older API answers still type-check.
  assessments_completed?: number;
  pct_recommendations_verified?: number | null;
  checklist?: { items_completed: number; items_available: number; reports_with_progress: number };
  localized_guidance?: {
    served_in_requested_language: number;
    english_fallback: number;
    by_requested_language: Record<string, number>;
  };
}

// ---- Evaluation results (backend/evaluation/results.py) ----

export type EvaluationMode = "offline" | "live";

export interface EvaluationMetric {
  value: number | null;
  numerator: number | null;
  denominator: number | null;
  unit: string;
  mode: EvaluationMode;
  status: "measured" | "not_run";
  note: string;
  details: Record<string, unknown>;
}

export interface EvaluationFailure {
  scenario_id: string | null;
  metric: string;
  detail: string;
}

export interface EvaluationRun {
  mode: EvaluationMode;
  mode_label: string;
  status: "ok" | "failed";
  error: string | null;
  command: string;
  started_at: string;
  finished_at: string | null;
  dataset_version: string;
  settings: Record<string, unknown>;
  scenario_ids: string[];
  metrics: Record<string, EvaluationMetric>;
  failures: EvaluationFailure[];
}

export interface EvaluationResults {
  schema_version: string;
  synthetic: boolean;
  label: string;
  runs: { offline: EvaluationRun | null; live: EvaluationRun | null };
}

export interface HealthView {
  status: "ok";
  version: string;
  weather_provider: string;
  agent_mode: string;
  model_id?: string;
  demo_locations?: string[];
}

export interface FieldError {
  field: string;
  message: string;
}

export interface ErrorBody {
  error: { code: string; message: string; fields: FieldError[] };
}
