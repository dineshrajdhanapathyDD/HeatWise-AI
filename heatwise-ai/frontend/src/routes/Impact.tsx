import { Link } from "react-router-dom";

import { api } from "../api/client";
import type { EvaluationMode, EvaluationResults, EvaluationRun, MetricsView } from "../api/types";
import { useLoad } from "../api/useLoad";
import { BlockError } from "../components/BlockError";
import { MODE_LABELS, formatDate, metricName, metricValue } from "../lib/evaluation";
import { DASH, formatDuration, formatPct } from "../lib/format";

const CARD = "rounded-card border border-line bg-surface p-5";

export const OUTCOME_STATEMENT =
  "These are counts of assessments stored by this HeatWise instance. HeatWise does not measure or claim real-world health outcomes.";
export const LANGUAGE_DEFINITION =
  "English is the only supported language; other requests get English with a notice.";
export const NO_RESULTS_FILE = "No evaluation results file is available.";

interface Kpi {
  label: string;
  value: string;
  caption: string;
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
    },
    {
      label: "Plans generated",
      value: String(m.plans_generated),
      caption: m.plans_generated ? "Reports that include a preparedness plan" : "No plans are stored yet",
    },
    {
      label: "Recommendations verified",
      value: formatPct(pct, 1),
      caption: pct === null ? "No plan items are stored yet" : "Plan items that passed the safety checks, all plans",
    },
    {
      label: "Average completion time",
      value: formatDuration(m.mean_duration_ms),
      caption: m.mean_duration_ms === null ? "No timed assessments yet" : "From request to stored report",
    },
    {
      label: "Checklist items completed",
      value: String(checklist.items_completed),
      caption: `Of ${checklist.items_available} shown items, on ${checklist.reports_with_progress} ${
        checklist.reports_with_progress === 1 ? "report" : "reports"
      }`,
    },
    {
      label: "Plans in the requested language",
      value: String(lang.served_in_requested_language),
      caption: `${lang.english_fallback} in English with a notice. ${LANGUAGE_DEFINITION}`,
    },
  ];
}

function Counts() {
  const metrics = useLoad("metrics", api.metrics);
  const empty = metrics.data !== null && metrics.data.total === 0;
  return (
    <section aria-labelledby="counts-h" className={CARD}>
      <h2 id="counts-h" className="text-section font-medium">
        Stored assessments
      </h2>
      {metrics.error ? (
        <div className="mt-3">
          <BlockError what="the counts" error={metrics.error} onRetry={metrics.retry} />
        </div>
      ) : (
        <>
          {empty && (
            <p className="mt-1 text-body">
              No assessments are stored yet.{" "}
              <Link to="/assess" className="underline">
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
          <dl className="mt-4 grid gap-px overflow-hidden rounded-card border border-line bg-line sm:grid-cols-2 lg:grid-cols-3">
            {(metrics.data ? kpis(metrics.data) : PLACEHOLDER).map((k) => (
              <div key={k.label} className="bg-surface p-4">
                <dt className="text-body text-muted">{k.label}</dt>
                <dd className="mt-1">
                  {metrics.data ? (
                    k.value === DASH ? (
                      // Missing is a small grey dash, never a dash at value size (app-screens §11).
                      <span className="flex h-9 items-center text-section text-muted">{DASH}</span>
                    ) : (
                      <span className="num block text-kpi">{k.value}</span>
                    )
                  ) : (
                    <span aria-hidden="true" className="block h-9 w-20 rounded-chip bg-raised" />
                  )}
                  <span className="mt-1 block text-small text-muted">{metrics.data ? k.caption : "\u00a0"}</span>
                </dd>
              </div>
            ))}
          </dl>
        </>
      )}
    </section>
  );
}

const PLACEHOLDER: Kpi[] = [
  "Assessments completed",
  "Plans generated",
  "Recommendations verified",
  "Average completion time",
  "Checklist items completed",
  "Plans in the requested language",
].map((label) => ({ label, value: "", caption: "" }));

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
      <ul className="mt-2 space-y-1 text-body">
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
                <th scope="col" className="py-2 pr-4 font-normal">Metric</th>
                {runs.map(([mode, run]) => (
                  <th key={mode} scope="col" className="py-2 pr-4 text-right font-normal last:pr-0">
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
    <section aria-labelledby="eval-h" className={CARD}>
      <h2 id="eval-h" className="text-section font-medium">
        Synthetic evaluation results
      </h2>
      <p className="mt-1 text-body text-muted">
        Measured on synthetic test scenarios by the evaluation suite, not on stored assessments or real communities.
      </p>
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
          <div aria-hidden="true" className="mt-4 space-y-2">
            {[0, 1, 2, 3].map((i) => (
              <div key={i} className="h-5 rounded-chip bg-raised" />
            ))}
          </div>
        </>
      )}
    </section>
  );
}

/** Screen H: what has this HeatWise instance done, and how did it score on synthetic tests? */
export function Impact() {
  return (
    <>
      <h1 className="text-title font-medium">Impact</h1>
      <p className="mt-1 max-w-[72ch] text-body text-muted">{OUTCOME_STATEMENT}</p>
      <div className="mt-6 space-y-6">
        <Counts />
        <Evaluation />
      </div>
    </>
  );
}
