import { directionLabel, verdictLabel } from "./adapter.js";

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
    const verdict = verdictLabel(node.verdict_code || "RANGE_NO_EDGE");
    const confidence = formatNumber(confidenceFromNode(node), 0);
    return `
      <tr>
        <td><strong>${escapeHtml(node.timeframe)}</strong><small>${escapeHtml(node.role_label)}</small></td>
        <td>${escapeHtml(node.horizon)}</td>
        <td>${escapeHtml(directionLabel(node.direction))}</td>
        <td>${escapeHtml(confidence)}</td>
        <td>${escapeHtml(formatNumber(node.long_score, 0))} / ${escapeHtml(formatNumber(node.short_score, 0))}</td>
        <td>${escapeHtml(verdict)}</td>
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
            <tr><th>周期</th><th>视野</th><th>方向</th><th>置信</th><th>多/空分</th><th>结论</th></tr>
          </thead>
          <tbody>${rows || `<tr><td colspan="6" class="empty-row">暂无周期证据</td></tr>`}</tbody>
        </table>
      </div>
    </section>
  `;
}