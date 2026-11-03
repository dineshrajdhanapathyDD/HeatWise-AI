import { motion } from "framer-motion";
import {
  ArrowRight,
  Baby,
  CalendarDays,
  Droplets,
  ExternalLink,
  Gauge,
  HandHeart,
  MapPin,
  Megaphone,
  Sprout,
  Sun,
  Thermometer,
  TriangleAlert,
  UsersRound,
  Wind,
} from "lucide-react";
import { useCallback } from "react";
import { Link } from "react-router-dom";

import { api } from "../api/client";
import type { AssessmentRecord, PreparednessReport } from "../api/types";
import { useLoad } from "../api/useLoad";
import { AgentPipeline } from "../components/AgentPipeline";
import { AnimatedNumber } from "../components/AnimatedNumber";
import { BlockError } from "../components/BlockError";
import { RiskLabel, StatusLabel } from "../components/Pill";
import { RiskGauge } from "../components/RiskGauge";
import { WeatherVisual } from "../components/WeatherVisual";
import { WeatherTrendChart } from "../components/charts/WeatherTrendChart";
import { DataTag, MetricCard, SectionHeading, SkeletonLines, Unavailable } from "../components/ui";
import {
  AUDIENCE_LABELS,
  COMMUNITY_GROUPS,
  PHASE_LABELS,
  audienceTopics,
  highestForecast,
  osmLink,
  topActions,
} from "../lib/dashboard";
import { DASH, formatDateTime, formatDay, formatNumber, formatPct, formatTemp, placeName } from "../lib/format";
import { indicatorLabel, riskLabel } from "../lib/risk";
import { riskHue } from "../lib/riskScale";
import { renderablePlanItems } from "../lib/safety";
import { SCENE_TEXT, sceneBasis, sceneFor } from "../lib/weatherScene";

const temp = (n: number) => formatTemp(n);
const pct = (n: number) => formatPct(n);

const GROUP_ICONS = { elderly: HandHeart, young_children: Baby, outdoor_workers: UsersRound, farmers: Sprout } as const;

/** Screen A, the home dashboard: what is happening with the weather, who is at risk, what to do. */
export function Landing() {
  const loadLatest = useCallback((signal: AbortSignal) => api.history(1, 0, signal), []);
  const latest = useLoad("latest", loadLatest);
  const item = latest.data?.items[0] ?? null;

  const reportId = item?.report_id ?? null;
  const loadRecord = useCallback(
    (signal: AbortSignal) => (reportId ? api.report(reportId, signal) : Promise.resolve(null)),
    [reportId],
  );
  const detail = useLoad<AssessmentRecord | null>(`latest-record:${reportId ?? "none"}`, loadRecord);
  const record = detail.data;
  const report = record?.report ?? null;

  const empty = !latest.loading && !latest.error && !item;

  return (
    <div className="space-y-8">
      <Hero report={report} loading={latest.loading || (Boolean(item) && detail.loading)} empty={empty} />

      {latest.error && <BlockError what="the latest report" error={latest.error} onRetry={latest.retry} />}
      {detail.error && <BlockError what="the latest report details" error={detail.error} onRetry={detail.retry} />}

      {report && record && (
        <>
          <RiskOverview report={report} />
          <WeatherIntelligence record={record} />
          <CommunityImpact report={report} />
          <div className="grid gap-6 xl:grid-cols-[minmax(0,1.6fr)_minmax(0,1fr)]">
            <ActNow report={report} />
            <LatestAssessment record={record} />
          </div>
          <AgentPipeline input={{ phase: "finished", report }} headingId="pipeline-h" title="Agent workflow, latest run" />
        </>
      )}

      {empty && <AgentPipeline input={{ phase: "idle" }} headingId="pipeline-h" />}
    </div>
  );
}

/* ---------- A. Weather hero ---------- */

