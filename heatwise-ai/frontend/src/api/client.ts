import type {
  AssessmentRecord,
  AssessmentRequest,
  ChecklistProgress,
  EvaluationResults,
  FieldError,
  HealthView,
  HistoryPage,
  JobView,
  MetricsView,
} from "./types";

export const API_BASE: string =
  (import.meta.env.VITE_API_BASE_URL as string | undefined)?.replace(/\/+$/, "") ?? "http://localhost:8000";

/** Any failed API call: an error envelope from the server, a non-JSON error, or no connection. */
export class ApiError extends Error {
  readonly status: number;
  readonly code: string;
  readonly fields: FieldError[];

  constructor(status: number, code: string, message: string, fields: FieldError[] = []) {
    super(message);
    this.name = "ApiError";
    this.status = status;
    this.code = code;
    this.fields = fields;
  }
}

function isEnvelope(body: unknown): body is { error: { code: string; message: string; fields?: FieldError[] } } {
  if (typeof body !== "object" || body === null || !("error" in body)) return false;
  const err = (body as { error: unknown }).error;
  return (
    typeof err === "object" &&
    err !== null &&
    typeof (err as { code?: unknown }).code === "string" &&
    typeof (err as { message?: unknown }).message === "string"
  );
}

/** Turns a failed response into an ApiError, reading the {"error": {...}} envelope when present. */
export async function parseError(res: Response): Promise<ApiError> {
  let body: unknown = null;
  try {
    body = await res.json();
  } catch {
    body = null;
  }
  if (isEnvelope(body)) {
    const fields = Array.isArray(body.error.fields) ? body.error.fields : [];
    return new ApiError(res.status, body.error.code, body.error.message, fields);
  }
  return new ApiError(res.status, `http_${res.status}`, `The server answered with HTTP ${res.status}.`);
}

/** Normalises anything thrown by a fetch into an ApiError (AbortErrors are rethrown untouched). */
export function toApiError(err: unknown): ApiError {
  if (err instanceof ApiError) return err;
  return new ApiError(0, "network_error", "Could not reach the HeatWise API. Check that the server is running.");
}

interface JsonInit {
  method?: "GET" | "POST";
  body?: unknown;
  signal?: AbortSignal;
}

export async function fetchJson<T>(path: string, init: JsonInit = {}): Promise<T> {
  let res: Response;
  try {
    res = await fetch(`${API_BASE}${path}`, {
      method: init.method ?? "GET",
      headers: init.body === undefined ? undefined : { "Content-Type": "application/json" },
      body: init.body === undefined ? undefined : JSON.stringify(init.body),
      signal: init.signal,
    });
  } catch (err) {
    if (err instanceof DOMException && err.name === "AbortError") throw err;
    throw toApiError(err);
  }
  if (!res.ok) throw await parseError(res);
  return (await res.json()) as T;
}

export const api = {
  health: (signal?: AbortSignal) => fetchJson<HealthView>("/api/health", { signal }),
  createAssessment: (body: AssessmentRequest) =>
    fetchJson<JobView>("/api/assessments", { method: "POST", body }),
  job: (jobId: string, signal?: AbortSignal) =>
    fetchJson<JobView>(`/api/assessments/${encodeURIComponent(jobId)}`, { signal }),
  report: (reportId: string, signal?: AbortSignal) =>
    fetchJson<AssessmentRecord>(`/api/reports/${encodeURIComponent(reportId)}`, { signal }),
  history: (limit: number, offset: number, signal?: AbortSignal) =>
    fetchJson<HistoryPage>(`/api/history?limit=${limit}&offset=${offset}`, { signal }),
  metrics: (signal?: AbortSignal) => fetchJson<MetricsView>("/api/metrics", { signal }),
  setChecklistItem: (reportId: string, itemId: string, completed: boolean) =>
    fetchJson<ChecklistProgress>(`/api/reports/${encodeURIComponent(reportId)}/checklist`, {
      method: "POST",
      body: { item_id: itemId, completed },
    }),
  evaluation: (signal?: AbortSignal) => fetchJson<EvaluationResults>("/api/evaluation", { signal }),
};
