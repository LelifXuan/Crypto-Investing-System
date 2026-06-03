import { api } from "../core/api.js";
import {
  escapeHtml,
  formatDateOnly,
  formatDateTime,
  formatNumber,
  setRoot,
  statusBanner,
} from "../core/dom.js";
import { scheduleIdlePrecompute } from "../core/precompute.js";

let activeController = null;
let refreshInFlight = false;
const queuedKeys = new Set();

const DASH = "-";
const MONITORING_TECH_INSTRUMENT_ID = "btc-usdt-perp";
const MONITORING_TECH_TIMEFRAME = "1d";
const TECH_OBSERVATION_MAX_AGE_MS = 18 * 60 * 60 * 1000;

const INVALID_TEXT_VALUES = new Set([
  "",
  "-",
  "unavailable",
  "source_error",
  "pending",
  "pending_release",
  "placeholder",
  "missing",
  "none",
  "null",
  "nan",
  "unavailable_placeholder",
]);

const MOJIBAKE_CODES = [0xfffd, 0x934b, 0x7039, 0x93c6, 0x951f, 0x9225];
const MOJIBAKE_PATTERN = new RegExp(
  `[${MOJIBAKE_CODES.map((code) => `\\u${code.toString(16).padStart(4, "0")}`).join("")}]`,
);

const SOURCE_LABELS = {
  gateio: "Gate.io",
  fred: "FRED",
  market_events: "市场事件",
  ashare_etf: "A股ETF",
};

const SOURCE_DEFAULT_MESSAGES = {
  gateio: "K 线缓存及快照可用。",
  fred: "宏观利率观测可用。",
  market_events: "事件信息流缓存可用。",
  ashare_etf: "A股ETF 行情快照可用。",
};

const SOURCE_STATUS_META = {
  online: ["在线", "chip-bullish"],
  ready: ["在线", "chip-bullish"],
  fresh: ["在线", "chip-bullish"],
  stale: ["使用缓存", "chip-warning"],
  stale_cache: ["使用缓存", "chip-warning"],
  cached: ["使用缓存", "chip-warning"],
  no_data: ["无数据", "chip-neutral"],
  missing: ["后台准备中", "chip-neutral"],
  not_configured: ["未配置", "chip-neutral"],
  auth_missing: ["未配置", "chip-neutral"],
  offline: ["离线", "chip-bearish"],
  source_error: ["离线", "chip-bearish"],
  unavailable: ["无数据", "chip-neutral"],
};

const LAYER_LABELS = {
  policy: "利率与政策",
  rates_policy: "利率与政策",
  inflation: "通胀与价格",
  inflation_price: "通胀与价格",
  growth: "增长与就业",
  growth_jobs: "增长与就业",
  liquidity: "流动性与信用",
  liquidity_credit: "流动性与信用",
  cross_asset: "跨资产确认",
  events: "事件窗口",
  event_window: "事件窗口",
};

const MACRO_DISPLAY_LABELS = {
  effr: "EFFR 美国有效联邦基金利率",
  sofr: "SOFR 隔夜融资利率",
  sofr_rate: "SOFR 隔夜融资利率",
  us03m_yield: "US3M 美国3个月国债收益率",
  us3m_yield: "US3M 美国3个月国债收益率",
  us02y_yield: "US2Y 美国2年期国债收益率",
  us2y_yield: "US2Y 美国2年期国债收益率",
  us10y_yield: "US10Y 美国10年期国债收益率",
  us30y_yield: "US30Y 美国30年期国债收益率",
  us10y_2y_spread: "US10Y-2Y 美债10Y-2Y利差",
  us10y_3m_spread: "US10Y-3M 美债10Y-3M利差",
  cpi_yoy: "US CPI 美国CPI同比",
  cpi_mom: "US CPI 美国CPI环比",
  core_cpi_yoy: "US Core CPI 美国核心CPI同比",
  core_cpi_mom: "US Core CPI 美国核心CPI环比",
  pce_yoy: "US PCE 美国PCE同比",
  core_pce_yoy: "US Core PCE 美国核心PCE同比",
  nfp: "US NFP 美国非农就业",
  unemployment_rate: "美国失业率",
  wti: "WTI原油",
  brent: "Brent原油",
  vix: "VIX波动率",
  dxy: "DXY美元指数",
  ig_spread: "IG SPREAD 投资级信用利差",
};

