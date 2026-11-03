import type { ReportStatus } from "../api/types";

export type Tone = "positive" | "warning" | "negative" | "neutral";

const RISK_LABELS: Record<string, string> = {
  low: "Low",
  moderate: "Moderate",
  high: "High",
  very_high: "Very high",
  extreme: "Extreme",
  unknown: "Unknown",
};

const RISK_TONES: Record<string, Tone> = {
  low: "positive",
  moderate: "warning",
  high: "negative",
  very_high: "negative",
  extreme: "negative",
  unknown: "neutral",
};

/** The text label for a risk category. Colour is never shown without it. */
export function riskLabel(category: string | null | undefined): string {
  return RISK_LABELS[category ?? "unknown"] ?? "Unknown";
}

export function riskTone(category: string | null | undefined): Tone {
  return RISK_TONES[category ?? "unknown"] ?? "neutral";
}

const STATUS_LABELS: Record<ReportStatus, string> = {
  complete: "Complete",
  needs_human_review: "Needs human review",
  incomplete: "Incomplete",
};

const STATUS_TONES: Record<ReportStatus, Tone> = {
  complete: "positive",
  needs_human_review: "warning",
  incomplete: "neutral",
};

export function statusLabel(status: ReportStatus): string {
  return STATUS_LABELS[status];
}

export function statusTone(status: ReportStatus): Tone {
  return STATUS_TONES[status];
}

/** Pale pill pairs from the sheet: a tint with dark text of the same hue. */
export const TONE_CLASSES: Record<Tone, string> = {
  positive: "bg-pos-bg text-pos-ink",
  warning: "bg-warn-bg text-warn-ink",
  negative: "bg-neg-bg text-neg-ink",
  neutral: "bg-neutral-bg text-neutral-ink",
};

const INDICATOR_LABELS: Record<string, string> = {
  elderly: "Older people",
  young_children: "Young children",
  pregnant_women: "Pregnant women",
  chronic_illness_group: "People with chronic illness",
  outdoor_workers: "People who work outdoors",
  farmers: "Farming households",
  limited_water_access: "Limited water access",
  limited_shade_or_cooling: "Limited shade or cooling",
};

export function indicatorLabel(code: string): string {
  return INDICATOR_LABELS[code] ?? code.replaceAll("_", " ");
}
