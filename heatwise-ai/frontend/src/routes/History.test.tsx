import { screen, within } from "@testing-library/react";
import userEvent from "@testing-library/user-event";
import { describe, expect, it } from "vitest";

import type { HistoryItem, MetricsView } from "../api/types";
import { mockApi, renderApp } from "../test/helpers";

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

const METRICS: MetricsView = {
  total: 2,
  by_status: { complete: 1, needs_human_review: 1, incomplete: 0 },
  by_risk_category: { low: 0, moderate: 0, high: 1, very_high: 0, extreme: 1, unknown: 0 },
  by_data_mode: { live: 2, demo: 0 },
  plans_generated: 2,
  verification: { passed: 1, failed: 1, not_run: 0 },
  mean_pct_items_verified: 98.8,
  mean_duration_ms: 1100,
};

describe("History", () => {
  it("lists reports with their changes in words and the counts line", async () => {
    const newest = item("b".repeat(32), {
      status: "needs_human_review",
      changes: {
        previous_report_id: "a".repeat(32),
        previous_created_at: "2026-05-09T09:00:00Z",
        risk_category_from: "high",
        risk_category_to: "extreme",
        heat_index_delta_c: 2.1,
        max_forecast_delta_c: -0.5,
        indicators_added: ["limited_water_access"],
        indicators_removed: [],
      },
    });
    const older = item("a".repeat(32), { risk_category: "high", created_at: "2026-05-09T09:00:00Z" });
    mockApi({
      "GET /api/history": { body: { items: [newest, older], total: 2, limit: 20, offset: 0 } },
      "GET /api/metrics": { body: METRICS },
    });
    renderApp("/history");

    const table = await screen.findByRole("table");
    expect(
      within(table).getByText(
        "Risk High → Extreme; heat index +2.1 °C; max forecast -0.5 °C; added: limited water access",
      ),
    ).toBeInTheDocument();
    expect(within(table).getByText("First report for this place")).toBeInTheDocument();
    expect(within(table).getAllByRole("link", { name: "Wardha, Maharashtra, India" })[0]).toHaveAttribute(
      "href",
      `/reports/${"b".repeat(32)}/climate`,
    );
    expect(await screen.findByText("2 stored reports: 1 complete, 1 need human review, 0 incomplete.")).toBeInTheDocument();
    expect(screen.queryByRole("button", { name: "Load more" })).not.toBeInTheDocument();
  });

  it("keeps the frame with an empty state when nothing is stored", async () => {
    mockApi({
      "GET /api/history": { body: { items: [], total: 0, limit: 20, offset: 0 } },
      "GET /api/metrics": {
        body: { ...METRICS, total: 0, by_status: { complete: 0, needs_human_review: 0, incomplete: 0 } },
      },
    });
    renderApp("/history");
    expect((await screen.findAllByText(/No assessments are stored yet/)).length).toBeGreaterThan(0);
    expect(screen.getByRole("heading", { name: "Stored reports" })).toBeInTheDocument();
    expect(screen.getByRole("columnheader", { name: "Changes since the last report here" })).toBeInTheDocument();
    expect(await screen.findByText("0 stored reports: 0 complete, 0 need human review, 0 incomplete.")).toBeInTheDocument();
  });

  it("loads the next page with Load more", async () => {
    const first = Array.from({ length: 20 }, (_, i) => item(i.toString(16).padStart(32, "0")));
    const last = item("f".repeat(32), { location_name: "Nagpur", query: "Nagpur" });
    mockApi({
      "GET /api/history?limit=20&offset=0": { body: { items: first, total: 21, limit: 20, offset: 0 } },
      "GET /api/history?limit=20&offset=20": { body: { items: [last], total: 21, limit: 20, offset: 20 } },
      "GET /api/metrics": { body: METRICS },
    });
    renderApp("/history");
    await userEvent.click(await screen.findByRole("button", { name: "Load more" }));
    expect((await screen.findAllByRole("link", { name: "Nagpur, Maharashtra, India" })).length).toBeGreaterThan(0);
    expect(screen.queryByRole("button", { name: "Load more" })).not.toBeInTheDocument();
  });
});