const TECHNICAL_LABELS = {
  ema_20: "EMA 20",
  ema_50: "EMA 50",
  ema_200: "EMA 200",
  rsi_14: "RSI 14",
  macd_hist: "MACD 柱状值",
  atr_14: "ATR 14",
  natr_14: "NATR 14",
  bbands_width: "BOLL 宽度",
  percent_b: "Percent B",
  adx_14: "ADX 14",
  plus_di: "+DI",
  minus_di: "-DI",
  obv: "OBV",
  kdj_j: "KDJ J",
  cci_20: "CCI 20",
  volume: "成交量",
  vwap_50: "VWAP 50",
  vwap_100: "VWAP 100",
  vwap_spread_pct: "VWAP 价差",
  vwap_slope_10: "VWAP 斜率",
};

const MISSING_REASON_LABELS = {
  auth_missing: "API未配置",
  not_configured: "API未配置",
  dependency_missing: "缺依赖指标",
  missing_dependency: "缺依赖指标",
  no_provider: "无数据源映射",
  unsupported: "待接入行情源",
  source_error: "网络或接口失败",
  rate_limited: "网络或限流失败",
  unavailable_placeholder: "仅占位",
  placeholder: "仅占位",
  pending: "同步未运行或缓存未命中",
  pending_release: "等待数据发布",
  missing: "同步未运行或缓存未命中",
  no_data: "同步未运行或缓存未命中",
};

function cleanText(value, fallback = DASH) {
  if (value === null || value === undefined || value === "") return fallback;
  return String(value);
}

function looksMojibake(value) {
  return MOJIBAKE_PATTERN.test(String(value || ""));
}

function readableText(value, fallback = DASH) {
  const text = cleanText(value, fallback);
  return looksMojibake(text) ? fallback : text;
}

function numeric(value) {
  const num = Number(value);
  return Number.isFinite(num) ? num : null;
}

function normalizeKey(value) {
  return String(value ?? "")
    .trim()
    .toLowerCase()
    .replaceAll("-", "_")
    .replaceAll(" ", "_");
}

function chip(label, className = "chip-neutral") {
  return `<span class="status-chip ${className}">${escapeHtml(label)}</span>`;
}

function unifiedSignalMeta(kind) {
  const meta = {
    strong_bullish: { label: "强偏多", className: "chip-bullish", hint: "强偏多影响。" },
    bullish: { label: "偏多", className: "chip-bullish", hint: "偏多影响。" },
    soft_bullish: { label: "中性偏多", className: "chip-bullish-soft", hint: "中性偏多影响。" },
    neutral: { label: "中性", className: "chip-neutral", hint: "中性影响。" },
    soft_bearish: { label: "中性偏空", className: "chip-bearish-soft", hint: "中性偏空影响。" },
    bearish: { label: "偏空", className: "chip-bearish", hint: "偏空影响。" },
    strong_bearish: { label: "强偏空", className: "chip-bearish", hint: "强偏空影响。" },
    volatility: { label: "波动环境", className: "chip-warning", hint: "波动环境，方向需等待确认。" },
  };
  return meta[kind] || meta.neutral;
}

function signalMeta(raw) {
  const key = normalizeKey(raw);
  if (["strong_bullish", "strong_long", "强偏多"].includes(key)) {
    return unifiedSignalMeta("strong_bullish");
  }
  if (["bullish", "positive", "long", "upside", "看多", "偏多"].includes(key)) {
    return unifiedSignalMeta("bullish");
  }
  if (
    ["soft_bullish", "neutral_bullish", "positive_hist", "developing_trend", "strengthening", "strong", "偏强", "中性偏多"].includes(key)
  ) {
    return unifiedSignalMeta("soft_bullish");
  }
  if (["strong_bearish", "strong_short", "强偏空"].includes(key)) {
    return unifiedSignalMeta("strong_bearish");
  }
  if (["bearish", "negative", "short", "downside", "看空", "偏空"].includes(key)) {
    return unifiedSignalMeta("bearish");
  }
  if (["soft_bearish", "neutral_bearish", "negative_hist", "weakening", "weak", "偏弱", "中性偏空"].includes(key)) {
    return unifiedSignalMeta("soft_bearish");
  }
  if (["volatile", "high_volatility", "risk", "compressed", "event", "波动", "波动环境"].includes(key)) {
    return unifiedSignalMeta("volatility");
  }
  return unifiedSignalMeta("neutral");
}

function macroBiasMeta(raw) {
  const key = normalizeKey(raw);
  if (["strong_bullish", "risk_on_strong", "强偏多"].includes(key)) {
    return unifiedSignalMeta("strong_bullish");
  }
  if (["bullish", "positive", "risk_on", "easing", "看多", "偏多"].includes(key)) {
    return unifiedSignalMeta("bullish");
  }
  if (["cooling", "falling", "down", "downside", "risk_easing", "风险缓和", "中性偏多"].includes(key)) {
    return unifiedSignalMeta("soft_bullish");
  }
  if (["strong_bearish", "risk_off_strong", "强偏空"].includes(key)) {
    return unifiedSignalMeta("strong_bearish");
  }
  if (["bearish", "negative", "risk_off", "tight", "看空", "偏空"].includes(key)) {
    return unifiedSignalMeta("bearish");
  }
  if (["rising", "up", "upside", "steepening", "risk_rising", "风险升温", "中性偏空"].includes(key)) {
    return unifiedSignalMeta("soft_bearish");
  }
  if (["inactive", "not_triggered", "event_wait", "未触发"].includes(key)) {
    return unifiedSignalMeta("neutral");
  }
  if (["volatile", "high_volatility", "event", "波动环境"].includes(key)) {
    return unifiedSignalMeta("volatility");
  }
  return unifiedSignalMeta("neutral");
}

