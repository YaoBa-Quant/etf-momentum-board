// P1–P10 横截面动量档位色板（绿=最弱 → 红=最强），HeatCell 与图例共用。

export interface TierStyle {
  bg: string;
  text: string;
}

export const TIER_ORDER = [
  "P1",
  "P2",
  "P3",
  "P4",
  "P5",
  "P6",
  "P7",
  "P8",
  "P9",
  "P10",
] as const;

export type TierName = (typeof TIER_ORDER)[number];

export const TIER_STYLE: Record<TierName, TierStyle> = {
  P1: { bg: "#2e7d32", text: "#ffffff" },
  P2: { bg: "#4caf50", text: "#ffffff" },
  P3: { bg: "#8bc34a", text: "#ffffff" },
  P4: { bg: "#cddc39", text: "#1f2937" },
  P5: { bg: "#ffeb3b", text: "#1f2937" },
  P6: { bg: "#ffc107", text: "#1f2937" },
  P7: { bg: "#ff9800", text: "#1f2937" },
  P8: { bg: "#f57c00", text: "#ffffff" },
  P9: { bg: "#f4511e", text: "#ffffff" },
  P10: { bg: "#e53935", text: "#ffffff" },
};

export const getTierStyle = (tier: string | null | undefined): TierStyle | null =>
  tier && (tier in TIER_STYLE) ? TIER_STYLE[tier as TierName] : null;
