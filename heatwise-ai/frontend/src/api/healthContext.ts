import { createContext, useContext } from "react";

import type { ApiError } from "./client";
import type { HealthView } from "./types";

export interface HealthState {
  health: HealthView | null;
  error: ApiError | null;
  loading: boolean;
}

export const HealthContext = createContext<HealthState>({ health: null, error: null, loading: true });

export function useHealth(): HealthState {
  return useContext(HealthContext);
}