function sourceMeta(status) {
  const [label, className] = SOURCE_STATUS_META[normalizeKey(status)] || ["后台准备中", "chip-neutral"];
  return { label, className };
}

function normalizeUnit(unit) {
  return String(unit || "")
    .trim()
    .toLowerCase()
    .replaceAll("_", " ")
    .replaceAll("-", " ");
}

function macroUnitSuffix(unit) {
  const normalized = normalizeUnit(unit);
  if (!normalized) return "";
  if (normalized === "%") return "%";
  if (normalized === "pp" || normalized === "percentage point" || normalized === "percentage points") {
    return "pp";
  }
  if (["usd billion", "billion usd", "billion_usd"].includes(normalized)) {
    return "B USD";
  }
  if (["usd million", "million usd", "million_usd"].includes(normalized)) {
    return "M USD";
  }
  if (["usd", "dollar", "dollars"].includes(normalized)) return "美元";
  if (["usd/bbl", "usd bbl", "usd per barrel", "dollar per barrel"].includes(normalized)) {
    return "美元/桶";
  }
  if (["thousand persons", "thousand people", "thousands persons"].includes(normalized)) {
    return "千人";
  }
  if (["persons", "people"].includes(normalized)) return "人";
  if (normalized === "index" || normalized === "ratio") return "";
  return unit ? ` ${unit}` : "";
}

function macroDisplayValue(item) {
  const rawText = cleanText(item?.value_text, "");
  const rawNum = numeric(item?.value_num);
  const unit = cleanText(item?.unit, "").trim();
  if (rawNum !== null) {
    const value = formatNumber(rawNum, 2);
    return `${value}${macroUnitSuffix(unit)}`;
  }
  if (rawText && !INVALID_TEXT_VALUES.has(normalizeKey(rawText))) return readableText(rawText);
  return DASH;
}

function validMacroIndicator(item) {
  const rawText = normalizeKey(item?.value_text);
  const hasIndicatorValue = numeric(item?.value_num) !== null
    || (rawText && !INVALID_TEXT_VALUES.has(rawText));
  if (!hasIndicatorValue) return false;
  const status = normalizeKey(item?.status);
  if (["source_error", "unavailable", "unavailable_placeholder", "placeholder", "missing"].includes(status)) {
    return false;
  }
  return true;
}

function macroTitle(item) {
  const key = normalizeKey(item?.indicator_key || item?.key);
  return readableText(
    item?.display_label || item?.label || item?.name_cn || item?.name || MACRO_DISPLAY_LABELS[key] || key,
    "宏观指标",
  );
}

function macroScore(macro) {
  return numeric(macro?.total_score) ?? numeric(macro?.score) ?? 50;
}

function macroCompleteness(macro) {
  const value =
    macro?.data_completeness?.percent ??
    macro?.data_completeness?.score ??
    macro?.data_completeness?.overall ??
    macro?.data_completeness_pct ??
    0;
  const num = numeric(value) ?? 0;
  return num <= 1 ? num * 100 : num;
}

function macroConfidence(macro) {
  const key = normalizeKey(macro?.confidence || macro?.confidence_label);
  if (["high", "strong", "good", "较高"].includes(key)) return "较高";
  if (["medium", "normal", "ok", "中等"].includes(key)) return "中等";
  if (["low", "weak", "poor", "不足"].includes(key)) return "不足";
  return readableText(macro?.confidence_label || macro?.confidence, "不足");
}

function macroBiasLabel(macro) {
  return readableText(
    macro?.score_band || macro?.regime_label_cn || macro?.operation_bias || macro?.direction_label,
    "中性震荡",
  );
}

function getMacroIndicators(macro) {
  if (!macro) return [];
  if (Array.isArray(macro.indicators)) return macro.indicators;
  if (macro.indicators && typeof macro.indicators === "object") {
    return Object.values(macro.indicators);
  }
  if (Array.isArray(macro.layers)) {
    return macro.layers.flatMap((layer) =>
      (layer.indicators || []).map((item) => ({
        ...item,
        layer_key: item.layer_key || layer.layer_key,
        layer_label: item.layer_label || layer.label_cn,
      })),
    );
  }
  return [];
}

