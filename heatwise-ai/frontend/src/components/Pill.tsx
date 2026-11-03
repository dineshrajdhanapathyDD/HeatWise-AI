import type { ReportStatus } from "../api/types";
import { TONE_CLASSES, type Tone, riskLabel, riskTone, statusLabel, statusTone } from "../lib/risk";

export function Pill({ tone, children }: { tone: Tone; children: string }) {
  return (
    <span
      className={`inline-flex h-5 flex-none items-center whitespace-nowrap rounded-chip px-2 text-small font-medium ${TONE_CLASSES[tone]}`}
    >
      {children}
    </span>
  );
}

/** Risk category as a pale pill that always carries its text label. */
export function RiskLabel({ category, prefix = "Risk: " }: { category: string | null | undefined; prefix?: string }) {
  return <Pill tone={riskTone(category)}>{`${prefix}${riskLabel(category)}`}</Pill>;
}

export function StatusLabel({ status }: { status: ReportStatus }) {
  return <Pill tone={statusTone(status)}>{statusLabel(status)}</Pill>;
}
