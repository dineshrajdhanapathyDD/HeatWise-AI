import { motion } from "framer-motion";
import { Building2, CircleCheck, Clock, FileText, ListChecks, Languages } from "lucide-react";
import { useCallback } from "react";
import { Link } from "react-router-dom";
import {
  Bar,
  BarChart,
  CartesianGrid,
  Cell,
  ResponsiveContainer,
  Scatter,
  ScatterChart,
  Tooltip,
  XAxis,
  YAxis,
  ZAxis,
} from "recharts";

import { api } from "../api/client";
import type { EvaluationMode, EvaluationResults, EvaluationRun, HistoryItem, MetricsView } from "../api/types";
import { useLoad } from "../api/useLoad";
import { BlockError } from "../components/BlockError";
import { DataTag, SectionHeading, SkeletonLines } from "../components/ui";
import { MODE_LABELS, formatDate, metricName, metricValue } from "../lib/evaluation";
import { DASH, formatDateTime, formatDuration, formatPct } from "../lib/format";
import { communities, indicatorCounts, riskTrend } from "../lib/impact";
import { PALETTE, TICK, TOOLTIP_STYLE } from "../lib/palette";
import { indicatorLabel, riskLabel, statusLabel } from "../lib/risk";
import { RISK_ORDER, riskHue } from "../lib/riskScale";

const CARD = "glass rounded-card p-5 sm:p-6";
const HISTORY_LIMIT = 100;

export const OUTCOME_STATEMENT =
  "These are counts of assessments stored by this HeatWise instance. HeatWise does not measure or claim real-world health outcomes.";
export const LANGUAGE_DEFINITION =
  "English is the only supported language; other requests get English with a notice.";
export const NO_RESULTS_FILE = "No evaluation results file is available.";

interface Kpi {
  label: string;
  value: string;
  caption: string;
  icon: typeof FileText;
}

function kpis(m: MetricsView): Kpi[] {
  const checklist = m.checklist ?? { items_completed: 0, items_available: 0, reports_with_progress: 0 };
  const lang = m.localized_guidance ?? { served_in_requested_language: 0, english_fallback: 0, by_requested_language: {} };
  const pct = m.pct_recommendations_verified ?? null;
  return [
    {
      label: "Assessments completed",
      value: String(m.assessments_completed ?? 0),
      caption: `Status complete, of ${m.total} stored`,
      icon: CircleCheck,
    },
    {
      label: "Plans generated",
      value: String(m.plans_generated),
      caption: m.plans_generated ? "Reports that include a preparedness plan" : "No plans are stored yet",
      icon: FileText,
    },
    {
      label: "Recommendations verified",
      value: formatPct(pct, 1),
      caption: pct === null ? "No plan items are stored yet" : "Plan items that passed the safety checks, all plans",
      icon: ListChecks,
    },
    {
      label: "Average completion time",
      value: formatDuration(m.mean_duration_ms),
      caption: m.mean_duration_ms === null ? "No timed assessments yet" : "From request to stored report",
      icon: Clock,
    },
    {
      label: "Checklist items completed",
      value: String(checklist.items_completed),
      caption: `Of ${checklist.items_available} shown items, on ${checklist.reports_with_progress} ${
        checklist.reports_with_progress === 1 ? "report" : "reports"
      }`,
      icon: ListChecks,
    },
    {
      label: "Plans in the requested language",
      value: String(lang.served_in_requested_language),
      caption: `${lang.english_fallback} in English with a notice. ${LANGUAGE_DEFINITION}`,
      icon: Languages,
    },
  ];
}

const PLACEHOLDER: Kpi[] = [
  "Assessments completed",
  "Plans generated",
  "Recommendations verified",
  "Average completion time",
  "Checklist items completed",
  "Plans in the requested language",
].map((label) => ({ label, value: "", caption: "", icon: FileText }));

