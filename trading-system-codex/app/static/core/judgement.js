const AXIS_LABELS = {
  price_structure: "价格结构",
  momentum: "动能",
  trend_strength: "趋势强度",
  volatility: "波动率",
  capital_flow: "资金流",
  liquidity: "流动性",
  derivatives_positioning: "衍生品持仓",
  crowding: "拥挤度",
  risk: "风险",
  event: "事件",
  data_quality: "数据质量",
};

const EFFECT_LABELS = {
  SUPPORT: "方向支持",
  CONFIRM: "等待确认",
  DOWNGRADE: "风险降级",
  BLOCK: "交易阻断",
  LEVEL_ONLY: "仅关键价位",
  OBSERVE: "仅观察",
};

const STATE_LABELS = {
  // Compatibility aliases from pre-contract indicator snapshots.
  BULLISH: "看多",
  BEARISH: "看空",
  NEUTRAL: "方向平衡",
  NORMAL: "正常",
  STABLE: "持仓稳定",
  EXPANDED: "波动扩张",
  COMPRESSED: "波动收缩",
  OVERBOUGHT: "超买",
  OVERSOLD: "超卖",
  BULLISH_STRUCTURE: "上涨结构",
  BEARISH_STRUCTURE: "下跌结构",
  MIXED_STRUCTURE: "结构交错",
  STRONG_TREND: "强趋势",
  DEVELOPING_TREND: "趋势形成中",
  WEAK_TREND: "趋势较弱",
  POSITIVE_MOMENTUM: "正向动能",
  NEGATIVE_MOMENTUM: "负向动能",
  POSITIVE_ACCELERATING: "多头动能增强",
  POSITIVE_DECELERATING: "多头动能衰减",
  NEGATIVE_ACCELERATING: "空头动能增强",
  NEGATIVE_DECELERATING: "空头动能衰减",
  OVERBOUGHT_RISK: "超买风险",
  OVERSOLD_RISK: "超卖风险",
  BALANCED_MOMENTUM: "动能平衡",
  HIGH_VOLATILITY: "高波动",
  NORMAL_VOLATILITY: "正常波动",
  NORMAL_OR_COMPRESSION: "正常或压缩",
  EXPANSION_BREAKOUT_UP: "向上波动扩张",
  EXPANSION_BREAKOUT_DOWN: "向下波动扩张",
  DATA_UNAVAILABLE: "数据不足",
  UNREGISTERED: "语义待登记",
};

export function judgementMeta(judgement = {}) {
  const rawState = String(judgement.state || "").trim();
  const stateKey = rawState.toUpperCase();
  const contextualState = stateKey === "NEUTRAL" && judgement.axis === "crowding"
    ? "拥挤度中性"
    : STATE_LABELS[stateKey];
  return {
    axisLabel: AXIS_LABELS[judgement.axis] || judgement.axis || "指标状态",
    stateLabel: contextualState || "状态待确认",
    effectLabel: EFFECT_LABELS[judgement.action_effect] || judgement.action_effect || "仅观察",
    dataLabel: judgement.data_status === "ready" ? "数据可用" : judgement.data_status === "unregistered" ? "待登记" : "数据不足",
  };
}
