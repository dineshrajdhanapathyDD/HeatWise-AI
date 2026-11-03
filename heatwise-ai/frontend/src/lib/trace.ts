import type { AgentTraceEntry } from "../api/types";

export interface Step {
  index: number;
  lead: AgentTraceEntry | null;
  calls: AgentTraceEntry[];
}

/** Groups the trace by step_index; the coordinator (or fallback) entry leads, specialist calls sorted by agent then tool. */
export function groupTrace(trace: AgentTraceEntry[]): Step[] {
  const byIndex = new Map<number, AgentTraceEntry[]>();
  for (const e of trace) byIndex.set(e.step_index, [...(byIndex.get(e.step_index) ?? []), e]);
  return [...byIndex.entries()]
    .sort(([a], [b]) => a - b)
    .map(([index, entries]) => {
      const lead = entries.find((e) => e.agent.startsWith("coordinator")) ?? null;
      const calls = entries
        .filter((e) => e !== lead)
        .sort((a, b) => a.agent.localeCompare(b.agent) || a.tool.localeCompare(b.tool));
      return { index, lead, calls };
    });
}