function Hero({ report, loading, empty }: { report: PreparednessReport | null; loading: boolean; empty: boolean }) {
  const current = report?.current_conditions ?? null;
  const loc = report?.location ?? null;
  const scene = sceneFor(current, report?.risk?.heat_index_c);
  const heat = scene === "extreme-heat" || scene === "hot";

  return (
    <section
      aria-labelledby="hero-h"
      className="glass-strong relative isolate overflow-hidden rounded-[28px] p-6 sm:p-8 lg:p-10"
    >
      <div
        aria-hidden="true"
        className="absolute inset-0 -z-10"
        style={{
          background: heat
            ? "radial-gradient(80% 90% at 85% 10%, rgb(255 122 69 / 0.30), transparent 60%), radial-gradient(60% 70% at 0% 100%, rgb(56 198 244 / 0.10), transparent 60%)"
            : scene === "rain"
              ? "radial-gradient(80% 90% at 85% 10%, rgb(110 168 255 / 0.25), transparent 60%)"
              : "radial-gradient(80% 90% at 85% 10%, rgb(245 165 36 / 0.18), transparent 60%), radial-gradient(60% 70% at 0% 100%, rgb(56 198 244 / 0.12), transparent 60%)",
        }}
      />
      <div className="grid gap-8 lg:grid-cols-[minmax(0,1fr)_minmax(0,1.05fr)] lg:items-center">
        <div>
          <p className="eyebrow">Community heatwave preparedness</p>
          <h1 id="hero-h" className="mt-2 text-[40px] font-semibold leading-[44px] tracking-tight sm:text-display">
            HeatWise AI
          </h1>
          <p className="mt-3 text-section text-amber">From Weather Intelligence to Community Action.</p>
          <p className="mt-4 max-w-[52ch] text-body text-muted">
            Heatwaves hurt older people, young children, outdoor workers and farming households first. HeatWise reads
            the weather for one community, rates the heat risk with published criteria, and prepares a checked
            action plan you can share.
          </p>
          <div className="mt-6 flex flex-wrap gap-3">
            <Link to="/assess" className="btn-primary">
              Start an assessment
              <ArrowRight size={16} aria-hidden="true" />
            </Link>
            {report && (
              <Link to={`/reports/${report.report_id}/climate`} className="btn-secondary">
                View latest report
              </Link>
            )}
          </div>
        </div>

        <div className="relative">
          {loading ? (
            <div className="glass rounded-card p-6">
              <p role="status" className="sr-only">
                Loading the latest weather
              </p>
              <SkeletonLines lines={4} />
            </div>
          ) : (
            <div className="glass rounded-card p-5 sm:p-6">
              <div className="flex flex-col gap-4 sm:flex-row sm:items-center">
                <div className="mx-auto flex-none sm:mx-0">
                  <WeatherVisual scene={scene} size={176} />
                </div>
                <div className="min-w-0 flex-1">
                  {report && loc ? (
                    <>
                      <p className="flex items-center gap-1.5 text-body font-medium">
                        <MapPin size={16} aria-hidden="true" className="text-cyan" />
                        {placeName([loc.name, loc.admin1, loc.country])}
                      </p>
                      <p className="mt-0.5 text-small text-muted">
                        {`Weather retrieved ${formatDateTime(report.data_retrieved_at, loc.timezone)}`}
                      </p>
                      <p className="num mt-3 text-[52px] font-semibold leading-none tracking-tight">
                        <AnimatedNumber value={current?.temperature_c} format={temp} />
                      </p>
                      <p className="mt-1 text-body text-muted">
                        {`${SCENE_TEXT[scene]} · feels like `}
                        <span className="num text-ink">{formatTemp(current?.apparent_temperature_c)}</span>
                      </p>
                    </>
                  ) : (
                    <>
                      <p className="text-section font-semibold">No weather yet</p>
                      <p className="mt-1 text-body text-muted">
                        {empty
                          ? "No assessments are stored yet. Start one to see its report here."
                          : "The latest report has no weather data."}
                      </p>
                    </>
                  )}
                </div>
              </div>

              {report && (
                <>
                  <dl className="mt-5 grid grid-cols-3 gap-2">
                    {[
                      { label: "Humidity", value: formatPct(current?.relative_humidity_pct), icon: Droplets },
                      { label: "Wind", value: formatNumber(current?.wind_speed_kmh, "km/h"), icon: Wind },
                      { label: "Heat index", value: formatTemp(report.risk?.heat_index_c), icon: Thermometer },
                    ].map(({ label, value, icon: Icon }) => (
                      <div key={label} className="rounded-control bg-raised/60 p-3">
                        <dt className="flex items-center gap-1.5 text-small text-muted">
                          <Icon size={14} aria-hidden="true" />
                          {label}
                        </dt>
                        <dd className="num mt-1 text-section font-semibold">{value}</dd>
                      </div>
                    ))}
                  </dl>
                  {report.weather_summary && <p className="mt-4 text-body">{report.weather_summary}</p>}
                  <p className="mt-3 text-small text-muted">{sceneBasis(scene)}</p>
                </>
              )}
            </div>
          )}
        </div>
      </div>
    </section>
  );
}

