import { screen, within } from "@testing-library/react";
import { describe, expect, it } from "vitest";

import type { HistoryItem } from "../api/types";
import { fixtures, mockApi, recordFor, renderApp } from "../test/helpers";

function historyFor(report: ReturnType<typeof fixtures.complete>): HistoryItem {
  return {
    report_id: report.report_id,
    created_at: report.created_at,
    duration_ms: 1200,
    query: report.query,
    location_name: report.location?.name ?? null,
    admin1: report.location?.admin1 ?? null,
    country: report.location?.country ?? null,
    status: report.status,
    risk_category: report.risk_category,
    heat_index_c: report.risk?.heat_index_c ?? null,
    max_forecast_c: 46,
    indicators: report.risk?.vulnerability_indicators ?? [],
    data_mode: "live",
    verification_status: report.verification_status,
    changes: null,
  };
}

function serveLatest(report: ReturnType<typeof fixtures.complete>) {
  mockApi({
    "GET /api/history": { body: { items: [historyFor(report)], total: 1, limit: 1, offset: 0 } },
    [`GET /api/reports/${report.report_id}`]: { body: recordFor(report) },
  });
}

describe("Home dashboard", () => {
  it("shows the latest weather, risk, communities, actions and the finished pipeline from the stored report", async () => {
    const report = fixtures.complete();
    serveLatest(report);
    renderApp("/");

    const hero = screen.getByRole("region", { name: "HeatWise AI" });
    expect(await within(hero).findByText("Wardha, Maharashtra, India")).toBeInTheDocument();
    expect(within(hero).getByText("44.2 °C")).toBeInTheDocument();
    expect(within(hero).getByText(/Visual based on temperature/)).toBeInTheDocument();

    const overview = screen.getByRole("region", { name: "How serious is the heat?" });
    expect(within(overview).getByText("Extreme")).toBeInTheDocument();
    expect(within(overview).getByText("46.4 °C")).toBeInTheDocument();
    expect(within(overview).getByText("NWS band: Danger")).toBeInTheDocument();
    expect(within(overview).getByText("Provider has no official warnings")).toBeInTheDocument();

    const weather = screen.getByRole("region", { name: "What is the weather doing?" });
    expect(within(weather).getByRole("list", { name: "Forecast days" }).children).toHaveLength(report.forecast!.days.length);
    expect(within(weather).getByText("Hourly timeline not available")).toBeInTheDocument();
    expect(within(weather).getByText("forecast.hourly")).toBeInTheDocument();
    expect(within(weather).getByRole("table", { name: "Forecast daily maximum, minimum and feels-like maximum" })).toBeInTheDocument();

    const community = screen.getByRole("region", { name: "Who may be at risk?" });
    expect(within(community).getAllByText("Present")).toHaveLength(3); // elderly, outdoor workers, farmers
    expect(within(community).getByText("Not reported")).toBeInTheDocument(); // young children

    const actions = screen.getByRole("region", { name: "What should the community do?" });
    expect(within(actions).getAllByRole("listitem")).toHaveLength(4);
    expect(within(actions).getByRole("link", { name: "Open the full plan" })).toHaveAttribute("href", `/reports/${report.report_id}/plan`);

    const latest = screen.getByRole("region", { name: "Wardha, Maharashtra, India" });
    expect(within(latest).getByRole("link", { name: "Open the report" })).toHaveAttribute("href", `/reports/${report.report_id}/climate`);

    const pipeline = screen.getByRole("region", { name: "Agent workflow, latest run" });
    expect(within(pipeline).getAllByText("Completed")).toHaveLength(5);
    expect(within(pipeline).getByText("Report verified and complete.")).toBeInTheDocument();
  });

  it("shows only verified actions for a report that needs human review", async () => {
    const report = fixtures.needsReview();
    serveLatest(report);
    renderApp("/");
    const actions = await screen.findByRole("region", { name: "What should the community do?" });
    const verified = new Set(report.verification!.verified_item_ids);
    for (const i of report.recommended_actions!.items) {
      if (!verified.has(i.id)) expect(within(actions).queryByText(i.text)).not.toBeInTheDocument();
    }
    expect(document.body.textContent?.toLowerCase()).not.toContain("aspirin");
    expect(within(actions).getByText(/only actions that passed verification are shown/)).toBeInTheDocument();
  });

  it("shows an idle pipeline and no weather values when nothing is stored", async () => {
    mockApi({ "GET /api/history": { body: { items: [], total: 0, limit: 1, offset: 0 } } });
    renderApp("/");
    const pipeline = await screen.findByRole("region", { name: "Agent workflow" });
    expect(within(pipeline).getAllByText("Not running")).toHaveLength(5);
    expect(screen.queryByText(/°C/)).not.toBeInTheDocument();
  });
});
