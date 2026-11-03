/** Shown for any missing value. */
export const DASH = "\u2014";
/** Keeps a value and its unit on one line ("44.5 °C" never breaks before °C). */
const NBSP = "\u00a0";

export function formatTemp(value: number | null | undefined): string {
  return value === null || value === undefined ? DASH : `${value.toFixed(1)}${NBSP}°C`;
}

export function formatPct(value: number | null | undefined, decimals = 0): string {
  return value === null || value === undefined ? DASH : `${value.toFixed(decimals)}%`;
}

export function formatNumber(value: number | null | undefined, unit?: string | null): string {
  if (value === null || value === undefined) return DASH;
  const text = Number.isInteger(value) ? String(value) : value.toFixed(1);
  return unit ? `${text} ${unit}` : text;
}

/** A change with its sign: "+2.1 °C", "-0.5 °C", "0.0 °C". */
export function formatDelta(value: number | null | undefined, unit = "°C"): string {
  if (value === null || value === undefined) return DASH;
  const sign = value > 0 ? "+" : value < 0 ? "-" : "";
  return `${sign}${Math.abs(value).toFixed(1)}${NBSP}${unit}`;
}

export function formatDuration(ms: number | null | undefined): string {
  if (ms === null || ms === undefined) return DASH;
  return ms >= 1000 ? `${(ms / 1000).toFixed(1)}${NBSP}s` : `${ms.toFixed(1)}${NBSP}ms`;
}

/** Date and time with the time zone named, e.g. "10 May 2026, 14:30 IST". */
export function formatDateTime(iso: string | null | undefined, timeZone?: string | null): string {
  if (!iso) return DASH;
  const date = new Date(iso);
  if (Number.isNaN(date.getTime())) return DASH;
  const opts: Intl.DateTimeFormatOptions = {
    day: "numeric",
    month: "short",
    year: "numeric",
    hour: "2-digit",
    minute: "2-digit",
    hourCycle: "h23",
    timeZoneName: "short",
  };
  try {
    return new Intl.DateTimeFormat("en-GB", { ...opts, timeZone: timeZone ?? undefined }).format(date);
  } catch {
    return new Intl.DateTimeFormat("en-GB", opts).format(date);
  }
}

/** A forecast date ("2026-05-10") as "Sun 10 May". */
export function formatDay(isoDate: string): string {
  const date = new Date(`${isoDate}T00:00:00Z`);
  if (Number.isNaN(date.getTime())) return isoDate;
  return new Intl.DateTimeFormat("en-GB", { weekday: "short", day: "numeric", month: "short", timeZone: "UTC" }).format(
    date,
  );
}

export function placeName(parts: (string | null | undefined)[]): string {
  return parts.filter((p): p is string => Boolean(p && p.trim())).join(", ");
}
