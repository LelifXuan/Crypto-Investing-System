export const RANGE_STATE_LABELS = Object.freeze({
  UPWARD_RANGE: "上行震荡",
  DOWNWARD_RANGE: "下行震荡",
  NEUTRAL_RANGE: "中性震荡",
  NONE: "",
});

export function rangeStateLabel(value, fallback = "状态待确认") {
  const code = String(value?.range_state || value || "").toUpperCase();
  return value?.range_label || RANGE_STATE_LABELS[code] || fallback;
}

export function rangeStateTone(value) {
  const code = String(value?.range_state || value || "").toUpperCase();
  if (code === "UPWARD_RANGE") return "bullish";
  if (code === "DOWNWARD_RANGE") return "bearish";
  return "neutral";
}
