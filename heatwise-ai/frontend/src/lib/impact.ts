import type { HistoryItem } from "../api/types";
import { placeName } from "./format";
import { riskIndex } from "./riskScale";

/** Distinct places among stored reports, most assessed first. */
export function communities(items: HistoryItem[]): { name: string; count: number }[] {
  const counts = new Map<string, number>();
  for (const i of items) {
    const name = placeName([i.location_name ?? i.query, i.admin1, i.country]);
    counts.set(name, (counts.get(name) ?? 0) + 1);
  }
  return [...counts.entries()].map(([name, count]) => ({ name, count })).sort((a, b) => b.count - a.count || a.name.localeCompare(b.name));
}

/** How many stored reports listed each vulnerability indicator. */
export function indicatorCounts(items: HistoryItem[]): { code: string; count: number }[] {
  const counts = new Map<string, number>();
  for (const i of items) for (const code of i.indicators) counts.set(code, (counts.get(code) ?? 0) + 1);
  return [...counts.entries()].map(([code, count]) => ({ code, count })).sort((a, b) => b.count - a.count);
}

export interface TrendPoint {
  t: number;
  date: string;
  place: string;
  category: string;
  level: number;
}

/** Stored reports with a scaled risk category, oldest first, for the risk trend chart. */
export function riskTrend(items: HistoryItem[]): TrendPoint[] {
  return items
    .map((i) => ({
      t: new Date(i.created_at).getTime(),
      date: i.created_at,
      place: placeName([i.location_name ?? i.query, i.admin1]),
      category: i.risk_category,
      level: riskIndex(i.risk_category),
    }))
    .filter((p): p is TrendPoint => p.level !== null && Number.isFinite(p.t))
    .sort((a, b) => a.t - b.t);
}
