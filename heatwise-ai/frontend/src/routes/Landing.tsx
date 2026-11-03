import { useCallback } from "react";
import { Link } from "react-router-dom";

import { api } from "../api/client";
import { useLoad } from "../api/useLoad";
import { BlockError } from "../components/BlockError";
import { RiskLabel, StatusLabel } from "../components/Pill";
import { formatDateTime, formatTemp, placeName } from "../lib/format";

const AGENTS = [
  {
    name: "Weather Intelligence",
    does: "retrieves current conditions, the forecast and the official-warning status for the place, with their sources.",
  },
  {
    name: "Community Risk",
    does: "sets the risk category with deterministic rules (heat index bands, IMD criteria, the community profile). No AI model decides it.",
  },
  {
    name: "Action Planner",
    does: "builds the preparedness plan for households, outdoor workers and farmers from a catalog of verified guidance.",
  },
  {
    name: "Safety and Verification",
    does: "checks every plan item; a plan that fails gets one revision, and what still fails is withheld for human review.",
  },
  {
    name: "Coordinator",
    does: "runs the four in order and assembles the report, the checklist and the record of what each agent did.",
  },
];

/** Screen A, the app's home: what HeatWise does and what the latest assessment found. */
export function Landing() {
  const loadLatest = useCallback((signal: AbortSignal) => api.history(1, 0, signal), []);
  const latest = useLoad("latest", loadLatest);
  const item = latest.data?.items[0] ?? null;

  return (
    <div className="grid gap-6 lg:grid-cols-[minmax(0,1fr)_400px] lg:grid-rows-[auto_1fr] lg:gap-x-10 lg:gap-y-8">
      <div>
        <h1 className="text-title font-medium">HeatWise AI</h1>
        <p className="mt-1 text-section">From Weather Intelligence to Community Action.</p>
        <p className="mt-4 max-w-[60ch] text-body">
          Heatwaves hurt older people, young children, outdoor workers and farming households first, and local
          coordinators rarely have time to turn a forecast into a plan. HeatWise reads the weather for one community,
          rates the heat risk with published criteria, and prepares a checked action plan you can share.
        </p>
        <Link
          to="/assess"
          className="mt-5 inline-flex h-9 items-center rounded-control bg-primary px-4 text-body font-medium text-surface hover:bg-ink"
        >
          Start an assessment
        </Link>
      </div>

      {/* Second in the DOM so phones and screen readers reach the latest result before the explainer. */}
      <section
        aria-labelledby="latest-report"
        className="self-start rounded-card border border-line bg-surface p-5 lg:col-start-2 lg:row-span-2 lg:row-start-1"
      >
        <h2 id="latest-report" className="text-section font-medium">
          Latest report
        </h2>
        {latest.loading && (
          <div aria-hidden="true" className="mt-3 space-y-2">
            <div className="h-6 w-2/3 rounded-chip bg-raised" />
            <div className="h-5 w-1/2 rounded-chip bg-raised" />
            <div className="h-5 w-1/3 rounded-chip bg-raised" />
          </div>
        )}
        {latest.error && (
          <div className="mt-3">
            <BlockError what="the latest report" error={latest.error} onRetry={latest.retry} />
          </div>
        )}
        {!latest.loading && !latest.error && !item && (
          <p className="mt-2 text-body text-muted">No assessments are stored yet. Start one to see its report here.</p>
        )}
        {item && (
          <div className="mt-2">
            <p className="text-section">{placeName([item.location_name ?? item.query, item.admin1, item.country])}</p>
            <p className="mt-1 text-small text-muted">{formatDateTime(item.created_at)}</p>
            <div className="mt-3 flex flex-wrap gap-1.5">
              <RiskLabel category={item.risk_category} />
              <StatusLabel status={item.status} />
            </div>
            <dl className="mt-3 grid grid-cols-2 gap-3 text-body">
              <div>
                <dt className="text-small text-muted">Highest forecast max</dt>
                <dd className="num">{formatTemp(item.max_forecast_c)}</dd>
              </div>
              <div>
                <dt className="text-small text-muted">Heat index</dt>
                <dd className="num">{formatTemp(item.heat_index_c)}</dd>
              </div>
            </dl>
            <Link to={`/reports/${item.report_id}/climate`} className="mt-4 inline-block text-body font-medium underline">
              Open the report
            </Link>
          </div>
        )}
      </section>

      <section aria-labelledby="how-agents" className="lg:col-start-1 lg:row-start-2">
        <h2 id="how-agents" className="text-section font-medium">
          How the agents work together
        </h2>
        <ol className="mt-3 list-decimal space-y-2 pl-5 text-body">
          {AGENTS.map((a) => (
            <li key={a.name}>
              <span className="font-medium">{a.name}</span> {a.does}
            </li>
          ))}
        </ol>
      </section>
    </div>
  );
}