/* ---------- B. Heat risk overview ---------- */

function RiskOverview({ report }: { report: PreparednessReport }) {
  const risk = report.risk;
  const high = highestForecast(report.forecast?.days);
  const alerts = report.alerts;
  const indicators = risk?.vulnerability_indicators ?? [];
  const warning =
    alerts === null
      ? { value: DASH, caption: "No warning information was retrieved" }
      : alerts.alerts.length > 0
        ? { value: String(alerts.alerts.length), caption: alerts.alerts.length === 1 ? "official alert" : "official alerts" }
        : { value: "None", caption: alerts.alerts_supported ? "No official alerts reported" : "Provider has no official warnings" };

  return (
    <section aria-labelledby="risk-overview-h" className="space-y-4">
      <SectionHeading
        id="risk-overview-h"
        eyebrow="Heat risk overview"
        title="How serious is the heat?"
        description="From the latest assessment. The risk category comes from the backend's deterministic rules, never from this screen or an AI model."
        actions={<DataTag>From the latest assessment</DataTag>}
      />
      <dl className="grid gap-4 sm:grid-cols-2 xl:grid-cols-5">
        <MetricCard
          index={0}
          label="Heat index now"
          icon={Thermometer}
          accent="#ff7a45"
          value={<AnimatedNumber value={risk?.heat_index_c} format={temp} />}
          caption={
            risk?.heat_index_band
              ? `NWS band: ${risk.heat_index_band}`
              : risk?.heat_index_c !== null && risk?.heat_index_c !== undefined
                ? "NWS band: below Caution"
                : "Not computed"
          }
        />
        <MetricCard
          index={1}
          label="Highest forecast max"
          icon={Sun}
          accent="#f5a524"
          value={<AnimatedNumber value={high.value} format={temp} />}
          caption={high.date ? `On ${formatDay(high.date)}` : "No daily maximum"}
        />
        <MetricCard
          index={2}
          label="Heat-risk category"
          icon={Gauge}
          accent={riskHue(report.risk_category)}
          value={<span style={{ color: riskHue(report.risk_category) }}>{riskLabel(report.risk_category)}</span>}
          caption={risk ? `Rules ${risk.rules_version}, ${risk.confidence} confidence` : "Risk was not assessed"}
        />
        <MetricCard
          index={3}
          label="Official warnings"
          icon={Megaphone}
          accent="#6ea8ff"
          value={warning.value}
          caption={warning.caption}
        />
        <MetricCard
          index={4}
          label="Vulnerability indicators"
          icon={TriangleAlert}
          accent="#38c6f4"
          value={<AnimatedNumber value={indicators.length} format={(n) => String(Math.round(n))} />}
          caption={indicators.length ? indicators.map(indicatorLabel).join(", ") : "None reported"}
        />
      </dl>
    </section>
  );
}

/* ---------- C. Weather intelligence ---------- */

