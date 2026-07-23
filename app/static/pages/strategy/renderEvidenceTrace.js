function asArray(value) {
  return Array.isArray(value) ? value.filter((item) => item !== null && item !== undefined && item !== "") : [];
}

function formatConfidence(value) {
  const number = Number(value);
  if (!Number.isFinite(number)) return "置信不足";
  return `置信 ${Math.round(number)}%`;
}

function textOf(item) {
  return String(item?.human_explanation || item?.summary || item?.message || "").trim();
}

function findTrace(traces, matcher) {
  return traces.find((item) => matcher(String(item?.conclusion_key || ""), item));
}

function shortText(text, limit = 96) {
  if (!text) return "";
  return text.length > limit ? `${text.slice(0, limit)}...` : text;
}

function summaryItem(kind, title, body, meta) {
  return { kind, title, body: shortText(body), meta };
}

function buildEvidenceSummary(model) {
  const traces = asArray(model.evidence_trace);
  const stateTrace = findTrace(traces, (key) => key === "unified_state.code") || {};
  const strategicTrace = findTrace(traces, (key) => key === "horizon_views.strategic.direction") || {};
  const tacticalTrace = findTrace(traces, (key) => key === "horizon_views.tactical.direction") || {};
  const executionTrace = findTrace(traces, (key) => key === "horizon_views.execution.direction") || {};
  const riskTrace = findTrace(traces, (key) => key === "horizon_governance.position_cap")
    || findTrace(traces, (key) => key.includes("risk"))
    || {};
  const state = model.unified_state || {};
  const strategic = model.horizon_views?.strategic || {};
  const tactical = model.horizon_views?.tactical || {};
  const execution = model.horizon_views?.execution || {};
  return [
    summaryItem(
      "decision",
      state.label || stateTrace.conclusion || "最终结论",
      state.instruction || textOf(stateTrace) || "当前结论等待更多数据确认。",
      formatConfidence(stateTrace.confidence),
    ),
    summaryItem(
      "direction",
      "方向依据",
      [
        textOf(strategicTrace) || strategic.instruction,
        textOf(tacticalTrace) || tactical.instruction,
        textOf(executionTrace) || execution.instruction,
      ].filter(Boolean).join(" "),
      `战略 ${strategic.direction || "-"} / 战术 ${tactical.direction || "-"} / 执行 ${execution.direction || "-"}`,
    ),
    summaryItem(
      "risk",
      "风险与缺口",
      textOf(riskTrace) || `仓位上限 ${model.horizon_governance?.position_cap || "-"}；若关键数据缺失或事件门禁触发，暂停提高仓位。`,
      formatConfidence(riskTrace.confidence),
    ),
  ].filter((item) => item.body);
}

function renderSummaryItem(item, escapeHtml) {
  return `
    <article class="strategy-evidence-summary-item ${escapeHtml(item.kind)}">
      <div>
        <h3>${escapeHtml(item.title)}</h3>
        <p>${escapeHtml(item.body)}</p>
      </div>
      <small>${escapeHtml(item.meta || "")}</small>
    </article>
  `;
}

export function renderEvidenceTrace(model, helpers) {
  const { escapeHtml } = helpers;
  const items = buildEvidenceSummary(model);
  return `
    <section class="strategy-v2-section strategy-evidence-trace card">
      <div class="section-heading compact">
        <div>
          <p class="eyebrow">EVIDENCE TRACE</p>
          <h2>结论依据摘要</h2>
        </div>
      </div>
      <div class="strategy-evidence-summary">
        ${items.map((item) => renderSummaryItem(item, escapeHtml)).join("") || helpers.emptyState("暂无证据摘要")}
      </div>
    </section>
  `;
}
