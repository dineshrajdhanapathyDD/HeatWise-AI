import { AnimatePresence, motion } from "framer-motion";
import { ArrowRight, Eye, Search, X } from "lucide-react";
import { useCallback, useMemo, useState } from "react";
import { Link } from "react-router-dom";

import { type ApiError, api, toApiError } from "../api/client";
import type { HistoryItem, ReportStatus } from "../api/types";
import { useLoad } from "../api/useLoad";
import { BlockError } from "../components/BlockError";
import { RiskLabel, StatusLabel } from "../components/Pill";
import { formatDateTime, formatDuration, formatTemp, placeName } from "../lib/format";
import { type DateFilter, type HistoryFilters, changesInWords, countsLine, filterHistory } from "../lib/history";
import { indicatorLabel, riskLabel, statusLabel } from "../lib/risk";
import { RISK_ORDER, riskHue } from "../lib/riskScale";

const PAGE = 20;

const DATE_OPTIONS: { value: DateFilter; label: string }[] = [
  { value: "any", label: "Any time" },
  { value: "7d", label: "Last 7 days" },
  { value: "30d", label: "Last 30 days" },
];

function place(item: HistoryItem): string {
  return placeName([item.location_name ?? item.query, item.admin1, item.country]);
}

function indicators(item: HistoryItem): string {
  return item.indicators.length ? item.indicators.map(indicatorLabel).join(", ") : "No indicators given";
}

const EMPTY_FILTERS: HistoryFilters = { query: "", risk: "all", status: "all", date: "any" };

