import { screen, waitFor, within } from "@testing-library/react";
import userEvent from "@testing-library/user-event";
import { describe, expect, it } from "vitest";

import { mockApi, renderApp } from "../test/helpers";

describe("Landing and shell", () => {
  it("shows the product, the tagline, the main action and the shell landmarks", async () => {
    mockApi({ "GET /api/history": { body: { items: [], total: 0, limit: 1, offset: 0 } } });
    renderApp("/");
    expect(screen.getByRole("heading", { level: 1, name: "HeatWise AI" })).toBeInTheDocument();
    expect(screen.getByText("From Weather Intelligence to Community Action.")).toBeInTheDocument();
    expect(screen.getByRole("link", { name: "Start an assessment" })).toHaveAttribute("href", "/assess");
    expect(screen.getByRole("link", { name: "Skip to main content" })).toHaveAttribute("href", "#main");
    expect(screen.getByRole("navigation", { name: "Main" })).toBeInTheDocument();
    expect(screen.getByRole("main")).toHaveAttribute("id", "main");
    expect(screen.getByRole("contentinfo")).toBeInTheDocument();
    expect(await screen.findByText("Live weather")).toBeInTheDocument();
    expect(await screen.findByText(/No assessments are stored yet/)).toBeInTheDocument();
  });

  it("names the screen correctly on a trailing-slash URL (Amplify deep links)", async () => {
    mockApi({ "GET /api/history": { body: { items: [], total: 0, limit: 20, offset: 0 } } });
    renderApp("/history/");
    await waitFor(() => expect(document.title).toBe("History - HeatWise AI"));
  });

  it("sets a per-screen title and moves focus to main after navigation", async () => {
    mockApi({ "GET /api/history": { body: { items: [], total: 0, limit: 1, offset: 0 } } });
    renderApp("/");
    await waitFor(() => expect(document.title).toBe("Home - HeatWise AI"));
    expect(screen.getByRole("main")).not.toHaveFocus();

    const nav = screen.getByRole("navigation", { name: "Main" });
    await userEvent.click(within(nav).getByRole("link", { name: "New assessment" }));
    await waitFor(() => expect(document.title).toBe("New assessment - HeatWise AI"));
    expect(screen.getByRole("main")).toHaveFocus();
  });
});
