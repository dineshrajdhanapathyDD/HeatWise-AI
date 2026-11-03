import { screen, waitFor, within } from "@testing-library/react";
import userEvent from "@testing-library/user-event";
import { describe, expect, it, vi } from "vitest";

import type { PreparednessReport } from "../../api/types";
import { DISCLAIMER } from "../../components/Disclaimer";
import { fixtures, mockApi, recordFor, renderApp } from "../../test/helpers";
import { REVIEW_BANNER } from "./PlanView";

const TABS = ["climate", "risk", "plan", "activity"] as const;

function serve(report: PreparednessReport) {
  mockApi({ [`GET /api/reports/${report.report_id}`]: { body: recordFor(report) } });
}

async function openTab(report: PreparednessReport, tab: (typeof TABS)[number]) {
  serve(report);
  renderApp(`/reports/${report.report_id}/${tab}`);
  await screen.findByRole("navigation", { name: "Report sections" });
}

describe("PlanView on a needs_human_review report", () => {
  it("renders only verified items under the review banner and never the rejected item", async () => {
    const report = fixtures.needsReview();
    await openTab(report, "plan");

    expect(screen.getByRole("heading", { name: REVIEW_BANNER })).toBeInTheDocument();
    const verified = new Set(report.verification?.verified_item_ids);
    for (const item of report.recommended_actions?.items ?? []) {
      if (verified.has(item.id)) expect(screen.getAllByText(item.text).length).toBeGreaterThan(0);
      else expect(screen.queryByText(item.text)).not.toBeInTheDocument();
    }
    expect(document.body.textContent?.toLowerCase()).not.toContain("aspirin");
    expect(screen.getByText(`${verified.size} verified actions for the community`)).toBeInTheDocument();
  });

  it("downloads exactly report.checklist_markdown", async () => {
    const report = fixtures.needsReview();
    const blobs: Blob[] = [];
    URL.createObjectURL = vi.fn((b: Blob | MediaSource) => {
      blobs.push(b as Blob);
      return "blob:checklist";
    });
    URL.revokeObjectURL = vi.fn();
    const click = vi.spyOn(HTMLAnchorElement.prototype, "click").mockImplementation(function (this: HTMLAnchorElement) {
      expect(this.download).toBe(`heatwise-checklist-${report.report_id}.md`);
      expect(this.href).toBe("blob:checklist");
    });

    await openTab(report, "plan");
    await userEvent.click(screen.getByRole("button", { name: "Download checklist" }));

    expect(click).toHaveBeenCalledTimes(1);
    expect(blobs).toHaveLength(1);
    const text = await blobs[0]!.text();
    expect(text).toBe(report.checklist_markdown);
    expect(text).toContain(REVIEW_BANNER);
    expect(text.toLowerCase()).not.toContain("aspirin");
  });
});

describe("PlanView checklist", () => {
  it("posts the item id and flag, starting from the stored progress", async () => {
    const report = fixtures.complete();
    const items = report.recommended_actions!.items;
    const record = { ...recordFor(report), checklist_completed: { [items[0]!.id]: "2026-05-10T09:00:00Z" } };
    const bodies: unknown[] = [];
    mockApi({
      [`GET /api/reports/${report.report_id}`]: { body: record },
      [`POST /api/reports/${report.report_id}/checklist`]: (init) => {
        bodies.push(JSON.parse(String(init?.body)));
        return {
          body: {
            report_id: report.report_id,
            completed_item_ids: [items[0]!.id, items[1]!.id],
            completed_count: 2,
            available_count: items.length,
          },
        };
      },
    });
    renderApp(`/reports/${report.report_id}/plan`);
    const first = await screen.findByRole("checkbox", { name: items[0]!.text });
    expect(first).toBeChecked();
    expect(screen.getAllByRole("checkbox")).toHaveLength(items.length);
    expect(screen.getByText(`1 of ${items.length} done`)).toBeInTheDocument();

    await userEvent.click(screen.getByRole("checkbox", { name: items[1]!.text }));
    expect(bodies).toEqual([{ item_id: items[1]!.id, completed: true }]);
    await waitFor(() => expect(screen.getByRole("checkbox", { name: items[1]!.text })).toBeChecked());
    expect(screen.getByText(`2 of ${items.length} done`)).toBeInTheDocument();
  });

  it("offers checkboxes only for verified items on a needs_human_review report", async () => {
    const report = fixtures.needsReview();
    await openTab(report, "plan");
    const verified = report.verification!.verified_item_ids;
    const boxes = screen.getAllByRole("checkbox");
    expect(boxes).toHaveLength(verified.length);
    const verifiedTexts = new Set(report.recommended_actions!.items.filter((i) => verified.includes(i.id)).map((i) => i.text));
    for (const box of boxes) expect(verifiedTexts.has((box as HTMLInputElement).labels![0]!.textContent!)).toBe(true);
    expect(document.body.textContent?.toLowerCase()).not.toContain("aspirin");
  });

  it("shows an inline alert when saving fails and keeps the box unchanged", async () => {
    const report = fixtures.complete();
    const item = report.recommended_actions!.items[0]!;
    mockApi({
      [`GET /api/reports/${report.report_id}`]: { body: recordFor(report) },
      [`POST /api/reports/${report.report_id}/checklist`]: {
        status: 500,
        body: { error: { code: "internal_error", message: "Something went wrong on the server.", fields: [] } },
      },
    });
    renderApp(`/reports/${report.report_id}/plan`);
    await userEvent.click(await screen.findByRole("checkbox", { name: item.text }));
    expect(await screen.findByRole("alert")).toHaveTextContent(
      "Couldn't save the checklist change. Something went wrong on the server.",
    );
    expect(screen.getByRole("checkbox", { name: item.text })).not.toBeChecked();
  });
});

