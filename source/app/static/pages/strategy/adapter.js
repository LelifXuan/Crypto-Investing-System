const DEFAULT_STATE = {
  code: "DATA_DEGRADED",
  label: "数据质量不足",
  permission: "no_trade",
  risk_level: "high",
  instruction: "关键数据尚未就绪，先等待缓存刷新。",
};

const DEFAULT_HORIZON = {
  direction: "NEUTRAL",
  score: 0,
  confidence: null,
  instruction: "等待更多跨周期证据。",
};

const UNIFIED_LABELS = {
  STRATEGIC_LONG_TACTICAL_LONG: "顺周期多头",
  STRATEGIC_LONG_TACTICAL_SHORT: "短空长多",
  STRATEGIC_SHORT_TACTICAL_SHORT: "顺周期空头",
  STRATEGIC_SHORT_TACTICAL_LONG: "空头趋势中的战术反弹",
  STRATEGIC_ACCUMULATION_TACTICAL_DISTRIBUTION: "战略吸筹区内的战术派发",
  RANGE_NO_EDGE: "多周期中性震荡",
  EVENT_LOCKED: "事件锁定",
  DATA_DEGRADED: "数据质量不足",
  RISK_OFF: "风险关闭",
  CONTEXT_ALIGNED_LONG: "顺势偏多",
  CONTEXT_ALIGNED_SHORT: "顺势偏空",
};

function ensureArray(value) {
  return Array.isArray(value) ? value : [];
}

function ensureObject(value) {
  return value && typeof value === "object" && !Array.isArray(value) ? value : {};
}

function toFiniteNumber(value, fallback = 0) {
  const n = Number(value);
  return Number.isFinite(n) ? n : fallback;
}

function toOptionalNumber(value) {
  if (value === null || value === undefined || value === "") return null;
  const n = Number(value);
  return Number.isFinite(n) ? n : null;
}

function buildEvidenceIndex(trace) {
  const index = new Map();
  ensureArray(trace).forEach((item, idx) => {
    const key = String(item?.conclusion_key || "");
    if (!key) return;
    index.set(key, { ...item, evidence_index: idx });
  });
  return index;
}

function attachEvidenceRef(node, evidenceIndex) {
  if (!node || typeof node !== "object") return node;
  const timeframe = node.timeframe || "";
  const horizon = node.horizon || "";
  const candidates = [
    `horizon_views.${horizon.toLowerCase()}.direction`,
    `timeframe_stack.${timeframe}`,
    `horizon_views.${timeframe}.direction`,
  ];
  for (const key of candidates) {
    const evidence = evidenceIndex.get(key);
    if (evidence) {
      return { ...node, evidence_ref: evidence.evidence_index, evidence_confidence: evidence.confidence, evidence_freshness: evidence.freshness };
    }
  }
  return { ...node, evidence_ref: null, evidence_confidence: node.confidence ?? null, evidence_freshness: node.freshness || "unknown" };
}

function normalizeHorizonViews(value, evidenceIndex) {
  const views = ensureObject(value);
  const map = {
    strategic: { ...DEFAULT_HORIZON, ...ensureObject(views.strategic) },
    tactical: { ...DEFAULT_HORIZON, ...ensureObject(views.tactical) },
    execution: { ...DEFAULT_HORIZON, ...ensureObject(views.execution) },
  };
  const out = {};
  for (const key of Object.keys(map)) {
    out[key] = attachEvidenceRef(map[key], evidenceIndex);
  }
  return out;
}

