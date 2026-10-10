/** Shared chart styling so every Recharts chart matches the dark-glass theme. */

export const C = {
  accent: "#7dd3fc",
  accentStrong: "#3b82f6",
  accentSoft: "#60a5fa",
  good: "#34d399",
  watch: "#fbbf24",
  risk: "#fb7185",
  muted: "#8590a0",
  grid: "#ffffff14",
};

export const axis = { stroke: C.muted, fontSize: 11, tickLine: false, axisLine: false } as const;

export const tooltip = {
  contentStyle: { background: "#0f141c", border: "1px solid #ffffff26", borderRadius: 12, fontSize: 12 },
  labelStyle: { color: "#b6bfcc" },
  itemStyle: { color: "#f6f3f8" },
  cursor: { stroke: "#ffffff33" },
} as const;

export const compact = new Intl.NumberFormat("en-US", { notation: "compact", maximumFractionDigits: 1 });
