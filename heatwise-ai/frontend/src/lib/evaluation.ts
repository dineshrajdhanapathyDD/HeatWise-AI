import type { EvaluationMetric, EvaluationMode } from "../api/types";
import { DASH, formatDuration, formatPct } from "./format";

/** The mode label shown beside every synthetic evaluation value. */
export const MODE_LABELS: Record<EvaluationMode, string> = {
  offline: "Offline scripted",
  live: "Live Nova",
};

const METRIC_NAMES: Record<string, string> = {
  workflow_completion: "Workflow completion",
  risk_agreement: "Risk category agreement",
  safety_pass: "Safety status agreement",
  weather_extraction: "Weather fields extracted",
  source_verification: "Items citing trusted sources",
  items_verified: "Items passing safety checks",
  delegation_order_effective: "Delegation order (with fallback)",
  delegation_order_model_driven: "Delegation order (model alone)",
  language_notice: "Language notice on non-English requests",
  timing_ms: "Mean time per scenario",
  adversarial_direct_rejection: "Unsafe items rejected",
  adversarial_controls_pass: "Safe control items passed",
  adversarial_end_to_end: "Unsafe plan held for review, end to end",
  recommendation_relevance: "Recommendation relevance (LLM judge)",
  knowledge_test_baseline: "Knowledge test, model without checklist",
  knowledge_test_with_checklist: "Knowledge test, model with checklist",
};

export function metricName(key: string): string {
  return METRIC_NAMES[key] ?? key.replace(/_/g, " ");
}

/** A run date ("3 Nov 2026", UTC). */
export function formatDate(iso: string | null | undefined): string {
  if (!iso) return DASH;
  const date = new Date(iso);
  if (Number.isNaN(date.getTime())) return DASH;
  return new Intl.DateTimeFormat("en-GB", { day: "numeric", month: "short", year: "numeric", timeZone: "UTC" }).format(
    date,
  );
}

/** "13 of 18 scenarios (72.2%)", "16.3 s", or "Not run". Values come from the results file only. */
export function metricValue(metric: EvaluationMetric | undefined): string {
  if (!metric || metric.status === "not_run" || metric.value === null) return "Not run";
  if (metric.unit.startsWith("ms")) return formatDuration(metric.value);
  const pct = formatPct(Math.round(metric.value * 1000) / 10, 1);
  if (metric.numerator !== null && metric.denominator !== null) {
    return `${metric.numerator} of ${metric.denominator} ${metric.unit} (${pct})`;
  }
  return pct;
}
