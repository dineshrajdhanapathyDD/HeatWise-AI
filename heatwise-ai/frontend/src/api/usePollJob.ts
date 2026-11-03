import { useEffect, useState } from "react";

import { ApiError, api, toApiError } from "./client";
import type { JobView } from "./types";

export interface PollTiming {
  intervalMs: number;
  slowIntervalMs: number;
  slowAfterMs: number;
  timeoutMs: number;
}

/** Every 1.5 s, every 3 s after 30 s, give up after 5 minutes. */
export const DEFAULT_POLL_TIMING: PollTiming = {
  intervalMs: 1500,
  slowIntervalMs: 3000,
  slowAfterMs: 30_000,
  timeoutMs: 5 * 60_000,
};

/** Consecutive transient poll failures (no connection or 5xx) tolerated before giving up. */
export const MAX_TRANSIENT_POLL_FAILURES = 3;

function isTransient(err: ApiError): boolean {
  return err.code === "network_error" || err.status >= 500;
}

interface PollState {
  jobId: string;
  job: JobView | null;
  error: ApiError | null;
  timedOut: boolean;
}

/** Polls GET /api/assessments/{jobId} until the job succeeds or fails, the timeout passes, or unmount. */
export function usePollJob(jobId: string, timing: PollTiming = DEFAULT_POLL_TIMING) {
  const [state, setState] = useState<PollState>({ jobId, job: null, error: null, timedOut: false });

  useEffect(() => {
    const ctrl = new AbortController();
    const started = Date.now();
    let timer: ReturnType<typeof setTimeout> | undefined;
    let failures = 0;

    const tick = async () => {
      try {
        const job = await api.job(jobId, ctrl.signal);
        if (ctrl.signal.aborted) return;
        failures = 0;
        setState({ jobId, job, error: null, timedOut: false });
        if (job.status === "succeeded" || job.status === "failed") return;
      } catch (err) {
        if (ctrl.signal.aborted) return;
        const apiErr = toApiError(err);
        failures += 1;
        // A dropped request or a 5xx does not mean the job stopped: keep checking a few times.
        if (!isTransient(apiErr) || failures >= MAX_TRANSIENT_POLL_FAILURES) {
          setState((s) => ({ ...s, jobId, error: apiErr }));
          return;
        }
      }
      const elapsed = Date.now() - started;
      if (elapsed >= timing.timeoutMs) {
        setState((s) => ({ ...s, jobId, timedOut: true }));
        return;
      }
      timer = setTimeout(tick, elapsed < timing.slowAfterMs ? timing.intervalMs : timing.slowIntervalMs);
    };
    void tick();

    return () => {
      ctrl.abort();
      if (timer !== undefined) clearTimeout(timer);
    };
  }, [jobId, timing]);

  return state.jobId === jobId ? state : { jobId, job: null, error: null, timedOut: false };
}
