import { formatNextCheck } from "./formatHelpers.js?v=iso-v1";
import { cleanUserText, directionLabel } from "./adapter.js?v=range-direction-v1";

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

const CATEGORY_FALLBACKS = {
  macro: "宏观数据尚未完整到达；本轮不判断利率、美元与风险偏好对仓位的影响。",
  macro_regime: "宏观数据尚未完整到达；本轮不判断利率、美元与风险偏好对仓位的影响。",
  capital_flow: "资金流数据尚未完整到达；本轮不把稳定币、现货成交与资金广度计入方向。",
  derivatives_regime: "衍生品数据尚未完整到达；本轮不使用资金费率、持仓量与期权结构确认方向。",
  onchain_regime: "链上数据尚未完整到达；本轮不把链上活动计入中长期方向置信。",
  price_structure: "价格结构数据尚未完整到达；当前无法确定支撑、阻力、突破与失效位置。",
  supply_event_regime: "供给事件数据尚未完整到达；当前不把计划解锁解释为方向信号。",
};

const CATEGORY_DIRECTION_COPY = {
  macro: {
    LONG: "利率、美元与风险偏好组合对风险资产偏友好，可提高多头策略的宏观置信，但不单独决定入场。",
    SHORT: "利率、美元与风险偏好组合对风险资产形成压力，应降低多头仓位并提高空头策略的宏观置信。",
    NEUTRAL: "宏观变量对风险资产的影响接近平衡，本类别暂不增减方向分。",
  },
  capital_flow: {
    LONG: "稳定币、现货成交与资金广度偏向流入，多头方向获得资金面确认。",
    SHORT: "稳定币、现货成交与资金广度偏向流出，空头方向获得资金面确认。",
    NEUTRAL: "资金流入与流出证据接近平衡，本类别暂不增减方向分。",
  },
  derivatives: {
    LONG: "资金费率、持仓量与期权结构综合偏多，为多头方向提供确认。",
    SHORT: "资金费率、持仓量与期权结构综合偏空，为空头方向提供确认。",
    NEUTRAL: "衍生品仓位与定价信号互相抵消，本类别暂不增减方向分。",
  },
  onchain: {
    LONG: "链上活动与持币行为偏向积累，可提高中长期多头置信。",
    SHORT: "链上活动与持币行为偏向派发，可提高中长期空头置信。",
    NEUTRAL: "链上活动未形成明确积累或派发优势，本类别暂不增减方向分。",
  },
  price_structure: {
    LONG: "价格结构偏多，支撑、突破位与失效位将用于确定具体多头计划。",
    SHORT: "价格结构偏空，阻力、跌破位与失效位将用于确定具体空头计划。",
    NEUTRAL: "价格仍在关键区间内，需结合区间位置和其他类别选择优先方向。",
  },
  technical: {
    LONG: "趋势与动量指标偏多，为多头方向提供技术确认。",
    SHORT: "趋势与动量指标偏空，为空头方向提供技术确认。",
    NEUTRAL: "趋势与动量指标互相抵消，本类别暂不增减方向分。",
  },
};

function fallbackDecisionText(item, key) {
  const safe = item || {};
  const state = String(safe.state || safe.details?.data_status || safe.freshness || "").toLowerCase();
  const bias = String(safe.bias || safe.direction || "").toUpperCase();
  if (state.includes("missing") || state.includes("degraded") || state.includes("error")) {
    return CATEGORY_FALLBACKS[key] || "该维度数据还不足，本轮不参与方向评分。";
  }
  const categoryCopy = CATEGORY_DIRECTION_COPY[key];
  if (categoryCopy) return categoryCopy[bias] || categoryCopy.NEUTRAL;
  if (bias === "LONG") return "该维度对多头更友好，可作为方向确认的加分项。";
  if (bias === "SHORT") return "该维度对空头更友好，可作为方向确认的加分项。";
  return CATEGORY_FALLBACKS[key] || "该维度当前多空影响接近平衡。";
}

