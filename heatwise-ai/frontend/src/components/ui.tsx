import { motion } from "framer-motion";
import type { LucideIcon } from "lucide-react";
import type { ReactNode } from "react";

/** Section heading with an optional eyebrow, a description and actions on the right. */
export function SectionHeading({
  id,
  eyebrow,
  title,
  description,
  actions,
  level = 2,
}: {
  id: string;
  eyebrow?: string;
  title: string;
  description?: ReactNode;
  actions?: ReactNode;
  level?: 2 | 3;
}) {
  const H = level === 2 ? "h2" : "h3";
  return (
    <div className="flex flex-wrap items-end justify-between gap-3">
      <div className="min-w-0">
        {eyebrow && <p className="eyebrow">{eyebrow}</p>}
        <H id={id} className={`${eyebrow ? "mt-1" : ""} text-section font-semibold`}>
          {title}
        </H>
        {description && <p className="mt-1 max-w-[70ch] text-body text-muted">{description}</p>}
      </div>
      {actions}
    </div>
  );
}

/** Says where a figure comes from, e.g. "Measured from stored reports" or "From the latest assessment". */
export function DataTag({ children, tone = "measured" }: { children: string; tone?: "measured" | "synthetic" | "unavailable" }) {
  const cls =
    tone === "synthetic"
      ? "border-sky/30 bg-sky/10 text-sky"
      : tone === "unavailable"
        ? "border-line bg-raised text-muted"
        : "border-positive/25 bg-positive/10 text-pos-ink";
  return (
    <span className={`inline-flex h-6 items-center whitespace-nowrap rounded-full border px-2.5 text-small font-medium ${cls}`}>
      {children}
    </span>
  );
}

/** A metric card: label, value (any node, often an AnimatedNumber) and a caption. */
export function MetricCard({
  label,
  value,
  caption,
  icon: Icon,
  accent,
  index = 0,
}: {
  label: string;
  value: ReactNode;
  caption?: ReactNode;
  icon?: LucideIcon;
  accent?: string;
  index?: number;
}) {
  return (
    <motion.div
      initial={{ opacity: 0, y: 10 }}
      whileInView={{ opacity: 1, y: 0 }}
      viewport={{ once: true, margin: "-40px" }}
      transition={{ delay: index * 0.05, duration: 0.35, ease: "easeOut" }}
      className="glass lift relative overflow-hidden rounded-card p-5"
    >
      {accent && (
        <span aria-hidden="true" className="absolute inset-x-0 top-0 h-0.5" style={{ background: accent }} />
      )}
      <div className="flex items-center justify-between gap-2">
        <dt className="text-small font-medium text-muted">{label}</dt>
        {Icon && <Icon size={18} strokeWidth={1.75} aria-hidden="true" className="flex-none text-muted" />}
      </div>
      <dd className="mt-2">
        <span className="num block text-kpi font-semibold">{value}</span>
        {caption && <span className="mt-1 line-clamp-2 block text-small text-muted">{caption}</span>}
      </dd>
    </motion.div>
  );
}

/** Loading placeholder bars. */
export function SkeletonLines({ lines = 3, className = "" }: { lines?: number; className?: string }) {
  return (
    <div aria-hidden="true" className={`space-y-2 ${className}`}>
      {Array.from({ length: lines }, (_, i) => (
        <div key={i} className="skeleton h-5" style={{ width: `${90 - i * 18}%` }} />
      ))}
    </div>
  );
}

/** Panel for data the backend does not provide: names the missing field instead of inventing it. */
export function Unavailable({ title, reason, field }: { title: string; reason: string; field: string }) {
  return (
    <div className="rounded-control border border-dashed border-control p-4">
      <p className="text-body font-medium">{title}</p>
      <p className="mt-1 text-small text-muted">{reason}</p>
      <p className="mt-2 text-small">
        <span className="text-muted">Missing field: </span>
        <code className="rounded-chip bg-raised px-1.5 py-0.5 text-small text-ink">{field}</code>
      </p>
    </div>
  );
}
