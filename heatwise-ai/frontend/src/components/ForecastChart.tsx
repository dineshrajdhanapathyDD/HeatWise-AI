import {
  Area,
  CartesianGrid,
  ComposedChart,
  Line,
  ReferenceLine,
  ResponsiveContainer,
  Tooltip,
  XAxis,
  YAxis,
} from "recharts";

import type { DailyForecast } from "../api/types";
import { DASH, formatDay, formatTemp } from "../lib/format";
import { IMD_HEAT_WAVE_C, IMD_PLAINS_C, IMD_SEVERE_C, imdApplies, imdNotAppliedText } from "../lib/imd";
import { PALETTE, TICK, TOOLTIP_STYLE } from "../lib/palette";

interface Props {
  days: DailyForecast[];
  terrain: string | null | undefined;
}

/**
 * Daily max in the heat hue, daily min in cyan, IMD reference lines dashed and labelled.
 * The SVG is hidden from assistive technology; a visually hidden table carries the same data.
 */
export function ForecastChart({ days, terrain }: Props) {
  const imd = imdApplies(terrain);
  const data = days.map((d) => ({ day: formatDay(d.date), max: d.temperature_max_c, min: d.temperature_min_c }));
  const values = data.flatMap((d) => [d.max, d.min]).filter((v): v is number => v !== null);
  // Without IMD lines the axis fits the data alone.
  const lo = Math.floor((Math.min(...values, ...(imd ? [IMD_PLAINS_C] : [])) - 2) / 5) * 5;
  const hi = Math.ceil((Math.max(...values, ...(imd ? [IMD_SEVERE_C] : [])) + 1) / 5) * 5;
  const ticks: number[] = [];
  for (let t = lo; t <= hi; t += 5) ticks.push(t);

  const references = imd
    ? [
        { y: IMD_PLAINS_C, label: `IMD ${IMD_PLAINS_C} °C threshold` },
        { y: IMD_HEAT_WAVE_C, label: `IMD heat wave ${IMD_HEAT_WAVE_C} °C` },
        { y: IMD_SEVERE_C, label: `IMD severe ${IMD_SEVERE_C} °C` },
      ]
    : [];

  return (
    <figure>
      <div aria-hidden="true" className="h-[260px] w-full">
        <ResponsiveContainer width="100%" height="100%">
          <ComposedChart data={data} margin={{ top: 8, right: imd ? 132 : 16, bottom: 0, left: 0 }}>
            <defs>
              <linearGradient id="hw-report-max" x1="0" y1="0" x2="0" y2="1">
                <stop offset="0%" stopColor={PALETTE.heat} stopOpacity={0.35} />
                <stop offset="100%" stopColor={PALETTE.heat} stopOpacity={0} />
              </linearGradient>
            </defs>
            <CartesianGrid vertical={false} stroke={PALETTE.grid} />
            <XAxis dataKey="day" tick={TICK} tickLine={false} axisLine={{ stroke: PALETTE.axis }} interval="preserveStartEnd" />
            <YAxis domain={[lo, hi]} ticks={ticks} tick={TICK} tickLine={false} axisLine={false} width={40} unit="°" />
            {references.map((r) => (
              <ReferenceLine
                key={r.y}
                y={r.y}
                stroke={PALETTE.reference}
                strokeDasharray="4 4"
                label={{ value: r.label, position: "right", fill: PALETTE.muted, fontSize: 12 }}
              />
            ))}
            <Tooltip
              formatter={(v) => (typeof v === "number" ? formatTemp(v) : DASH)}
              contentStyle={TOOLTIP_STYLE}
              labelStyle={{ color: PALETTE.muted }}
            />
            <Area
              type="linear"
              dataKey="max"
              name="Daily maximum"
              stroke={PALETTE.heat}
              strokeWidth={2.5}
              fill="url(#hw-report-max)"
              isAnimationActive={false}
            />
            <Line type="linear" dataKey="min" name="Daily minimum" stroke={PALETTE.cyan} strokeWidth={2} dot={false} isAnimationActive={false} />
          </ComposedChart>
        </ResponsiveContainer>
      </div>
      <figcaption className="mt-2 text-small text-muted">
        {imd
          ? "Dashed lines mark IMD criteria for an indication only, not an official declaration."
          : `${imdNotAppliedText(terrain)}, so no IMD lines are drawn.`}
      </figcaption>
      <table className="sr-only">
        <caption>Forecast daily maximum and minimum temperature</caption>
        <thead>
          <tr>
            <th scope="col">Day</th>
            <th scope="col">Maximum</th>
            <th scope="col">Minimum</th>
          </tr>
        </thead>
        <tbody>
          {days.map((d) => (
            <tr key={d.date}>
              <th scope="row">{formatDay(d.date)}</th>
              <td>{formatTemp(d.temperature_max_c)}</td>
              <td>{formatTemp(d.temperature_min_c)}</td>
            </tr>
          ))}
        </tbody>
      </table>
    </figure>
  );
}