function dimensionText(item, key) {
  const safe = item || {};
  const candidates = [
    safe.details?.strategy_impact,
    safe.details?.human_explanation,
    safe.summary,
    ...(Array.isArray(safe.evidence) ? safe.evidence : []),
  ];
  const useful = candidates.find(isUsefulDecisionText);
  return useful || fallbackDecisionText(safe, key);
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
    supply_event_regime: "供给事件",
  };
  const safe = item || {};
  return `
    <article class="strategy-v2-card">
      <p class="eyebrow">${escapeHtml(labels[key] || key)}</p>
      <h3>${escapeHtml(safe.label || labels[key] || "-")}</h3>
      <p>${escapeHtml(dimensionText(safe, key))}</p>
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

function isMethodologyText(text) {
  return [
    /只有在.+才/,
    /采用.+区间/,
    /只能用于确认/,
    /不能单独/,
    /只影响风险和仓位/,
    /低周期只用于/,
    /高周期决定/,
  ].some((pattern) => pattern.test(text));
}

function keyLevelText(levels) {
  if (!levels || typeof levels !== "object") return "";
  const labels = {
    support: "支撑",
    resistance: "阻力",
    invalidation: "失效位",
    call_wall: "看涨期权持仓墙",
    put_wall: "看跌期权持仓墙",
    max_pain: "最大痛点",
  };
  const items = Object.entries(levels)
    .filter(([, value]) => Number.isFinite(Number(value)))
    .slice(0, 3)
    .map(([key, value]) => `${labels[key] || key} ${Number(value).toLocaleString("zh-CN")}`);
  return items.join(" · ");
}

function macroCoverageText(detail) {
  const completeness = detail?.data_completeness || {};
  const effective = Number(completeness.effective_count);
  const total = Number(completeness.total_count);
  if (!Number.isFinite(effective) || !Number.isFinite(total) || total <= 0) return "";
  const incompleteLayers = (Array.isArray(detail.layer_coverage) ? detail.layer_coverage : [])
    .filter((item) => Number(item.effective_count) < Number(item.total_count))
    .map((item) => `${item.label} ${item.effective_count}/${item.total_count}`)
    .join("；");
  return `宏观覆盖 ${effective}/${total}${incompleteLayers ? `；缺口集中在 ${incompleteLayers}` : ""}`;
}

function sourceModuleLabel(value) {
  return {
    MacroOverviewService: "宏观总览",
    MarketContextBuilder: "市场上下文",
    IndicatorMonitoringService: "技术指标",
    BtcDerivativesService: "衍生品总览",
    OnchainFeatureEngine: "链上特征",
    UnifiedStrategyService: "统一策略",
  }[value] || value;
}

function renderResolutionOperationCard(card, dimension, helpers) {
  const { escapeHtml } = helpers;
  const safe = card || {};
  const sourceDimension = dimension || {};
  const detail = sourceDimension.details || {};
  const meaning = cleanUserText(
    detail.human_explanation
    || detail.strategy_impact
    || safe.trading_meaning
    || fallbackDecisionText(sourceDimension, safe.key),
  );
  const evidence = [
    ...(Array.isArray(sourceDimension.evidence) ? sourceDimension.evidence : []),
    ...(Array.isArray(safe.evidence) ? safe.evidence : []),
  ]
      .filter(Boolean)
      .map(cleanUserText)
      .filter((item) => item !== meaning && !isMethodologyText(item))
      .filter((item, index, rows) => rows.indexOf(item) === index)
      .slice(0, 4);
  const levelsText = keyLevelText(safe.key_levels);
  const direction = sourceDimension.bias || safe.direction || "NEUTRAL";
  const confidence = sourceDimension.confidence ?? safe.confidence;
  const freshness = sourceDimension.freshness || safe.freshness || "unknown";
  const statusLabel = STATUS_LABELS[freshness] || STATUS_LABELS.unknown;
  const sources = [
    ...(Array.isArray(sourceDimension.source_modules) ? sourceDimension.source_modules : []),
    ...(Array.isArray(safe.source_modules) ? safe.source_modules : []),
  ].flatMap((item) => String(item || "").split("/"))
    .map(sourceModuleLabel)
    .filter((item, index, rows) => item && rows.indexOf(item) === index);
  const missingInputs = Array.isArray(detail.missing_inputs) ? detail.missing_inputs : [];
  const coverageText = safe.key === "macro" ? macroCoverageText(detail) : "";
  // 2026-07-31: tone key derived from semantic direction so the card
  // chrome can color the title row consistently with the bias token.
  // WAIT_* / NONE / NEUTRAL all share the neutral tone; LONG/SHORT map
  // to bull/bear.
  const tone = (() => {
    if (direction === "LONG" || direction === "LONG_BIAS") return "bull";
    if (direction === "SHORT" || direction === "SHORT_BIAS") return "bear";
    return "neutral";
  })();
  return `
    <details class="strategy-v2-card strategy-operation-card" data-tone="${tone}">
      <summary>
        <p class="eyebrow">${escapeHtml(safe.title || safe.key || "-")}</p>
        <div class="strategy-operation-card-title">
          <strong>${escapeHtml(directionLabel(direction))}</strong>
          <span>${escapeHtml(`${statusLabel} · 置信 ${formatConfidence(confidence)}`)}</span>
        </div>
        <p>${escapeHtml(meaning)}</p>
        <small><span class="op-chevron" aria-hidden="true"></span><span class="op-chevron-label">展开本类别证据与缺失项</span></small>
      </summary>
      <div class="strategy-operation-card-detail">
        ${levelsText ? `<p><strong>关键位置：</strong>${escapeHtml(levelsText)}</p>` : ""}
        ${coverageText ? `<p><strong>数据覆盖：</strong>${escapeHtml(coverageText)}</p>` : ""}
        <ul>
          ${evidence.map((item) => `<li>${escapeHtml(item)}</li>`).join("")
            || `<li>${escapeHtml(fallbackDecisionText(sourceDimension, safe.key))}</li>`}
        </ul>
        ${missingInputs.length
          ? `<p><strong>本轮缺失：</strong>${escapeHtml(missingInputs.slice(0, 12).join("、"))}${missingInputs.length > 12 ? ` 等 ${missingInputs.length} 项` : ""}</p>`
          : '<p><strong>本轮缺失：</strong>没有影响本类别判断的关键缺口</p>'}
        <p><strong>数据来源：</strong>${escapeHtml(sources.join("、") || "尚未记录")}</p>
        <p><strong>策略影响：</strong>${escapeHtml(`权限 ${effectLabel(safe.permission_effect)}；仓位 ${effectLabel(safe.position_effect)}`)}</p>
        <p><strong>下一步：</strong>${escapeHtml(cleanUserText(safe.next_check || formatNextCheck(safe) || "等待下一轮数据更新"))}</p>
      </div>
    </details>
  `;
}

export function renderMarketOperation(model, helpers) {
  const operation = model.market_operation || {};
  const resolutionCards = Array.isArray(model.operation_cards) && model.operation_cards.length
    ? model.operation_cards
    : Array.isArray(operation.operation_cards) ? operation.operation_cards : [];
  const chain = operation.chain || operation;
  const keys = ["macro_regime", "capital_flow", "derivatives_regime", "onchain_regime", "price_structure", "supply_event_regime"];
  const cardsHtml = resolutionCards.length
    ? resolutionCards.map((card) => {
      const dimensionKey = {
        macro: "macro_regime",
        capital_flow: "capital_flow",
        derivatives: "derivatives_regime",
        onchain: "onchain_regime",
        price_structure: "price_structure",
        supply_event: "supply_event_regime",
      }[card.key];
      return renderResolutionOperationCard(card, dimensionKey ? chain[dimensionKey] : null, helpers);
    }).join("")
    : keys.map((key) => operationCard(key, chain[key] || operation[key], helpers)).join("");
  const shadowOnly = model.direction_resolution?.affects_active_decision === false;
  return `
    <section class="strategy-v2-section strategy-market-operation card">
      <div class="section-heading">
        <div>
          <p class="eyebrow">MARKET OPERATION</p>
          <h2>跨维度市场作战图</h2>
          ${shadowOnly ? '<small>正式模型与影子模型共用同一方向选择规则；影子结果仅用于持续验证</small>' : ""}
        </div>
        <p>${helpers.escapeHtml(operation.summary || "宏观、资金、衍生品、链上与价格结构按同一推演链路合成。")}</p>
      </div>
      <div class="strategy-v2-grid five">
        ${cardsHtml}
      </div>
    </section>
  `;
}
