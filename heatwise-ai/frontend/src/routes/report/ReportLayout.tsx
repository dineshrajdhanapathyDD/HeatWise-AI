import { motion } from "framer-motion";
import { useCallback } from "react";
import { NavLink, Outlet, useParams } from "react-router-dom";

import { api } from "../../api/client";
import { useLoad } from "../../api/useLoad";
import { BlockError } from "../../components/BlockError";
import { Disclaimer } from "../../components/Disclaimer";
import { MissingInfo } from "../../components/MissingInfo";
import { RiskLabel, StatusLabel } from "../../components/Pill";
import { formatDateTime, formatTemp, placeName } from "../../lib/format";
import { riskHue } from "../../lib/riskScale";
import type { ReportOutlet } from "./reportContext";

const TABS = [
  { to: "climate", label: "Climate" },
  { to: "risk", label: "Risk" },
  { to: "plan", label: "Plan" },
  { to: "activity", label: "Agent activity" },
] as const;

function Skeleton() {
  return (
    <div aria-hidden="true">
      <div className="skeleton h-[132px] w-full !rounded-card" />
      <div className="skeleton mt-5 h-11 w-96 max-w-full" />
      <div className="skeleton mt-6 h-[360px] !rounded-card" />
    </div>
  );
}

/** Loads one stored report and frames screens C-F: title row, tabs, missing information, disclaimer and notices. */
export function ReportLayout() {
  const { reportId = "" } = useParams();
  const load = useCallback((signal: AbortSignal) => api.report(reportId, signal), [reportId]);
  const { data: record, error, loading, retry } = useLoad(`report:${reportId}`, load);

  if (loading) {
    return (
      <>
        <p role="status" className="sr-only">
          Loading the report
        </p>
        <Skeleton />
      </>
    );
  }
  if (error) {
    return (
      <>
        <h1 className="text-title font-semibold">Report</h1>
        <div className="mt-6">
          <BlockError what="this report" error={error} onRetry={retry} />
        </div>
      </>
    );
  }
  if (!record) return null;

  const report = record.report;
  const loc = report.location;
  const title = loc ? placeName([loc.name, loc.admin1, loc.country]) : report.query;
  const outlet: ReportOutlet = { record };

  const maxima = (report.forecast?.days ?? []).map((d) => d.temperature_max_c).filter((v): v is number => v !== null);
  const quick = [
    { label: "Temperature", value: formatTemp(report.current_conditions?.temperature_c) },
    { label: "Heat index", value: formatTemp(report.risk?.heat_index_c) },
    { label: "Highest forecast max", value: formatTemp(maxima.length ? Math.max(...maxima) : null) },
  ];

  return (
    <>
      <div className="glass-strong relative overflow-hidden rounded-card p-5 sm:p-6">
        <span aria-hidden="true" className="absolute inset-x-0 top-0 h-1" style={{ background: riskHue(report.risk_category) }} />
        <div className="flex flex-wrap items-start justify-between gap-4">
          <div className="min-w-0">
            <p className="eyebrow">Preparedness report</p>
            <h1 className="mt-1 text-title font-semibold">{title}</h1>
            <p className="mt-1 text-small text-muted">
              {`Report created ${formatDateTime(report.created_at, loc?.timezone)} · ${record.request.forecast_days}-day forecast`}
            </p>
            <div className="mt-3 flex flex-wrap gap-1.5">
              <RiskLabel category={report.risk_category} />
              <StatusLabel status={report.status} />
            </div>
          </div>
          <dl className="grid grid-cols-3 gap-2 sm:gap-3">
            {quick.map((q) => (
              <div key={q.label} className="rounded-control border border-line bg-raised/50 px-3 py-2">
                <dt className="text-small text-muted">{q.label}</dt>
                <dd className="num mt-0.5 text-section font-semibold">{q.value}</dd>
              </div>
            ))}
          </dl>
        </div>
      </div>

      <nav aria-label="Report sections" className="mt-5 overflow-x-auto">
        <ul className="glass inline-flex min-w-max gap-1 rounded-control p-1">
          {TABS.map((t) => (
            <li key={t.to}>
              <NavLink
                to={t.to}
                className={({ isActive }) =>
                  `relative inline-flex h-9 items-center rounded-[8px] px-4 text-body font-medium transition-colors ${
                    isActive ? "text-surface" : "text-muted hover:text-ink"
                  }`
                }
              >
                {({ isActive }) => (
                  <>
                    {isActive && (
                      <motion.span
                        layoutId="report-tab"
                        aria-hidden="true"
                        className="absolute inset-0 rounded-[8px] bg-amber"
                        transition={{ type: "spring", stiffness: 420, damping: 34 }}
                      />
                    )}
                    <span className="relative">{t.label}</span>
                  </>
                )}
              </NavLink>
            </li>
          ))}
        </ul>
      </nav>

      <div className="mt-6 space-y-6">
        {report.status === "incomplete" && <MissingInfo items={report.missing_information} />}
        <Outlet context={outlet} />
        <Disclaimer notices={report.notices} />
      </div>
    </>
  );
}
