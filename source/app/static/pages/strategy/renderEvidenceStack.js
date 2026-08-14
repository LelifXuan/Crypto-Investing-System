import { cleanUserText, directionLabel, riskLevelLabel } from "./adapter.js?v=compact-v3";
import { rangeStateLabel } from "../../core/rangeState.js";
import { formatNextCheck } from "./formatHelpers.js?v=iso-v1";

const STRUCTURE_LABELS = {
  BULLISH: "上涨结构",
  BEARISH: "下跌结构",
  UPWARD_RANGE: "上行震荡",
  DOWNWARD_RANGE: "下行震荡",
  NEUTRAL_RANGE: "中性震荡",
  RANGE: "区间状态待分类",
  TRANSITION: "转换中",
  DATA_UNAVAILABLE: "数据不足",
};

function confidence(value) {
  const number = Number(value);
  return Number.isFinite(number) ? `${Math.round(number)}%` : "-";
}

function evidenceText(model) {
  const traces = Array.isArray(model.evidence_trace) ? model.evidence_trace : [];
  return traces
    .map((item) => item?.human_explanation || item?.summary || item?.message)
    .filter(Boolean)
    .slice(0, 3)
    .map(cleanUserText);
}

function watchItems(model) {
  const narrative = model.narrative || {};
  const watchlist = Array.isArray(narrative.watchlist) ? narrative.watchlist : [];
  return watchlist.slice(0, 6);
}

export function renderEvidenceStack(model, helpers) {
  const { escapeHtml, formatNumber } = helpers;
  const decision = model.trade_decision || {};
  const narrative = model.narrative || {};
  const nodes = Array.isArray(model.timeframe_stack) ? model.timeframe_stack : [];
  const evidence = evidenceText(model);
  const watches = watchItems(model);
  const rows = nodes.map((node) => `
    <tr>
      <td><strong>${escapeHtml(node.timeframe)}</strong><small>${escapeHtml(node.role_label)}</small></td>
      <td>${escapeHtml(node.range_state && node.range_state !== "NONE" ? rangeStateLabel(node) : STRUCTURE_LABELS[node.timeframe_state] || "状态待确认")}</td>
      <td>${escapeHtml(directionLabel(node.direction))}</td>
      <td class="numeric">${escapeHtml(`${formatNumber(node.long_score, 0)} / ${formatNumber(node.short_score, 0)}`)}</td>
      <td class="numeric">${escapeHtml(confidence(node.evidence_confidence ?? node.confidence))}</td>
    </tr>
  `).join("");
  return `
    <section class="strategy-v2-section strategy-evidence-stack card">
      <div class="section-heading strategy-compact-heading">
        <div>
          <p class="eyebrow">EVIDENCE & TIMEFRAMES</p>
          <h2>周期证据与后续观察</h2>
        </div>
      </div>
      <div class="strategy-evidence-lead">
        <strong>${escapeHtml(cleanUserText(narrative.headline || decision.primary_reason?.message || "等待周期证据确认"))}</strong>
        <p>${escapeHtml(cleanUserText(narrative.action || decision.entry_condition || "等待下一周期收盘确认。"))}</p>
      </div>
      <div class="table-shell strategy-timeframe-table-shell">
        <table class="data-table strategy-timeframe-table">
          <thead><tr><th>周期</th><th>结构</th><th>方向</th><th>多/空分</th><th>置信</th></tr></thead>
          <tbody>${rows || `<tr><td colspan="5" class="empty-row">暂无周期证据</td></tr>`}</tbody>
        </table>
      </div>
      <div class="strategy-evidence-footer">
        <article>
          <span>关键依据</span>
          <ul>${evidence.map((item) => `<li>${escapeHtml(item)}</li>`).join("") || "<li>暂无额外证据</li>"}</ul>
        </article>
        <article>
          <span>风险与下一检查</span>
          <p>${escapeHtml(`当前${riskLevelLabel(model.unified_state?.risk_level)}；${formatNextCheck(decision, "下一检查 ")}`)}</p>
          <ul>${watches.map((item) => `<li><strong>${escapeHtml(item.timeframe || "-")}</strong> ${escapeHtml(item.condition || item.indicator || "等待确认")}</li>`).join("") || "<li>等待下一周期收盘</li>"}</ul>
        </article>
      </div>
    </section>
  `;
}
