/** HeatWise mark: the sun sitting on the horizon, in the heat hue over an ink line. */
export function Mark({ size = 20 }: { size?: number }) {
  return (
    <svg width={size} height={size} viewBox="0 0 20 20" aria-hidden="true" focusable="false">
      <circle cx="10" cy="9" r="5.5" fill="var(--color-heat)" />
      <rect x="2" y="15" width="16" height="2.5" rx="1.25" fill="var(--color-ink)" />
    </svg>
  );
}