function WeatherIntelligence({ record }: { record: AssessmentRecord }) {
  const report = record.report;
  const days = report.forecast?.days ?? [];
  const current = report.current_conditions;
  const loc = report.location;
  const maxHumidity = Math.max(100, ...days.map((d) => d.relative_humidity_max_pct ?? 0));

  return (
    <section aria-labelledby="weather-h" className="space-y-4">
      <SectionHeading
        id="weather-h"
        eyebrow="Weather intelligence"
        title="What is the weather doing?"
        description={
          report.forecast
            ? `${days.length}-day daily forecast from ${report.weather_source.provider ?? "the provider"}. Forecast values are not official warnings.`
            : "No forecast was retrieved for the latest assessment."
        }
        actions={<DataTag>{report.weather_source.data_mode === "demo" ? "Demo data" : "Live provider data"}</DataTag>}
      />

      <div className="grid gap-4 xl:grid-cols-3">
        <div className="glass rounded-card p-5 xl:col-span-2">
          <h3 className="text-body font-semibold">Temperature and feels-like trend</h3>
          {days.length ? (
            <div className="mt-3">
              <WeatherTrendChart
                days={days}
                caption="Feels-like is the provider's apparent temperature. The backend computes the heat index for current conditions only."
              />
            </div>
          ) : (
            <p className="mt-2 text-body text-muted">The provider returned no daily values.</p>
          )}
        </div>

        <div className="glass flex flex-col items-center justify-center rounded-card p-5">
          <h3 className="self-start text-body font-semibold">Heat-risk gauge</h3>
          <div className="mt-4 w-full">
            <RiskGauge category={report.risk_category} />
          </div>
          {report.risk?.explanation && <p className="mt-4 text-small text-muted">{report.risk.explanation}</p>}
        </div>
      </div>

      <div className="grid gap-4 xl:grid-cols-3">
        <div className="glass rounded-card p-5 xl:col-span-2">
          <div className="flex flex-wrap items-center justify-between gap-2">
            <h3 className="flex items-center gap-2 text-body font-semibold">
              <CalendarDays size={16} aria-hidden="true" className="text-cyan" />
              Daily timeline
            </h3>
            <span className="text-small text-muted">Daily values only</span>
          </div>
          {days.length ? (
            <ol
              aria-label="Forecast days"
              className="mt-4 grid grid-cols-2 gap-3 sm:grid-cols-[repeat(auto-fit,minmax(112px,1fr))]"
            >
              {days.map((d, i) => (
                <motion.li
                  key={d.date}
                  initial={{ opacity: 0, y: 8 }}
                  whileInView={{ opacity: 1, y: 0 }}
                  viewport={{ once: true }}
                  transition={{ delay: i * 0.05 }}
                  className="rounded-control border border-line bg-raised/50 p-3"
                >
                  <p className="text-small font-medium text-muted">{formatDay(d.date)}</p>
                  <p className="num mt-1 text-section font-semibold text-heat">{formatTemp(d.temperature_max_c)}</p>
                  <p className="num text-small text-muted">{`Min ${formatTemp(d.temperature_min_c)}`}</p>
                  <dl className="mt-2 space-y-1 text-small">
                    <div className="flex justify-between gap-2">
                      <dt className="text-muted">Feels like</dt>
                      <dd className="num">{formatTemp(d.apparent_temperature_max_c)}</dd>
                    </div>
                    <div className="flex justify-between gap-2">
                      <dt className="text-muted">UV max</dt>
                      <dd className="num">{formatNumber(d.uv_index_max)}</dd>
                    </div>
                    <div className="flex justify-between gap-2">
                      <dt className="text-muted">Rain</dt>
                      <dd className="num">{formatNumber(d.precipitation_sum_mm, "mm")}</dd>
                    </div>
                    <div>
                      <div className="flex justify-between gap-2">
                        <dt className="text-muted">Humidity max</dt>
                        <dd className="num">{formatPct(d.relative_humidity_max_pct)}</dd>
                      </div>
                      {d.relative_humidity_max_pct !== null && (
                        <div aria-hidden="true" className="mt-1 h-1 rounded-full bg-grid">
                          <div
                            className="h-1 rounded-full bg-cyan"
                            style={{ width: `${(d.relative_humidity_max_pct / maxHumidity) * 100}%` }}
                          />
                        </div>
                      )}
                    </div>
                  </dl>
                </motion.li>
              ))}
            </ol>
          ) : (
            <p className="mt-2 text-body text-muted">No forecast days.</p>
          )}
          <div className="mt-4">
            <Unavailable
              title="Hourly timeline not available"
              reason="The backend requests current conditions and daily values from Open-Meteo, not hourly data, so no hourly readings are shown."
              field="forecast.hourly"
            />
          </div>
        </div>

        <div className="space-y-4">
          <div className="glass rounded-card p-5">
            <h3 className="text-body font-semibold">Humidity and wind now</h3>
            {current ? (
              <dl className="mt-4 space-y-4">
                <div>
                  <div className="flex items-center justify-between text-small">
                    <dt className="flex items-center gap-1.5 text-muted">
                      <Droplets size={14} aria-hidden="true" />
                      Relative humidity
                    </dt>
                    <dd className="num text-body font-semibold">
                      <AnimatedNumber value={current.relative_humidity_pct} format={pct} />
                    </dd>
                  </div>
                  <div aria-hidden="true" className="mt-2 h-2 rounded-full bg-grid">
                    <motion.div
                      initial={{ width: 0 }}
                      whileInView={{ width: `${Math.min(100, current.relative_humidity_pct ?? 0)}%` }}
                      viewport={{ once: true }}
                      transition={{ duration: 0.8, ease: "easeOut" }}
                      className="h-2 rounded-full bg-cyan"
                    />
                  </div>
                </div>
                <div className="flex items-center justify-between text-small">
                  <dt className="flex items-center gap-1.5 text-muted">
                    <Wind size={14} aria-hidden="true" />
                    Wind speed
                  </dt>
                  <dd className="num text-body font-semibold">{formatNumber(current.wind_speed_kmh, "km/h")}</dd>
                </div>
                <div className="flex items-center justify-between text-small">
                  <dt className="text-muted">Precipitation</dt>
                  <dd className="num text-body font-semibold">{formatNumber(current.precipitation_mm, "mm")}</dd>
                </div>
              </dl>
            ) : (
              <p className="mt-2 text-body text-muted">No current conditions were retrieved.</p>
            )}
            <p className="mt-3 text-small text-muted">Wind direction is not part of the provider data HeatWise requests.</p>
          </div>

          {loc && (
            <div className="glass rounded-card p-5">
              <h3 className="flex items-center gap-2 text-body font-semibold">
                <MapPin size={16} aria-hidden="true" className="text-cyan" />
                Location
              </h3>
              <p className="mt-2 text-body">{placeName([loc.name, loc.admin2, loc.admin1, loc.country])}</p>
              <dl className="mt-3 grid grid-cols-2 gap-2 text-small">
                <div>
                  <dt className="text-muted">Latitude</dt>
                  <dd className="num">{loc.latitude.toFixed(4)}</dd>
                </div>
                <div>
                  <dt className="text-muted">Longitude</dt>
                  <dd className="num">{loc.longitude.toFixed(4)}</dd>
                </div>
                <div className="col-span-2">
                  <dt className="text-muted">Time zone</dt>
                  <dd>{loc.timezone ?? DASH}</dd>
                </div>
              </dl>
              <a
                href={osmLink(loc.latitude, loc.longitude)}
                target="_blank"
                rel="noreferrer"
                className="mt-3 inline-flex items-center gap-1.5 text-body font-medium text-cyan underline"
              >
                Open in OpenStreetMap
                <ExternalLink size={14} aria-hidden="true" />
                <span className="sr-only">(opens in a new tab)</span>
              </a>
              <p className="mt-2 text-small text-muted">No map tiles load until you open the link.</p>
            </div>
          )}
        </div>
      </div>
    </section>
  );
}

