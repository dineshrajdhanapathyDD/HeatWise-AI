import { describe, expect, it } from "vitest";

import { fixtures } from "../test/helpers";
import { renderablePlanItems } from "./safety";

describe("renderablePlanItems", () => {
  it("returns every item of a complete report", () => {
    const report = fixtures.complete();
    expect(renderablePlanItems(report)).toEqual(report.recommended_actions?.items);
    expect(renderablePlanItems(report).length).toBeGreaterThan(0);
  });

  it("returns only verified items on needs_human_review and drops the rejected one", () => {
    const report = fixtures.needsReview();
    const verified = report.verification?.verified_item_ids ?? [];
    const ids = renderablePlanItems(report).map((i) => i.id);
    expect(ids).toEqual(report.recommended_actions?.items.map((i) => i.id).filter((id) => verified.includes(id)));
    expect(ids).not.toContain("general-1");
    expect(report.recommended_actions?.items.some((i) => i.id === "general-1")).toBe(true);
  });

  it("returns nothing on needs_human_review without a verification result", () => {
    const report = fixtures.needsReview();
    report.verification = null;
    expect(renderablePlanItems(report)).toEqual([]);
  });

  it("returns nothing for an incomplete report, even if a plan is present", () => {
    const report = fixtures.incomplete();
    expect(renderablePlanItems(report)).toEqual([]);
    report.recommended_actions = fixtures.complete().recommended_actions;
    expect(renderablePlanItems(report)).toEqual([]);
  });
});