/** Screen G: how have this place's assessments changed? */
export function History() {
  const loadFirst = useCallback((signal: AbortSignal) => api.history(PAGE, 0, signal), []);
  const first = useLoad("history", loadFirst);
  const metrics = useLoad("metrics", api.metrics);
  const [more, setMore] = useState<HistoryItem[]>([]);
  const [loadingMore, setLoadingMore] = useState(false);
  const [moreError, setMoreError] = useState<ApiError | null>(null);
  const [filters, setFilters] = useState<HistoryFilters>(EMPTY_FILTERS);
  const [previewId, setPreviewId] = useState<string | null>(null);

  const items = useMemo(() => [...(first.data?.items ?? []), ...more], [first.data, more]);
  const total = first.data?.total ?? 0;
  const shown = useMemo(() => filterHistory(items, filters), [items, filters]);
  const filtering = JSON.stringify(filters) !== JSON.stringify(EMPTY_FILTERS);
  const preview = shown.find((i) => i.report_id === previewId) ?? null;

  async function loadMore() {
    setLoadingMore(true);
    setMoreError(null);
    try {
      const page = await api.history(PAGE, items.length);
      setMore((m) => [...m, ...page.items]);
    } catch (err) {
      setMoreError(toApiError(err));
    } finally {
      setLoadingMore(false);
    }
  }

  const setFilter = <K extends keyof HistoryFilters>(k: K, v: HistoryFilters[K]) => setFilters((f) => ({ ...f, [k]: v }));
  const emptyStore = !first.loading && items.length === 0;

  const empty = (
    <>
      No assessments are stored yet.{" "}
      <Link to="/assess" className="text-amber underline">
        Start an assessment
      </Link>{" "}
      to see it here.
    </>
  );

  return (
    <div className="space-y-6">
      <div className="flex flex-wrap items-end justify-between gap-3">
        <div>
          <p className="eyebrow">Assessment history</p>
          <h1 className="mt-1 text-title font-semibold">History</h1>
          <p className="mt-1 text-body text-muted">
            {metrics.data ? countsLine(metrics.data) : metrics.error ? "Counts are not available." : "Counting stored reports…"}
          </p>
        </div>
        <Link to="/assess" className="btn-primary">
          New assessment
        </Link>
      </div>

      {metrics.data && metrics.data.total > 0 && (
        <ul aria-label="Reports by risk category" className="flex flex-wrap gap-2">
          {RISK_ORDER.map((c) => (
            <li key={c} className="glass inline-flex items-center gap-2 rounded-full px-3 py-1 text-small">
              <span aria-hidden="true" className="h-2 w-2 rounded-full" style={{ background: riskHue(c) }} />
              {riskLabel(c)}
              <span className="num font-semibold">{metrics.data!.by_risk_category[c] ?? 0}</span>
            </li>
          ))}
        </ul>
      )}

      <section aria-labelledby="filters-h" className="glass rounded-card p-4 sm:p-5">
        <h2 id="filters-h" className="sr-only">
          Search and filter
        </h2>
        <div className="grid gap-3 md:grid-cols-[minmax(0,2fr)_repeat(3,minmax(0,1fr))]">
          <div>
            <label htmlFor="history-search" className="text-small font-medium text-muted">
              Search places
            </label>
            <div className="relative mt-1">
              <Search size={16} aria-hidden="true" className="pointer-events-none absolute left-3 top-1/2 -translate-y-1/2 text-muted" />
              <input
                id="history-search"
                type="search"
                value={filters.query}
                onChange={(e) => setFilter("query", e.target.value)}
                placeholder="Place, district or state"
                className="field pl-9"
              />
            </div>
          </div>
          <div>
            <label htmlFor="history-risk" className="text-small font-medium text-muted">
              Risk level
            </label>
            <select id="history-risk" value={filters.risk} onChange={(e) => setFilter("risk", e.target.value)} className="field mt-1">
              <option value="all">All risk levels</option>
              {[...RISK_ORDER, "unknown"].map((c) => (
                <option key={c} value={c}>
                  {riskLabel(c)}
                </option>
              ))}
            </select>
          </div>
          <div>
            <label htmlFor="history-status" className="text-small font-medium text-muted">
              Status
            </label>
            <select id="history-status" value={filters.status} onChange={(e) => setFilter("status", e.target.value)} className="field mt-1">
              <option value="all">All statuses</option>
              {(["complete", "needs_human_review", "incomplete"] as ReportStatus[]).map((s) => (
                <option key={s} value={s}>
                  {statusLabel(s)}
                </option>
              ))}
            </select>
          </div>
          <div>
            <label htmlFor="history-date" className="text-small font-medium text-muted">
              Assessed
            </label>
            <select
              id="history-date"
              value={filters.date}
              onChange={(e) => setFilter("date", e.target.value as DateFilter)}
              className="field mt-1"
            >
              {DATE_OPTIONS.map((o) => (
                <option key={o.value} value={o.value}>
                  {o.label}
                </option>
              ))}
            </select>
          </div>
        </div>
        <div className="mt-3 flex flex-wrap items-center justify-between gap-2 text-small text-muted">
          <p aria-live="polite">
            {filtering
              ? `${shown.length} of ${items.length} loaded reports match.${items.length < total ? " Load more to search older reports." : ""}`
              : `${items.length} of ${total} reports loaded.`}
          </p>
          {filtering && (
            <button type="button" onClick={() => setFilters(EMPTY_FILTERS)} className="inline-flex items-center gap-1 rounded-chip text-ink underline">
              <X size={14} aria-hidden="true" />
              Clear filters
            </button>
          )}
        </div>
      </section>

      <div className={`grid gap-6 ${preview ? "2xl:grid-cols-[minmax(0,1fr)_360px]" : ""}`}>
        <section aria-labelledby="reports-h" className="glass min-w-0 rounded-card p-5">
          <h2 id="reports-h" className="text-section font-semibold">
            Stored reports
          </h2>
          {first.error ? (
            <div className="mt-3">
              <BlockError what="the history" error={first.error} onRetry={first.retry} />
            </div>
          ) : (
            <>
              <table className="mt-3 hidden w-full text-body xl:table">
                <thead>
                  <tr className="border-b border-line text-left text-small text-muted">
                    <th scope="col" className="py-2 pr-4 font-medium">Date</th>
                    <th scope="col" className="py-2 pr-4 font-medium">Place</th>
                    <th scope="col" className="py-2 pr-4 font-medium">Status</th>
                    <th scope="col" className="py-2 pr-4 font-medium">Risk</th>
                    <th scope="col" className="py-2 pr-4 text-right font-medium">Heat index</th>
                    <th scope="col" className="py-2 pr-4 text-right font-medium">Max forecast</th>
                    <th scope="col" className="py-2 pr-4 font-medium">Changes since the last report here</th>
                    <th scope="col" className="py-2 font-medium">
                      <span className="sr-only">Preview</span>
                    </th>
                  </tr>
                </thead>
                <tbody>
                  {first.loading &&
                    [0, 1, 2].map((i) => (
                      <tr key={i} aria-hidden="true">
                        <td colSpan={8} className="py-3">
                          <div className="skeleton h-6" />
                        </td>
                      </tr>
                    ))}
                  {emptyStore && (
                    <tr>
                      <td colSpan={8} className="py-6 text-body">
                        {empty}
                      </td>
                    </tr>
                  )}
                  {!emptyStore && !first.loading && shown.length === 0 && (
                    <tr>
                      <td colSpan={8} className="py-6 text-body text-muted">
                        No loaded reports match these filters.
                      </td>
                    </tr>
                  )}
                  {shown.map((item) => (
                    <tr
                      key={item.report_id}
                      className={`border-b border-rule align-top transition-colors hover:bg-raised/40 ${
                        previewId === item.report_id ? "bg-raised/50" : ""
                      }`}
                    >
                      <td className="num w-36 py-3 pr-4 text-small text-muted">{formatDateTime(item.created_at)}</td>
                      <td className="min-w-48 py-3 pr-4">
                        <span className="flex items-start gap-2">
                          <span aria-hidden="true" className="mt-1.5 h-2 w-2 flex-none rounded-full" style={{ background: riskHue(item.risk_category) }} />
                          <span>
                            <Link to={`/reports/${item.report_id}/climate`} className="font-medium underline decoration-control hover:decoration-amber">
                              {place(item)}
                            </Link>
                            <span className="mt-0.5 block text-small text-muted">{indicators(item)}</span>
                          </span>
                        </span>
                      </td>
                      <td className="py-3 pr-4">
                        <StatusLabel status={item.status} />
                      </td>
                      <td className="py-3 pr-4">
                        <RiskLabel category={item.risk_category} prefix="" />
                      </td>
                      <td className="num py-3 pr-4 text-right whitespace-nowrap">{formatTemp(item.heat_index_c)}</td>
                      <td className="num py-3 pr-4 text-right whitespace-nowrap">{formatTemp(item.max_forecast_c)}</td>
                      <td className="min-w-64 py-3 pr-4 text-muted">{changesInWords(item.changes)}</td>
                      <td className="py-3">
                        <PreviewButton item={item} active={previewId === item.report_id} onToggle={setPreviewId} />
                      </td>
                    </tr>
                  ))}
                </tbody>
              </table>

              <ul aria-label="Stored reports" className="mt-3 space-y-3 xl:hidden">
                {emptyStore && <li className="text-body">{empty}</li>}
                {first.loading &&
                  [0, 1].map((i) => (
                    <li key={i} aria-hidden="true">
                      <div className="skeleton h-20" />
                    </li>
                  ))}
                {!emptyStore && !first.loading && shown.length === 0 && (
                  <li className="text-body text-muted">No loaded reports match these filters.</li>
                )}
                {shown.map((item) => (
                  <li key={item.report_id} className="relative overflow-hidden rounded-control border border-line bg-raised/40 p-4">
                    <span aria-hidden="true" className="absolute inset-y-0 left-0 w-1" style={{ background: riskHue(item.risk_category) }} />
                    <div className="flex items-start justify-between gap-2">
                      <Link to={`/reports/${item.report_id}/climate`} className="font-medium underline decoration-control">
                        {place(item)}
                      </Link>
                      <RiskLabel category={item.risk_category} prefix="" />
                    </div>
                    <p className="num mt-1 text-small text-muted">
                      {`${formatDateTime(item.created_at)} · ${statusLabel(item.status)} · heat index ${formatTemp(item.heat_index_c)} · max ${formatTemp(item.max_forecast_c)}`}
                    </p>
                    <p className="mt-0.5 text-small text-muted">{indicators(item)}</p>
                    <p className="mt-1 text-body">{changesInWords(item.changes)}</p>
                  </li>
                ))}
              </ul>

              {items.length < total && (
                <div className="mt-4 flex items-center gap-3">
                  <button type="button" onClick={loadMore} disabled={loadingMore} className="btn-secondary h-9">
                    {loadingMore ? "Loading…" : "Load more"}
                  </button>
                  <span className="num text-small text-muted">{`${items.length} of ${total}`}</span>
                </div>
              )}
              {moreError && <p role="alert" className="mt-2 text-body">{`Couldn't load more reports. ${moreError.message}`}</p>}
            </>
          )}
        </section>

        <AnimatePresence>
          {preview && (
            <motion.aside
              key={preview.report_id}
              aria-labelledby="preview-h"
              initial={{ opacity: 0, x: 16 }}
              animate={{ opacity: 1, x: 0 }}
              exit={{ opacity: 0, x: 16 }}
              transition={{ duration: 0.2, ease: "easeOut" }}
              className="glass-strong relative hidden self-start overflow-hidden rounded-card p-5 xl:block 2xl:sticky 2xl:top-6"
            >
              <span aria-hidden="true" className="absolute inset-x-0 top-0 h-1" style={{ background: riskHue(preview.risk_category) }} />
              <div className="flex items-start justify-between gap-2">
                <div>
                  <p className="eyebrow">Report preview</p>
                  <h2 id="preview-h" className="mt-1 text-section font-semibold">
                    {place(preview)}
                  </h2>
                </div>
                <button
                  type="button"
                  onClick={() => setPreviewId(null)}
                  aria-label="Close the preview"
                  className="rounded-chip text-muted hover:text-ink"
                >
                  <X size={18} aria-hidden="true" />
                </button>
              </div>
              <p className="mt-1 text-small text-muted">{formatDateTime(preview.created_at)}</p>
              <div className="mt-3 flex flex-wrap gap-1.5">
                <RiskLabel category={preview.risk_category} />
                <StatusLabel status={preview.status} />
              </div>
              <dl className="mt-4 grid grid-cols-2 gap-3">
                <div>
                  <dt className="text-small text-muted">Heat index</dt>
                  <dd className="num text-section font-semibold">{formatTemp(preview.heat_index_c)}</dd>
                </div>
                <div>
                  <dt className="text-small text-muted">Max forecast</dt>
                  <dd className="num text-section font-semibold">{formatTemp(preview.max_forecast_c)}</dd>
                </div>
                <div>
                  <dt className="text-small text-muted">Verification</dt>
                  <dd className="text-body">{preview.verification_status.replaceAll("_", " ")}</dd>
                </div>
                <div>
                  <dt className="text-small text-muted">Run time</dt>
                  <dd className="num text-body">{formatDuration(preview.duration_ms)}</dd>
                </div>
              </dl>
              <p className="mt-4 text-small text-muted">Groups</p>
              <p className="text-body">{indicators(preview)}</p>
              <p className="mt-3 text-small text-muted">Since the last report here</p>
              <p className="text-body">{changesInWords(preview.changes)}</p>
              <Link to={`/reports/${preview.report_id}/climate`} className="btn-primary mt-5 w-full justify-center">
                Open the full report
                <ArrowRight size={16} aria-hidden="true" />
              </Link>
            </motion.aside>
          )}
        </AnimatePresence>
      </div>
    </div>
  );
}

function PreviewButton({ item, active, onToggle }: { item: HistoryItem; active: boolean; onToggle: (id: string | null) => void }) {
  return (
    <button
      type="button"
      onClick={() => onToggle(active ? null : item.report_id)}
      aria-pressed={active}
      aria-label={`Preview ${place(item)}`}
      className={`grid h-8 w-8 place-items-center rounded-control border transition-colors ${
        active ? "border-amber/60 text-amber" : "border-line text-muted hover:text-ink"
      }`}
    >
      <Eye size={16} aria-hidden="true" />
    </button>
  );
}