function Counts({ metrics }: { metrics: ReturnType<typeof useLoad<MetricsView>> }) {
  const empty = metrics.data !== null && metrics.data.total === 0;
  return (
    <section aria-labelledby="counts-h" className={CARD}>
      <SectionHeading id="counts-h" title="Stored assessments" actions={<DataTag>Measured from stored reports</DataTag>} />
      {metrics.error ? (
        <div className="mt-3">
          <BlockError what="the counts" error={metrics.error} onRetry={metrics.retry} />
        </div>
      ) : (
        <>
          {empty && (
            <p className="mt-2 text-body text-muted">
              No assessments are stored yet.{" "}
              <Link to="/assess" className="text-amber underline">
                Start an assessment
              </Link>{" "}
              to see counts here.
            </p>
          )}
          {metrics.loading && (
            <p role="status" className="sr-only">
              Loading the counts
            </p>
          )}
          <dl className="mt-5 grid gap-3 sm:grid-cols-2 xl:grid-cols-3">
            {(metrics.data ? kpis(metrics.data) : PLACEHOLDER).map((k, i) => {
              const Icon = k.icon;
              return (
                <motion.div
                  key={k.label}
                  initial={{ opacity: 0, y: 8 }}
                  animate={{ opacity: 1, y: 0 }}
                  transition={{ delay: i * 0.04, duration: 0.3 }}
                  className="lift rounded-control border border-line bg-raised/50 p-4"
                >
                  <dt className="flex items-center justify-between gap-2 text-body text-muted">
                    {k.label}
                    <Icon size={16} aria-hidden="true" className="flex-none" />
                  </dt>
                  <dd className="mt-2">
                    {metrics.data ? (
                      k.value === DASH ? (
                        <span className="flex h-9 items-center text-section text-muted">{DASH}</span>
                      ) : (
                        <span className="num block text-kpi font-semibold">{k.value}</span>
                      )
                    ) : (
                      <span aria-hidden="true" className="skeleton block h-9 w-20" />
                    )}
                    <span className="mt-1 block text-small text-muted">{metrics.data ? k.caption : "\u00a0"}</span>
                  </dd>
                </motion.div>
              );
            })}
          </dl>
        </>
      )}
    </section>
  );
}

/* ---------- Charts from stored data ---------- */

function RiskDistribution({ metrics }: { metrics: MetricsView }) {
  const data = [...RISK_ORDER, "unknown"].map((c) => ({ category: c, label: riskLabel(c), count: metrics.by_risk_category[c] ?? 0 }));
  return (
    <section aria-labelledby="risk-dist-h" className={CARD}>
      <SectionHeading
        id="risk-dist-h"
        title="Risk categories identified"
        description="How many stored reports ended in each category set by the rules."
        actions={<DataTag>Measured</DataTag>}
      />
      <div aria-hidden="true" className="mt-4 h-[220px]">
        <ResponsiveContainer width="100%" height="100%">
          <BarChart data={data} margin={{ top: 8, right: 8, bottom: 0, left: 0 }}>
            <CartesianGrid vertical={false} stroke={PALETTE.grid} />
            <XAxis dataKey="label" tick={TICK} tickLine={false} axisLine={{ stroke: PALETTE.axis }} interval={0} />
            <YAxis allowDecimals={false} tick={TICK} tickLine={false} axisLine={false} />
            <Tooltip contentStyle={TOOLTIP_STYLE} cursor={{ fill: "rgba(148,164,195,0.08)" }} />
            <Bar dataKey="count" name="Reports" radius={[6, 6, 0, 0]} animationDuration={800}>
              {data.map((d) => (
                <Cell key={d.category} fill={riskHue(d.category)} />
              ))}
            </Bar>
          </BarChart>
        </ResponsiveContainer>
      </div>
      <div className="sr-only">
        <table>
          <caption>Stored reports by risk category</caption>
          <tbody>
            {data.map((d) => (
              <tr key={d.category}>
                <th scope="row">{d.label}</th>
                <td className="text-right">{d.count}</td>
              </tr>
            ))}
          </tbody>
        </table>
      </div>
    </section>
  );
}

