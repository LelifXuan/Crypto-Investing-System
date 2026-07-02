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
  confidence: 0,
  instruction: "等待更多跨周期证据。",
};

const UNIFIED_LABELS = {
  STRATEGIC_LONG_TACTICAL_LONG: "顺周期多头",
  STRATEGIC_LONG_TACTICAL_SHORT: "短空长多",
  STRATEGIC_SHORT_TACTICAL_SHORT: "顺周期空头",
  STRATEGIC_SHORT_TACTICAL_LONG: "空头趋势中的战术反弹",
  STRATEGIC_ACCUMULATION_TACTICAL_DISTRIBUTION: "战略吸筹区内的战术派发",
  RANGE_NO_EDGE: "多周期震荡无优势",
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
  return { ...node, evidence_ref: null, evidence_confidence: node.confidence ?? 0, evidence_freshness: node.freshness || "unknown" };
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
    confidence: Number(safe.confidence || 0),
    long_score: Number(safe.long_score || 0),
    short_score: Number(safe.short_score || 0),
    structure_state: safe.structure_state || safe.state || "unknown",
    state: safe.state || safe.structure_state || "unknown",
    verdict_code: safe.verdict_code || "RANGE_NO_EDGE",
    verdict_label: safe.verdict_label || UNIFIED_LABELS[safe.verdict_code] || "多周期震荡无优势",
    current_price: toOptionalNumber(safe.current_price),
    key_support: toOptionalNumber(safe.key_support),
    key_resistance: toOptionalNumber(safe.key_resistance),
    invalidation: toOptionalNumber(safe.invalidation),
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
    out[key] = { ...dim, evidence_ref: null, evidence_confidence: dim.confidence ?? 0 };
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
  return `
    <section class="strategy-v2-section strategy-degraded-footer card">
      <div class="section-heading compact">
        <div>
          <p class="eyebrow">DATA ACCESS</p>
          <h2>数据源接入状态</h2>
        </div>
      </div>
      <div class="strategy-degraded-grid">${items}</div>
    </section>
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
  const model = {
    instrument_id: safe.instrument_id || "btc-usdt-perp",
    generated_at: safe.generated_at || null,
    status: safe.status || "ready",
    refresh_state: safe.refresh_state || "cache_only",
    refresh_limitations: ensureArray(safe.refresh_limitations),
    snapshot_key: safe.snapshot_key || null,
    payload_hash: safe.payload_hash || null,
    unified_state: unifiedState,
    horizon_views: horizonViews,
    horizon_governance: ensureObject(safe.horizon_governance),
    market_operation: marketOperation,
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
  };
  return map[direction] || direction || "-";
}

export function verdictLabel(code) {
  return UNIFIED_LABELS[code] || code || "-";
}

export function permissionLabel(permission) {
  const map = {
    conditional: "有条件执行",
    observe: "观察",
    no_trade: "不交易",
  };
  return map[permission] || permission || "-";
}