import { type ReactNode, useMemo } from "react";

import { api } from "../api/client";
import { HealthContext } from "../api/healthContext";
import { useLoad } from "../api/useLoad";

/** Loads /api/health once; drives the shell badges and the demo-location select. */
export function HealthProvider({ children }: { children: ReactNode }) {
  const { data, error, loading } = useLoad("health", api.health);
  const value = useMemo(() => ({ health: data, error, loading }), [data, error, loading]);
  return <HealthContext.Provider value={value}>{children}</HealthContext.Provider>;
}