/* ---------- D. Community impact ---------- */

function CommunityImpact({ report }: { report: PreparednessReport }) {
  const present = new Set(report.risk?.vulnerability_indicators ?? []);
  const items = renderablePlanItems(report);
  return (
    <section aria-labelledby="community-h" className="space-y-4">
      <SectionHeading
        id="community-h"
        eyebrow="Community impact"
        title="Who may be at risk?"
        description="Groups reported for this community in the latest assessment, and the verified guidance the plan has for them."
      />
      <ul className="grid gap-4 sm:grid-cols-2 xl:grid-cols-4">
        {COMMUNITY_GROUPS.map((g, i) => {
          const Icon = GROUP_ICONS[g.code];
          const isPresent = present.has(g.code);
          const count = items.filter((it) => it.audience === g.audience).length;
          const topics = audienceTopics(items, g.audience);
          return (
            <motion.li
              key={g.code}
              initial={{ opacity: 0, y: 10 }}
              whileInView={{ opacity: 1, y: 0 }}
              viewport={{ once: true }}
              transition={{ delay: i * 0.06 }}
              className={`glass lift rounded-card p-5 ${isPresent ? "" : "opacity-75"}`}
            >
              <div className="flex items-start justify-between gap-3">
                <span
                  className={`grid h-11 w-11 place-items-center rounded-control ${isPresent ? "bg-heat/15 text-heat" : "bg-raised text-muted"}`}
                >
                  <Icon size={22} strokeWidth={1.75} aria-hidden="true" />
                </span>
                <span
                  className={`rounded-full px-2.5 py-0.5 text-small font-medium ${isPresent ? "bg-neg-bg text-neg-ink" : "bg-neutral-bg text-neutral-ink"}`}
                >
                  {isPresent ? "Present" : "Not reported"}
                </span>
              </div>
              <h3 className="mt-3 text-section font-semibold">{g.title}</h3>
              <p className="mt-1 text-small text-muted">
                {isPresent
                  ? "Reported for this community, so the vulnerability rules count this group."
                  : "Not reported in the latest assessment."}
              </p>
              <p className="mt-3 text-small">
                <span className="num font-semibold">{count}</span>
                <span className="text-muted">{` verified ${g.audienceLabel} ${count === 1 ? "action" : "actions"}`}</span>
              </p>
              {topics.length > 0 && <p className="mt-1 text-small text-muted">{`Covers: ${topics.join(", ")}`}</p>}
            </motion.li>
          );
        })}
      </ul>
    </section>
  );
}