function getMacroLayers(macro) {
  if (Array.isArray(macro?.layers) && macro.layers.length) return macro.layers;
  const contributions = macro?.layer_contributions || {};
  return Object.entries(contributions).map(([key, score]) => ({
    layer_key: key,
    label_cn: LAYER_LABELS[key] || key,
    score,
    effective_count: 0,
    total_count: 0,
  }));
}

function getTechnicalItems(data) {
  const items = data?.technical_observations || data?.data?.technical_observations || [];
  return Array.isArray(items)
    ? items.filter(isFreshTechnicalObservation).map((item) => ({
        key: normalizeKey(item.indicator_key || item.key || item.name),
        label: readableText(
          item.label || item.name || TECHNICAL_LABELS[normalizeKey(item.indicator_key || item.key)],
          "技术指标",
        ),
        value: item.value_num ?? item.value ?? item.latest_value ?? item.value_text,
        signal: item.signal_state || item.state || item.status || item.value_json?.signal,
        hint: item.summary || item.message || item.value_json?.hint,
        comment: item.comment || "",
        formula: item.formula || "",
        rule: item.rule || "",
        signal_label: item.signal_label || "",
        tone: item.tone || "",
      }))
    : [];
}

function isFreshTechnicalObservation(item) {
  const rawTs = item?.observation_ts || item?.updated_at || item?.timestamp;
  if (!rawTs) return false;
  const ts = Date.parse(rawTs);
  if (!Number.isFinite(ts)) return false;
  return Date.now() - ts <= TECH_OBSERVATION_MAX_AGE_MS;
}

function getMacroPayload(data) {
  return data?.macro_overview || data?.data?.macro_overview || data?.macro || null;
}

function getTerminalSummary(data) {
  return data?.terminal_summary || data?.data?.terminal_summary || null;
}

function mergeMacroIntoBundle(bundle, macro) {
  if (macro && !bundle?.macro_overview) {
    return { ...(bundle || {}), macro_overview: macro };
  }
  return bundle || { macro_overview: macro };
}

function currentSelection() {
  return {
    instrumentId: MONITORING_TECH_INSTRUMENT_ID,
    timeframe: MONITORING_TECH_TIMEFRAME,
  };
}

function getSourceStatus(data) {
  const raw = data?.source_status || data?.data?.source_status || {};
  const allowed = ["gateio", "fred", "market_events", "ashare_etf"];
  return allowed.map((key) => {
    const value = raw?.[key] || {};
    return {
      key,
      label: SOURCE_LABELS[key],
      status: value.status || value.cache_state || (value.ok ? "online" : "missing"),
      message: readableText(value.message || value.status_message, SOURCE_DEFAULT_MESSAGES[key]),
      updatedAt: value.updated_at || value.snapshot_at,
    };
  });
}

function missingReason(item) {
  const raw =
    item?.missing_reason ||
    item?.reason_key ||
    item?.status_reason ||
    item?.score_block_reason ||
    item?.reason ||
    item?.status ||
    "missing";
  return MISSING_REASON_LABELS[normalizeKey(raw)] || readableText(raw, "暂无数据");
}

function renderShellFallback(message) {
  return `
    ${statusBanner(message, "warning")}
    <section class="monitoring-surface">
      <div class="section-heading-row">
        <div>
          <p class="eyebrow">MONITORING</p>
          <h2>监控总览</h2>
          <p class="section-summary">后台准备中，稍后会回填宏观、技术与信源状态。</p>
        </div>
      </div>
    </section>
  `;
}

function renderTopbar(data, macro) {
  const indicators = getMacroIndicators(macro);
  const visible = indicators.filter(validMacroIndicator);
  const technical = getTechnicalItems(data);
  const missing = Math.max(indicators.length - visible.length, 0);
  const statusMessage = readableText(data?.status_message, "数据已就绪");
  return `
    <section class="monitoring-surface monitoring-topbar">
      <div class="monitoring-top-status">
        ${statusBanner(statusMessage, data?.status === "error" ? "warning" : "success")}
      </div>
      <div class="monitoring-topbar-grid">
        <article class="monitoring-topbar-item wide">
          <span>监控总览</span>
          <strong>${escapeHtml(data?.status === "missing" ? "后台准备中" : "监控快照可用")}</strong>
        </article>
        <article class="monitoring-topbar-item score">
          <span>宏观总分</span>
          <strong>${escapeHtml(formatNumber(macroScore(macro), 0))}</strong>
        </article>
        <article class="monitoring-topbar-item">
          <span>置信度</span>
          <strong>${escapeHtml(macroConfidence(macro))}</strong>
        </article>
        <article class="monitoring-topbar-item">
          <span>完整度</span>
          <strong>${escapeHtml(formatNumber(macroCompleteness(macro), 0))}%</strong>
        </article>
        <article class="monitoring-topbar-item">
          <span>技术指标</span>
          <strong>${technical.length} 项</strong>
        </article>
        <article class="monitoring-topbar-item">
          <span>主要缺口</span>
          <strong>${missing} 项</strong>
        </article>
        <button class="primary-button monitoring-refresh button compact" type="button">刷新监控</button>
      </div>
      <div class="monitoring-source-pills">
        ${getSourceStatus(data).map((source) => {
          const meta = sourceMeta(source.status);
          return `<span class="monitoring-source-pill"><span class="source-dot source-dot-${meta.className}"></span>${escapeHtml(source.label)}</span>`;
        }).join("")}
      </div>
    </section>
  `;
}

