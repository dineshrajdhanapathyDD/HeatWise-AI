import type { HistoryChanges, HistoryItem, MetricsView } from "../api/types";
import { formatDelta, placeName } from "./format";
import { indicatorLabel, riskLabel } from "./risk";

export type DateFilter = "any" | "7d" | "30d";

export interface HistoryFilters {
  query: string;
  risk: string;
  status: string;
  date: DateFilter;
}

/** Client-side filter over the loaded reports: place text, risk category, status and age. */
export function filterHistory(items: HistoryItem[], f: HistoryFilters, now = Date.now()): HistoryItem[] {
  const q = f.query.trim().toLowerCase();
  const maxAgeMs = f.date === "7d" ? 7 * 864e5 : f.date === "30d" ? 30 * 864e5 : Infinity;
  return items.filter((i) => {
    const text = `${placeName([i.location_name ?? i.query, i.admin1, i.country])} ${i.query}`.toLowerCase();
    if (q && !text.includes(q)) return false;
    if (f.risk !== "all" && i.risk_category !== f.risk) return false;
    if (f.status !== "all" && i.status !== f.status) return false;
    if (maxAgeMs !== Infinity && now - new Date(i.created_at).getTime() > maxAgeMs) return false;
    return true;
  });
}

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