function normalizeNode(node, evidenceIndex) {
  const safe = ensureObject(node);
  const merged = {
    timeframe: safe.timeframe || "-",
    cache_timeframe: safe.cache_timeframe || safe.cacheTimeframe || safe.timeframe || "-",
    role: safe.role || "unknown",
    role_label: safe.role_label || safe.role || "未分类",
    horizon: safe.horizon || "-",
    direction: safe.direction || safe.bias || "NEUTRAL",
    bias: safe.bias || safe.direction || "NEUTRAL",
    confidence: toOptionalNumber(safe.confidence),
    long_score: Number(safe.long_score || 0),
    short_score: Number(safe.short_score || 0),
    structure_state: safe.structure_state || safe.state || "unknown",
    state: safe.state || safe.structure_state || "unknown",
    verdict_code: safe.verdict_code || "RANGE_NO_EDGE",
    verdict_label: safe.verdict_label || UNIFIED_LABELS[safe.verdict_code] || "多周期中性震荡",
    current_price: toOptionalNumber(safe.current_price),
    key_support: toOptionalNumber(safe.key_support),
    key_resistance: toOptionalNumber(safe.key_resistance),
    invalidation: toOptionalNumber(safe.invalidation),
    timeframe_state: safe.timeframe_state || "DATA_UNAVAILABLE",
    range_state: safe.range_state || "NONE",
    range_label: safe.range_label || "",
    range_score: Number(safe.range_score || 0),
    range_basis: ensureArray(safe.range_basis),
    range_conflicts: ensureArray(safe.range_conflicts),
    source: ensureObject(safe.source),
    source_modules: ensureArray(safe.source_modules),
    raw_status: ensureObject(safe.raw_status),
    freshness: safe.freshness || "unknown",
    evidence: ensureArray(safe.evidence),
  };
  return attachEvidenceRef(merged, evidenceIndex);
}

function normalizeTradePlan(plan) {
  const safe = ensureObject(plan);
  return {
    ...safe,
    type: safe.type || safe.plan_type || "PLAN",
    plan_type: safe.plan_type || safe.type || "PLAN",
    label: safe.label || safe.title || "策略计划",
    title: safe.title || safe.label || "策略计划",
    take_profit: ensureArray(safe.take_profit),
    entry_zone: ensureArray(safe.entry_zone),
    stop_loss: toOptionalNumber(safe.stop_loss),
    recommended_leverage: toOptionalNumber(safe.recommended_leverage) ?? 0,
    max_leverage: toOptionalNumber(safe.max_leverage) ?? 0,
    leverage_status: safe.leverage_status || "blocked",
    leverage_reason: safe.leverage_reason || "当前计划不建议使用杠杆。",
    order_type: safe.order_type || "NONE",
    order_status: safe.order_status || "NO_DIRECTION",
    execution_price: toOptionalNumber(safe.execution_price),
    limit_price: toOptionalNumber(safe.limit_price),
    planned_leverage: toOptionalNumber(safe.planned_leverage) ?? 0,
    activation_conditions: ensureArray(safe.activation_conditions),
    price_protection: ensureObject(safe.price_protection),
    trade_timeframe: safe.trade_timeframe || "4h",
    direction_timeframes: ensureArray(safe.direction_timeframes).length ? ensureArray(safe.direction_timeframes) : ["1d", "4h"],
    execution_timeframes: ensureArray(safe.execution_timeframes).length ? ensureArray(safe.execution_timeframes) : ["1h", "15m"],
    evidence: ensureArray(safe.evidence),
  };
}

function normalizeRisk(risk) {
  const safe = ensureObject(risk);
  return {
    ...safe,
    label: safe.label || safe.category || "风险提示",
    affected_horizons: ensureArray(safe.affected_horizons),
  };
}

function normalizeDirectionResolution(value) {
  const safe = ensureObject(value);
  return {
    ...safe,
    operation_cards: ensureArray(safe.operation_cards).map((item) => ({ ...ensureObject(item) })),
    governance_cards: ensureArray(safe.governance_cards).map((item) => ({ ...ensureObject(item) })),
    conflicts: ensureArray(safe.conflicts).map((item) => ({ ...ensureObject(item) })),
    allowed_actions: ensureArray(safe.allowed_actions),
    blocked_actions: ensureArray(safe.blocked_actions),
  };
}

function normalizeTradeDecision(value) {
  const safe = ensureObject(value);
  return {
    ...safe,
    side: safe.side || "NONE",
    status: safe.status || "NO_DIRECTION",
    primary_reason: ensureObject(safe.primary_reason),
    secondary_reasons: ensureArray(safe.secondary_reasons).map((item) => ensureObject(item)),
    entry_zone: ensureArray(safe.entry_zone),
    risk_reward: ensureObject(safe.risk_reward),
    permission: safe.permission || "observe",
    recommended_leverage: toOptionalNumber(safe.recommended_leverage) ?? 0,
    max_leverage: toOptionalNumber(safe.max_leverage) ?? 0,
    leverage_status: safe.leverage_status || "blocked",
    leverage_reason: safe.leverage_reason || "当前条件不允许使用杠杆。",
    order_type: safe.order_type || "NONE",
    order_status: safe.order_status || "NO_DIRECTION",
    execution_price: toOptionalNumber(safe.execution_price),
    limit_price: toOptionalNumber(safe.limit_price),
    planned_leverage: toOptionalNumber(safe.planned_leverage) ?? 0,
    activation_conditions: ensureArray(safe.activation_conditions),
    price_protection: ensureObject(safe.price_protection),
    trade_timeframe: safe.trade_timeframe || "4h",
    direction_timeframes: ensureArray(safe.direction_timeframes).length ? ensureArray(safe.direction_timeframes) : ["1d", "4h"],
    execution_timeframes: ensureArray(safe.execution_timeframes).length ? ensureArray(safe.execution_timeframes) : ["1h", "15m"],
    levels_active: safe.levels_active !== false,
  };
}

