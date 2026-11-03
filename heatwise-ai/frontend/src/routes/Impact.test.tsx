import { screen, waitFor, within } from "@testing-library/react";
import userEvent from "@testing-library/user-event";
import { describe, expect, it } from "vitest";

import type { EvaluationMetric, EvaluationResults, EvaluationRun, MetricsView } from "../api/types";
import { mockApi, renderApp } from "../test/helpers";
import { LANGUAGE_DEFINITION, NO_RESULTS_FILE, OUTCOME_STATEMENT } from "./Impact";

const ZERO: MetricsView = {
  total: 0,
  by_status: { complete: 0, needs_human_review: 0, incomplete: 0 },
  by_risk_category: { low: 0, moderate: 0, high: 0, very_high: 0, extreme: 0, unknown: 0 },
  by_data_mode: { live: 0, demo: 0 },
  plans_generated: 0,
  verification: { passed: 0, failed: 0, not_run: 0 },
  mean_pct_items_verified: null,
  mean_duration_ms: null,
  assessments_completed: 0,
  pct_recommendations_verified: null,
  checklist: { items_completed: 0, items_available: 0, reports_with_progress: 0 },
  localized_guidance: { served_in_requested_language: 0, english_fallback: 0, by_requested_language: {} },
};

const COUNTS: MetricsView = {
  ...ZERO,
  total: 3,
  by_status: { complete: 2, needs_human_review: 1, incomplete: 0 },
  plans_generated: 3,
  verification: { passed: 2, failed: 1, not_run: 0 },
  mean_duration_ms: 2500,
  assessments_completed: 2,
  pct_recommendations_verified: 95.5,
  checklist: { items_completed: 4, items_available: 40, reports_with_progress: 2 },
  localized_guidance: { served_in_requested_language: 2, english_fallback: 1, by_requested_language: { en: 2, hi: 1 } },
};

function metric(mode: "offline" | "live", extra: Partial<EvaluationMetric> = {}): EvaluationMetric {
  return {
    value: 1,
    numerator: 18,
    denominator: 18,
    unit: "scenarios",
    mode,
    status: "measured",
    note: "",
    details: {},
    ...extra,
  };
}

function run(mode: "offline" | "live", metrics: Record<string, EvaluationMetric>, extra: Partial<EvaluationRun> = {}): EvaluationRun {
  return {
    mode,
    mode_label: mode === "offline" ? "offline (scripted models)" : "live (Amazon Bedrock)",
    status: "ok",
    error: null,
    command: "python -m backend.evaluation run",
    started_at: "2026-11-03T06:00:52Z",
    finished_at: "2026-11-03T06:01:00Z",
    dataset_version: "heatwise-eval-v1",
    settings: {},
    scenario_ids: ["S01", "S02"],
    metrics,
    failures: [],
    ...extra,
  };
}

const RESULTS: EvaluationResults = {
  schema_version: "heatwise-eval-results-v1",
  synthetic: true,
  label: "Synthetic test scenarios. No real-world health outcome is measured or claimed.",
  runs: {
    offline: run("offline", {
      risk_agreement: metric("offline"),
      recommendation_relevance: metric("offline", { status: "not_run", value: null, numerator: null, denominator: null }),
    }),
    live: null,
  },
};

