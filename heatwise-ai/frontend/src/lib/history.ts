import type { HistoryChanges, MetricsView } from "../api/types";
import { formatDelta } from "./format";
import { indicatorLabel, riskLabel } from "./risk";

/** "Risk High → Very high; heat index +2.1 °C; max forecast unchanged; added: limited water access". */
export function changesInWords(changes: HistoryChanges | null): string {
  if (!changes) return "First report for this place";
  const parts: string[] = [];
  parts.push(
    changes.risk_category_from === changes.risk_category_to
      ? `Risk unchanged (${riskLabel(changes.risk_category_to)})`
      : `Risk ${riskLabel(changes.risk_category_from)} → ${riskLabel(changes.risk_category_to)}`,
  );
  const delta = (label: string, value: number | null) => {
    if (value === null) return;
    parts.push(value === 0 ? `${label} unchanged` : `${label} ${formatDelta(value)}`);
  };
  delta("heat index", changes.heat_index_delta_c);
  delta("max forecast", changes.max_forecast_delta_c);
  if (changes.indicators_added.length)
    parts.push(`added: ${changes.indicators_added.map((i) => indicatorLabel(i).toLowerCase()).join(", ")}`);
  if (changes.indicators_removed.length)
    parts.push(`removed: ${changes.indicators_removed.map((i) => indicatorLabel(i).toLowerCase()).join(", ")}`);
  // Semicolons keep the indicator lists (which use commas) readable.
  return parts.join("; ");
}

export function countsLine(m: MetricsView): string {
  const s = m.by_status;
  const noun = m.total === 1 ? "stored report" : "stored reports";
  return `${m.total} ${noun}: ${s.complete ?? 0} complete, ${s.needs_human_review ?? 0} need human review, ${
    s.incomplete ?? 0
  } incomplete.`;
}
