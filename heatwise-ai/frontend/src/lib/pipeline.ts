import type { AgentTraceEntry, JobStatus, PreparednessReport } from "../api/types";
import { groupTrace } from "./trace";

/** The five agents in the order the coordinator runs them; the coordinator assembles the report last. */
export const PIPELINE_AGENTS = [
  { key: "weather_intelligence", name: "Weather Intelligence", role: "Live weather, forecast and warnings" },
  { key: "community_risk", name: "Community Risk", role: "Deterministic heat-risk rules" },
  { key: "action_planner", name: "Action Planner", role: "Plan from verified guidance" },
  { key: "safety_verifier", name: "Safety and Verification", role: "Checks every plan item" },
  { key: "finalize_report", name: "Coordinator", role: "Orders the agents, assembles the report" },
] as const;

export type AgentKey = (typeof PIPELINE_AGENTS)[number]["key"];

/**
 * idle: nothing is executing. waiting: the job runs but the API does not say which agent is active.
 * done / failed / skipped come from the recorded trace of a finished report.
 */
export type AgentState = "idle" | "waiting" | "done" | "revised" | "failed" | "skipped";

export interface PipelineStage {
  key: AgentKey;
  name: string;
  role: string;
  state: AgentState;
  runs: number;
  durationMs: number | null;
}

export type PipelineInput =
  | { phase: "idle" }
  | { phase: "running"; status: JobStatus }
  | { phase: "finished"; report: PreparednessReport };

function leadsFor(trace: AgentTraceEntry[], key: AgentKey): AgentTraceEntry[] {
  return groupTrace(trace)
    .map((s) => s.lead)
    .filter((l): l is AgentTraceEntry => l !== null && l.tool === key);
}

/** Stage states. Only a finished report's trace marks an agent done; nothing is shown as working without data. */
export function pipelineStages(input: PipelineInput): PipelineStage[] {
  return PIPELINE_AGENTS.map((a) => {
    if (input.phase !== "finished") {
      return { ...a, state: input.phase === "running" ? "waiting" : "idle", runs: 0, durationMs: null };
    }
    const leads = leadsFor(input.report.trace, a.key);
    if (!leads.length) return { ...a, state: "skipped", runs: 0, durationMs: null };
    const last = leads[leads.length - 1]!;
    const durationMs = leads.reduce<number | null>(
      (sum, l) => (l.duration_ms === null ? sum : (sum ?? 0) + l.duration_ms),
      null,
    );
    let state: AgentState = last.status === "success" ? "done" : "failed";
    if (state === "done" && a.key === "action_planner" && leads.length > 1) state = "revised";
    return { ...a, state, runs: leads.length, durationMs };
  });
}

export const STATE_TEXT: Record<AgentState, string> = {
  idle: "Not running",
  waiting: "Waiting for result",
  done: "Completed",
  revised: "Completed after revision",
  failed: "Did not complete",
  skipped: "Not run",
};

/** A one-line verdict for the pipeline footer. */
export function pipelineVerdict(input: PipelineInput): string {
  if (input.phase === "idle") return "No assessment is running. The agents start when you run one.";
  if (input.phase === "running") {
    return input.status === "queued"
      ? "Queued. The job will start when a worker is free."
      : "Running on the server. The API reports overall job status only, so each agent's result appears when the report is ready.";
  }
  const r = input.report;
  if (r.status === "complete") return "Report verified and complete.";
  if (r.status === "needs_human_review") return "Report needs human review: only verified actions are shown.";
  return "Report incomplete: no preparedness plan was built.";
}
