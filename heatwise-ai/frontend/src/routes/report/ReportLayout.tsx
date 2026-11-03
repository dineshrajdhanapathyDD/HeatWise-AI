import { useCallback } from "react";
import { NavLink, Outlet, useParams } from "react-router-dom";

import { api } from "../../api/client";
import { useLoad } from "../../api/useLoad";
import { BlockError } from "../../components/BlockError";
import { Disclaimer } from "../../components/Disclaimer";
import { MissingInfo } from "../../components/MissingInfo";
import { RiskLabel, StatusLabel } from "../../components/Pill";
import { formatDateTime, placeName } from "../../lib/format";
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
      <div className="h-8 w-72 max-w-full rounded-chip bg-raised" />
      <div className="mt-2 h-4 w-96 max-w-full rounded-chip bg-raised" />
      <div className="mt-6 h-9 w-80 max-w-full rounded-chip bg-raised" />
      <div className="mt-6 h-[360px] rounded-card bg-raised" />
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
        <h1 className="text-title font-medium">Report</h1>
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

  return (
    <>
      <div className="flex flex-wrap items-start justify-between gap-3">
        <div className="min-w-0">
          <h1 className="text-title font-medium">{title}</h1>
          <p className="mt-1 text-small text-muted">
            {`Report created ${formatDateTime(report.created_at, loc?.timezone)} · ${record.request.forecast_days}-day forecast`}
          </p>
        </div>
        <div className="flex flex-wrap gap-1.5">
          <RiskLabel category={report.risk_category} />
          <StatusLabel status={report.status} />
        </div>
      </div>

      <nav aria-label="Report sections" className="mt-5 overflow-x-auto">
        <ul className="flex min-w-max gap-5 border-b border-line">
          {TABS.map((t) => (
            <li key={t.to}>
              <NavLink
                to={t.to}
                className={({ isActive }) =>
                  `-mb-px inline-flex h-10 items-center border-b-2 text-body ${
                    isActive ? "border-ink font-medium text-ink" : "border-transparent text-muted hover:text-ink"
                  }`
                }
              >
                {t.label}
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
