import { formatNextCheck } from "./formatHelpers.js?v=iso-v1";

function formatConfidence(value) {
  if (value === null || value === undefined || value === "") return "数据不足";
  const n = Number(value);
  if (!Number.isFinite(n) || n <= 0) return "数据不足";
  return `${Math.round(n)}%`;
}

function safeConfidence(item) {
  if (!item) return null;
  if (item.evidence_confidence !== undefined && item.evidence_confidence !== null) {
    const value = Number(item.evidence_confidence);
    return Number.isFinite(value) ? value : null;
  }
  const value = Number(item.confidence);
  return Number.isFinite(value) ? value : null;
}

const INTERNAL_TEXT_PATTERNS = [
  /operation[_-]?bias/i,
  /regime[_-]?key/i,
  /DATA_[A-Z_]+/,
  /RISK_[A-Z_]+/,
  /PRICE_[A-Z_]+/,
  /MACRO_[A-Z_]+/,
  /CAPITAL_[A-Z_]+/,
  /CONTEXT_[A-Z_]+/,
  /战略栈\s*=/,
  /战术栈\s*=/,
  /\[['"]?(LONG|SHORT|NEUTRAL)/,
];

const STATUS_LABELS = {
  fresh: "数据可用",
  ready: "数据可用",
  computed: "本轮已计算",
  usable_stale: "可参考，建议刷新确认",
  stale: "数据偏旧，建议刷新",
  mixed: "多源状态不一致",
  upstream_missing: "上游数据需补齐",
  missing: "数据需补齐",
  unknown: "状态待确认",
};

function isUsefulDecisionText(text) {
  if (!text || typeof text !== "string") return false;
  return !INTERNAL_TEXT_PATTERNS.some((pattern) => pattern.test(text));
}

function fallbackDecisionText(item) {
  const safe = item || {};
  const state = String(safe.state || safe.details?.data_status || safe.freshness || "").toLowerCase();
  const bias = String(safe.bias || safe.direction || "").toUpperCase();
  if (state.includes("missing") || state.includes("degraded") || state.includes("error")) {
    return "该维度数据还不足，暂不参与强方向判断；优先补齐数据后再确认。";
  }
  if (bias === "LONG") return "该维度对多头更友好，可作为顺势或回踩确认的加分项。";
  if (bias === "SHORT") return "该维度对空头更友好，反弹失败或跌破关键位时风险更高。";
  return "当前未形成可执行方向优势，等待突破、回踩或关键结构确认。";
}

function dimensionText(item) {
  const safe = item || {};
  const candidates = [
    safe.details?.strategy_impact,
    safe.details?.human_explanation,
    safe.summary,
    ...(Array.isArray(safe.evidence) ? safe.evidence : []),
  ];
  const useful = candidates.find(isUsefulDecisionText);
  return useful || fallbackDecisionText(safe);
}

function statusText(item) {
  const safe = item || {};
  const details = safe.details && typeof safe.details === "object" ? safe.details : {};
  const status = details.data_status || safe.freshness || "unknown";
  const confidence = formatConfidence(safeConfidence(safe));
  const statusLabel = STATUS_LABELS[status] || STATUS_LABELS[String(status).toLowerCase()] || "状态待确认";
  return `数据状态：${statusLabel} · 置信 ${confidence}`;
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

function effectLabel(value) {
  const map = {
    no_trade: "暂停交易",
    conditional: "条件执行",
    can_confirm: "确认后执行",
    can_support: "支持既有计划",
    observe_levels: "只观察价位",
    observe: "观察",
    reduce: "降低仓位",
    allow_standard_after_trigger: "触发后标准仓位",
    support_existing_plan: "支持既有计划",
    no_size_change: "不改变仓位",
  };
  return map[value] || value || "-";
}

function renderResolutionOperationCard(card, helpers) {
  const { escapeHtml } = helpers;
  const safe = card || {};
  const evidence = Array.isArray(safe.evidence) ? safe.evidence.filter(Boolean).slice(0, 2) : [];
  const evidenceText = evidence.length ? evidence.join(" / ") : safe.next_check || "";
  return `
    <article class="strategy-v2-card">
      <p class="eyebrow">${escapeHtml(safe.title || safe.key || "-")}</p>
      <h3>${escapeHtml(safe.trading_meaning || "-")}</h3>
      <p>${escapeHtml(evidenceText)}</p>
      <small>${escapeHtml(`权限：${effectLabel(safe.permission_effect)} · 仓位：${effectLabel(safe.position_effect)}${formatNextCheck(safe) ? ` · ${formatNextCheck(safe)}` : ""}`)}</small>
    </article>
  `;
}

export function renderMarketOperation(model, helpers) {
  const operation = model.market_operation || {};
  const resolutionCards = Array.isArray(model.operation_cards) && model.operation_cards.length
    ? model.operation_cards
    : Array.isArray(operation.operation_cards) ? operation.operation_cards : [];
  const chain = operation.chain || operation;
  const keys = ["macro_regime", "capital_flow", "derivatives_regime", "onchain_regime", "price_structure"];
  const cardsHtml = resolutionCards.length
    ? resolutionCards.map((card) => renderResolutionOperationCard(card, helpers)).join("")
    : keys.map((key) => operationCard(key, chain[key] || operation[key], helpers)).join("");
  const shadowOnly = model.direction_resolution?.affects_active_decision === false;
  return `
    <section class="strategy-v2-section strategy-market-operation card">
      <div class="section-heading">
        <div>
          <p class="eyebrow">MARKET OPERATION</p>
          <h2>跨维度市场作战图</h2>
          ${shadowOnly ? '<small>以下规则模型处于影子模式，不改变当前主策略方向</small>' : ""}
        </div>
        <p>${helpers.escapeHtml(operation.summary || "宏观、资金、衍生品、链上与价格结构按同一推演链路合成。")}</p>
      </div>
      <div class="strategy-v2-grid five">
        ${cardsHtml}
      </div>
    </section>
  `;
}
