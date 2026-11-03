import { AnimatePresence, motion } from "framer-motion";
import { ChevronDown } from "lucide-react";
import { useId, useState } from "react";

import type { AgentTraceEntry, PreparednessReport } from "../../api/types";
import { AgentPipeline } from "../../components/AgentPipeline";
import { formatDuration } from "../../lib/format";
import { riskLabel, statusLabel } from "../../lib/risk";
import { renderablePlanItems } from "../../lib/safety";
import { type Step, groupTrace } from "../../lib/trace";
import { useReportRecord } from "./reportContext";

const CARD = "glass rounded-card p-5";

const AGENT_NAMES: Record<string, string> = {
  coordinator: "Coordinator",
  coordinator_fallback: "Coordinator fallback (deterministic)",
  weather_intelligence: "Weather Intelligence",
  community_risk: "Community Risk",
  action_planner: "Action Planner",
  safety_verifier: "Safety and Verification",
};

const STEP_TITLES: Record<string, string> = {
  weather_intelligence: "Weather Intelligence",
  community_risk: "Community Risk (rules)",
  action_planner: "Action Planner",
  safety_verifier: "Safety and Verification",
  finalize_report: "Report assembled",
};

const STATUS_TEXT = { success: "Succeeded", error: "Error", cancelled: "Cancelled" } as const;

function stepSummary(report: PreparednessReport, step: Step, steps: Step[]): string | null {
  const tool = step.lead?.tool;
  const later = steps.filter((s) => s.index > step.index).map((s) => s.lead?.tool);
  switch (tool) {
    case "weather_intelligence": {
      const days = report.forecast?.days.length ?? 0;
      return `${report.current_conditions ? "Current conditions retrieved" : "No current conditions"}; ${
        days ? `${days}-day forecast retrieved` : "no forecast"
      }.`;
    }
    case "community_risk":
      return report.risk ? `Risk category set to ${riskLabel(report.risk.category).toLowerCase()}.` : "Risk not assessed.";
    case "action_planner":
      return steps.some((s) => s.index < step.index && s.lead?.tool === "action_planner")
        ? "Plan revised after the safety check."
        : "Plan drafted from the verified guidance catalog.";
    case "safety_verifier":
      if (later.includes("action_planner")) return "Verification failed; the plan was sent back for one revision.";
      if (!report.verification) return "Verification did not run.";
      return `Verification ${report.verification.status}: ${report.verification.pct_items_verified.toFixed(1)}% of items verified, ${renderablePlanItems(report).length} shown.`;
    case "finalize_report":
      return `Report status: ${statusLabel(report.status).toLowerCase()}.`;
    default:
      return null;
  }
}

function CallRow({ entry }: { entry: AgentTraceEntry }) {
  return (
    <tr>
      <td className="hidden py-2 pr-4 sm:table-cell">{AGENT_NAMES[entry.agent] ?? entry.agent}</td>
      <td className="py-2 pr-3 break-all sm:pr-4">
        {entry.tool}
        <span className="block text-small text-muted sm:hidden">{AGENT_NAMES[entry.agent] ?? entry.agent}</span>
      </td>
      <td className="py-2 pr-3 sm:pr-4">
        {STATUS_TEXT[entry.status]}
        {entry.cancel_reason && <span className="block text-small text-muted">{entry.cancel_reason}</span>}
      </td>
      <td className="num py-2 text-right whitespace-nowrap">{formatDuration(entry.duration_ms)}</td>
    </tr>
  );
}