function Outcomes({ metrics }: { metrics: MetricsView }) {
  const total = Math.max(1, metrics.total);
  const statuses = (["complete", "needs_human_review", "incomplete"] as const).map((s) => ({
    key: s,
    label: statusLabel(s),
    count: metrics.by_status[s] ?? 0,
    color: s === "complete" ? "#34d399" : s === "needs_human_review" ? "#fbbf24" : "#64748b",
  }));
  const v = metrics.verification;
  return (
    <section aria-labelledby="outcomes-h" className={CARD}>
      <SectionHeading
        id="outcomes-h"
        title="Assessment outcomes"
        description="Report status and safety verification across stored reports."
        actions={<DataTag>Measured</DataTag>}
      />
      <div aria-hidden="true" className="mt-5 flex h-3 overflow-hidden rounded-full bg-raised">
        {statuses.map((s) => (
          <motion.span
            key={s.key}
            initial={{ width: 0 }}
            animate={{ width: `${(s.count / total) * 100}%` }}
            transition={{ duration: 0.8, ease: "easeOut" }}
            style={{ background: s.color }}
          />
        ))}
      </div>
      <dl className="mt-4 grid grid-cols-3 gap-3">
        {statuses.map((s) => (
          <div key={s.key}>
            <dt className="flex items-center gap-1.5 text-small text-muted">
              <span aria-hidden="true" className="h-2 w-2 rounded-full" style={{ background: s.color }} />
              {s.label}
            </dt>
            <dd className="num text-section font-semibold">{s.count}</dd>
          </div>
        ))}
      </dl>
      <dl className="mt-5 grid grid-cols-3 gap-3 border-t border-line pt-4">
        {[
          { label: "Verification passed", value: v.passed },
          { label: "Verification failed", value: v.failed },
          { label: "Not run", value: v.not_run },
        ].map((x) => (
          <div key={x.label}>
            <dt className="text-small text-muted">{x.label}</dt>
            <dd className="num text-section font-semibold">{x.value}</dd>
          </div>
        ))}
      </dl>
    </section>
  );
}

function RiskTrend({ items }: { items: HistoryItem[] }) {
  const points = riskTrend(items);
  // Within two days, dates alone repeat ("3 Nov, 3 Nov"), so show the time as well.
  const span = points.length ? points[points.length - 1]!.t - points[0]!.t : 0;
  const tickFormat = new Intl.DateTimeFormat(
    "en-GB",
    span < 2 * 864e5 ? { day: "numeric", month: "short", hour: "2-digit", minute: "2-digit", hourCycle: "h23" } : { day: "numeric", month: "short" },
  );
  return (
    <section aria-labelledby="trend-h" className={`${CARD} xl:col-span-2`}>
      <SectionHeading
        id="trend-h"
        title="Historical risk trend"
        description="Each dot is a stored report, placed at its risk category and assessment time."
        actions={<DataTag>Measured</DataTag>}
      />
      {points.length ? (
        <>
          <div aria-hidden="true" className="mt-4 h-[240px]">
            <ResponsiveContainer width="100%" height="100%">
              <ScatterChart margin={{ top: 8, right: 16, bottom: 0, left: 8 }}>
                <CartesianGrid stroke={PALETTE.grid} />
                <XAxis
                  dataKey="t"
                  type="number"
                  domain={["dataMin", "dataMax"]}
                  tick={TICK}
                  tickLine={false}
                  axisLine={{ stroke: PALETTE.axis }}
                  tickFormatter={(t: number) => tickFormat.format(t)}
                  tickCount={5}
                />
                <YAxis
                  dataKey="level"
                  type="number"
                  domain={[0, 4]}
                  ticks={[0, 1, 2, 3, 4]}
                  tick={TICK}
                  tickLine={false}
                  axisLine={false}
                  width={72}
                  tickFormatter={(l: number) => riskLabel(RISK_ORDER[l])}
                />
                <ZAxis range={[90, 90]} />
                <Tooltip
                  contentStyle={TOOLTIP_STYLE}
                  cursor={{ stroke: PALETTE.axis }}
                  formatter={(_v, _n, p) => [riskLabel((p.payload as { category: string }).category), (p.payload as { place: string }).place]}
                  labelFormatter={() => ""}
                />
                <Scatter data={points} animationDuration={800}>
                  {points.map((p) => (
                    <Cell key={`${p.t}-${p.place}`} fill={riskHue(p.category)} />
                  ))}
                </Scatter>
              </ScatterChart>
            </ResponsiveContainer>
          </div>
          <div className="sr-only">
          <table>
            <caption>Risk category of each stored report over time</caption>
            <thead>
              <tr>
                <th scope="col">Assessed</th>
                <th scope="col">Place</th>
                <th scope="col">Risk</th>
              </tr>
            </thead>
            <tbody>
              {points.map((p) => (
                <tr key={`${p.t}-${p.place}`}>
                  <td>{formatDateTime(p.date)}</td>
                  <td>{p.place}</td>
                  <td>{riskLabel(p.category)}</td>
                </tr>
              ))}
            </tbody>
          </table>
          </div>
        </>
      ) : (
        <p className="mt-3 text-body text-muted">The trend appears once reports with a risk category are stored.</p>
      )}
    </section>
  );
}

