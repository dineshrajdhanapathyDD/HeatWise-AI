import { describe, expect, it } from "vitest";

import type { HistoryItem, PlanItem } from "../api/types";
import { fixtures } from "../test/helpers";
import { audienceTopics, highestForecast, osmLink, topActions } from "./dashboard";
import { filterHistory } from "./history";
import { communities, indicatorCounts, riskTrend } from "./impact";
import { pipelineStages, pipelineVerdict } from "./pipeline";
import { riskHue, riskIndex, riskPositionText } from "./riskScale";
import { sceneFor } from "./weatherScene";

const current = (over: Partial<NonNullable<ReturnType<typeof fixtures.complete>["current_conditions"]>> = {}) => ({
  ...fixtures.complete().current_conditions!,
  ...over,
});

describe("riskScale", () => {
  it("only maps the backend's categories and leaves unknown off the scale", () => {
    expect(riskIndex("low")).toBe(0);
    expect(riskIndex("extreme")).toBe(4);
    expect(riskIndex("unknown")).toBeNull();
    expect(riskIndex("severe")).toBeNull();
    expect(riskPositionText("very_high")).toBe("Very high (4 of 5)");
    expect(riskHue("made-up")).toBe(riskHue("unknown"));
  });
});

describe("weatherScene", () => {
  it("chooses the scene from returned values only", () => {
    expect(sceneFor(null, null)).toBe("none");
    expect(sceneFor(current({ temperature_c: 44.2 }), 46.4)).toBe("extreme-heat");
    expect(sceneFor(current({ temperature_c: 31, apparent_temperature_c: 34 }), null)).toBe("hot");
    expect(sceneFor(current({ temperature_c: 27, apparent_temperature_c: 27 }), null)).toBe("warm");
    expect(sceneFor(current({ temperature_c: 18, apparent_temperature_c: 18 }), null)).toBe("mild");
    expect(sceneFor(current({ precipitation_mm: 2.4 }), 46)).toBe("rain");
    expect(sceneFor(current({ temperature_c: null, apparent_temperature_c: null }), null)).toBe("none");
  });
});

describe("pipeline", () => {
  it("never shows an agent as working without execution data", () => {
    expect(pipelineStages({ phase: "idle" }).every((s) => s.state === "idle")).toBe(true);
    expect(pipelineStages({ phase: "running", status: "running" }).every((s) => s.state === "waiting")).toBe(true);
    expect(pipelineVerdict({ phase: "running", status: "running" })).toMatch(/overall job status only/);
  });

  it("reads each agent's result from the finished report's trace", () => {
    const stages = pipelineStages({ phase: "finished", report: fixtures.complete() });
    expect(stages.map((s) => s.state)).toEqual(["done", "done", "done", "done", "done"]);
    expect(pipelineVerdict({ phase: "finished", report: fixtures.complete() })).toBe("Report verified and complete.");
  });

  it("marks a revised plan and a report that needs review", () => {
    const report = fixtures.needsReview();
    const planner = pipelineStages({ phase: "finished", report }).find((s) => s.key === "action_planner")!;
    expect(planner.runs).toBeGreaterThan(1);
    expect(planner.state).toBe("revised");
    expect(pipelineVerdict({ phase: "finished", report })).toMatch(/needs human review/);
  });

  it("marks agents that did not run in an incomplete report", () => {
    const stages = pipelineStages({ phase: "finished", report: fixtures.incomplete() });
    expect(stages.some((s) => s.state === "skipped")).toBe(true);
  });
});

describe("dashboard helpers", () => {
  it("finds the highest forecast day and ignores nulls", () => {
    const days = fixtures.complete().forecast!.days;
    expect(highestForecast(days)).toEqual({ value: 46, date: days[2]!.date });
    expect(highestForecast([{ ...days[0]!, temperature_max_c: null }])).toEqual({ value: null, date: null });
    expect(highestForecast(null)).toEqual({ value: null, date: null });
  });

  it("picks during-heatwave actions first, one per audience first", () => {
    const items = fixtures.complete().recommended_actions!.items;
    const picked = topActions(items);
    expect(picked).toHaveLength(4);
    expect(picked[0]!.phase).toBe("during");
    expect(new Set(picked.slice(0, 3).map((i) => i.audience)).size).toBe(3);
  });

  it("lists distinct topics per audience", () => {
    const items: PlanItem[] = [
      { id: "a", audience: "farmer", phase: "before", topic: "livestock_water", text: "x", source_ids: [], kind: "sourced", added_by: "agent" },
      { id: "b", audience: "farmer", phase: "during", topic: "livestock_water", text: "y", source_ids: [], kind: "sourced", added_by: "agent" },
      { id: "c", audience: "household", phase: "during", topic: "hydration", text: "z", source_ids: [], kind: "sourced", added_by: "rules" },
    ];
    expect(audienceTopics(items, "farmer")).toEqual(["livestock water"]);
  });

  it("builds a map link without sending anything", () => {
    expect(osmLink(20.74, 78.6)).toBe("https://www.openstreetmap.org/?mlat=20.7400&mlon=78.6000#map=11/20.7400/78.6000");
  });
});

function item(id: string, extra: Partial<HistoryItem> = {}): HistoryItem {
  return {
    report_id: id,
    created_at: "2026-05-10T09:00:00Z",
    duration_ms: 1200,
    query: "Wardha",
    location_name: "Wardha",
    admin1: "Maharashtra",
    country: "India",
    status: "complete",
    risk_category: "extreme",
    heat_index_c: 46.4,
    max_forecast_c: 46,
    indicators: ["elderly", "farmers"],
    data_mode: "live",
    verification_status: "passed",
    changes: null,
    ...extra,
  };
}

describe("history and impact helpers", () => {
  const items = [
    item("a"),
    item("b", { location_name: "Chennai", query: "Chennai", admin1: "Tamil Nadu", risk_category: "high", status: "needs_human_review", created_at: "2026-05-01T09:00:00Z", indicators: ["elderly"] }),
    item("c", { risk_category: "unknown", status: "incomplete", indicators: [] }),
  ];

  it("filters by place text, risk, status and age", () => {
    const base = { query: "", risk: "all", status: "all", date: "any" as const };
    const now = new Date("2026-05-11T00:00:00Z").getTime();
    expect(filterHistory(items, { ...base, query: "tamil" }, now).map((i) => i.report_id)).toEqual(["b"]);
    expect(filterHistory(items, { ...base, risk: "extreme" }, now).map((i) => i.report_id)).toEqual(["a"]);
    expect(filterHistory(items, { ...base, status: "incomplete" }, now).map((i) => i.report_id)).toEqual(["c"]);
    expect(filterHistory(items, { ...base, date: "7d" }, now).map((i) => i.report_id)).toEqual(["a", "c"]);
  });

  it("counts communities and groups, and drops unknown risk from the trend", () => {
    expect(communities(items)).toEqual([
      { name: "Wardha, Maharashtra, India", count: 2 },
      { name: "Chennai, Tamil Nadu, India", count: 1 },
    ]);
    expect(indicatorCounts(items)).toEqual([
      { code: "elderly", count: 2 },
      { code: "farmers", count: 1 },
    ]);
    expect(riskTrend(items).map((p) => p.category)).toEqual(["high", "extreme"]);
  });
});
