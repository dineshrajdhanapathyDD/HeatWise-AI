import { riskLabel } from "./risk";

/**
 * The backend's risk categories in order (backend/services/risk_rules.py). The frontend only displays a
 * category it was given; it never computes or changes one. "unknown" sits outside the scale.
 */
export const RISK_ORDER = ["low", "moderate", "high", "very_high", "extreme"] as const;
export type ScaledRisk = (typeof RISK_ORDER)[number];

const HUES: Record<string, string> = {
  low: "#2dd4bf",
  moderate: "#facc15",
  high: "#fb923c",
  very_high: "#f4664a",
  extreme: "#e8365d",
  unknown: "#64748b",
};

/** 0-4 for a scaled category, null for unknown or anything unexpected. */
export function riskIndex(category: string | null | undefined): number | null {
  const i = RISK_ORDER.indexOf((category ?? "") as ScaledRisk);
  return i === -1 ? null : i;
}

export function riskHue(category: string | null | undefined): string {
  return HUES[category ?? "unknown"] ?? HUES.unknown!;
}

/** Category label plus its position, e.g. "Extreme (5 of 5)". */
export function riskPositionText(category: string | null | undefined): string {
  const i = riskIndex(category);
  return i === null ? riskLabel(category) : `${riskLabel(category)} (${i + 1} of ${RISK_ORDER.length})`;
}