function StepBlock({ step, summary }: { step: Step; summary: string | null }) {
  const [open, setOpen] = useState(true);
  const panelId = useId();
  const title = STEP_TITLES[step.lead?.tool ?? ""] ?? step.lead?.tool ?? "Unattributed tool calls";
  return (
    <li className={CARD}>
      <h3 className="text-section font-medium">
        <button
          type="button"
          aria-expanded={open}
          aria-controls={panelId}
          onClick={() => setOpen((o) => !o)}
          className="flex w-full items-center justify-between gap-3 rounded-control text-left"
        >
          <span>{title}</span>
          <ChevronDown
            size={16}
            strokeWidth={1.5}
            aria-hidden="true"
            className={`flex-none text-muted transition-transform ${open ? "rotate-180" : ""}`}
          />
        </button>
      </h3>
      {step.lead && (
        <p className="mt-1 text-small text-muted">
          {`${AGENT_NAMES[step.lead.agent] ?? step.lead.agent} · ${STATUS_TEXT[step.lead.status]} · `}
          <span className="num">{formatDuration(step.lead.duration_ms)}</span>
          {step.lead.cancel_reason ? ` · ${step.lead.cancel_reason}` : ""}
        </p>
      )}
      {summary && <p className="mt-2 text-body">{summary}</p>}
      <AnimatePresence initial={false}>
        {open && step.calls.length > 0 && (
          <motion.div
            id={panelId}
            key="calls"
            initial={{ height: 0, opacity: 0 }}
            animate={{ height: "auto", opacity: 1 }}
            exit={{ height: 0, opacity: 0 }}
            transition={{ duration: 0.18, ease: "easeOut" }}
            className="overflow-hidden"
          >
            <table className="mt-3 w-full text-body">
              <caption className="text-left text-small text-muted">
                Tools called in this step (may run at the same time)
              </caption>
              <thead>
                <tr className="text-left text-small text-muted">
                  <th scope="col" className="hidden py-2 pr-4 font-normal sm:table-cell">Agent</th>
                  <th scope="col" className="py-2 pr-3 font-normal sm:pr-4">Tool</th>
                  <th scope="col" className="py-2 pr-3 font-normal sm:pr-4">Status</th>
                  <th scope="col" className="py-2 text-right font-normal">Duration</th>
                </tr>
              </thead>
              <tbody>
                {step.calls.map((c, i) => (
                  <CallRow key={`${c.agent}-${c.tool}-${i}`} entry={c} />
                ))}
              </tbody>
            </table>
          </motion.div>
        )}
      </AnimatePresence>
    </li>
  );
}

/** Screen F: what did each agent do to produce this report? */
export function ActivityView() {
  const { report } = useReportRecord();
  const steps = groupTrace(report.trace);

  return (
    <div className="space-y-6">
      <AgentPipeline input={{ phase: "finished", report }} headingId="activity-pipeline-h" title="Agent workflow for this report" />
      <section aria-labelledby="steps-h">
        <h2 id="steps-h" className="text-section font-medium">
          Agent steps
        </h2>
        <p className="mt-1 text-body text-muted">
          {`${steps.length} steps, ${report.trace.length} recorded tool calls, ${report.revision_count} plan ${
            report.revision_count === 1 ? "revision" : "revisions"
          }.`}
        </p>
        {steps.length ? (
          <ol className="mt-4 grid gap-3 xl:grid-cols-2">
            {steps.map((s) => (
              <StepBlock key={s.index} step={s} summary={stepSummary(report, s, steps)} />
            ))}
          </ol>
        ) : (
          <p className="mt-3 text-body">No agent activity was recorded.</p>
        )}
      </section>

      <div className="grid gap-6 md:grid-cols-2">
        <section aria-labelledby="blocks-h" className={CARD}>
          <h2 id="blocks-h" className="text-section font-medium">
            Blocked tool calls
          </h2>
          {report.steering_blocks.length ? (
            <ul className="mt-2 space-y-2 text-body">
              {report.steering_blocks.map((b, i) => (
                <li key={`${b.tool ?? "tool"}-${i}`}>
                  <span className="font-medium">{b.tool ?? "Unknown tool"}</span>
                  {b.reason ? `: ${b.reason}` : ""}
                </li>
              ))}
            </ul>
          ) : (
            <p className="mt-1 text-body">No tool calls were blocked.</p>
          )}
        </section>
        <section aria-labelledby="consistency-h" className={CARD}>
          <h2 id="consistency-h" className="text-section font-medium">
            Consistency issues
          </h2>
          {report.consistency_issues.length ? (
            <ul className="mt-2 list-disc space-y-1 pl-5 text-body">
              {report.consistency_issues.map((c) => (
                <li key={c}>{c}</li>
              ))}
            </ul>
          ) : (
            <p className="mt-1 text-body">No consistency issues were found.</p>
          )}
        </section>
      </div>
    </div>
  );
}