function renderSourceRow(source) {
  const meta = sourceMeta(source.status);
  return `
    <article class="monitoring-source-row">
      <div>
        <strong>${escapeHtml(source.label)}</strong>
        <p>${escapeHtml(source.message)}</p>
        ${source.updatedAt ? `<small>${escapeHtml(formatDateTime(source.updatedAt))}</small>` : ""}
      </div>
      <div class="monitoring-source-status">${chip(meta.label, meta.className)}</div>
    </article>
  `;
}

function renderSourcePanel(data) {
  const rows = getSourceStatus(data).map(renderSourceRow).join("");
  return `
    <section class="monitoring-source-panel">
      <div class="monitoring-panel-head compact">
        <div>
          <p class="eyebrow">SOURCES</p>
          <h3>信源状态</h3>
        </div>
      </div>
      <div class="monitoring-source-list">${rows}</div>
    </section>
  `;
}

function renderLayerChip(layer) {
  const key = layer.layer_key || layer.key;
  const label = readableText(layer.label_cn || layer.label || LAYER_LABELS[key], "宏观层");
  const score = numeric(layer.score) ?? numeric(layer.contribution) ?? 0;
  const count = layer.effective_count ?? layer.scored_count ?? 0;
  const total = layer.total_count ?? layer.indicator_count ?? 0;
  return `
    <article class="macro-layer-card">
      <strong>${escapeHtml(label)}</strong>
      <b>${escapeHtml(formatNumber(score, 0))}</b>
      <small>贡献 ${escapeHtml(formatNumber(layer.contribution ?? 0, 2))} · 有效 ${count}/${total}</small>
      <span class="macro-layer-bar"><i style="width:${Math.max(0, Math.min(100, score))}%"></i></span>
    </article>
  `;
}

function renderMacroPanel(data, macro) {
  const layers = getMacroLayers(macro);
  const bias = macroBiasLabel(macro);
  const biasChip = signalMeta(bias);
  return `
    <article class="monitoring-panel macro">
      <div class="monitoring-panel-head">
        <div>
          <p class="eyebrow">MACRO</p>
          <h2>宏观环境</h2>
        </div>
        ${chip(bias, biasChip.className)}
      </div>
      <div class="macro-score-block">
        <strong>${escapeHtml(formatNumber(macroScore(macro), 0))}</strong>
        <div class="macro-score-copy">
          <strong class="macro-bias-label">${escapeHtml(bias)}</strong>
        </div>
      </div>
      <div class="macro-layer-strip">
        ${layers.map(renderLayerChip).join("") || `<p class="monitoring-empty-note">暂无分层贡献。</p>`}
      </div>
    </article>
  `;
}

function renderTechnicalCard(item) {
  const meta = signalMeta(item.signal_state || item.signal);
  const value = numeric(item.value_num ?? item.value) !== null ? formatNumber(item.value_num ?? item.value, 2) : readableText(item.value_text ?? item.value);
  const formula = item.formula || "";
  const comment = item.comment || item.rule || item.hint || "";
  return `
    <article class="technical-chip">
      <div class="technical-chip-head">
        <span>${escapeHtml(item.label || item.signal_label || item.indicator_key)}</span>
        ${chip(item.signal_label || meta.label, meta.className)}
      </div>
      <strong>${escapeHtml(value)}</strong>
      <small>${escapeHtml(readableText(comment, meta.hint))}</small>
      ${formula ? `<small class="muted compact">${escapeHtml(formula)}</small>` : ""}
    </article>
  `;
}

function renderTechnicalPanel(data) {
  const items = getTechnicalItems(data);
  const body = items.length
    ? items.map(renderTechnicalCard).join("")
    : `
        <div class="technical-empty-state">
          <strong>技术快照准备中</strong>
          <p>后台会在指标缓存可用后填充趋势、动量与波动观测。</p>
        </div>
      `;
  return `
    <article class="monitoring-panel technical">
      <div class="monitoring-panel-head">
        <div>
          <p class="eyebrow">TECHNICAL</p>
          <h2>技术观测</h2>
        </div>
        ${chip(`${items.length} 项`, "chip-neutral")}
      </div>
      <div class="technical-chip-grid">
        ${body}
      </div>
    </article>
  `;
}

