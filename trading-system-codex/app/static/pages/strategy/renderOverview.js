import { directionLabel, permissionLabel } from "./adapter.js";

function metric(label, value, escapeHtml) {
  return `
    <article class="strategy-v2-metric">
      <span>${escapeHtml(label)}</span>
      <strong>${escapeHtml(value)}</strong>
    </article>
  `;
}

export function renderOverview(model, helpers) {
  const { escapeHtml, formatNumber, formatDateTime } = helpers;
  const state = model.unified_state;
  const horizons = model.horizon_views;
  return `
    <section class="strategy-unified-overview card">
      <div class="strategy-overview-main">
        <p class="eyebrow">UNIFIED STRATEGY</p>
        <h2>${escapeHtml(state.label || state.code)}</h2>
        <p>${escapeHtml(state.instruction || "等待统一策略推演。")}</p>
        <small>生成时间 ${escapeHtml(formatDateTime(model.generated_at))}</small>
      </div>
      <div class="strategy-overview-metrics">
        ${metric("策略权限", permissionLabel(state.permission), escapeHtml)}
        ${metric("风险等级", state.risk_level || "-", escapeHtml)}
        ${metric("现价", formatNumber(state.current_price, 2), escapeHtml)}
        ${metric("战略", directionLabel(horizons.strategic.direction), escapeHtml)}
        ${metric("战术", directionLabel(horizons.tactical.direction), escapeHtml)}
        ${metric("执行", directionLabel(horizons.execution.direction), escapeHtml)}
      </div>
    </section>
  `;
}
