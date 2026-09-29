import { cleanUserText } from "./adapter.js?v=compact-v3";

const PERIOD_LABEL = { "1w": "周线", "1d": "日线", "4h": "4H" };

export function renderTimeframeFocus(model, timeframe, helpers) {
  const { escapeHtml, formatNumber } = helpers;
  const node = (model.timeframe_stack || []).find((item) => item?.timeframe === timeframe);
  const period = PERIOD_LABEL[timeframe] || timeframe.toUpperCase();
  if (!node) {
    return `<section class="strategy-timeframe-focus card" data-timeframe="${escapeHtml(timeframe)}">
      <p class="eyebrow">SELECTED TIMEFRAME · ${escapeHtml(period)}</p>
      <h2>${escapeHtml(period)}数据待发布</h2>
      <p>该周期尚无独立判断，等待后台快照更新。</p>
    </section>`;
  }

  const side = String(node.direction || "WAIT").toUpperCase();
  const directional = side === "LONG" || side === "SHORT";
  const tone = side === "LONG" ? "bullish" : side === "SHORT" ? "bearish" : "neutral";
  const conclusion = side === "LONG" ? "做多" : side === "SHORT" ? "做空" : "等待确认";
  const evidence = (Array.isArray(node.evidence) ? node.evidence : [])
    .map((item) => cleanUserText(String(item || "")))
    .filter((item) => item && !item.includes("当前策略状态") && !item.includes("INVALID_PLAN_LEVELS"))
    .slice(0, 2);
  const score = (value) => Number.isFinite(Number(value)) ? formatNumber(value, 0) : "—";
  const confidence = node.confidence == null ? "—" : `${score(node.confidence)}%`;
  const livePrice = node.current_price ?? model.unified_state?.current_price;
  const metrics = [
    ["多 / 空评分", `${score(node.long_score)} / ${score(node.short_score)}`],
    ...([
      ["现价", livePrice],
      ["支撑参考", node.key_support],
      ["压力参考", node.key_resistance],
      ["结构失效参考", node.invalidation],
    ].filter(([, value]) => value != null).map(([label, value]) => [label, formatNumber(value, 2)])),
  ];

  return `<section class="strategy-timeframe-focus card" data-timeframe="${escapeHtml(timeframe)}" data-tone="${tone}">
    <div class="strategy-timeframe-focus-head">
      <div>
        <p class="eyebrow">SELECTED TIMEFRAME · ${escapeHtml(period)}</p>
        <h2>${escapeHtml(period)}判断：${escapeHtml(conclusion)}</h2>
        <p>该周期的结构证据用于上方独立交易机会的方向判断；执行价位来自下一交易级别。</p>
      </div>
      <span class="strategy-timeframe-focus-confidence">置信度 ${escapeHtml(confidence)}</span>
    </div>
    <div class="strategy-timeframe-focus-metrics">
      ${metrics.map(([label, value]) => `<div><span>${escapeHtml(label)}</span><strong>${escapeHtml(value)}</strong></div>`).join("")}
    </div>
    ${evidence.length ? `<ul class="strategy-timeframe-focus-evidence">${evidence.map((line) => `<li>${escapeHtml(line)}</li>`).join("")}</ul>` : ""}
  </section>`;
}
