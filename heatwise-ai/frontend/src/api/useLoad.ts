import { useCallback, useEffect, useState } from "react";

import { ApiError, toApiError } from "./client";

interface Loaded<T> {
  key: string;
  data: T | null;
  error: ApiError | null;
}

/**
 * Loads data for `key` with `load` (wrap it in useCallback). Keeps the result tied to the key, so a new
 * key or a retry shows the loading state until its own answer lands.
 */
export function useLoad<T>(key: string, load: (signal: AbortSignal) => Promise<T>) {
  const [attempt, setAttempt] = useState(0);
  const [result, setResult] = useState<Loaded<T> | null>(null);
  const fullKey = `${key}#${attempt}`;

  useEffect(() => {
    const ctrl = new AbortController();
    load(ctrl.signal).then(
      (data) => setResult({ key: fullKey, data, error: null }),
      (err: unknown) => {
        if (!ctrl.signal.aborted) setResult({ key: fullKey, data: null, error: toApiError(err) });
      },
    );
    return () => ctrl.abort();
  }, [fullKey, load]);

  const retry = useCallback(() => setAttempt((a) => a + 1), []);
  const current = result?.key === fullKey ? result : null;
  return { data: current?.data ?? null, error: current?.error ?? null, loading: current === null, retry };
}
