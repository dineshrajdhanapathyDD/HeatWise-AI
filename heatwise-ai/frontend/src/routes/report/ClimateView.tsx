import { ForecastChart } from "../../components/ForecastChart";
import { Pill } from "../../components/Pill";
import { DASH, formatDateTime, formatDay, formatPct, formatTemp } from "../../lib/format";
import { IMD_HEAT_WAVE_C, IMD_PLAINS_C, IMD_SEVERE_C, imdApplies, imdLevel, imdNotAppliedText } from "../../lib/imd";
import { useReportRecord } from "./reportContext";

const CARD = "rounded-card border border-line bg-surface p-5";

/**
 * Screen C: how hot will it get here over the forecast days, against the IMD thresholds?
 * Signature element: each forecast day's maximum placed on a 30-50 °C track with the IMD marks.
 * Like the risk rules, IMD levels are shown only on plains (or unknown terrain), never for hilly or coastal.
 */
export function ClimateView() {
  const { report, request } = useReportRecord();
  const current = report.current_conditions;
  const forecast = report.forecast;
  const alerts = report.alerts;
  const terrain = request.profile.terrain;
  const imd = imdApplies(terrain);
  const tz = report.location?.timezone;

  const maxima = (forecast?.days ?? []).map((d) => d.temperature_max_c).filter((v): v is number => v !== null);
  const highest = maxima.length ? Math.max(...maxima) : null;
  const highestDay = forecast?.days.find((d) => d.temperature_max_c === highest) ?? null;
  const highestLevel = imdLevel(highest, terrain);
  const highestNote = imd
    ? highestLevel
      ? `: ${highestLevel.charAt(0).toLowerCase() + highestLevel.slice(1)}, an indication only.`
      : "."
    : `. ${imdNotAppliedText(terrain)}.`;

  if (!current && !forecast) {
    return (
      <section aria-labelledby="climate-h" className={CARD}>
        <h2 id="climate-h" className="text-section font-medium">
          Climate
        </h2>
        <p className="mt-1 text-body">No weather data was retrieved for this report.</p>
      </section>
    );
  }

  const scaleLo = 30;
  const scaleHi = 50;
  const pos = (v: number) => `${Math.min(100, Math.max(0, ((v - scaleLo) / (scaleHi - scaleLo)) * 100))}%`;

  return (
    <div className="space-y-6">
      <section aria-labelledby="forecast-h" className={CARD}>
        <div className="flex flex-wrap items-start justify-between gap-4">
          <div>
            <h2 id="forecast-h" className="text-section font-medium">
              {imd ? "Forecast against the IMD criteria" : "Forecast daily maximum"}
            </h2>
            <p className="mt-1 text-body">
              {highest === null
                ? "The forecast has no daily maximum values."
                : `Highest forecast maximum ${formatTemp(highest)}${highestDay ? ` on ${formatDay(highestDay.date)}` : ""}${highestNote}`}
            </p>
          </div>
          <ul aria-label="Chart key" className="flex gap-4 text-small text-muted">
            <li className="flex items-center gap-1.5">
              <span aria-hidden="true" className="inline-block h-0.5 w-4 bg-heat" />
              Daily maximum
            </li>
            <li className="flex items-center gap-1.5">
              <span aria-hidden="true" className="inline-block h-0.5 w-4 bg-chart-min" />
              Daily minimum
            </li>
          </ul>
        </div>

        {forecast && forecast.days.length > 0 && (
          <>
            <ol
              aria-label={imd ? "Forecast days against the IMD criteria" : "Forecast daily maximum by day"}
              className="mt-5 grid grid-cols-[repeat(auto-fit,minmax(128px,1fr))] gap-3"
            >
              {forecast.days.map((d) => {
                const level = imd ? imdLevel(d.temperature_max_c, terrain) : "IMD rule not applied";
                return (
                  <li key={d.date} className="rounded-control bg-ground p-3">
                    <p className="text-small text-muted">{formatDay(d.date)}</p>
                    <p className="num mt-0.5 text-section font-medium">{formatTemp(d.temperature_max_c)}</p>
                    <div aria-hidden="true" className="relative mt-2 h-1.5 rounded-full bg-raised">
                      {d.temperature_max_c !== null && (
                        <div className="absolute inset-y-0 left-0 rounded-full bg-heat" style={{ width: pos(d.temperature_max_c) }} />
                      )}
                      {(imd ? [IMD_PLAINS_C, IMD_HEAT_WAVE_C, IMD_SEVERE_C] : []).map((t) => (
                        <span key={t} className="absolute -top-1 h-3.5 w-px bg-ink" style={{ left: pos(t) }} />
                      ))}
                    </div>
                    <p className="mt-2 text-small">{level ?? DASH}</p>
                  </li>
                );
              })}
            </ol>
            <div className="mt-6">
              <ForecastChart days={forecast.days} terrain={terrain} />
            </div>
            <p className="mt-2 text-small text-muted">{forecast.note}</p>
          </>
        )}
      </section>

      <div className="grid gap-6 md:grid-cols-2">
        <section aria-labelledby="current-h" className={CARD}>
          <h2 id="current-h" className="text-section font-medium">
            Current conditions
          </h2>
          {current ? (
            <dl className="mt-3 grid grid-cols-3 gap-3">
              <div>
                <dt className="text-small text-muted">Temperature</dt>
                <dd className="num mt-0.5 text-section font-medium">{formatTemp(current.temperature_c)}</dd>
              </div>
              <div>
                <dt className="text-small text-muted">Humidity</dt>
                <dd className="num mt-0.5 text-section font-medium">{formatPct(current.relative_humidity_pct)}</dd>
              </div>
              <div>
                <dt className="text-small text-muted">Feels like</dt>
                <dd className="num mt-0.5 text-section font-medium">{formatTemp(current.apparent_temperature_c)}</dd>
              </div>
            </dl>
          ) : (
            <p className="mt-1 text-body">No current conditions were retrieved.</p>
          )}
          {current && <p className="mt-3 text-small text-muted">Feels like is the provider's apparent temperature.</p>}
        </section>

        <section aria-labelledby="warnings-h" className={CARD}>
          <h2 id="warnings-h" className="text-section font-medium">
            Official warnings
          </h2>
          {alerts && alerts.alerts.length > 0 ? (
            <ul className="mt-2 space-y-2 text-body">
              {alerts.alerts.map((a) => (
                <li key={`${a.issuer}-${a.headline}`}>
                  <a href={a.source_url} target="_blank" rel="noreferrer" className="underline">
                    {a.headline}
                  </a>{" "}
                  <span className="text-muted">{a.issuer}</span>
                </li>
              ))}
            </ul>
          ) : (
            <p className="mt-1 text-body">
              {alerts?.explanation ?? "No warning information was retrieved."} HeatWise never generates warnings.
            </p>
          )}
          {alerts && alerts.official_sources.length > 0 ? (
            <ul aria-label="Official sources" className="mt-3 space-y-1 text-body">
              {alerts.official_sources.map((url) => (
                <li key={url}>
                  <a href={url} target="_blank" rel="noreferrer" className="break-all underline">
                    {url}
                  </a>
                </li>
              ))}
            </ul>
          ) : (
            <p className="mt-3 text-small text-muted">No official source link returned.</p>
          )}
        </section>
      </div>

      <section aria-labelledby="source-h" className={CARD}>
        <div className="flex flex-wrap items-center justify-between gap-2">
          <h2 id="source-h" className="text-section font-medium">
            Weather source
          </h2>
          {report.weather_source.data_mode && (
            <Pill tone="neutral">{report.weather_source.data_mode === "demo" ? "Demo data" : "Live weather"}</Pill>
          )}
        </div>
        <dl className="mt-3 grid gap-3 text-body sm:grid-cols-[160px_minmax(0,1fr)]">
          <dt className="text-muted">Provider</dt>
          <dd>{report.weather_source.provider ?? DASH}</dd>
          <dt className="text-muted">Last updated</dt>
          <dd className="num">{formatDateTime(report.data_retrieved_at, tz)}</dd>
          <dt className="text-muted">Source links</dt>
          <dd>
            {report.weather_source.source_urls.length ? (
              <ul className="space-y-1">
                {report.weather_source.source_urls.map((u) => (
                  <li key={u}>
                    <a href={u} target="_blank" rel="noreferrer" className="break-all underline">
                      {u}
                    </a>
                  </li>
                ))}
              </ul>
            ) : (
              DASH
            )}
          </dd>
        </dl>
        {report.weather_summary && <p className="mt-3 text-body">{report.weather_summary}</p>}
      </section>
    </div>
  );
}