function renderTerminalSummary(data) {
  const summary = getTerminalSummary(data);
  if (!summary || typeof summary !== "object") {
    return `
      <article class="terminal-summary-card terminal-summary-empty">
        <div class="monitoring-panel-head">
          <div>
            <p class="eyebrow">TERMINAL BRIEF</p>
            <h2>全局市场摘要</h2>
          </div>
          ${chip("等待数据", "chip-neutral")}
        </div>
        <p>全局摘要暂不可用：关键输入不足，等待宏观、技术与结构数据刷新。</p>
      </article>
    `;
  }
  const modules = summary.module_scores || {};
  const moduleLabels = {
    macro: "宏观",
    technical_trend: "趋势",
    momentum_volume: "动量成交",
    volatility: "波动",
    structure: "结构",
    event_risk: "事件",
  };
  const moduleVotes = ["macro", "technical_trend", "momentum_volume", "volatility", "structure", "event_risk"]
    .map((key) => {
      const item = modules[key] || {};
      const meta = signalMeta(item.impact || item.state);
      const score = numeric(item.score) !== null ? formatNumber(item.score, 0) : DASH;
      return `
        <article class="terminal-summary-vote">
          <span>${escapeHtml(moduleLabels[key] || key)}</span>
          <strong>${escapeHtml(readableText(item.state, "待确认"))}</strong>
          <small>${escapeHtml(score)}</small>
          ${chip(readableText(item.impact, "neutral"), meta.className)}
        </article>
      `;
    })
    .join("");
  const confidence = numeric(summary.confidence) !== null ? formatNumber(summary.confidence, 0) : DASH;
  const regime = readableText(summary.regime, "中性震荡");
  // V1.5.5 ②: the regime already carries the sub-direction
  // (偏多震荡 / 偏空震荡 / 中性震荡). Drop the separate bias chip
  // so the user gets one unambiguous answer to "is this
  // 偏多震荡 or 偏空震荡?". Confidence goes into a single
  // combined chip for readability.
  const bias = readableText(summary.bias, "中性");
  const regimeTone = ["偏多震荡", "强趋势偏多", "温和偏多", "多头修复"].includes(regime)
    ? "bullish"
    : ["偏空震荡", "弱势震荡", "空头加速", "弱势下行", "高波动风险"].includes(regime)
    ? "bearish"
    : "neutral";
  const regimeMeta = signalMeta(regimeTone);
  const decisionRows = getTerminalDecisionRows(summary);
  return `
    <article class="terminal-summary-card">
      <div class="terminal-summary-head">
        <div>
          <p class="eyebrow">TERMINAL BRIEF</p>
          <h2>全局市场摘要</h2>
        </div>
        <div class="terminal-summary-badges">
          ${chip(regime, regimeMeta.className)}
          <span class="terminal-summary-confidence" title="置信度">${escapeHtml(confidence)}</span>
        </div>
      </div>
      <p class="terminal-summary-headline">${escapeHtml(readableText(summary.headline, "全局摘要正在等待关键输入。"))}</p>
      <div class="terminal-summary-votes">${moduleVotes}</div>
      <div class="terminal-summary-brief">
        ${decisionRows.map((row) => renderTerminalDecisionRow(row)).join("")}
      </div>
    </article>
  `;
}

function getTerminalDecisionRows(summary) {
  if (!summary || typeof summary !== "object") return [];
  const brief = summary.decision_brief || {};
  const rows = Array.isArray(brief.rows) ? brief.rows : [];
  return rows.map((row) => ({
    key: String(row.key || ""),
    title: String(row.title || "市场观察"),
    tone: String(row.tone || "neutral"),
    summary: String(row.summary || ""),
    bullets: Array.isArray(row.bullets) ? row.bullets : [],
    source_refs: Array.isArray(row.source_refs) ? row.source_refs : [],
  }));
}

