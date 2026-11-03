import { RiskLabel } from "../../components/Pill";
import { DASH, formatNumber, formatTemp } from "../../lib/format";
import { imdIndicationText } from "../../lib/imd";
import { indicatorLabel, riskLabel } from "../../lib/risk";
import { sourceFor } from "../../lib/sources";
import { useReportRecord } from "./reportContext";

const CARD = "rounded-card border border-line bg-surface p-5";
const CONFIDENCE = { high: "High", medium: "Medium", low: "Low" } as const;

/** Screen D: how serious is the heat risk for this community, and why? */
export function RiskView() {
  const { report } = useReportRecord();
  const risk = report.risk;

  if (!risk) {
    return (
      <section aria-labelledby="risk-h" className={CARD}>
        <h2 id="risk-h" className="text-section font-medium">
          Community risk
        </h2>
        <p className="mt-1 text-body">Community risk was not assessed for this report.</p>
      </section>
    );
  }

  const imd = imdIndicationText(risk.imd_indication);

  return (
    <div className="space-y-6">
      <section aria-labelledby="risk-h" className={CARD}>
        <h2 id="risk-h" className="text-section font-medium">
          Community risk
        </h2>
        <div className="mt-3 flex flex-wrap items-center gap-3">
          <p className="text-kpi font-medium">{riskLabel(risk.category)}</p>
          <RiskLabel category={risk.category} prefix="Risk category: " />
        </div>
        <p className="mt-2 text-body">
          {`This category is set by deterministic rules (${risk.rules_version}), not by an AI model.`}
        </p>
        <dl className="mt-5 grid grid-cols-2 gap-4 sm:grid-cols-4">
          <div>
            <dt className="text-small text-muted">Hazard score</dt>
            <dd className="num mt-0.5 text-section font-medium">
              {risk.hazard_score === null ? DASH : `${risk.hazard_score} of 4`}
            </dd>
          </div>
          <div>
            <dt className="text-small text-muted">Heat index</dt>
            <dd className="num mt-0.5 text-section font-medium">{formatTemp(risk.heat_index_c)}</dd>
            <dd className="text-small text-muted">{risk.heat_index_band ? `NWS band: ${risk.heat_index_band}` : "Below the Caution band"}</dd>
          </div>
          <div>
            <dt className="text-small text-muted">IMD indication</dt>
            <dd className="mt-0.5 text-body font-medium">{imd ?? DASH}</dd>
          </div>
          <div>
            <dt className="text-small text-muted">Confidence</dt>
            <dd className="mt-0.5 text-section font-medium">{CONFIDENCE[risk.confidence]}</dd>
          </div>
        </dl>
        <p className="mt-3 text-small text-muted">
          The IMD indication is for one forecast point, not an official declaration.
        </p>
      </section>

      <div className="grid gap-6 md:grid-cols-2">
        <section aria-labelledby="factors-h" className={CARD}>
          <h2 id="factors-h" className="text-section font-medium">
            Contributing factors
          </h2>
          {risk.contributing_factors.length ? (
            <ul className="mt-3 space-y-3 text-body">
              {risk.contributing_factors.map((f) => {
                const src = f.source_id ? sourceFor(f.source_id) : null;
                return (
                  <li key={f.code}>
                    <p>
                      <span className="num font-medium">{formatNumber(f.value, f.unit)}</span> {f.description}
                    </p>
                    {src && (
                      <a href={src.url} target="_blank" rel="noreferrer" className="text-small text-muted underline">
                        {src.title}
                      </a>
                    )}
                  </li>
                );
              })}
            </ul>
          ) : (
            <p className="mt-1 text-body">No contributing factors were recorded.</p>
          )}
        </section>

        <section aria-labelledby="vuln-h" className={CARD}>
          <h2 id="vuln-h" className="text-section font-medium">
            Community vulnerability
          </h2>
          {risk.vulnerability_indicators.length ? (
            <ul className="mt-3 flex flex-wrap gap-1.5">
              {risk.vulnerability_indicators.map((v) => (
                <li key={v} className="rounded-chip bg-neutral-bg px-2 py-0.5 text-small text-neutral-ink">
                  {indicatorLabel(v)}
                </li>
              ))}
            </ul>
          ) : (
            <p className="mt-1 text-body">No vulnerability indicators were given.</p>
          )}
          <p className="mt-3 text-body">
            {risk.heuristic_adjustment_applied
              ? "These indicators raised the category one step (a project heuristic, not an official standard)."
              : "These indicators did not change the category."}
          </p>
          <h3 className="mt-5 text-body font-medium">Missing data</h3>
          {risk.missing_data.length ? (
            <ul className="mt-1 list-disc space-y-1 pl-5 text-body">
              {risk.missing_data.map((m) => (
                <li key={m}>{m}</li>
              ))}
            </ul>
          ) : (
            <p className="mt-1 text-body">None.</p>
          )}
        </section>
      </div>

      <section aria-labelledby="explain-h" className={CARD}>
        <h2 id="explain-h" className="text-section font-medium">
          Explanation
        </h2>
        <p className="mt-1 text-body">{risk.explanation ?? "No explanation was written."}</p>
        {risk.explanation_source && (
          <p className="mt-2 text-small text-muted">
            {risk.explanation_source === "model"
              ? "Written by the risk agent and checked against the rule output."
              : "Written by the rules, because no model explanation passed the checks."}
          </p>
        )}
      </section>
    </div>
  );
}
