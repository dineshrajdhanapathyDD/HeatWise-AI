import { describe, expect, it, vi } from "vitest";

import { ApiError, api, fetchJson } from "./client";

function respond(status: number, body: string, contentType = "application/json") {
  vi.spyOn(globalThis, "fetch").mockResolvedValue(new Response(body, { status, headers: { "Content-Type": contentType } }));
}

describe("fetchJson", () => {
  it("parses the error envelope with field errors", async () => {
    respond(
      422,
      JSON.stringify({
        error: {
          code: "validation_error",
          message: "The request is not valid.",
          fields: [{ field: "forecast_days", message: "Forecast days must be between 1 and 7." }],
        },
      }),
    );
    const err = await fetchJson("/api/assessments", { method: "POST", body: {} }).catch((e: unknown) => e);
    expect(err).toBeInstanceOf(ApiError);
    expect(err).toMatchObject({
      status: 422,
      code: "validation_error",
      message: "The request is not valid.",
      fields: [{ field: "forecast_days", message: "Forecast days must be between 1 and 7." }],
    });
  });

  it("falls back to http_<status> when the body is not an envelope", async () => {
    respond(502, "<html>Bad gateway</html>", "text/html");
    await expect(api.metrics()).rejects.toMatchObject({ status: 502, code: "http_502", fields: [] });
  });

  it("reports a network failure as network_error", async () => {
    vi.spyOn(globalThis, "fetch").mockRejectedValue(new TypeError("Failed to fetch"));
    await expect(api.health()).rejects.toMatchObject({ status: 0, code: "network_error" });
  });

  it("sends JSON bodies with a Content-Type header", async () => {
    const spy = vi
      .spyOn(globalThis, "fetch")
      .mockResolvedValue(new Response(JSON.stringify({ job_id: "j1" }), { status: 202 }));
    await fetchJson("/api/assessments", { method: "POST", body: { a: 1 } });
    const [url, init] = spy.mock.calls[0] ?? [];
    expect(String(url)).toMatch(/\/api\/assessments$/);
    expect(init).toMatchObject({ method: "POST", body: '{"a":1}', headers: { "Content-Type": "application/json" } });
  });
});
