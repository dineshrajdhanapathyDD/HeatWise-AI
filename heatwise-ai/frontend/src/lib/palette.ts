// Hex values for SVG charts (Recharts props), kept equal to the tokens in index.css.
export const PALETTE = {
  ink: "#e6edf7",
  muted: "#93a4c3",
  grid: "#1e2b45",
  axis: "#34486c",
  surface: "#0d1628",
  heat: "#ff7a45",
  amber: "#f5a524",
  coral: "#ff6b5b",
  cyan: "#38c6f4",
  sky: "#6ea8ff",
  reference: "#5d6f92",
} as const;

export const TICK = { fill: PALETTE.muted, fontSize: 12 };

export const TOOLTIP_STYLE = {
  background: "rgba(13, 22, 40, 0.96)",
  border: "1px solid #1f2e4a",
  borderRadius: 10,
  fontSize: 12,
  color: PALETTE.ink,
};
