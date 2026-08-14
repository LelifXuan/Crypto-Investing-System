import { directionLabel } from "./adapter.js";
import { rangeStateLabel } from "../../core/rangeState.js";

const STRUCTURE_STATE_LABELS = {
  BULLISH: "上涨结构",
  BEARISH: "下跌结构",
  UPWARD_RANGE: "上行震荡",
  DOWNWARD_RANGE: "下行震荡",
  NEUTRAL_RANGE: "中性震荡",
  RANGE: "区间状态待分类",
  TRANSITION: "结构转换中",
  DATA_UNAVAILABLE: "数据不足",
};

function safeNumber(value) {
  const n = Number(value);
  return Number.isFinite(n) ? n : null;
}

function confidenceFromNode(node) {
  if (node.evidence_ref !== null && node.evidence_ref !== undefined) {
    return safeNumber(node.evidence_confidence);
  }
  return safeNumber(node.confidence);
}

export function renderHorizonStack(model, helpers) {
  const { escapeHtml, formatNumber } = helpers;
  const rows = model.timeframe_stack.map((node) => {
    const structureState = node.range_state && node.range_state !== "NONE"
      ? rangeStateLabel(node)
      : STRUCTURE_STATE_LABELS[node.timeframe_state] || "数据不足";
    const confidence = formatNumber(confidenceFromNode(node), 0);
    return `
      <tr>
        <td><strong>${escapeHtml(node.timeframe)}</strong><small>${escapeHtml(node.role_label)}</small></td>
        <td>${escapeHtml(node.horizon)}</td>
        <td>${escapeHtml(directionLabel(node.direction))}</td>
        <td>${escapeHtml(confidence)}</td>
        <td>${escapeHtml(formatNumber(node.long_score, 0))} / ${escapeHtml(formatNumber(node.short_score, 0))}</td>
        <td>${escapeHtml(structureState)}</td>
      </tr>
    `;
  }).join("");
  return `
    <section class="strategy-v2-section strategy-horizon-stack card">
      <div class="section-heading">
        <div>
          <p class="eyebrow">TIMEFRAME STACK</p>
          <h2>固定六周期证据栈</h2>
        </div>
      </div>
      <div class="table-shell">
        <table class="data-table">
          <thead>
            <tr><th>周期</th><th>视野</th><th>方向</th><th>置信</th><th>多/空分</th><th>结构状态</th></tr>
          </thead>
          <tbody>${rows || `<tr><td colspan="6" class="empty-row">暂无周期证据</td></tr>`}</tbody>
        </table>
      </div>
    </section>
  `;
}
