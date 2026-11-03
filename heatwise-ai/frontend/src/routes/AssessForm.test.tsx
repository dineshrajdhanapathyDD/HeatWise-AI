import { screen, waitFor, within } from "@testing-library/react";
import userEvent from "@testing-library/user-event";
import { describe, expect, it } from "vitest";

import type { AssessmentRequest } from "../api/types";
import { LIVE_HEALTH, mockApi, renderApp } from "../test/helpers";

type User = ReturnType<typeof userEvent.setup>;

function jobFor(body: AssessmentRequest) {
  return {
    job_id: "job-1",
    status: "queued",
    created_at: "2026-05-10T09:00:00Z",
    started_at: null,
    finished_at: null,
    duration_ms: null,
    report_id: null,
    error: null,
    request: body,
    report: null,
  };
}

function captureSubmit() {
  const sent: AssessmentRequest[] = [];
  mockApi({
    "POST /api/assessments": (init) => {
      const body = JSON.parse(String(init?.body)) as AssessmentRequest;
      sent.push(body);
      return { status: 202, body: jobFor(body) };
    },
    "GET /api/assessments/job-1": () => ({ body: jobFor(sent[0]!) }),
  });
  return sent;
}

async function next(user: User, heading: string) {
  await user.click(screen.getByRole("button", { name: "Next" }));
  expect(await screen.findByRole("heading", { level: 2, name: heading })).toBeInTheDocument();
}

