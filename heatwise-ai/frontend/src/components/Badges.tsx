import { useHealth } from "../api/healthContext";

function Badge({ dot, children }: { dot: string; children: string }) {
  return (
    <li className="inline-flex h-6 items-center gap-1.5 rounded-full border border-line bg-raised/70 px-2.5 text-small font-medium text-neutral-ink">
      <span aria-hidden="true" className="h-1.5 w-1.5 rounded-full" style={{ background: dot }} />
      {children}
    </li>
  );
}

/** Data and agent mode, from /api/health. */
export function Badges() {
  const { health, error, loading } = useHealth();
  if (loading) return <p className="h-6 text-small text-muted">Checking the API…</p>;
  if (error || !health) {
    return (
      <ul aria-label="Data and agent mode" className="flex flex-wrap gap-1.5">
        <Badge dot="#f87171">API not reachable</Badge>
      </ul>
    );
  }
  return (
    <ul aria-label="Data and agent mode" className="flex flex-wrap gap-1.5">
      <Badge dot={health.weather_provider === "demo" ? "#facc15" : "#34d399"}>
        {health.weather_provider === "demo" ? "Demo data" : "Live weather"}
      </Badge>
      {health.agent_mode === "offline" && <Badge dot="#93a4c3">Scripted agents</Badge>}
      {health.agent_mode === "agentcore" && <Badge dot="#38c6f4">AgentCore Runtime</Badge>}
    </ul>
  );
}
