function formatConfidence(value) {
  const n = Number(value);
  if (!Number.isFinite(n)) return "-";
  return `${Math.round(n)}%`;
}

function safeConfidence(item) {
  if (!item) return 0;
  if (item.evidence_confidence !== undefined && item.evidence_confidence !== null) {
    return Number(item.evidence_confidence) || 0;
  }
  return Number(item.confidence) || 0;
}

function dimensionText(item) {
  const safe = item || {};
  if (safe.details && safe.details.strategy_impact) return safe.details.strategy_impact;
  if (safe.details && safe.details.human_explanation) return safe.details.human_explanation;
  if (safe.summary) return safe.summary;
  if (Array.isArray(safe.evidence) && safe.evidence.length) return safe.evidence[0];
  const bias = safe.bias || safe.direction || "-";
  return `方向 ${bias}`;
}

function statusText(item) {
  const safe = item || {};
  const details = safe.details && typeof safe.details === "object" ? safe.details : {};
  const source = details.source_page || "共享上下文";
  const status = details.data_status || safe.freshness || "unknown";
  const confidence = formatConfidence(safeConfidence(safe));
  return `来源 ${source} · 状态 ${status} · 置信 ${confidence}`;
}

function operationCard(key, item, helpers) {
  const { escapeHtml } = helpers;
  const labels = {
    macro: "宏观",
    macro_regime: "宏观",
    capital_flow: "资金",
    derivatives: "衍生品",
    derivatives_regime: "衍生品",
    onchain: "链上",
    onchain_regime: "链上",
    price_structure: "价格结构",
  };
  const safe = item || {};
  return `
    <article class="strategy-v2-card">
      <p class="eyebrow">${escapeHtml(labels[key] || key)}</p>
      <h3>${escapeHtml(safe.label || labels[key] || "-")}</h3>
      <p>${escapeHtml(dimensionText(safe))}</p>
      <small>${escapeHtml(statusText(safe))}</small>
    </article>
  `;
}

export function renderMarketOperation(model, helpers) {
  const operation = model.market_operation || {};
  const chain = operation.chain || operation;
  const keys = ["macro_regime", "capital_flow", "derivatives_regime", "onchain_regime", "price_structure"];
  return `
    <section class="strategy-v2-section strategy-market-operation card">
      <div class="section-heading">
        <div>
          <p class="eyebrow">MARKET OPERATION</p>
          <h2>跨维度市场作战图</h2>
        </div>
        <p>${helpers.escapeHtml(operation.summary || "宏观、资金、衍生品、链上与价格结构按同一推演链路合成。")}</p>
      </div>
      <div class="strategy-v2-grid five">
        ${keys.map((key) => operationCard(key, chain[key] || operation[key], helpers)).join("")}
      </div>
    </section>
  `;
}