describe("PlanView on a needs_human_review report with no verified items", () => {
  it("keeps the review banner and says 0 items passed, showing no item", async () => {
    const report = fixtures.needsReview();
    report.verification!.verified_item_ids = [];
    await openTab(report, "plan");

    expect(screen.getByRole("heading", { name: REVIEW_BANNER })).toBeInTheDocument();
    expect(screen.getByText(/0 items passed verification, so no actions are shown/)).toBeInTheDocument();
    expect(screen.queryByText(/no preparedness plan was built/i)).not.toBeInTheDocument();
    for (const item of report.recommended_actions?.items ?? []) expect(screen.queryByText(item.text)).not.toBeInTheDocument();
    expect(document.body.textContent?.toLowerCase()).not.toContain("aspirin");
  });
});

describe("PlanView on a complete report", () => {
  it("renders every plan item and no review banner", async () => {
    const report = fixtures.complete();
    await openTab(report, "plan");
    const items = report.recommended_actions?.items ?? [];
    expect(items.length).toBeGreaterThan(0);
    for (const item of items) expect(screen.getAllByText(item.text).length).toBeGreaterThan(0);
    expect(screen.queryByRole("heading", { name: REVIEW_BANNER })).not.toBeInTheDocument();
    expect(screen.getByRole("button", { name: "Download checklist" })).toBeInTheDocument();
  });
});

describe("incomplete report", () => {
  it.each(TABS)("shows missing information and no plan or download on the %s tab", async (tab) => {
    const report = fixtures.incomplete();
    await openTab(report, tab);
    const missing = screen.getByRole("region", { name: "Missing information" });
    for (const m of report.missing_information) expect(within(missing).getByText(m)).toBeInTheDocument();
    expect(screen.getAllByText(/no preparedness plan was built/i).length).toBeGreaterThan(0);
    expect(screen.queryByRole("button", { name: "Download checklist" })).not.toBeInTheDocument();
    expect(screen.queryByRole("heading", { name: "Households" })).not.toBeInTheDocument();
  });
});

describe("disclaimer and notices", () => {
  it.each(TABS)("appear on the %s tab", async (tab) => {
    const report = fixtures.needsReview();
    await openTab(report, tab);
    const about = screen.getByRole("region", { name: "About this report" });
    expect(within(about).getByText(DISCLAIMER)).toBeInTheDocument();
    expect(DISCLAIMER).toMatch(/not medical advice/);
    expect(DISCLAIMER).toMatch(/not an emergency service/);
    expect(DISCLAIMER).toMatch(/not a substitute for official warnings/);
    for (const n of report.notices) expect(within(about).getByText(n)).toBeInTheDocument();
  });
});

describe("RiskView", () => {
  it("states the category comes from rules and shows a text label", async () => {
    const report = fixtures.complete();
    await openTab(report, "risk");
    expect(
      screen.getByText(`This category is set by deterministic rules (${report.risk?.rules_version}), not by an AI model.`),
    ).toBeInTheDocument();
    expect(screen.getByText("Risk category: Extreme")).toBeInTheDocument();
    expect(screen.getByText("The IMD indication is for one forecast point, not an official declaration.")).toBeInTheDocument();
  });
});