describe("Impact", () => {
  it("shows honest zeros, the statement and no invented numbers when nothing is stored", async () => {
    mockApi({ "GET /api/metrics": { body: ZERO }, "GET /api/evaluation": { body: RESULTS } });
    renderApp("/impact");
    expect(await screen.findByText(/No assessments are stored yet/)).toBeInTheDocument();
    expect(screen.getByText(OUTCOME_STATEMENT)).toBeInTheDocument();
    const counts = screen.getByRole("region", { name: "Stored assessments" });
    expect(within(counts).getAllByText("0")).toHaveLength(4);
    expect(within(counts).getAllByText("\u2014")).toHaveLength(2);
    expect(within(counts).getByText("No plan items are stored yet")).toBeInTheDocument();
    expect(within(counts).getByText(`0 in English with a notice. ${LANGUAGE_DEFINITION}`)).toBeInTheDocument();
  });

  it("shows counts from the metrics endpoint", async () => {
    mockApi({ "GET /api/metrics": { body: COUNTS }, "GET /api/evaluation": { body: RESULTS } });
    renderApp("/impact");
    const counts = await screen.findByRole("region", { name: "Stored assessments" });
    expect(await within(counts).findByText("95.5%")).toBeInTheDocument();
    expect(within(counts).getByText("Status complete, of 3 stored")).toBeInTheDocument();
    expect(within(counts).getByText("2.5 s")).toBeInTheDocument();
    expect(within(counts).getByText("4")).toBeInTheDocument();
    expect(within(counts).getByText("Of 40 shown items, on 2 reports")).toBeInTheDocument();
    expect(within(counts).getByText(/^1 in English with a notice/)).toBeInTheDocument();
    expect(screen.queryByText(/No assessments are stored yet/)).not.toBeInTheDocument();
    expect(screen.getByText(OUTCOME_STATEMENT)).toBeInTheDocument();
  });

  it("labels the evaluation panel as synthetic with a mode on every value", async () => {
    mockApi({ "GET /api/metrics": { body: COUNTS }, "GET /api/evaluation": { body: RESULTS } });
    renderApp("/impact");
    const panel = await screen.findByRole("region", { name: "Synthetic evaluation results" });
    const table = await within(panel).findByRole("table");
    expect(within(panel).getByText("Live Nova: not run.")).toBeInTheDocument();
    expect(within(panel).getByText(/^Offline scripted run on 3 Nov 2026, 2 scenarios/)).toBeInTheDocument();
    const row = within(table).getByRole("rowheader", { name: "Risk category agreement" }).closest("tr")!;
    const cells = within(row).getAllByRole("cell");
    expect(cells[0]).toHaveTextContent("18 of 18 scenarios (100.0%)Offline scripted");
    expect(cells[1]).toHaveTextContent("Not runLive Nova");
    const relevance = within(table).getByRole("rowheader", { name: "Recommendation relevance (LLM judge)" }).closest("tr")!;
    expect(within(relevance).getAllByRole("cell")[0]).toHaveTextContent("Not runOffline scripted");
    for (const cell of within(table).getAllByRole("cell")) expect(cell.textContent).toMatch(/(Offline scripted|Live Nova)$/);
    expect(within(panel).getByText(RESULTS.label)).toBeInTheDocument();
  });

  it("shows a failed live run as text", async () => {
    const failed: EvaluationResults = {
      ...RESULTS,
      runs: { ...RESULTS.runs, live: run("live", {}, { status: "failed", error: "AccessDeniedException" }) },
    };
    mockApi({ "GET /api/metrics": { body: COUNTS }, "GET /api/evaluation": { body: failed } });
    renderApp("/impact");
    expect(await screen.findByText("Live Nova run on 3 Nov 2026 failed: AccessDeniedException.")).toBeInTheDocument();
  });

  it("says when no evaluation results file is available", async () => {
    mockApi({ "GET /api/metrics": { body: COUNTS } });
    renderApp("/impact");
    expect(await screen.findByText(NO_RESULTS_FILE)).toBeInTheDocument();
    expect(screen.getByRole("heading", { name: "Synthetic evaluation results" })).toBeInTheDocument();
  });

  it("shows a metrics error inside its block with Retry, keeping the statement", async () => {
    let calls = 0;
    mockApi({
      "GET /api/metrics": () => {
        calls += 1;
        return calls === 1
          ? { status: 500, body: { error: { code: "internal_error", message: "Something went wrong on the server.", fields: [] } } }
          : { body: COUNTS };
      },
      "GET /api/evaluation": { body: RESULTS },
    });
    renderApp("/impact");
    const counts = screen.getByRole("region", { name: "Stored assessments" });
    expect(await within(counts).findByRole("alert")).toHaveTextContent("Couldn't load the counts.");
    expect(screen.getByText(OUTCOME_STATEMENT)).toBeInTheDocument();
    await userEvent.click(within(counts).getByRole("button", { name: "Retry" }));
    expect(await within(counts).findByText("95.5%")).toBeInTheDocument();
  });

  it("is reachable from the main navigation and sets the document title", async () => {
    mockApi({ "GET /api/metrics": { body: ZERO }, "GET /api/evaluation": { body: RESULTS } });
    renderApp("/history");
    const nav = screen.getByRole("navigation", { name: "Main" });
    await userEvent.click(within(nav).getByRole("link", { name: "Impact" }));
    expect(await screen.findByRole("heading", { level: 1, name: "Impact" })).toBeInTheDocument();
    await waitFor(() => expect(document.title).toBe("Impact - HeatWise AI"));
  });
});