function Groups({ items }: { items: HistoryItem[] }) {
  const counts = indicatorCounts(items);
  const max = Math.max(1, ...counts.map((c) => c.count));
  return (
    <section aria-labelledby="groups-h" className={CARD}>
      <SectionHeading
        id="groups-h"
        title="Vulnerable groups considered"
        description="How often each group or condition was reported across stored reports."
        actions={<DataTag>Measured</DataTag>}
      />
      {counts.length ? (
        <ul className="mt-4 space-y-3">
          {counts.map((c) => (
            <li key={c.code}>
              <div className="flex items-center justify-between text-body">
                <span>{indicatorLabel(c.code)}</span>
                <span className="num font-semibold">{c.count}</span>
              </div>
              <div aria-hidden="true" className="mt-1 h-2 rounded-full bg-raised">
                <motion.div
                  initial={{ width: 0 }}
                  whileInView={{ width: `${(c.count / max) * 100}%` }}
                  viewport={{ once: true }}
                  transition={{ duration: 0.7, ease: "easeOut" }}
                  className="h-2 rounded-full bg-cyan"
                />
              </div>
            </li>
          ))}
        </ul>
      ) : (
        <p className="mt-3 text-body text-muted">No vulnerable groups have been reported in stored reports.</p>
      )}
    </section>
  );
}

function Communities({ items, total }: { items: HistoryItem[]; total: number }) {
  const list = communities(items);
  return (
    <section aria-labelledby="communities-h" className={CARD}>
      <SectionHeading
        id="communities-h"
        title="Communities assessed"
        description={
          total > items.length
            ? `Distinct places in the latest ${items.length} of ${total} stored reports.`
            : "Distinct places among stored reports."
        }
        actions={<DataTag>Measured</DataTag>}
      />
      <p className="num mt-4 text-kpi font-semibold">{list.length}</p>
      {list.length ? (
        <ul className="mt-3 divide-y divide-rule">
          {list.slice(0, 6).map((c) => (
            <li key={c.name} className="flex items-center justify-between gap-3 py-2 text-body">
              <span className="flex min-w-0 items-center gap-2">
                <Building2 size={14} aria-hidden="true" className="flex-none text-muted" />
                <span className="truncate">{c.name}</span>
              </span>
              <span className="num text-small text-muted">{`${c.count} ${c.count === 1 ? "report" : "reports"}`}</span>
            </li>
          ))}
        </ul>
      ) : (
        <p className="mt-1 text-body text-muted">No places have been assessed yet.</p>
      )}
    </section>
  );
}

/* ---------- Synthetic evaluation ---------- */

function runLine(mode: EvaluationMode, run: EvaluationRun | null): string {
  if (!run) return `${MODE_LABELS[mode]}: not run.`;
  if (run.status === "failed") return `${MODE_LABELS[mode]} run on ${formatDate(run.started_at)} failed: ${run.error ?? "no error text"}.`;
  return `${MODE_LABELS[mode]} run on ${formatDate(run.started_at)}, ${run.scenario_ids.length} scenarios: ${run.mode_label}.`;
}

function cellMode(mode: EvaluationMode, run: EvaluationRun | null): string {
  return run ? `${MODE_LABELS[mode]}, ${formatDate(run.started_at)}` : MODE_LABELS[mode];
}

