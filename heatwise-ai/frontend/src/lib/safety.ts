import type { PlanItem, PreparednessReport } from "../api/types";

/**
 * The one place that decides which plan items may be shown as advice (design decision D-M3-9).
 *
 * - complete: every item in the plan.
 * - needs_human_review: only items whose id is in verification.verified_item_ids. Rejected items stay in
 *   recommended_actions for a reviewer, but they never render as advice.
 * - incomplete, or no plan: nothing.
 */
export function renderablePlanItems(report: PreparednessReport): PlanItem[] {
  const items = report.recommended_actions?.items ?? [];
  if (report.status === "complete") return items;
  if (report.status === "needs_human_review") {
    const verified = new Set(report.verification?.verified_item_ids ?? []);
    return items.filter((item) => verified.has(item.id));
  }
  return [];
}
