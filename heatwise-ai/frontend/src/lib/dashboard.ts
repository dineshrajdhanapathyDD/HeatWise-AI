import type { DailyForecast, PlanItem } from "../api/types";

/** Highest daily maximum in the forecast and its day, or nulls when the provider gave none. */
export function highestForecast(days: DailyForecast[] | null | undefined): { value: number | null; date: string | null } {
  let best: DailyForecast | null = null;
  for (const d of days ?? []) {
    if (d.temperature_max_c === null) continue;
    if (best === null || d.temperature_max_c > (best.temperature_max_c ?? -Infinity)) best = d;
  }
  return { value: best?.temperature_max_c ?? null, date: best?.date ?? null };
}

/** The community groups the dashboard features, with the plan audience whose guidance applies to them. */
export const COMMUNITY_GROUPS = [
  { code: "elderly", title: "Older adults", audience: "household", audienceLabel: "household" },
  { code: "young_children", title: "Young children", audience: "household", audienceLabel: "household" },
  { code: "outdoor_workers", title: "Outdoor workers", audience: "outdoor_worker", audienceLabel: "outdoor worker" },
  { code: "farmers", title: "Farming households", audience: "farmer", audienceLabel: "farmer" },
] as const;

/** Distinct topics of the shown plan items for one audience, in plan order (e.g. ["hydration", "shade"]). */
export function audienceTopics(items: PlanItem[], audience: string, limit = 4): string[] {
  const seen: string[] = [];
  for (const i of items) {
    if (i.audience !== audience) continue;
    const t = i.topic.replaceAll("_", " ");
    if (!seen.includes(t)) seen.push(t);
  }
  return seen.slice(0, limit);
}

const PHASE_ORDER: Record<string, number> = { during: 0, before: 1, after: 2 };

/** Up to `limit` shown plan items for the "act now" panel: during-heatwave items first, one per audience first. */
export function topActions(items: PlanItem[], limit = 4): PlanItem[] {
  const sorted = [...items].sort((a, b) => (PHASE_ORDER[a.phase] ?? 9) - (PHASE_ORDER[b.phase] ?? 9));
  const picked: PlanItem[] = [];
  const audiences = new Set<string>();
  for (const i of sorted) {
    if (picked.length >= limit) break;
    if (!audiences.has(i.audience)) {
      picked.push(i);
      audiences.add(i.audience);
    }
  }
  for (const i of sorted) {
    if (picked.length >= limit) break;
    if (!picked.includes(i)) picked.push(i);
  }
  return picked;
}

export const AUDIENCE_LABELS: Record<string, string> = {
  household: "Households",
  outdoor_worker: "Outdoor workers",
  farmer: "Farmers",
};

export const PHASE_LABELS: Record<string, string> = {
  before: "Before",
  during: "During",
  after: "After",
};

/** OpenStreetMap link for the resolved coordinates. Opened only when the user follows it. */
export function osmLink(lat: number, lon: number): string {
  const la = lat.toFixed(4);
  const lo = lon.toFixed(4);
  return `https://www.openstreetmap.org/?mlat=${la}&mlon=${lo}#map=11/${la}/${lo}`;
}
