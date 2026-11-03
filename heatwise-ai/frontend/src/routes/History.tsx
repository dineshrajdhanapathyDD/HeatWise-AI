import { useCallback, useState } from "react";
import { Link } from "react-router-dom";

import { type ApiError, api, toApiError } from "../api/client";
import type { HistoryItem } from "../api/types";
import { useLoad } from "../api/useLoad";
import { BlockError } from "../components/BlockError";
import { RiskLabel, StatusLabel } from "../components/Pill";
import { formatDateTime, formatTemp, placeName } from "../lib/format";
import { changesInWords, countsLine } from "../lib/history";
import { indicatorLabel, statusLabel } from "../lib/risk";

const PAGE = 20;

function place(item: HistoryItem): string {
  return placeName([item.location_name ?? item.query, item.admin1, item.country]);
}

function indicators(item: HistoryItem): string {
  return item.indicators.length ? item.indicators.map(indicatorLabel).join(", ") : "No indicators given";
}

/** Screen G: how have this place's assessments changed? */
export function History() {
  const loadFirst = useCallback((signal: AbortSignal) => api.history(PAGE, 0, signal), []);
  const first = useLoad("history", loadFirst);
  const metrics = useLoad("metrics", api.metrics);
  const [more, setMore] = useState<HistoryItem[]>([]);
  const [loadingMore, setLoadingMore] = useState(false);
  const [moreError, setMoreError] = useState<ApiError | null>(null);

  const items = [...(first.data?.items ?? []), ...more];
  const total = first.data?.total ?? 0;

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

  return (
    <>
      <div className="flex flex-wrap items-start justify-between gap-3">
        <div>
          <h1 className="text-title font-medium">History</h1>
          <p className="mt-1 text-body text-muted">
            {metrics.data ? countsLine(metrics.data) : metrics.error ? "Counts are not available." : "Counting stored reports…"}
          </p>
        </div>
        <Link
          to="/assess"
          className="inline-flex h-9 items-center rounded-control bg-primary px-4 text-body font-medium text-surface hover:bg-ink"
        >
          New assessment
        </Link>
      </div>

      <section aria-labelledby="reports-h" className="mt-6 rounded-card border border-line bg-surface p-5">
        <h2 id="reports-h" className="text-section font-medium">
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
                  <th scope="col" className="py-2 pr-4 font-normal">Date</th>
                  <th scope="col" className="py-2 pr-4 font-normal">Place</th>
                  <th scope="col" className="py-2 pr-4 font-normal">Status</th>
                  <th scope="col" className="py-2 pr-4 font-normal">Risk</th>
                  <th scope="col" className="py-2 pr-4 text-right font-normal">Heat index</th>
                  <th scope="col" className="py-2 pr-4 text-right font-normal">Max forecast</th>
                  <th scope="col" className="py-2 font-normal">Changes since the last report here</th>
                </tr>
              </thead>
              <tbody>
                {first.loading &&
                  [0, 1, 2].map((i) => (
                    <tr key={i} aria-hidden="true">
                      <td colSpan={7} className="py-3">
                        <div className="h-5 rounded-chip bg-raised" />
                      </td>
                    </tr>
                  ))}
                {!first.loading && items.length === 0 && (
                  <tr>
                    <td colSpan={7} className="py-6 text-body">
                      No assessments are stored yet.{" "}
                      <Link to="/assess" className="underline">
                        Start an assessment
                      </Link>{" "}
                      to see it here.
                    </td>
                  </tr>
                )}
                {items.map((item) => (
                  <tr key={item.report_id} className="border-b border-rule align-top">
                    <td className="num w-32 py-3 pr-4">{formatDateTime(item.created_at)}</td>
                    <td className="min-w-48 py-3 pr-4">
                      <Link to={`/reports/${item.report_id}/climate`} className="font-medium underline">
                        {place(item)}
                      </Link>
                      <span className="mt-0.5 block text-small text-muted">{indicators(item)}</span>
                    </td>
                    <td className="py-3 pr-4">
                      <StatusLabel status={item.status} />
                    </td>
                    <td className="py-3 pr-4">
                      <RiskLabel category={item.risk_category} prefix="" />
                    </td>
                    <td className="num py-3 pr-4 text-right whitespace-nowrap">{formatTemp(item.heat_index_c)}</td>
                    <td className="num py-3 pr-4 text-right whitespace-nowrap">{formatTemp(item.max_forecast_c)}</td>
                    <td className="min-w-64 py-3">{changesInWords(item.changes)}</td>
                  </tr>
                ))}
              </tbody>
            </table>

            <ul aria-label="Stored reports" className="mt-3 divide-y divide-rule xl:hidden">
              {!first.loading && items.length === 0 && (
                <li className="text-body">
                  No assessments are stored yet.{" "}
                  <Link to="/assess" className="underline">
                    Start an assessment
                  </Link>{" "}
                  to see it here.
                </li>
              )}
              {items.map((item) => (
                <li key={item.report_id} className="py-3 first:pt-0">
                  <div className="flex items-start justify-between gap-2">
                    <Link to={`/reports/${item.report_id}/climate`} className="font-medium underline">
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
                <button
                  type="button"
                  onClick={loadMore}
                  disabled={loadingMore}
                  className="inline-flex h-8 items-center rounded-control border border-control bg-surface px-3 text-body"
                >
                  {loadingMore ? "Loading…" : "Load more"}
                </button>
                <span className="num text-small text-muted">{`${items.length} of ${total}`}</span>
              </div>
            )}
            {moreError && <p role="alert" className="mt-2 text-body">{`Couldn't load more reports. ${moreError.message}`}</p>}
          </>
        )}
      </section>
    </>
  );
}