function normalizeMarketOperation(operation, evidenceIndex) {
  const safe = ensureObject(operation);
  const chain = ensureObject(safe.chain);
  const dimensions = ["macro_regime", "capital_flow", "derivatives_regime", "onchain_regime", "price_structure"];
  const out = { ...safe };
  const attachDimension = (key, dim) => {
    if (!dim) return;
    const refKey = `market_operation.${key}.bias`;
    const evidence = evidenceIndex.get(refKey);
    if (evidence) {
      out[key] = {
        ...dim,
        evidence_ref: evidence.evidence_index,
        evidence_confidence: evidence.confidence,
        evidence_freshness: evidence.freshness,
      };
      return;
    }
    out[key] = { ...dim, evidence_ref: null, evidence_confidence: dim.confidence ?? null };
  };
  for (const key of dimensions) attachDimension(key, chain[key] || safe[key]);
  if (out.chain) {
    for (const key of dimensions) attachDimension(key, out.chain[key]);
  }
  return out;
}

function mergeWithDashboard(model, dashboard) {
  if (!dashboard) return model;
  const technical = ensureArray(dashboard.technical_observations);
  if (technical.length) {
    model.technical_observations_summary = technical.slice(0, 8).map((obs) => ({
      indicator_key: obs.indicator_key,
      category: obs.category,
      timeframe: obs.timeframe,
      value_num: obs.value_num ?? null,
      signal_state: obs.signal_state,
      source_provider: obs.source_provider,
      observation_ts: obs.observation_ts,
    }));
  }
  if (dashboard.macro_overview) {
    model.macro_overview_external = dashboard.macro_overview;
  }
  if (dashboard.terminal_summary) {
    model.terminal_summary_external = dashboard.terminal_summary;
  }
  if (ensureArray(dashboard.alert_events).length) {
    model.alert_events_external = dashboard.alert_events;
  }
  return model;
}

function mergeWithDerivatives(model, derivatives) {
  if (!derivatives) return model;
  const options = ensureObject(derivatives.options);
  const walls = ensureObject(options.walls);
  const pain = ensureObject(options.max_pain);
  const hedge = ensureObject(derivatives.hedge_context);
  model.derivatives_external = {
    snapshot_state: derivatives.snapshot_state,
    data_timestamp: derivatives.data_timestamp,
    spot_price: toOptionalNumber(hedge.spot_price),
    call_wall: toOptionalNumber(walls.call_wall_strike),
    put_wall: toOptionalNumber(walls.put_wall_strike),
    max_pain: toOptionalNumber(pain.strike),
  };
  return model;
}

function mergeWithMacro(model, macro) {
  if (!macro) return model;
  model.macro_external = {
    regime_key: macro.regime_key,
    operation_bias: macro.operation_bias,
    total_score: macro.total_score,
    confidence: macro.confidence,
    generated_at: macro.generated_at,
  };
  return model;
}

function buildDataDegradedFooter(model) {
  const endpoints = ensureArray(model.data_access_endpoints);
  if (endpoints.length === 0) return "";
  const items = endpoints
    .map((item) => {
      const state = item.status === "ok" ? "fresh" : item.status === "failed" ? "missing" : "unknown";
      return `
        <article class="strategy-degraded-item ${state}">
          <strong>${escapeHtmlSafe(item.label || item.name)}</strong>
          <span>${escapeHtmlSafe(item.status_label || state)}</span>
          <small>${escapeHtmlSafe(item.detail || "")}</small>
        </article>
      `;
    })
    .join("");
  const hasFailures = endpoints.some((item) => item.status !== "ok");
  return `
    <details class="strategy-degraded-footer strategy-collapsible card" ${hasFailures ? "open" : ""}>
      <summary class="strategy-degraded-summary strategy-collapsible-summary">
        <div>
          <p class="eyebrow">DATA ACCESS</p>
          <h2>数据源接入状态</h2>
          <small>${escapeHtmlSafe(endpoints.map((item) => `${item.label} ${item.status_label}`).join(" · "))}</small>
        </div>
        <span class="strategy-collapse-control" aria-hidden="true"></span>
      </summary>
      <div class="strategy-degraded-grid">${items}</div>
    </details>
  `;
}