/* ---------- F. Latest assessment ---------- */

function LatestAssessment({ record }: { record: AssessmentRecord }) {
  const report = record.report;
  const loc = report.location;
  const high = highestForecast(report.forecast?.days);
  return (
    <section aria-labelledby="latest-report" className="glass-strong relative flex flex-col overflow-hidden rounded-card p-6">
      <span aria-hidden="true" className="absolute inset-x-0 top-0 h-1" style={{ background: riskHue(report.risk_category) }} />
      <p className="eyebrow">Latest assessment</p>
      <h2 id="latest-report" className="mt-1 text-title font-semibold">
        {loc ? placeName([loc.name, loc.admin1, loc.country]) : report.query}
      </h2>
      <p className="mt-1 text-small text-muted">{`Assessed ${formatDateTime(report.created_at, loc?.timezone)}`}</p>
      <div className="mt-4 flex flex-wrap gap-1.5">
        <RiskLabel category={report.risk_category} />
        <StatusLabel status={report.status} />
      </div>
      <dl className="mt-5 grid grid-cols-2 gap-4">
        <div>
          <dt className="text-small text-muted">Highest forecast max</dt>
          <dd className="num mt-0.5 text-kpi font-semibold">{formatTemp(high.value)}</dd>
        </div>
        <div>
          <dt className="text-small text-muted">Heat index</dt>
          <dd className="num mt-0.5 text-kpi font-semibold">{formatTemp(report.risk?.heat_index_c)}</dd>
        </div>
        <div>
          <dt className="text-small text-muted">Verification</dt>
          <dd className="mt-0.5 text-body font-medium">
            {report.verification
              ? `${report.verification.status === "passed" ? "Passed" : "Failed"}, ${report.verification.pct_items_verified.toFixed(0)}% of items`
              : "Not run"}
          </dd>
        </div>
        <div>
          <dt className="text-small text-muted">Forecast length</dt>
          <dd className="mt-0.5 text-body font-medium">{`${record.request.forecast_days} days`}</dd>
        </div>
      </dl>
      <Link to={`/reports/${report.report_id}/climate`} className="btn-primary mt-6 w-full justify-center xl:mt-auto">
        Open the report
        <ArrowRight size={16} aria-hidden="true" />
      </Link>
    </section>
  );
}

/* ---------- What to do now ---------- */

function ActNow({ report }: { report: PreparednessReport }) {
  const items = renderablePlanItems(report);
  const actions = topActions(items);
  return (
    <section aria-labelledby="act-h" className="space-y-4">
      <SectionHeading
        id="act-h"
        eyebrow="Community action"
        title="What should the community do?"
        description={
          report.status === "needs_human_review"
            ? "This report needs human review, so only actions that passed verification are shown."
            : "A few verified actions from the latest plan. The full plan has before, during and after steps."
        }
        actions={
          items.length > 0 ? (
            <Link to={`/reports/${report.report_id}/plan`} className="btn-secondary">
              Open the full plan
            </Link>
          ) : undefined
        }
      />
      {actions.length ? (
        <ol className="grid gap-4 md:grid-cols-2">
          {actions.map((a, i) => (
            <motion.li
              key={a.id}
              initial={{ opacity: 0, y: 10 }}
              whileInView={{ opacity: 1, y: 0 }}
              viewport={{ once: true }}
              transition={{ delay: i * 0.06 }}
              className="glass lift flex flex-col rounded-card p-5"
            >
              <div className="flex flex-wrap gap-1.5 text-small">
                <span className="rounded-full bg-raised px-2 py-0.5 text-neutral-ink">{AUDIENCE_LABELS[a.audience] ?? a.audience}</span>
                <span className="rounded-full bg-raised px-2 py-0.5 text-neutral-ink">{`${PHASE_LABELS[a.phase] ?? a.phase} a heatwave`}</span>
              </div>
              <p className="mt-3 flex-1 text-body">{a.text}</p>
              <p className="mt-3 text-small text-muted">
                {a.kind === "sourced" ? `Source: ${a.source_ids.join(", ")}` : "General educational advice"}
              </p>
            </motion.li>
          ))}
        </ol>
      ) : (
        <p className="glass rounded-card p-5 text-body text-muted">
          {report.status === "incomplete"
            ? "The latest report is incomplete, so it has no plan."
            : "No verified actions are available in the latest report."}
        </p>
      )}
    </section>
  );
}
