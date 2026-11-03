import { motion } from "framer-motion";
import { CircleCheck, CircleDashed, CircleX, CloudSun, LoaderCircle, Network, ShieldCheck, Thermometer, ClipboardList } from "lucide-react";

import { formatDuration } from "../lib/format";
import { type AgentState, type PipelineInput, STATE_TEXT, pipelineStages, pipelineVerdict } from "../lib/pipeline";

const ICONS = {
  weather_intelligence: CloudSun,
  community_risk: Thermometer,
  action_planner: ClipboardList,
  safety_verifier: ShieldCheck,
  finalize_report: Network,
} as const;

const STATE_STYLE: Record<AgentState, { ring: string; text: string }> = {
  idle: { ring: "border-line", text: "text-muted" },
  waiting: { ring: "border-amber/50", text: "text-warn-ink" },
  done: { ring: "border-positive/60", text: "text-pos-ink" },
  revised: { ring: "border-amber/60", text: "text-warn-ink" },
  failed: { ring: "border-negative/60", text: "text-neg-ink" },
  skipped: { ring: "border-line", text: "text-muted" },
};

function StateIcon({ state }: { state: AgentState }) {
  const common = { size: 16, strokeWidth: 2, "aria-hidden": true } as const;
  if (state === "done" || state === "revised") return <CircleCheck {...common} className="text-positive" />;
  if (state === "failed") return <CircleX {...common} className="text-negative" />;
  if (state === "waiting") return <LoaderCircle {...common} className="animate-spin text-amber motion-reduce:animate-none" />;
  return <CircleDashed {...common} className="text-muted" />;
}

/**
 * The five agents in execution order. Each stage's state comes from pipelineStages(): idle when nothing
 * runs, "waiting" while the job runs (the API does not report per-agent progress), and the recorded trace
 * once a report exists. The connectors animate only while a job is actually running.
 */
export function AgentPipeline({
  input,
  headingId,
  title = "Agent workflow",
  vertical = false,
}: {
  input: PipelineInput;
  headingId: string;
  title?: string;
  vertical?: boolean;
}) {
  const h = !vertical;
  const stages = pipelineStages(input);
  const running = input.phase === "running";
  const verdict = pipelineVerdict(input);
  const ok = input.phase === "finished" && input.report.status === "complete";

  return (
    <section aria-labelledby={headingId} className="glass rounded-card p-5 sm:p-6">
      <div className="flex flex-wrap items-start justify-between gap-3">
        <div>
          <p className="eyebrow">Strands multi-agent pipeline</p>
          <h2 id={headingId} className="mt-1 text-section font-semibold">
            {title}
          </h2>
        </div>
        <p
          className={`inline-flex items-center gap-1.5 rounded-full px-3 py-1 text-small font-medium ${
            running ? "bg-warn-bg text-warn-ink" : ok ? "bg-pos-bg text-pos-ink" : "bg-neutral-bg text-neutral-ink"
          }`}
        >
          {running ? "Running" : input.phase === "idle" ? "Idle" : ok ? "Verified" : "Finished"}
        </p>
      </div>

      <ol aria-label={`${title} stages`} className={`mt-5 grid gap-4 ${h ? "lg:grid-cols-5 lg:gap-0" : ""}`}>
        {stages.map((s, i) => {
          const Icon = ICONS[s.key];
          const style = STATE_STYLE[s.state];
          return (
            <motion.li
              key={s.key}
              initial={{ opacity: 0, y: 8 }}
              animate={{ opacity: 1, y: 0 }}
              transition={{ delay: i * 0.06, duration: 0.3, ease: "easeOut" }}
              className={`relative flex items-start gap-3 ${h ? "lg:flex-col lg:items-center lg:px-2 lg:text-center" : ""}`}
            >
              {i < stages.length - 1 && (
                <span
                  aria-hidden="true"
                  className={`absolute left-[21px] top-12 h-[calc(100%-36px)] w-0.5 rounded-full ${
                    h ? "lg:left-[calc(50%+30px)] lg:top-[21px] lg:h-0.5 lg:w-[calc(100%-60px)]" : ""
                  } ${running ? "hw-indeterminate bg-raised" : ""}`}
                  style={running ? undefined : { background: s.state === "done" || s.state === "revised" ? "#34d399" : "#34486c" }}
                />
              )}
              <span
                className={`relative z-10 grid h-11 w-11 flex-none place-items-center rounded-full border-2 bg-surface ${style.ring}`}
              >
                <Icon size={20} strokeWidth={1.75} aria-hidden="true" className="text-ink" />
              </span>
              <div className={`min-w-0 ${h ? "lg:mt-3" : ""}`}>
                <p className="text-body font-semibold">{s.name}</p>
                <p className="text-small text-muted">{s.role}</p>
                <p className={`mt-1 inline-flex items-center gap-1 text-small font-medium ${style.text}`}>
                  <StateIcon state={s.state} />
                  {STATE_TEXT[s.state]}
                  {s.runs > 1 && ` (${s.runs} runs)`}
                </p>
                {s.durationMs !== null && <p className="num text-small text-muted">{formatDuration(s.durationMs)}</p>}
              </div>
            </motion.li>
          );
        })}
      </ol>

      {running && <div aria-hidden="true" className="hw-indeterminate mt-5 h-1 rounded-full bg-raised" />}
      <p className="mt-4 text-small text-muted">{verdict}</p>
    </section>
  );
}
