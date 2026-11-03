import { render, screen } from "@testing-library/react";
import { MemoryRouter, Route, Routes } from "react-router-dom";
import { describe, expect, it } from "vitest";

import type { JobStatus } from "../api/types";
import type { PollTiming } from "../api/usePollJob";
import { mockApi } from "../test/helpers";
import { JobProgress } from "./JobProgress";

const FAST: PollTiming = { intervalMs: 10, slowIntervalMs: 20, slowAfterMs: 1000, timeoutMs: 5000 };

function job(status: JobStatus, extra: Record<string, unknown> = {}) {
  return {
    job_id: "job-1",
    status,
    created_at: "2026-05-10T09:00:00Z",
    started_at: null,
    finished_at: null,
    duration_ms: null,
    report_id: null,
    error: null,
    request: { place: { name: "Wardha", district: null, state: "Maharashtra" }, forecast_days: 3, profile: {} },
    report: null,
    ...extra,
  };
}

function renderJob(timing: PollTiming = FAST) {
  render(
    <MemoryRouter initialEntries={["/assessments/job-1"]}>
      <Routes>
        <Route path="/assessments/:jobId" element={<JobProgress timing={timing} />} />
        <Route path="/reports/:reportId/climate" element={<p>Climate tab of the report</p>} />
        <Route path="/assess" element={<p>Assessment form</p>} />
      </Routes>
    </MemoryRouter>,
  );
}

describe("JobProgress", () => {
  it("follows queued -> running -> succeeded to the report route", async () => {
    const replies = [job("queued"), job("running"), job("succeeded", { report_id: "abc123" })];
    const seen: string[] = [];
    mockApi({
      "GET /api/assessments/job-1": () => {
        const next = replies.length > 1 ? replies.shift()! : replies[0]!;
        seen.push(next.status);
        return { body: next };
      },
    });
    renderJob();
    expect(await screen.findByText("For Wardha, Maharashtra")).toBeInTheDocument();
    expect(await screen.findByText("Climate tab of the report")).toBeInTheDocument();
    expect(seen.slice(0, 3)).toEqual(["queued", "running", "succeeded"]);
  });

  it("shows the failure and a Try again link", async () => {
    mockApi({
      "GET /api/assessments/job-1": {
        body: job("failed", {
          error: { code: "assessment_failed", message: "The assessment could not be completed. Check the server log." },
        }),
      },
    });
    renderJob();
    expect(await screen.findByText("The assessment could not be completed. Check the server log.")).toBeInTheDocument();
    expect(screen.getByRole("link", { name: "Try again" })).toHaveAttribute("href", "/assess");
  });

  it("keeps polling through a transient 5xx and still opens the report", async () => {
    const unavailable = { status: 503, body: { error: { code: "http_503", message: "Unavailable.", fields: [] } } };
    const replies = [{ body: job("running") }, unavailable, unavailable, { body: job("succeeded", { report_id: "abc123" }) }];
    mockApi({ "GET /api/assessments/job-1": () => (replies.length > 1 ? replies.shift()! : replies[0]!) });
    renderJob();
    expect(await screen.findByText("Climate tab of the report")).toBeInTheDocument();
  });

  it("gives up after repeated transient failures", async () => {
    mockApi({
      "GET /api/assessments/job-1": { status: 503, body: { error: { code: "http_503", message: "Unavailable.", fields: [] } } },
    });
    renderJob();
    expect(await screen.findByText("Couldn't check the assessment. Unavailable.")).toBeInTheDocument();
  });

  it("stops polling after the timeout and says so", async () => {
    mockApi({ "GET /api/assessments/job-1": { body: job("running") } });
    renderJob({ intervalMs: 5, slowIntervalMs: 5, slowAfterMs: 10, timeoutMs: 30 });
    expect(await screen.findByText(/taking longer than 5 minutes/)).toBeInTheDocument();
  });

  it("announces status in a polite live region", async () => {
    mockApi({ "GET /api/assessments/job-1": { body: job("running") } });
    renderJob({ intervalMs: 1000, slowIntervalMs: 1000, slowAfterMs: 1000, timeoutMs: 60_000 });
    const status = await screen.findByText("The agents are working on the assessment.");
    expect(status.closest("[aria-live]")).toHaveAttribute("aria-live", "polite");
  });
});
