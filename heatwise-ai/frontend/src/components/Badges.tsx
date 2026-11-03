import { useHealth } from "../api/healthContext";
import { Pill } from "./Pill";

/** Data and agent mode, from /api/health. */
export function Badges() {
  const { health, error, loading } = useHealth();
  if (loading) return <p className="h-5 text-small text-muted">Checking the API…</p>;
  if (error || !health) {
    return (
      <ul aria-label="Data and agent mode" className="flex flex-wrap gap-1.5">
        <li>
          <Pill tone="neutral">API not reachable</Pill>
        </li>
      </ul>
    );
  }
  return (
    <ul aria-label="Data and agent mode" className="flex flex-wrap gap-1.5">
      <li>
        <Pill tone="neutral">{health.weather_provider === "demo" ? "Demo data" : "Live weather"}</Pill>
      </li>
      {health.agent_mode === "offline" && (
        <li>
          <Pill tone="neutral">Scripted agents</Pill>
        </li>
      )}
    </ul>
  );
}