function escapeHtmlSafe(value) {
  if (value === null || value === undefined) return "-";
  return String(value)
    .replace(/&/g, "&amp;")
    .replace(/</g, "&lt;")
    .replace(/>/g, "&gt;")
    .replace(/"/g, "&quot;")
    .replace(/'/g, "&#39;");
}

export function normalizeUnifiedStrategy(payload = {}, extras = {}) {
  const safe = ensureObject(payload);
  const evidenceIndex = buildEvidenceIndex(safe.evidence_trace);
  const unifiedState = { ...DEFAULT_STATE, ...ensureObject(safe.unified_state) };
  const horizonViews = normalizeHorizonViews(safe.horizon_views, evidenceIndex);
  const timeframeStack = ensureArray(safe.timeframe_stack).map((node) => normalizeNode(node, evidenceIndex));
  const marketOperation = normalizeMarketOperation(safe.market_operation, evidenceIndex);
  const directionResolution = normalizeDirectionResolution(safe.direction_resolution);
  const tradeDecision = normalizeTradeDecision(safe.trade_decision);
  const model = {
    instrument_id: safe.instrument_id || "btc-usdt-perp",
    generated_at: safe.generated_at || null,
    status: safe.status || "ready",
    refresh_state: safe.refresh_state || "cache_only",
    refresh_limitations: ensureArray(safe.refresh_limitations),
    snapshot_key: safe.snapshot_key || null,
    payload_hash: safe.payload_hash || null,
    degraded: safe.degraded ?? false,
    degraded_components: ensureArray(safe.degraded_components),
    prewarm_status: safe.prewarm_status || "idle",
    active_model_version: safe.active_model_version || safe.model_version || "legacy-cross-horizon-v2",
    candidate_model_version: safe.candidate_model_version || "auditable-rules-v3-shadow",
    strategy_as_of: safe.strategy_as_of || safe.generated_at || null,
    price_as_of: safe.price_as_of || null,
    price_source: safe.price_source || "",
    recompute_status: safe.recompute_status || "complete",
    market_decision_snapshot: ensureObject(safe.market_decision_snapshot),
    signal_coverage: ensureArray(safe.signal_coverage).map((item) => ({ ...ensureObject(item) })),
    cross_validation: ensureObject(safe.cross_validation),
    shadow_evaluation: ensureObject(safe.shadow_evaluation),
    unified_state: unifiedState,
    horizon_views: horizonViews,
    horizon_governance: ensureObject(safe.horizon_governance),
    market_operation: marketOperation,
    direction_resolution: directionResolution,
    trade_decision: tradeDecision,
    operation_cards: directionResolution.operation_cards.length
      ? directionResolution.operation_cards
      : ensureArray(marketOperation.operation_cards),
    governance_cards: directionResolution.governance_cards.length
      ? directionResolution.governance_cards
      : ensureArray(ensureObject(safe.horizon_governance).governance_cards),
    timeframe_stack: timeframeStack,
    trade_plans: ensureArray(safe.trade_plans).map(normalizeTradePlan),
    risk_alerts: ensureArray(safe.risk_alerts).map(normalizeRisk),
    risk_groups: ensureObject(safe.risk_groups),
    monitoring_focus: ensureArray(safe.monitoring_focus),
    event_watch: ensureArray(safe.event_watch),
    evidence_trace: ensureArray(safe.evidence_trace).map((item) => ({ ...item })),
    evidence_index: Array.from(evidenceIndex.values()),
    narrative: ensureObject(safe.narrative),
    verdict_labels: UNIFIED_LABELS,
  };
  mergeWithDashboard(model, extras.monitoring);
  mergeWithDerivatives(model, extras.derivatives);
  mergeWithMacro(model, extras.macro);
  return model;
}

export function buildDataDegradedCard(model) {
  if (!model) return "";
  const endpoints = [];
  const labels = {
    unified: { name: "/strategy/unified", label: "统一策略" },
    monitoring: { name: "/monitoring/dashboard", label: "监控总览" },
    derivatives: { name: "/btc-derivatives/dashboard", label: "衍生品" },
    macro: { name: "/monitoring/macro-overview", label: "宏观" },
  };
  const access = model.data_access || {};
  const failures = model.data_access_failures || {};
  for (const key of Object.keys(labels)) {
    const ok = access[key] !== null && access[key] !== undefined;
    endpoints.push({
      name: labels[key].name,
      label: labels[key].label,
      status: ok ? "ok" : "failed",
      status_label: ok ? "已接入" : "缺失",
      detail: ok
        ? (access[key]?.generated_at || access[key]?.data_timestamp || "已读取")
        : failures[key] || "数据源不可用",
    });
  }
  model.data_access_endpoints = endpoints;
  return buildDataDegradedFooter(model);
}

export function directionLabel(direction) {
  const map = {
    LONG: "看多",
    SHORT: "看空",
    NEUTRAL: "中性",
    WAIT_LONG_TRIGGER: "等多头触发",
    WAIT_SHORT_TRIGGER: "等空头触发",
    WAIT_CONFIRMATION: "等待确认",
    NONE: "暂无方向",
    LONG_BIAS: "上涨结构",
    SHORT_BIAS: "下跌结构",
    OBSERVE: "等待确认",
    WAIT: "等待确认",
    BLOCK: "暂停交易",
    NO_TRADE: "暂停交易",
  };
  if (!direction) return "-";
  if (!map[direction]) console.debug("strategy:unmapped-state", direction);
  return map[direction] || "状态待确认";
}

export function verdictLabel(code) {
  return UNIFIED_LABELS[code] || code || "-";
}

export function permissionLabel(permission) {
  const map = {
    allow: "可执行",
    conditional: "有条件执行",
    observe: "仅观察",
    no_trade: "暂停交易",
  };
  return map[permission] || "状态待确认";
}

export function riskLevelLabel(level) {
  const map = { low: "低风险", medium: "风险降级", high: "高风险" };
  return map[level] || "风险待确认";
}

export function decisionStatusLabel(status, side = "NONE") {
  const sideText = side === "SHORT" ? "看空" : side === "LONG" ? "看多" : "";
  const map = {
    READY: sideText ? `${sideText}，可执行` : "可以执行",
    WAIT_SETUP: sideText ? `${sideText}，等待4H形态` : "等待4H形态",
    WAIT_TRIGGER: sideText ? `${sideText}，等待1H触发` : "等待1H触发",
    BLOCKED: "暂停交易",
    NO_DIRECTION: "方向未确认",
    SETUP_INVALIDATED: "候选计划已失效，正在重新推演",
    STOP_HIT: "已入场计划触及止损",
    INVALID_PLAN_LEVELS: "计划价位无效",
    PRICE_STALE: "实时价格已过期，暂停执行",
    PRICE_UNAVAILABLE: "实时价格不可用，暂停执行",
  };
  return map[status] || "状态待确认";
}

export function planLabel(plan = {}) {
  const map = {
    TACTICAL_LONG: "顺势做多计划",
    TACTICAL_SHORT: "顺势做空计划",
    EXECUTION_TRIGGER: "入场触发条件",
    STRATEGIC_ACCUMULATION: "长期配置计划",
    STRATEGIC_RISK_REDUCTION: "长期风险控制",
    WAIT_RANGE: "等待区间方向确认",
    NO_TRADE: "暂停交易",
  };
  return map[plan.type || plan.plan_type] || plan.label || plan.title || "交易计划";
}

export function cleanUserText(value) {
  const replacements = [
    [/SHORT_BIAS/g, "下跌结构"],
    [/LONG_BIAS/g, "上涨结构"],
    [/WAIT_SHORT_TRIGGER/g, "等待空头触发"],
    [/WAIT_LONG_TRIGGER/g, "等待多头触发"],
    [/\bSHORT\b/g, "看空"],
    [/\bLONG\b/g, "看多"],
    [/\bNEUTRAL\b/g, "方向未确认"],
    [/\bOBSERVE\b/g, "等待确认"],
    [/\bstrategic\b/gi, "长期"],
    [/\btactical\b/gi, "战术"],
    [/\bexecution\b/gi, "执行"],
  ];
  return replacements.reduce((text, [pattern, label]) => text.replace(pattern, label), String(value || ""));
}