describe("AssessForm", () => {
  it("walks the three steps and maps the form onto the request body", async () => {
    const sent = captureSubmit();
    const user = userEvent.setup();
    renderApp("/assess");

    expect(screen.getByRole("list", { name: "Assessment steps" })).toBeInTheDocument();
    expect(screen.getByRole("heading", { level: 2, name: "Place" })).toBeInTheDocument();
    await user.type(screen.getByLabelText("City, town or village"), "Wardha");
    await user.type(screen.getByLabelText("District (optional)"), "Wardha");
    await user.type(screen.getByLabelText("State (optional)"), "Maharashtra");
    await next(user, "Community");

    await user.click(screen.getByLabelText("Older people"));
    await user.click(screen.getByLabelText("Farming households"));
    await user.click(within(screen.getByRole("group", { name: "Drinking water access" })).getByRole("radio", { name: "Limited" }));
    await user.click(screen.getByRole("radio", { name: "Plains" }));
    await next(user, "Settings and review");

    await user.selectOptions(screen.getByLabelText("Forecast days"), "5");
    await user.selectOptions(screen.getByLabelText("Preferred language"), "hi");
    const review = screen.getByRole("region", { name: "Review" });
    expect(within(review).getByText("Wardha, Wardha, Maharashtra")).toBeInTheDocument();
    expect(within(review).getByText("Older people, Farming households")).toBeInTheDocument();
    await user.click(screen.getByRole("button", { name: "Run the assessment" }));

    expect(await screen.findByRole("heading", { name: "Assessment in progress" })).toBeInTheDocument();
    expect(sent).toEqual([
      {
        place: { name: "Wardha", district: "Wardha", state: "Maharashtra" },
        forecast_days: 5,
        profile: {
          elderly: true,
          young_children: false,
          pregnant_women: false,
          chronic_illness_group: false,
          outdoor_workers: false,
          farmers: true,
          limited_water_access: true,
          limited_shade_or_cooling: false,
          terrain: "plains",
          preferred_language: "hi",
        },
      },
    ]);
    expect(await screen.findByText("Assessment started for Wardha.")).toBeInTheDocument();
  }, 20_000);

  it("keeps answers when going back a step", async () => {
    mockApi({});
    const user = userEvent.setup();
    renderApp("/assess");
    await user.type(screen.getByLabelText("City, town or village"), "Nagpur");
    await next(user, "Community");
    await user.click(screen.getByLabelText("Young children"));
    await user.click(screen.getByRole("button", { name: "Back" }));
    expect(screen.getByLabelText("City, town or village")).toHaveValue("Nagpur");
    await next(user, "Community");
    expect(screen.getByLabelText("Young children")).toBeChecked();
  });

  it("ties the English-only note to the language select", async () => {
    mockApi({});
    const user = userEvent.setup();
    renderApp("/assess");
    await user.type(screen.getByLabelText("City, town or village"), "Wardha");
    await next(user, "Community");
    await next(user, "Settings and review");
    expect(screen.getByLabelText("Preferred language")).toHaveAccessibleDescription("Plans are English only for now.");
  });

  it("sends null qualifiers and terrain when they are left empty", async () => {
    const sent = captureSubmit();
    const user = userEvent.setup();
    renderApp("/assess");
    await user.type(screen.getByLabelText("City, town or village"), "  Nagpur ");
    await next(user, "Community");
    await next(user, "Settings and review");
    await user.click(screen.getByRole("button", { name: "Run the assessment" }));
    await screen.findByRole("heading", { name: "Assessment in progress" });
    expect(sent[0]?.place).toEqual({ name: "Nagpur", district: null, state: null });
    expect(sent[0]?.profile.terrain).toBeNull();
    expect(Object.keys(sent[0] ?? {}).sort()).toEqual(["forecast_days", "place", "profile"]);
  });

  it("blocks an empty place name on the first step and focuses it", async () => {
    const sent = captureSubmit();
    const user = userEvent.setup();
    renderApp("/assess");
    await user.click(screen.getByRole("button", { name: "Next" }));
    const name = screen.getByLabelText("City, town or village");
    expect(name).toHaveAttribute("aria-invalid", "true");
    expect(name).toHaveAccessibleDescription("Enter the city, town or village.");
    await waitFor(() => expect(name).toHaveFocus());
    expect(screen.getByRole("heading", { level: 2, name: "Place" })).toBeInTheDocument();
    expect(sent).toHaveLength(0);
  });

  it("returns to the step with the first server field error and focuses it", async () => {
    mockApi({
      "POST /api/assessments": {
        status: 422,
        body: {
          error: {
            code: "validation_error",
            message: "The request is not valid.",
            fields: [
              { field: "place.state", message: "Location contains characters that are not allowed." },
              { field: "forecast_days", message: "Forecast days must be between 1 and 7." },
            ],
          },
        },
      },
    });
    const user = userEvent.setup();
    renderApp("/assess");
    await user.type(screen.getByLabelText("City, town or village"), "Wardha");
    await user.type(screen.getByLabelText("State (optional)"), "Maha");
    await next(user, "Community");
    await next(user, "Settings and review");
    await user.click(screen.getByRole("button", { name: "Run the assessment" }));

    expect(await screen.findByRole("heading", { level: 2, name: "Place" })).toBeInTheDocument();
    const state = screen.getByLabelText("State (optional)");
    await waitFor(() => expect(state).toHaveFocus());
    expect(state).toHaveAttribute("aria-invalid", "true");
    expect(state).toHaveAccessibleDescription("Location contains characters that are not allowed.");

    await next(user, "Community");
    await next(user, "Settings and review");
    expect(screen.getByLabelText("Forecast days")).toHaveAccessibleDescription(
      "From 1 to 7 days. Forecast days must be between 1 and 7.",
    );
  }, 20_000);

  it("can be filled in and submitted with the keyboard alone", async () => {
    const sent = captureSubmit();
    const user = userEvent.setup();
    renderApp("/assess");
    const name = screen.getByLabelText("City, town or village");

    for (let i = 0; i < 20 && document.activeElement !== name; i++) await user.tab();
    expect(name).toHaveFocus();
    await user.keyboard("Wardha{Enter}");
    const community = await screen.findByRole("heading", { level: 2, name: "Community" });
    await waitFor(() => expect(community).toHaveFocus());

    const older = screen.getByLabelText("Older people");
    for (let i = 0; i < 10 && document.activeElement !== older; i++) await user.tab();
    expect(older).toHaveFocus();
    await user.keyboard(" ");
    const nextButton = screen.getByRole("button", { name: "Next" });
    for (let i = 0; i < 30 && document.activeElement !== nextButton; i++) await user.tab();
    expect(nextButton).toHaveFocus();
    await user.keyboard("{Enter}");

    await screen.findByRole("heading", { level: 2, name: "Settings and review" });
    const submit = screen.getByRole("button", { name: "Run the assessment" });
    for (let i = 0; i < 30 && document.activeElement !== submit; i++) await user.tab();
    expect(submit).toHaveFocus();
    await user.keyboard("{Enter}");

    await screen.findByRole("heading", { name: "Assessment in progress" });
    expect(sent[0]?.place.name).toBe("Wardha");
    expect(sent[0]?.profile.elderly).toBe(true);
  }, 20_000);

  it("replaces the place fields with the demo locations in demo mode", async () => {
    const sent: AssessmentRequest[] = [];
    mockApi({
      "GET /api/health": {
        body: { ...LIVE_HEALTH, weather_provider: "demo", agent_mode: "offline", demo_locations: ["demo-hot-dry", "demo-mild"] },
      },
      "POST /api/assessments": (init) => {
        const body = JSON.parse(String(init?.body)) as AssessmentRequest;
        sent.push(body);
        return { status: 202, body: jobFor(body) };
      },
    });
    const user = userEvent.setup();
    renderApp("/assess");
    const select = await screen.findByLabelText("Demo location");
    expect(screen.queryByLabelText("City, town or village")).not.toBeInTheDocument();
    expect(screen.getByText("Demo data")).toBeInTheDocument();
    expect(screen.getByText("Scripted agents")).toBeInTheDocument();
    await user.selectOptions(select, "demo-mild");
    await next(user, "Community");
    await next(user, "Settings and review");
    await user.click(screen.getByRole("button", { name: "Run the assessment" }));
    await waitFor(() => expect(sent).toHaveLength(1));
    expect(sent[0]?.place).toEqual({ name: "demo-mild" });
  });
});