function EvaluationTable({ results }: { results: EvaluationResults }) {
  const { offline, live } = results.runs;
  const runs: [EvaluationMode, EvaluationRun | null][] = [
    ["offline", offline],
    ["live", live],
  ];
  const keys = [...new Set([...Object.keys(offline?.metrics ?? {}), ...Object.keys(live?.metrics ?? {})])];
  return (
    <>
      <ul className="mt-3 space-y-1 text-body">
        {runs.map(([mode, run]) => (
          <li key={mode}>{runLine(mode, run)}</li>
        ))}
      </ul>
      {keys.length === 0 ? (
        <p className="mt-3 text-body">The results file holds no measured runs yet.</p>
      ) : (
        <>
          <table className="mt-4 hidden w-full text-body md:table">
            <caption className="sr-only">Synthetic evaluation metrics by mode</caption>
            <thead>
              <tr className="border-b border-line text-left text-small text-muted">
                <th scope="col" className="py-2 pr-4 font-medium">Metric</th>
                {runs.map(([mode, run]) => (
                  <th key={mode} scope="col" className="py-2 pr-4 text-right font-medium last:pr-0">
                    {cellMode(mode, run)}
                  </th>
                ))}
              </tr>
            </thead>
            <tbody>
              {keys.map((key) => (
                <tr key={key} className="border-b border-rule align-top last:border-0">
                  <th scope="row" className="py-2.5 pr-4 text-left font-normal">
                    {metricName(key)}
                  </th>
                  {runs.map(([mode, run]) => (
                    <td key={mode} className="num py-2.5 pr-4 text-right last:pr-0">
                      {metricValue(run?.metrics[key])}
                      <span className="block text-small text-muted">{MODE_LABELS[mode]}</span>
                    </td>
                  ))}
                </tr>
              ))}
            </tbody>
          </table>
          <ul aria-label="Synthetic evaluation metrics" className="mt-3 divide-y divide-rule md:hidden">
            {keys.map((key) => (
              <li key={key} className="py-2.5">
                <p className="text-body font-medium">{metricName(key)}</p>
                {runs.map(([mode, run]) => (
                  <p key={mode} className="num mt-0.5 text-body">
                    <span className="text-muted">{`${cellMode(mode, run)}: `}</span>
                    {metricValue(run?.metrics[key])}
                  </p>
                ))}
              </li>
            ))}
          </ul>
        </>
      )}
      <p className="mt-4 text-small text-muted">
        The unsafe-item and safe-control rows measure the deterministic safety checks run on a plan, in both modes.
        They test the guardrail code, not whether the model refuses unsafe content.
      </p>
      <p className="mt-2 text-small text-muted">{results.label}</p>
    </>
  );
}

function Evaluation() {
  const evaluation = useLoad("evaluation", api.evaluation);
  return (
    <section aria-labelledby="eval-h" className={`${CARD} border-sky/20`}>
      <SectionHeading
        id="eval-h"
        title="Synthetic evaluation results"
        description="Measured on synthetic test scenarios by the evaluation suite, not on stored assessments or real communities."
        actions={<DataTag tone="synthetic">Synthetic test results</DataTag>}
      />
      {evaluation.error ? (
        evaluation.error.status === 404 ? (
          <p className="mt-3 text-body">{NO_RESULTS_FILE}</p>
        ) : (
          <div className="mt-3">
            <BlockError what="the evaluation results" error={evaluation.error} onRetry={evaluation.retry} />
          </div>
        )
      ) : evaluation.data ? (
        <EvaluationTable results={evaluation.data} />
      ) : (
        <>
          <p role="status" className="sr-only">
            Loading the evaluation results
          </p>
          <SkeletonLines lines={4} className="mt-4" />
        </>
      )}
    </section>
  );
}

/** Screen H: what has this HeatWise instance done, and how did it score on synthetic tests? */
export function Impact() {
  const metrics = useLoad("metrics", api.metrics);
  const loadHistory = useCallback((signal: AbortSignal) => api.history(HISTORY_LIMIT, 0, signal), []);
  const history = useLoad("impact-history", loadHistory);
  const items = history.data?.items ?? [];

  return (
    <div className="space-y-6">
      <div>
        <p className="eyebrow">Impact dashboard</p>
        <h1 className="mt-1 text-title font-semibold">Impact</h1>
        <p className="mt-1 max-w-[72ch] text-body text-muted">{OUTCOME_STATEMENT}</p>
        <div className="mt-3 flex flex-wrap items-center gap-2 text-small text-muted">
          <DataTag>Measured from stored reports</DataTag>
          <DataTag tone="synthetic">Synthetic test results</DataTag>
          <span>HeatWise reports no estimated or potential impact figures.</span>
        </div>
      </div>

      <Counts metrics={metrics} />

      {metrics.data && metrics.data.total > 0 && (
        <div className="grid gap-6 xl:grid-cols-2 xl:items-start">
          <RiskDistribution metrics={metrics.data} />
          <Outcomes metrics={metrics.data} />
        </div>
      )}

      {history.error ? (
        <BlockError what="the stored reports for the trends" error={history.error} onRetry={history.retry} />
      ) : history.loading ? (
        <div className={CARD}>
          <p role="status" className="sr-only">
            Loading the stored reports for the trends
          </p>
          <SkeletonLines lines={4} />
        </div>
      ) : items.length > 0 ? (
        <div className="grid gap-6 xl:grid-cols-2 xl:items-start">
          <RiskTrend items={items} />
          <Groups items={items} />
          <Communities items={items} total={history.data?.total ?? items.length} />
        </div>
      ) : (
        <p className={`${CARD} text-body text-muted`}>Trends and community counts appear once reports are stored.</p>
      )}

      <Evaluation />
    </div>
  );
}
