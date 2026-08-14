import {
  decisionStatusLabel,
  directionLabel,
  permissionLabel,
  riskLevelLabel,
} from "./adapter.js?v=trade-4h-v1";
import { formatEntryDistance, staleToneFor } from "./formatHelpers.js?v=iso-v2-stale";

function metric(label, value, escapeHtml, numeric = false) {
  return `
    <article class="strategy-v2-metric${numeric ? " numeric" : ""}">
      <span>${escapeHtml(label)}</span>
      <strong>${escapeHtml(value)}</strong>
    </article>
  `;
}

export function renderOverview(model, helpers) {
  const { escapeHtml, formatNumber, formatDateTime } = helpers;
  const state = model.unified_state;
  const tradeDecision = model.trade_decision || {};
  const decisionHeadline = tradeDecision.primary_reason?.message || state.label || state.code;
  const leverage = Number(tradeDecision.recommended_leverage || 0);
  const headline = decisionStatusLabel(tradeDecision.status, tradeDecision.side);
  const distancePct = Number(tradeDecision.plan_distance_pct || 0);
  const staleScore = Number(tradeDecision.plan_stale_score || 0);
  // V1.7.x: when a conditional-limit plan has drifted more than 1.5%
  // from the live price, replace the "建议杠杆" tile with an explicit
  // distance chip so the user immediately sees how far the trigger has
  // moved. The tile collapses back to the leverage row when the plan
  // is fresh or status is market / none.
  const showStaleChip =
    tradeDecision.order_type === "CONDITIONAL_LIMIT"
    && Number.isFinite(distancePct)
    && distancePct > 0;
  const staleChip = showStaleChip
    ? `
      <article class="strategy-v2-metric strategy-v2-metric-stale" data-tone="${escapeHtml(staleToneFor(tradeDecision))}">
        <span>距离触发</span>
        <strong>${escapeHtml(formatEntryDistance(tradeDecision) || `${distancePct.toFixed(2)}%`)}</strong>
      </article>
    `
    : "";
  return `
    <section class="strategy-unified-overview card">
      <div class="strategy-overview-main">
        <p class="eyebrow">UNIFIED STRATEGY</p>
        <h2>${escapeHtml(headline)}</h2>
        <p>${escapeHtml(decisionHeadline)}</p>
        <small>生成时间 ${escapeHtml(formatDateTime(model.generated_at))}</small>
      </div>
      <div class="strategy-overview-metrics">
        ${metric("当前状态", permissionLabel(tradeDecision.permission || state.permission), escapeHtml)}
        ${metric("交易方向", directionLabel(tradeDecision.side), escapeHtml)}
        ${metric("风险等级", riskLevelLabel(state.risk_level), escapeHtml)}
        ${metric("现价", formatNumber(state.current_price, 2), escapeHtml, true)}
        ${showStaleChip
          ? staleChip
          : metric("建议杠杆", leverage > 0 ? `${formatNumber(leverage, 0)}×` : "暂不使用", escapeHtml, true)}
      </div>
    </section>
  `;
}
