import { Area, CartesianGrid, ComposedChart, Line, ResponsiveContainer, Tooltip, XAxis, YAxis } from "recharts";

import type { DailyForecast } from "../../api/types";
import { DASH, formatDay, formatTemp } from "../../lib/format";
import { PALETTE, TICK, TOOLTIP_STYLE } from "../../lib/palette";

/**
 * Forecast trend from the provider's daily values: maximum (area), minimum, and the provider's feels-like
 * (apparent) daily maximum. The backend computes the heat index for current conditions only, so the
 * feels-like line is labelled as such and never called a heat index. A hidden table carries the same data.
 */
export function WeatherTrendChart({ days, caption }: { days: DailyForecast[]; caption?: string }) {
  const data = days.map((d) => ({
    day: formatDay(d.date),
    max: d.temperature_max_c,
    min: d.temperature_min_c,
    feels: d.apparent_temperature_max_c,
  }));
  const values = data.flatMap((d) => [d.max, d.min, d.feels]).filter((v): v is number => v !== null);
  const lo = values.length ? Math.floor((Math.min(...values) - 2) / 5) * 5 : 0;
  const hi = values.length ? Math.ceil((Math.max(...values) + 2) / 5) * 5 : 50;
  const hasFeels = data.some((d) => d.feels !== null);

  return (
    <figure>
      <ul aria-label="Chart key" className="mb-3 flex flex-wrap gap-x-4 gap-y-1 text-small text-muted">
        <li className="flex items-center gap-1.5">
          <span aria-hidden="true" className="inline-block h-2 w-4 rounded-sm" style={{ background: PALETTE.heat }} />
          Daily maximum
        </li>
        <li className="flex items-center gap-1.5">
          <span aria-hidden="true" className="inline-block h-0.5 w-4" style={{ background: PALETTE.cyan }} />
          Daily minimum
        </li>
        {hasFeels && (
          <li className="flex items-center gap-1.5">
            <span aria-hidden="true" className="inline-block h-0.5 w-4 border-t-2 border-dashed" style={{ borderColor: PALETTE.amber }} />
            Feels-like daily maximum
          </li>
        )}
      </ul>
      <div aria-hidden="true" className="h-[260px] w-full">
        <ResponsiveContainer width="100%" height="100%">
          <ComposedChart data={data} margin={{ top: 8, right: 12, bottom: 0, left: 0 }}>
            <defs>
              <linearGradient id="hw-max-fill" x1="0" y1="0" x2="0" y2="1">
                <stop offset="0%" stopColor={PALETTE.heat} stopOpacity={0.45} />
                <stop offset="100%" stopColor={PALETTE.heat} stopOpacity={0} />
              </linearGradient>
            </defs>
            <CartesianGrid vertical={false} stroke={PALETTE.grid} />
            <XAxis dataKey="day" tick={TICK} tickLine={false} axisLine={{ stroke: PALETTE.axis }} interval="preserveStartEnd" />
            <YAxis domain={[lo, hi]} tick={TICK} tickLine={false} axisLine={false} width={40} unit="°" allowDecimals={false} />
            <Tooltip
              formatter={(v) => (typeof v === "number" ? formatTemp(v) : DASH)}
              contentStyle={TOOLTIP_STYLE}
              labelStyle={{ color: PALETTE.muted }}
              cursor={{ stroke: PALETTE.axis }}
            />
            <Area
              type="monotone"
              dataKey="max"
              name="Daily maximum"
              stroke={PALETTE.heat}
              strokeWidth={2.5}
              fill="url(#hw-max-fill)"
              connectNulls={false}
              animationDuration={900}
            />
            <Line type="monotone" dataKey="min" name="Daily minimum" stroke={PALETTE.cyan} strokeWidth={2} dot={false} animationDuration={900} />
            {hasFeels && (
              <Line
                type="monotone"
                dataKey="feels"
                name="Feels-like daily maximum"
                stroke={PALETTE.amber}
                strokeWidth={2}
                strokeDasharray="5 5"
                dot={false}
                animationDuration={900}
              />
            )}
          </ComposedChart>
        </ResponsiveContainer>
      </div>
      {caption && <figcaption className="mt-2 text-small text-muted">{caption}</figcaption>}
      <table className="sr-only">
        <caption>Forecast daily maximum, minimum and feels-like maximum</caption>
        <thead>
          <tr>
            <th scope="col">Day</th>
            <th scope="col">Maximum</th>
            <th scope="col">Minimum</th>
            <th scope="col">Feels-like maximum</th>
          </tr>
        </thead>
        <tbody>
          {days.map((d) => (
            <tr key={d.date}>
              <th scope="row">{formatDay(d.date)}</th>
              <td>{formatTemp(d.temperature_max_c)}</td>
              <td>{formatTemp(d.temperature_min_c)}</td>
              <td>{formatTemp(d.apparent_temperature_max_c)}</td>
            </tr>
          ))}
        </tbody>
      </table>
    </figure>
  );
}
