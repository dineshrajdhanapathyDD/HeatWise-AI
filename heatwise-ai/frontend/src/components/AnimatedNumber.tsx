import { animate, useReducedMotion } from "framer-motion";
import { useEffect, useRef, useState } from "react";

import { DASH } from "../lib/format";

interface Props {
  value: number | null | undefined;
  format: (n: number) => string;
  className?: string;
}

/**
 * Counts up to a real value once it scrolls into view. Screen readers only ever get the final value (the
 * counting digits are aria-hidden). Without IntersectionObserver, or with reduced motion, the final value
 * renders at once as plain text. Missing values show a dash, never a number.
 */
export function AnimatedNumber({ value, format, className }: Props) {
  const reduce = useReducedMotion();
  const ref = useRef<HTMLSpanElement>(null);
  const canAnimate = !reduce && typeof IntersectionObserver !== "undefined" && value !== null && value !== undefined;
  const [shown, setShown] = useState<number | null>(canAnimate ? 0 : (value ?? null));

  useEffect(() => {
    // Without animation the final value renders directly below, so there is nothing to sync here.
    if (!canAnimate || value === null || value === undefined) return;
    const el = ref.current;
    if (!el) return;
    let stop: (() => void) | undefined;
    const io = new IntersectionObserver(
      (entries) => {
        if (!entries.some((e) => e.isIntersecting)) return;
        io.disconnect();
        const controls = animate(0, value, { duration: 0.9, ease: [0.16, 1, 0.3, 1], onUpdate: setShown });
        stop = () => controls.stop();
      },
      { threshold: 0.3 },
    );
    io.observe(el);
    return () => {
      io.disconnect();
      stop?.();
    };
  }, [value, canAnimate]);

  if (value === null || value === undefined) return <span className={className}>{DASH}</span>;
  const final = format(value);
  if (!canAnimate) return <span className={className}>{final}</span>;
  return (
    <span ref={ref} className={className}>
      <span aria-hidden="true">{shown === null ? final : format(shown)}</span>
      <span className="sr-only">{final}</span>
    </span>
  );
}
