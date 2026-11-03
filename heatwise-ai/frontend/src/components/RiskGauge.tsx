import { motion } from "framer-motion";

import { riskLabel } from "../lib/risk";
import { RISK_ORDER, riskHue, riskIndex } from "../lib/riskScale";

const CX = 110;
const CY = 110;
const R = 84;

function polar(angleDeg: number, r = R) {
  const a = ((angleDeg - 180) * Math.PI) / 180;
  return { x: CX + r * Math.cos(a), y: CY + r * Math.sin(a) };
}

function arc(from: number, to: number) {
  const s = polar(from);
  const e = polar(to);
  return `M ${s.x} ${s.y} A ${R} ${R} 0 0 1 ${e.x} ${e.y}`;
}

/**
 * Semicircle showing where the backend's risk category sits on its five-step scale. The needle points at the
 * category it was given; "unknown" draws no needle. The text label below is the accessible content.
 */
export function RiskGauge({ category, caption }: { category: string | null | undefined; caption?: string }) {
  const idx = riskIndex(category);
  const segment = 180 / RISK_ORDER.length;
  const gap = 2.5;
  const needleAngle = idx === null ? null : segment * idx + segment / 2;

  return (
    <figure className="flex flex-col items-center">
      <svg viewBox="0 0 220 128" className="w-full max-w-[260px]" aria-hidden="true" focusable="false">
        {RISK_ORDER.map((c, i) => (
          <path
            key={c}
            d={arc(i * segment + gap, (i + 1) * segment - gap)}
            fill="none"
            stroke={riskHue(c)}
            strokeWidth="16"
            strokeLinecap="round"
            opacity={idx === null ? 0.25 : i === idx ? 1 : 0.28}
          />
        ))}
        {needleAngle !== null && (
          <motion.g
            initial={{ rotate: 0 }}
            animate={{ rotate: needleAngle }}
            transition={{ type: "spring", stiffness: 60, damping: 14 }}
            // view-box makes the origin an SVG coordinate (the hub), not the needle's own bounding box.
            style={{ transformBox: "view-box", transformOrigin: `${CX}px ${CY}px` }}
          >
            <line x1={CX} y1={CY} x2={CX - 66} y2={CY} stroke="#e6edf7" strokeWidth="4" strokeLinecap="round" />
          </motion.g>
        )}
        <circle cx={CX} cy={CY} r="8" fill="#e6edf7" />
        <circle cx={CX} cy={CY} r="3.5" fill="#0d1628" />
      </svg>
      <figcaption className="-mt-1 text-center">
        <span className="block text-title font-semibold" style={{ color: riskHue(category) }}>
          {riskLabel(category)}
        </span>
        <span className="mt-0.5 block text-small text-muted">{caption ?? "Category set by the backend's rules"}</span>
      </figcaption>
    </figure>
  );
}