describe("ClimateView", () => {
  it("shows each forecast day against the IMD criteria and the official-warnings status", async () => {
    const report = fixtures.complete();
    await openTab(report, "climate");
    const strip = screen.getByRole("list", { name: "Forecast days against the IMD criteria" });
    expect(within(strip).getAllByRole("listitem")).toHaveLength(report.forecast?.days.length ?? 0);
    // Fixture maxima 44, 45 and 46 °C.
    expect(within(strip).getByText("Above the 40 °C threshold")).toBeInTheDocument();
    expect(within(strip).getAllByText("Heat wave level (45 °C)")).toHaveLength(2);
    expect(within(strip).queryByText(/Severe heat wave/)).not.toBeInTheDocument();
    expect(screen.getByText("No official source link returned.")).toBeInTheDocument();
    expect(screen.getByRole("table", { name: "Forecast daily maximum and minimum temperature" })).toBeInTheDocument();
  });

  it.each(["hilly", "coastal"] as const)("does not apply IMD levels for %s terrain, like the risk rules", async (terrain) => {
    const report = fixtures.complete();
    const record = recordFor(report);
    record.request.profile.terrain = terrain;
    mockApi({ [`GET /api/reports/${report.report_id}`]: { body: record } });
    renderApp(`/reports/${report.report_id}/climate`);
    await screen.findByRole("navigation", { name: "Report sections" });

    expect(screen.queryByRole("list", { name: "Forecast days against the IMD criteria" })).not.toBeInTheDocument();
    const strip = screen.getByRole("list", { name: "Forecast daily maximum by day" });
    expect(within(strip).getAllByText("IMD rule not applied")).toHaveLength(report.forecast?.days.length ?? 0);
    expect(document.body.textContent).not.toMatch(/Heat wave level|Above the \d+ °C threshold|Below the \d+ °C threshold/);
    expect(screen.getByText(`IMD actual-maximum rule not applied for ${terrain} terrain, so no IMD lines are drawn.`)).toBeInTheDocument();
    expect(screen.getByText(new RegExp(`IMD actual-maximum rule not applied for ${terrain} terrain\\.$`))).toBeInTheDocument();
  });
});

describe("ActivityView", () => {
  it("groups the trace by step and lists steering blocks", async () => {
    const report = fixtures.needsReview();
    report.steering_blocks = [{ tool: "finalize_report", reason: "finalize_report was called before safety_verifier." }];
    await openTab(report, "activity");

    const steps = new Set(report.trace.map((t) => t.step_index));
    const stepList = screen.getByRole("heading", { name: "Agent steps" }).parentElement!.querySelector("ol")!;
    expect(within(stepList).getAllByRole("listitem")).toHaveLength(steps.size);
    expect(screen.getAllByRole("button", { name: "Action Planner" })).toHaveLength(2);
    expect(screen.getByText("Plan revised after the safety check.")).toBeInTheDocument();
    expect(screen.getAllByText("Coordinator fallback (deterministic)", { exact: false }).length).toBeGreaterThan(0);

    // Specialist calls in the weather step are sorted by tool name.
    const weatherStep = screen.getByRole("button", { name: "Weather Intelligence" }).closest("li")!;
    const tools = within(weatherStep)
      .getAllByRole("row")
      .slice(1)
      // First text node only: the cell also holds the agent name shown on phones.
      .map((r) => within(r).getAllByRole("cell")[1]?.childNodes[0]?.textContent);
    expect(tools).toEqual(["get_forecast", "get_weather", "get_weather_alerts"]);
    expect(within(weatherStep).getByText("Tools called in this step (may run at the same time)")).toBeInTheDocument();

    const blocks = screen.getByRole("region", { name: "Blocked tool calls" });
    expect(within(blocks).getByText("finalize_report")).toBeInTheDocument();
    expect(within(blocks).getByText(/was called before safety_verifier/)).toBeInTheDocument();
  });

  it("collapses a step from the keyboard", async () => {
    const report = fixtures.complete();
    await openTab(report, "activity");
    const toggle = screen.getByRole("button", { name: "Community Risk (rules)" });
    expect(toggle).toHaveAttribute("aria-expanded", "true");
    toggle.focus();
    await userEvent.keyboard("{Enter}");
    expect(toggle).toHaveAttribute("aria-expanded", "false");
    await waitFor(() => expect(within(toggle.closest("li")!).queryByRole("table")).not.toBeInTheDocument());
  });
});

describe("ReportLayout", () => {
  it("shows an in-block error with Retry when the report cannot be loaded", async () => {
    mockApi({});
    renderApp("/reports/0123456789abcdef0123456789abcdef/climate");
    expect(await screen.findByRole("alert")).toHaveTextContent("Couldn't load this report.");
    expect(screen.getByRole("button", { name: "Retry" })).toBeInTheDocument();
  });

  it("marks the current tab with aria-current", async () => {
    const report = fixtures.complete();
    await openTab(report, "risk");
    const nav = screen.getByRole("navigation", { name: "Report sections" });
    expect(within(nav).getByRole("link", { name: "Risk" })).toHaveAttribute("aria-current", "page");
  });
});