function renderTerminalDecisionRow(row) {
  if (!row || typeof row !== "object") return "";
  const tone = normalizeKey(row.tone || "neutral");
  const toneClass = `terminal-brief-tone-${["bullish", "bearish", "warning", "neutral"].includes(tone) ? tone : "neutral"}`;
  const meta = signalMeta(row.tone || "neutral");
  const bullets = Array.isArray(row.bullets) ? row.bullets.filter(Boolean) : [];
  const sources = Array.isArray(row.source_refs) ? row.source_refs.filter(Boolean) : [];
  const sourceChips = sources.length
    ? sources
        .map((ref) => chip(String(ref), "chip-neutral"))
        .join("")
    : "";
  return `
    <article class="terminal-brief-row ${toneClass}">
      <div class="terminal-brief-row-head">
        <h3>${escapeHtml(String(row.title || "市场观察"))}</h3>
        ${chip(String(row.tone || "neutral"), meta.className)}
      </div>
      <p>${escapeHtml(String(row.summary || "等待关键输入。"))}</p>
      ${
        bullets.length
          ? `<ul class="terminal-brief-bullets">${bullets
              .map((item) => `<li>${escapeHtml(String(item))}</li>`)
              .join("")}</ul>`
          : ""
      }
      ${sourceChips ? `<div class="terminal-brief-sources">${sourceChips}</div>` : ""}
    </article>
  `;
}

function renderMacroIndicatorCard(item) {
  const bias = macroBiasMeta(item.direction_label || item.direction || item.signal_state || item.impact);
  const source = readableText(item.source_provider || item.source || item.provider, "宏观");
  const time = item.observation_ts || item.updated_at || item.timestamp;
  const layer = readableText(item.layer_label || item.layer || item.category, "宏观");
  return `
    <article class="macro-indicator-card">
      <div class="macro-indicator-head">
        <strong>${escapeHtml(macroTitle(item))}</strong>
        ${chip(bias.label, bias.className)}
      </div>
      <b>${escapeHtml(macroDisplayValue(item))}</b>
      <div class="macro-indicator-foot">
        <span>${escapeHtml(layer)} · ${escapeHtml(source)}</span>
        <time>${escapeHtml(time ? formatDateOnly(time) : DASH)}</time>
      </div>
    </article>
  `;
}

function renderMissingGroup([reason, items]) {
  return `
    <div class="macro-missing-group">
      <strong>${escapeHtml(reason)} ${items.length} 项</strong>
      <p>${items.map((item) => escapeHtml(macroTitle(item))).join("、")}</p>
    </div>
  `;
}

function renderMissingIndicators(items) {
  if (!items.length) return "";
  const groups = new Map();
  for (const item of items) {
    const reason = missingReason(item);
    groups.set(reason, [...(groups.get(reason) || []), item]);
  }
  return `
    <details class="macro-hidden-details">
      <summary>未获取指标 ${items.length} 项</summary>
      <div class="macro-missing-grid">
        ${Array.from(groups.entries()).map(renderMissingGroup).join("")}
      </div>
    </details>
  `;
}

function renderMacroIndicatorGrid(macro) {
  const all = getMacroIndicators(macro);
  const visible = all.filter(validMacroIndicator);
  const hidden = all.filter((item) => !validMacroIndicator(item));
  return `
    <section class="monitoring-surface monitoring-detail-panel">
      <div class="section-heading-row">
        <div>
          <p class="eyebrow">MACRO DETAIL</p>
          <h2>宏观指标明细</h2>
        </div>
      </div>
      <div class="macro-indicator-grid">
        ${visible.map(renderMacroIndicatorCard).join("") || `<p class="monitoring-empty-note">暂无可展示宏观指标。</p>`}
      </div>
      ${renderMissingIndicators(hidden)}
    </section>
  `;
}

function renderDashboard(data) {
  const macro = getMacroPayload(data);
  return `
    ${renderTopbar(data, macro)}
    <section class="monitoring-surface monitoring-summary-surface">
      <div class="monitoring-snapshot-grid">
        <div class="monitoring-left-stack">
          ${renderMacroPanel(data, macro)}
          ${renderTerminalSummary(data)}
        </div>
        <div class="monitoring-right-stack">
          ${renderTechnicalPanel(data)}
        </div>
      </div>
    </section>
    ${renderMacroIndicatorGrid(macro)}
  `;
}

// V1.5.4 C11: diff update. On the first render, build a stable shell
// with named containers; on subsequent renders, only swap the
// innerHTML of each container. The shell survives across refreshes,
// so the browser does not re-parse the layout box for the page
// itself, and the only work per refresh is re-rendering the 5 leaf
// HTML strings. The previous full-DOM rebuild paid ~30-60 ms per
// refresh on a mid-range laptop because the page shell (~3 KB of
// divs) was re-parsed on every refresh.
const MONITORING_SECTION_IDS = [
  "monitoring-topbar",
  "monitoring-macro-panel",
  "monitoring-terminal-summary",
  "monitoring-technical-panel",
  "monitoring-macro-grid",
];

function applyMonitoringDiff(data, options = {}) {
  const root = document.getElementById("page-root");
  if (!root) {
    setRoot(renderDashboard(data));
    return;
  }
  if (!root._monitoringSections) {
    root.innerHTML = `
      <div id="monitoring-topbar"></div>
      <section class="monitoring-surface monitoring-summary-surface">
        <div class="monitoring-snapshot-grid">
          <div class="monitoring-left-stack">
            <div id="monitoring-macro-panel"></div>
            <div id="monitoring-terminal-summary"></div>
          </div>
          <div class="monitoring-right-stack">
            <div id="monitoring-technical-panel"></div>
          </div>
        </div>
      </section>
      <div id="monitoring-macro-grid"></div>
    `;
    root._monitoringSections = {
      topbar: root.querySelector("#monitoring-topbar"),
      "monitoring-macro-panel": root.querySelector("#monitoring-macro-panel"),
      "monitoring-terminal-summary": root.querySelector("#monitoring-terminal-summary"),
      "monitoring-technical-panel": root.querySelector("#monitoring-technical-panel"),
      "monitoring-macro-grid": root.querySelector("#monitoring-macro-grid"),
    };
  }
  const macro = getMacroPayload(data);
  const sections = root._monitoringSections;
  sections.topbar.innerHTML = renderTopbar(data, macro);
  sections["monitoring-macro-panel"].innerHTML = renderMacroPanel(data, macro);
  sections["monitoring-terminal-summary"].innerHTML = renderTerminalSummary(data);
  sections["monitoring-technical-panel"].innerHTML = renderTechnicalPanel(data);
  sections["monitoring-macro-grid"].innerHTML = renderMacroIndicatorGrid(macro);
  if (options.skeleton) {
    // noop: skeleton handled by the caller
  }
}

function queueWarmup() {
  const { instrumentId, timeframe } = currentSelection();
  const key = `${instrumentId}:${timeframe}`;
  if (queuedKeys.has(key)) return;
  queuedKeys.add(key);
  scheduleIdlePrecompute({
    page: "monitoring-overview",
    current_page: "monitoring-overview",
    instrumentId,
    instrument_id: instrumentId,
    timeframe,
    reason: "monitoring_page_visible",
    priority: 20,
  });
}

function bindRefreshButton() {
  const button = document.querySelector(".monitoring-refresh");
  if (!button) return;
  button.addEventListener("click", async () => {
    if (refreshInFlight) return;
    refreshInFlight = true;
    button.disabled = true;
    button.textContent = "刷新中";
    const { instrumentId, timeframe } = currentSelection();
    try {
      await api.refreshMacro().catch(() => null);
      await api.refreshMonitoringDashboard(instrumentId, timeframe, { timeoutMs: 30000 }).catch(() => null);
      const [bundle, macro] = await Promise.all([
        api.getMonitoringDashboard(instrumentId, timeframe, {
          force: true,
          timeoutMs: 30000,
        }),
        api.getMacroOverview({
          force: true,
          timeoutMs: 30000,
        }).catch(() => null),
      ]);
      applyMonitoringDiff(mergeMacroIntoBundle(bundle, macro));
      bindRefreshButton();
      queueWarmup();
    } catch (error) {
      console.warn("monitoring refresh failed", error);
      const page = document.querySelector(".monitoring-surface");
      if (page) {
        page.insertAdjacentHTML(
          "afterbegin",
          statusBanner("刷新失败，已保留上一份可用快照。", "warning"),
        );
      }
    } finally {
      refreshInFlight = false;
      if (button.isConnected) {
        button.disabled = false;
        button.textContent = "刷新监控";
      }
    }
  });
}

async function loadDashboard() {
  if (activeController) activeController.abort();
  activeController = new AbortController();
  const { instrumentId, timeframe } = currentSelection();
  setRoot(renderShellFallback("正在读取监控快照"));

  let bundle = null;
  let macro = null;
  try {
    [bundle, macro] = await Promise.all([
      api.getMonitoringDashboard(instrumentId, timeframe, {
        signal: activeController.signal,
        timeoutMs: 30000,
      }),
      api.getMacroOverview({
        signal: activeController.signal,
        timeoutMs: 30000,
      }).catch(() => null),
    ]);
  } catch (error) {
    if (error?.name === "AbortError") return;
    console.warn("monitoring snapshot fetch failed", error);
    setRoot(renderShellFallback("监控快照读取失败，后台仍会继续准备数据。"));
    return;
  }

  try {
    applyMonitoringDiff(mergeMacroIntoBundle(bundle, macro));
    bindRefreshButton();
    queueWarmup();
  } catch (error) {
    console.error("monitoring render failed", {
      error,
      bundleStatus: bundle?.status,
      bundleKeys: bundle && Object.keys(bundle),
      macroKeys: macro && Object.keys(macro),
    });
    setRoot(renderShellFallback("页面渲染异常，已保留监控页骨架；请查看控制台详情。"));
  }
}

export async function renderMonitoring() {
  await loadDashboard();
}
