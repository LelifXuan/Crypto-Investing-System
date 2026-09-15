import { api } from "../core/api.js";
import {
  escapeHtml,
  formatDateOnly,
  formatDateTime,
  formatNumber,
  setRoot,
  statusBanner,
  updatePageContext,
} from "../core/dom.js";
import { scheduleIdlePrecompute, waitForAbortableDelay, waitForPrecomputeTask } from "../core/precompute.js";
import { judgementMeta } from "../core/judgement.js";
import { rangeStateLabel, rangeStateTone } from "../core/rangeState.js";
import { mountPageGuide } from "../ui/pageGuideFab.js";
import { renderDisclosureToggle, setDisclosureState } from "../ui/disclosure.js";
import { renderGovernanceLedger } from "../ui/governanceLedger.js";
import { createWorkbenchState } from "../core/workbenchState.js?v=operator-core-1";
import { mountWorkbenchUrlState } from "../core/workbenchUrlState.js";
import { mountInspector } from "../ui/inspector.js?v=operator-core-1";
import { markWorkbenchRelations } from "../ui/semanticMotion.js?v=operator-core-1";
import { animateStateChange, animateValueChange } from "../ui/semanticMotion.js?v=operator-core-1";

let activeController = null;
let refreshInFlight = false;
let pageController = null;
const boundRefreshButtons = new WeakSet();
let lastRenderedBundle = null;
let workbenchState = null;
let workbenchUrl = null;
let inspector = null;
let interactionController = null;
let workbenchUnsubscribe = null;
let previousWorkbenchValues = new Map();
const inspectionRegistry = new Map();
const queuedKeys = new Set();
const macroGroupCollapsed = new Map();
let macroGroupOrder = [];

const DASH = "-";
const MONITORING_TECH_INSTRUMENT_ID = "btc-usdt-perp";
const MONITORING_TECH_TIMEFRAME = "1d";
const MONITORING_SNAPSHOT_STORAGE_KEY = "monitoring.dashboard.lastSnapshot.v1";

function workbenchId(...parts) {
  return parts
    .filter(Boolean)
    .map((part) => normalizeKey(part).replace(/[^a-z0-9\u4e00-\u9fff_-]+/g, "-"))
    .join(":");
}

function sourceInspectionRows(data) {
  return getSourceStatus(data).map((source) => {
    const state = sourceMeta(source.status).tone;
    return {
      name: source.label,
      status: state === "live" ? "live" : state === "stale" ? "stale" : state === "offline" ? "degraded" : "unavailable",
      updatedAt: source.updatedAt || null,
    };
  });
}

function actualMacroScore(macro) {
  const raw = macro?.total_score ?? macro?.score;
  return raw === null || raw === undefined || raw === "" ? null : numeric(raw);
}

function actualMacroRegime(macro) {
  const raw = macro?.score_band || macro?.regime_label_cn || macro?.operation_bias || macro?.direction_label;
  return raw === null || raw === undefined || raw === "" ? null : readableText(raw, "");
}

function monitoringMarketTone(raw) {
  const meta = macroBiasMeta(raw);
  if (meta.className.includes("bullish")) return "bullish";
  if (meta.className.includes("bearish")) return "bearish";
  return "neutral";
}

function monitoringTimestamp(data) {
  return data?.updated_at || data?.snapshot_at || data?.data_ts || data?.source_updated_at || null;
}

function inspectionAttrs(item) {
  if (!item?.id) return "";
  inspectionRegistry.set(item.id, item);
  return `data-workbench-id="${escapeHtml(item.id)}" data-workbench-selectable tabindex="0" role="button" aria-label="查看 ${escapeHtml(item.title)} 的上下文"`;
}

function macroInspection(data, macro) {
  const layerIds = getMacroLayers(macro).map((layer) => workbenchId("monitoring", "layer", layer.layer_key || layer.key || layer.label));
  const score = actualMacroScore(macro);
  const regime = actualMacroRegime(macro);
  return {
    id: "monitoring:macro",
    type: "macro-state",
    title: "宏观环境",
    current: score === null ? null : {
      label: "宏观总分",
      value: formatNumber(score, 0),
      marketTone: monitoringMarketTone(regime),
    },
    interpretation: regime ? `当前宏观状态为${regime}；置信度为${macroConfidence(macro)}。` : "",
    evidence: getMacroLayers(macro).flatMap((layer) => {
      const raw = layer.score ?? layer.contribution;
      const value = raw === null || raw === undefined || raw === "" ? null : numeric(raw);
      if (value === null) return [];
      return [{
        id: workbenchId("monitoring", "layer", layer.layer_key || layer.key || layer.label),
        label: readableText(layer.label_cn || layer.label || LAYER_LABELS[layer.layer_key || layer.key], "宏观层"),
        value: formatNumber(value, 0),
        relatedIds: ["monitoring:terminal:macro"],
      }];
    }),
    impacts: [{ label: "终端摘要", summary: "作为全局市场摘要的宏观输入之一。" }],
    sources: sourceInspectionRows(data),
    updatedAt: monitoringTimestamp(data),
    relatedIds: ["monitoring:terminal:macro", ...layerIds],
  };
}

function ensureMonitoringWorkbench(root) {
  if (!workbenchState) workbenchState = createWorkbenchState({ scopeId: "monitoring-overview" });
  inspector?.destroy();
  inspector = mountInspector(root.querySelector("#monitoring-inspector"), {
    state: workbenchState,
    returnFocus: () => root.querySelector(".monitoring-refresh"),
  });
  if (interactionController) interactionController.abort();
  workbenchUnsubscribe?.();
  interactionController = new AbortController();
  const { signal } = interactionController;
  const selectable = (target) => target instanceof Element ? target.closest("[data-workbench-selectable]") : null;
  root.addEventListener("pointerover", (event) => {
    const element = selectable(event.target);
    const item = element && inspectionRegistry.get(element.dataset.workbenchId);
    if (item) workbenchState.preview(item);
  }, { signal });
  root.addEventListener("pointerout", (event) => {
    const element = selectable(event.target);
    if (element && !element.contains(event.relatedTarget)) workbenchState.clearPreview();
  }, { signal });
  root.addEventListener("focusin", (event) => {
    const element = selectable(event.target);
    const item = element && inspectionRegistry.get(element.dataset.workbenchId);
    if (item) workbenchState.preview(item);
  }, { signal });
  root.addEventListener("focusout", (event) => {
    const element = selectable(event.target);
    if (element && !element.contains(event.relatedTarget)) workbenchState.clearPreview();
  }, { signal });
  const commit = (element) => {
    const item = element && inspectionRegistry.get(element.dataset.workbenchId);
    if (item) workbenchState.select(item, { trigger: element });
  };
  root.addEventListener("click", (event) => commit(selectable(event.target)), { signal });
  root.addEventListener("keydown", (event) => {
    if (event.key !== "Enter" && event.key !== " ") return;
    const element = selectable(event.target);
    if (!element) return;
    event.preventDefault();
    commit(element);
  }, { signal });
  workbenchUnsubscribe = workbenchState.subscribe((snapshot) => {
    markWorkbenchRelations(root, snapshot);
  });
}
// The FOMC event-window observation remains part of macro scoring and the
// terminal summary. It is intentionally omitted from the detailed indicator
// ledger because that layer contains only one item and duplicates the event
// signal already surfaced elsewhere on this page.
const HIDDEN_MACRO_DISPLAY_LAYERS = new Set(["events", "event_window", "事件窗口"]);

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
  "suspect_zero",
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
  online: ["在线", "live"],
  ready: ["在线", "live"],
  fresh: ["在线", "live"],
  stale: ["使用缓存", "stale"],
  stale_cache: ["使用缓存", "stale"],
  cached: ["使用缓存", "stale"],
  no_data: ["无数据", "unavailable"],
  missing: ["后台准备中", "unavailable"],
  not_configured: ["未配置", "unavailable"],
  auth_missing: ["未配置", "unavailable"],
  offline: ["离线", "offline"],
  source_error: ["离线", "offline"],
  unavailable: ["无数据", "unavailable"],
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

const EYEBROW_LABELS = {
  rates_policy: "RATES & POLICY",
  inflation: "INFLATION & PRICES",
  growth: "GROWTH & EMPLOYMENT",
  liquidity: "LIQUIDITY & CREDIT",
  cross_asset: "CROSS ASSET",
  events: "EVENT WINDOW",
  macro: "MACRO LAYER",
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
  suspect_zero: "数据待发布（口径异常）",
  missing: "同步未运行或缓存未命中",
  no_data: "同步未运行或缓存未命中",
  display_only: "展示型指标（仅展示不计分）",
  registry_rule_missing: "评分规则未配置（仅展示）",
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
    ["soft_bullish", "mild_bullish", "weak_bullish", "neutral_bullish", "positive_hist", "developing_trend", "strengthening", "strong", "偏强", "中性偏多"].includes(key)
  ) {
    return unifiedSignalMeta("soft_bullish");
  }
  if (["strong_bearish", "strong_short", "强偏空"].includes(key)) {
    return unifiedSignalMeta("strong_bearish");
  }
  if (["bearish", "negative", "short", "downside", "看空", "偏空"].includes(key)) {
    return unifiedSignalMeta("bearish");
  }
  if (["soft_bearish", "mild_bearish", "weak_bearish", "neutral_bearish", "negative_hist", "weakening", "weak", "偏弱", "中性偏空"].includes(key)) {
    return unifiedSignalMeta("soft_bearish");
  }
  if (["volatile", "high_volatility", "risk", "compressed", "event", "execution_risk", "波动", "波动环境"].includes(key)) {
    return unifiedSignalMeta("volatility");
  }
  return unifiedSignalMeta("neutral");
}

function impactLabel(raw) {
  const key = normalizeKey(raw);
  if (["bearish", "short", "downside", "偏空", "看空"].includes(key)) return "偏空";
  if (["mild_bearish", "soft_bearish", "weak_bearish", "neutral_bearish", "偏弱", "中性偏空"].includes(key)) return "温和偏空";
  if (["bullish", "long", "upside", "偏多", "看多"].includes(key)) return "偏多";
  if (["mild_bullish", "soft_bullish", "weak_bullish", "neutral_bullish", "偏强", "中性偏多"].includes(key)) return "温和偏多";
  if (["execution_risk", "risk", "event", "warning", "volatile", "high_volatility"].includes(key)) return "执行风险";
  if (["unknown", "missing", "pending", "low_confidence", "待确认", "数据不足"].includes(key)) return "待确认";
  return "中性";
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
  const [label, tone] = SOURCE_STATUS_META[normalizeKey(status)] || ["后台准备中", "unavailable"];
  return { label, tone };
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
  // value_num may be null/undefined/"" when the DB has no numeric
  // observation yet (e.g. BLS only publishes monthly). Treat those as
  // "no numeric" and fall through to the text / DASH branch.
  // ``numeric(null)`` returns 0 because ``Number(null) === 0``, so we
  // explicitly gate on the raw value first.
  const rawValue = item?.value_num;
  const rawNum = (rawValue === null || rawValue === undefined || rawValue === "")
    ? null
    : numeric(rawValue);
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
  const rawValue = item?.value_num;
  // Same null/empty guard as ``macroDisplayValue``: literal null or
  // empty string means "no observation yet" and must not be coerced
  // to 0 by ``Number(null)``.
  const hasNumeric = (rawValue !== null && rawValue !== undefined && rawValue !== "")
    && numeric(rawValue) !== null;
  const hasIndicatorValue = hasNumeric
    || (rawText && !INVALID_TEXT_VALUES.has(rawText));
  if (!hasIndicatorValue) return false;
  const status = normalizeKey(item?.status);
  if (["source_error", "unavailable", "unavailable_placeholder", "placeholder", "missing", "suspect_zero"].includes(status)) {
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
  if (!key) return "待评估";
  if (["high", "strong", "good", "较高"].includes(key)) return "较高";
  if (["medium", "normal", "ok", "中等"].includes(key)) return "中等";
  if (["low", "weak", "poor", "不足"].includes(key)) return "不足";
  return readableText(macro?.confidence_label || macro?.confidence, "待评估");
}

function macroBiasLabel(macro) {
  return readableText(
    macro?.score_band || macro?.regime_label_cn || macro?.operation_bias || macro?.direction_label,
    "宏观中性",
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
    ? items.map((item) => ({
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
        judgement: item.indicator_judgement || {},
      }))
    : [];
}

function getMacroPayload(data) {
  return data?.macro_overview || data?.data?.macro_overview || data?.macro || null;
}

function getTerminalSummary(data) {
  return data?.terminal_summary || data?.data?.terminal_summary || null;
}

function mergeMacroIntoBundle(bundle, macro) {
  if (macro) {
    return { ...(bundle || {}), macro_overview: macro };
  }
  return bundle || {};
}

function readStoredMonitoringBundle(instrumentId, timeframe) {
  try {
    const raw = window.sessionStorage?.getItem(MONITORING_SNAPSHOT_STORAGE_KEY);
    if (!raw) return null;
    const stored = JSON.parse(raw);
    if (stored?.instrumentId !== instrumentId || stored?.timeframe !== timeframe) return null;
    if (!stored?.bundle || typeof stored.bundle !== "object") return null;
    return stored.bundle;
  } catch (error) {
    console.warn("monitoring stored snapshot unavailable", error);
    return null;
  }
}

function rememberMonitoringBundle(bundle, instrumentId, timeframe) {
  if (!bundle || typeof bundle !== "object") return;
  try {
    window.sessionStorage?.setItem(
      MONITORING_SNAPSHOT_STORAGE_KEY,
      JSON.stringify({
        instrumentId,
        timeframe,
        savedAt: Date.now(),
        bundle,
      }),
    );
  } catch (error) {
    console.warn("monitoring stored snapshot write failed", error);
  }
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

function missingTone(item) {
  const status = normalizeKey(item?.status);
  if (["auth_missing", "not_implemented", "disabled"].includes(status)) return "neutral";
  if (["source_error", "parser_error", "rate_limited"].includes(status)) return "warning";
  if (["missing", "unavailable", "stale_cache", "stale_seed"].includes(status)) return "stale";
  return "neutral";
}

function renderShellFallback(message, pending = false) {
  return `
    <div class="workbench-page-layout monitoring-workbench-layout">
      <div class="monitoring-primary">
        <div id="monitoring-topbar">
          <div class="monitoring-progress-banner" role="status">${statusBanner(message, pending ? "loading" : "warning")}</div>
          <section class="monitoring-surface monitoring-topbar" aria-busy="${pending}">
            <div class="monitoring-topbar-grid">
              <article class="monitoring-topbar-item monitoring-topbar-context wide">
                <span class="monitoring-context-status" data-status-tone="${pending ? "pending" : "neutral"}">${pending ? '<span class="monitoring-cold-spinner" aria-hidden="true"></span>正在读取最近快照' : '快照暂不可用'}</span>
                <small>监控总览</small>
                <strong>${pending ? "后台准备中" : "等待重新加载"}</strong>
              </article>
            </div>
          </section>
        </div>
        <section class="monitoring-surface monitoring-summary-surface">
          <div class="monitoring-snapshot-grid monitoring-snapshot-grid-full">
            <div id="monitoring-macro-panel"></div>
            <div id="monitoring-terminal-summary">
              <div class="monitoring-cold-content">
              <p class="section-summary">${escapeHtml(message)}</p>
              ${pending ? '<div class="monitoring-cold-placeholder" aria-hidden="true"><span></span><span></span><span></span></div>' : ''}
              </div>
            </div>
          </div>
        </section>
        <div id="monitoring-macro-grid"></div>
        <div id="monitoring-governance"></div>
      </div>
      <aside class="workbench-inspector" id="monitoring-inspector" hidden></aside>
    </div>
  `;
}

function attachMonitoringShell(root) {
  if (!root) return;
  root._monitoringSections = {
    topbar: root.querySelector("#monitoring-topbar"),
    "monitoring-macro-panel": root.querySelector("#monitoring-macro-panel"),
    "monitoring-terminal-summary": root.querySelector("#monitoring-terminal-summary"),
    "monitoring-macro-grid": root.querySelector("#monitoring-macro-grid"),
    "monitoring-governance": root.querySelector("#monitoring-governance"),
  };
  ensureMonitoringWorkbench(root);
}

function hasRenderedMonitoringShell() {
  const root = document.getElementById("page-root");
  return Boolean(
    root?._monitoringSections?.topbar?.isConnected &&
    root.querySelector("#monitoring-topbar"),
  );
}

function showMonitoringBanner(message, tone = "warning") {
  const root = document.getElementById("page-root");
  const target = root?.querySelector("#monitoring-topbar") || root?.firstElementChild || root;
  if (!target) return;
  target.querySelector?.(".monitoring-progress-banner")?.remove();
  target.insertAdjacentHTML("afterbegin", `<div class="monitoring-progress-banner">${statusBanner(message, tone)}</div>`);
}

function renderTopbar(data, macro) {
  const indicators = getMacroIndicators(macro);
  const visible = indicators.filter(validMacroIndicator);
  const technical = getTechnicalItems(data);
  const missing = Math.max(indicators.length - visible.length, 0);
  const technicalCount = numeric(data?.technical_indicator_count) ?? technical.length;
  const macroCoverage = macroCompleteness(macro);
  const confidence = macroConfidence(macro);
  const confidenceTone =
    confidence === "较高"
      ? "ready"
      : confidence === "中等"
        ? "neutral"
        : confidence === "不足"
          ? "warning"
          : "pending";
  const statusMessage =
    technicalCount > 0 && macroCoverage <= 0
      ? "技术指标已就绪，宏观覆盖待补齐。"
      : readableText(data?.status_message, "数据已就绪");
  return `
    <section class="monitoring-surface monitoring-topbar">
      <div class="monitoring-topbar-grid">
        <article class="monitoring-topbar-item monitoring-topbar-context wide">
          <span class="monitoring-context-status" data-status-tone="${data?.status === "error" ? "warning" : "ready"}">
            ${escapeHtml(statusMessage)}
          </span>
          <small>监控总览</small>
          <strong>${escapeHtml(data?.status === "missing" ? "后台准备中" : "监控快照可用")}</strong>
        </article>
        <div class="monitoring-metric-rail" aria-label="监控摘要指标">
          <article class="monitoring-topbar-item score">
            <span>宏观总分</span>
            <strong>${escapeHtml(formatNumber(macroScore(macro), 0))}</strong>
          </article>
          <article class="monitoring-topbar-item monitoring-confidence-item">
            <span>数据置信度</span>
            <span class="monitoring-confidence-chip" data-confidence-tone="${confidenceTone}">${escapeHtml(confidence)}</span>
          </article>
          <article class="monitoring-topbar-item" title="有有效数据的宏观指标占比；不足 100% 意味着部分指标缺失或过期，决策置信度会相应降低">
            <span>宏观数据覆盖</span>
            <strong>${escapeHtml(formatNumber(macroCoverage, 0))}%</strong>
          </article>
          <article class="monitoring-topbar-item">
            <span>技术指标</span>
            <strong>${technicalCount} 项</strong>
          </article>
          <article class="monitoring-topbar-item">
            <span>宏观待补</span>
            <strong>${missing} 项</strong>
          </article>
        </div>
      </div>
    </section>
  `;
}

function renderLayerChip(layer) {
  const key = layer.layer_key || layer.key;
  const label = readableText(layer.label_cn || layer.label || LAYER_LABELS[key], "宏观层");
  const rawScore = layer.score ?? layer.contribution;
  const score = rawScore === null || rawScore === undefined || rawScore === "" ? null : numeric(rawScore);
  const rawContribution = layer.contribution;
  const contribution = rawContribution === null || rawContribution === undefined || rawContribution === ""
    ? null
    : numeric(rawContribution);
  const count = layer.effective_count ?? layer.scored_count ?? 0;
  const total = layer.total_count ?? layer.indicator_count ?? 0;
  const coverage = total ? `评分 ${count}/${total}` : "无指标";
  const coverageTip =
    "该层 " + total + " 个指标中 " + count + " 个计入总分；其余为展示型指标，数据已获取但暂无评分阈值，仅展示不计分。";
  const id = workbenchId("monitoring", "layer", key || label);
  const item = {
    id,
    type: "macro-layer",
    title: label,
    current: score === null ? null : { label: "层评分", value: formatNumber(score, 0) },
    interpretation: contribution === null ? coverage : `${coverage}，当前对宏观总分贡献 ${formatNumber(contribution, 2)}。`,
    evidence: [{ id: `${id}:coverage`, label: "计入评分", value: total ? `${count}/${total}` : "无指标", relatedIds: ["monitoring:macro"] }],
    impacts: [{ label: "宏观环境", summary: "该层参与宏观总分与终端摘要。" }],
    relatedIds: ["monitoring:macro", "monitoring:terminal:macro"],
  };
  return `
    <article class="macro-layer-card" ${inspectionAttrs(item)}>
      <strong>${escapeHtml(label)}</strong>
      <b>${escapeHtml(score === null ? DASH : formatNumber(score, 0))}</b>
      <small title="${escapeHtml(coverageTip)}">${contribution === null ? "" : `贡献 ${escapeHtml(formatNumber(contribution, 2))} · `}${escapeHtml(coverage)}</small>
      <span class="macro-layer-bar"><i style="width:${score === null ? 0 : Math.max(0, Math.min(100, score))}%"></i></span>
    </article>
  `;
}

function renderMacroPanel(data, macro) {
  const layers = getMacroLayers(macro);
  const score = actualMacroScore(macro);
  const actualRegime = actualMacroRegime(macro);
  if (score === null && !actualRegime && !layers.length) {
    return `
      <article class="monitoring-panel macro is-availability-only">
        <div class="monitoring-panel-head"><div><p class="eyebrow">MACRO</p><h2>宏观环境</h2></div></div>
        <p class="monitoring-empty-note">宏观数据正在准备；当前不生成市场方向或风险判断。</p>
      </article>
    `;
  }
  const bias = macroBiasLabel(macro);
  const biasChip = signalMeta(bias);
  return `
    <article class="monitoring-panel macro" ${inspectionAttrs(macroInspection(data, macro))}>
      <div class="monitoring-panel-head">
        <div>
          <p class="eyebrow">MACRO</p>
          <h2>宏观环境</h2>
        </div>
        ${chip(bias, biasChip.className)}
      </div>
      <div class="macro-score-block">
        <strong>${escapeHtml(score === null ? DASH : formatNumber(score, 0))}</strong>
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
  const judgement = judgementMeta(item.judgement);
  const value = numeric(item.value_num ?? item.value) !== null ? formatNumber(item.value_num ?? item.value, 2) : readableText(item.value_text ?? item.value);
  const formula = item.formula || "";
  const comment = item.comment || item.rule || item.hint || "";
  return `
    <article class="technical-chip">
      <div class="technical-chip-head">
        <span>${escapeHtml(item.label || item.signal_label || item.indicator_key)}</span>
        ${chip(judgement.stateLabel, meta.className)}
      </div>
      <strong>${escapeHtml(value)}</strong>
      <small>${escapeHtml(readableText(comment, meta.hint))}</small>
      <small class="muted compact">${escapeHtml(`${judgement.axisLabel} · ${judgement.effectLabel} · ${judgement.dataLabel}`)}</small>
      ${formula ? `<small class="muted compact">${escapeHtml(formula)}</small>` : ""}
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
  // Short label of which indicators feed each technical sub-module. The
  // standalone '技术观测' panel was removed; instead the terminal summary
  // shows a one-line evidence annotation per technical module so users can
  // still tell what evidence is behind '趋势 / 动量 / 波动'. Non-technical
  // modules (macro / structure / event_risk) intentionally have no evidence
  // line because their inputs aren't on this chart.
  const moduleEvidence = {
    technical_trend: "EMA 20/50/200、MACD 柱、BOLL 宽度、VWAP 斜率",
    momentum_volume: "RSI 14、KDJ、CCI、OBV、VWAP 价差",
    volatility: "ATR 14、NATR 14、ADX 14、+DI/-DI、Percent B",
  };
  const moduleVotes = ["macro", "technical_trend", "momentum_volume", "volatility", "structure", "event_risk"]
    .map((key) => {
      const item = modules[key] || {};
      const meta = signalMeta(item.impact || item.state);
      const score = numeric(item.score) !== null ? formatNumber(item.score, 0) : DASH;
      const evidence = moduleEvidence[key];
      const id = workbenchId("monitoring", "terminal", key);
      const relatedIds = key === "macro"
        ? ["monitoring:macro", ...getMacroLayers(getMacroPayload(data)).map((layer) => workbenchId("monitoring", "layer", layer.layer_key || layer.key || layer.label))]
        : [];
      const inspection = {
        id,
        type: "terminal-module",
        title: moduleLabels[key] || key,
        current: { label: "模块评分", value: score, marketTone: key.includes("risk") ? "neutral" : undefined },
        interpretation: readableText(item.state, "当前模块状态待确认。"),
        evidence: evidence ? [{ id: `${id}:evidence`, label: "输入指标", value: evidence, relatedIds }] : [],
        impacts: [{ label: "全局市场摘要", summary: "该模块参与终端摘要与置信度计算。" }],
        sources: sourceInspectionRows(data),
        updatedAt: monitoringTimestamp(data),
        relatedIds,
      };
      return `
        <article class="terminal-summary-vote" ${inspectionAttrs(inspection)}>
          <div class="terminal-summary-vote-head">
            <span>${escapeHtml(moduleLabels[key] || key)}</span>
            <small class="terminal-summary-vote-score">${escapeHtml(score)}</small>
          </div>
          <strong>${escapeHtml(readableText(item.state, "待确认"))}</strong>
          ${chip(impactLabel(item.impact || item.state), meta.className)}
          ${evidence ? `<small class="terminal-summary-evidence">证据：${escapeHtml(evidence)}</small>` : ""}
        </article>
      `;
    })
    .join("");
  const confidence = numeric(summary.confidence) !== null ? formatNumber(summary.confidence, 0) : DASH;
  const regime = summary.range_state && summary.range_state !== "NONE"
    ? rangeStateLabel(summary)
    : readableText(summary.regime, "状态待确认");
  // The shared range contract already carries the sub-direction. Keep one
  // market-state chip and avoid rendering a second, potentially conflicting bias.
  const bias = readableText(summary.bias, "中性");
  const regimeTone = summary.range_state && summary.range_state !== "NONE"
    ? rangeStateTone(summary)
    : ["上行震荡", "强趋势偏多", "温和偏多", "多头修复"].includes(regime)
    ? "bullish"
    : ["下行震荡", "空头加速", "弱势下行", "高波动风险"].includes(regime)
    ? "bearish"
    : "neutral";
  const regimeMeta = signalMeta(regimeTone);
  // Older LKG snapshots can retain the superseded execution caveat even after
  // the summary engine copy is updated. Remove it at presentation time so a
  // stale-but-valid snapshot does not bring the redundant sentence back.
  const headline = readableText(summary.headline, "全局摘要正在等待关键输入。")
    .replace("追空质量取决于反弹失败或前低跌破确认。", "")
    .trim();
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
      <p class="terminal-summary-headline">${escapeHtml(headline)}</p>
      <div class="terminal-summary-votes">${moduleVotes}</div>
    </article>
  `;
}

function renderMacroIndicatorCard(item) {
  const bias = macroBiasMeta(item.direction_label || item.direction || item.signal_state || item.impact);
  const source = readableText(item.source_provider || item.source || item.provider, "宏观");
  const time = item.observation_ts || item.updated_at || item.timestamp;
  const layer = readableText(item.layer_label || item.layer || item.category, "宏观");
  const id = workbenchId("monitoring", "indicator", item.indicator_key || item.key || item.label);
  const layerId = workbenchId("monitoring", "layer", item.layer_key || item.layer || item.layer_label || item.category);
  const inspection = {
    id,
    type: "macro-indicator",
    title: macroTitle(item),
    current: { label: "当前值", value: macroDisplayValue(item) },
    interpretation: readableText(item.comment || item.rule || item.hint || item.direction_label, `${bias.label}影响。`),
    evidence: [{ id: `${id}:source`, label: "指标层 / 来源", value: `${layer} · ${source}`, relatedIds: [layerId] }],
    impacts: [{ label: "宏观环境", summary: `${bias.label}；作为 ${layer} 层输入。` }],
    sources: [{
      name: source,
      status: ["ok", "live", "ready"].includes(normalizeKey(item.status)) ? "live" : ["cached", "stale"].includes(normalizeKey(item.status)) ? "stale" : "degraded",
      updatedAt: time || null,
    }],
    updatedAt: time || null,
    relatedIds: [layerId, "monitoring:macro", "monitoring:terminal:macro"],
  };
  const sourceDetailId = `${id}-source-detail`;
  return `
    <article class="macro-indicator-card" ${inspectionAttrs(inspection)}>
      <div class="macro-indicator-head">
        <strong>${escapeHtml(macroTitle(item))}</strong>
        ${chip(bias.label, bias.className)}
      </div>
      <b>${escapeHtml(macroDisplayValue(item))}</b>
      <div class="macro-indicator-foot">
        <span>${escapeHtml(layer)} · ${escapeHtml(source)}</span>
        <time>${escapeHtml(time ? formatDateOnly(time) : DASH)}</time>
      </div>
      <div class="macro-indicator-source">
        ${renderDisclosureToggle({
          controls: sourceDetailId,
          expanded: false,
          expandLabel: "查看来源",
          collapseLabel: "收起来源",
          variant: "inline",
          className: "macro-indicator-source-toggle",
          data: { indicatorKey: item.indicator_key || item.key || "" },
        })}
        <dl id="${sourceDetailId}" class="macro-indicator-source-detail" hidden>
          <dt>来源</dt><dd>${escapeHtml(source)}</dd>
          <dt>更新时间</dt><dd>${escapeHtml(time ? formatDateTime(time) : DASH)}</dd>
          <dt>状态</dt><dd>${escapeHtml(item.status || DASH)}</dd>
        </dl>
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

function isHiddenMacroDisplayItem(item) {
  return [item?.layer, item?.layer_label, item?.category]
    .map(normalizeKey)
    .some((value) => HIDDEN_MACRO_DISPLAY_LAYERS.has(value));
}

function renderMacroIndicatorGrid(macro, data) {
  const all = getMacroIndicators(macro);
  const displayed = all.filter((item) => !isHiddenMacroDisplayItem(item));
  const visible = displayed.filter(validMacroIndicator);
  const hidden = displayed.filter((item) => !validMacroIndicator(item));

  // 按类别分组
  const groups = new Map();
  for (const item of visible) {
    const layer = readableText(item.layer_label || item.layer || item.category, "综合");
    if (!groups.has(layer)) groups.set(layer, []);
    groups.get(layer).push(item);
  }

  // 按 LAYER_LABELS 定义的顺序排列组
  const layerOrder = ["rates_policy", "inflation", "growth", "liquidity", "cross_asset"];
  const orderedGroups = [];
  for (const key of layerOrder) {
    const label = LAYER_LABELS[key] || key;
    if (groups.has(label)) orderedGroups.push([label, groups.get(label)]);
  }
  // 补充未在 LAYER_LABELS 中定义的组
  for (const [label, items] of groups.entries()) {
    if (!orderedGroups.find(([l]) => l === label)) orderedGroups.push([label, items]);
  }

  // 默认折叠：新发现的组自动折叠，已保留状态的沿用旧值
  for (const [label] of orderedGroups) {
    if (!macroGroupCollapsed.has(label)) macroGroupCollapsed.set(label, true);
  }
  // 记录当前顺序用于 diff 更新定位
  macroGroupOrder = orderedGroups.map(([label]) => label);

  // 缺数据原因明细 — 收集所有非 ok/live/cached 的指标
  const problematic = displayed.filter((item) => {
    const status = normalizeKey(item?.status);
    return !["ok", "live", "cached", "ready", ""].includes(status);
  });

  const gridContent = orderedGroups.length
    ? orderedGroups.map(([label, items]) => {
      const isCollapsed = macroGroupCollapsed.get(label);
      const eyebrowKey = layerOrder.find((k) => LAYER_LABELS[k] === label) || "macro";
      return `
      <article class="card macro-indicator-group${isCollapsed ? " is-collapsed" : ""}" data-macro-group="${escapeHtml(label)}">
        <div class="section-head">
          <div>
            <p class="eyebrow">${escapeHtml(EYEBROW_LABELS[eyebrowKey] || "MACRO LAYER")}</p>
            <h3>${escapeHtml(label)}</h3>
          </div>
          ${renderDisclosureToggle({
            controls: `macro-group-body-${label}`,
            expanded: !isCollapsed,
            expandLabel: "展开",
            collapseLabel: "收起",
            className: "macro-group-toggle",
            data: { toggleGroup: label },
          })}
        </div>
        <div id="macro-group-body-${escapeHtml(label)}" class="macro-group-cards" ${isCollapsed ? "hidden" : ""}>
          ${items.map(renderMacroIndicatorCard).join("")}
        </div>
      </article>`;
    }).join("")
    : `<p class="monitoring-empty-note">暂无可展示宏观指标。</p>`;

  // 信源状态 — 治理底栏用（governance bar）
  const sourceRows = getSourceStatus(data);

  // 缺数据原因明细
  const missingDetail = problematic.length ? `
    <div class="monitoring-missing-bar">
      <div class="section-head">
        <div>
          <p class="eyebrow">DATA GAPS</p>
          <h2>缺数据原因</h2>
        </div>
        ${renderDisclosureToggle({
          controls: "monitoring-missing-body",
          expanded: false,
          expandLabel: `展开 ${problematic.length} 项`,
          collapseLabel: `收起 ${problematic.length} 项`,
          className: "monitoring-missing-toggle",
          data: { missingToggle: "true" },
        })}
      </div>
      <div id="monitoring-missing-body" class="monitoring-missing-body" hidden>
        ${problematic.map((item) => {
          const label = readableText(item.label || item.display_label || item.indicator_key || item.key, "未知指标");
          const reason = missingReason(item);
          const layer = readableText(item.layer_label || item.layer || item.category, "");
          const tone = missingTone(item);
          return `<div class="monitoring-missing-row">
            <span class="status-chip chip-source data-source-state="${tone}">${escapeHtml(label)}</span>
            ${layer ? `<span class="monitoring-missing-layer">${escapeHtml(layer)}</span>` : ""}
            <span class="monitoring-missing-reason">${escapeHtml(reason)}</span>
          </div>`;
        }).join("")}
      </div>
    </div>
  ` : "";

  return `
    <section class="monitoring-surface monitoring-detail-panel">
      <div class="section-heading-row">
        <div>
          <p class="eyebrow">MACRO DETAIL</p>
          <h2>宏观指标明细</h2>
        </div>
        <button id="monitoring-refresh" class="primary-button monitoring-refresh button compact" type="button">刷新监控</button>
      </div>
      <div class="macro-indicator-grid">
        ${gridContent}
      </div>
      ${missingDetail}
      ${renderMissingIndicators(hidden)}
    </section>
  `;
}

function renderSourceRow(source) {
  const meta = sourceMeta(source.status);
  return `
    <article class="monitoring-source-row">
      <div class="monitoring-source-copy">
        <div class="monitoring-source-heading">
        <strong>${escapeHtml(source.label)}</strong>
          <div class="monitoring-source-status"><span class="status-chip" data-source-state="${meta.tone}">${escapeHtml(meta.label)}</span></div>
        </div>
        <p>${escapeHtml(source.message)}</p>
        ${source.updatedAt ? `<small class="monitoring-source-time"><span>更新</span><time datetime="${escapeHtml(source.updatedAt)}">${escapeHtml(formatDateTime(source.updatedAt))}</time></small>` : ""}
      </div>
    </article>
  `;
}

function renderDashboard(data) {
  const macro = getMacroPayload(data);
  return `
    ${renderTopbar(data, macro)}
    <section class="monitoring-surface monitoring-summary-surface">
      <div class="monitoring-snapshot-grid monitoring-snapshot-grid-full">
        ${renderMacroPanel(data, macro)}
        ${renderTerminalSummary(data)}
      </div>
    </section>
    ${renderMacroIndicatorGrid(macro, data)}
    ${renderMonitoringGovernanceBar(data)}
  `;
}

// 2026-08-19: 监控页底栏 — 参考 gold-allocation DATA GOVERNANCE 设计
// 左 header + 右网格（信源状态 + 缺数据计数）
function renderMonitoringGovernanceBar(data) {
  const macro = getMacroPayload(data);
  const indicators = getMacroIndicators(macro);
  const visible = indicators.filter(validMacroIndicator);
  const problematic = indicators.filter((item) => {
    const status = normalizeKey(item?.status);
    return !["ok", "live", "cached", "ready", ""].includes(status);
  });
  const sourceRows = getSourceStatus(data);
  const freshSources = sourceRows.filter((s) => sourceMeta(s.status).tone !== "offline").length;

  // 构建网格项：信源 + 缺数据
  const gridItems = sourceRows.map((s) => {
    const meta = sourceMeta(s.status);
    const state = meta.tone === "live" ? "fresh" : meta.tone === "stale" ? "stale" : "missing";
    const tone = meta.tone === "live" ? "info" : meta.tone === "stale" ? "warning" : "danger";
    return {
      label: s.label,
      value: meta.label,
      detail: "",
      state,
      tone,
    };
  });

  // 缺数据计数作为最后一个网格项
  if (problematic.length) {
    gridItems.push({
      label: "缺数据",
      value: `${problematic.length} 项`,
      detail: "",
      state: "missing",
      tone: "warning",
    });
  }

  return renderGovernanceLedger({
    variant: "monitoring",
    readyCount: freshSources,
    totalCount: sourceRows.length,
    items: gridItems,
  });
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
  "monitoring-macro-grid",
];

function applyMonitoringDiff(data, options = {}) {
  const root = document.getElementById("page-root");
  if (!root) {
    setRoot(renderDashboard(data));
    return;
  }
  if (!hasRenderedMonitoringShell()) {
    root.innerHTML = renderShellFallback("正在读取最近快照", true);
    attachMonitoringShell(root);
  }
  const macro = getMacroPayload(data);
  const sections = root._monitoringSections;
  inspectionRegistry.clear();
  sections.topbar.innerHTML = renderTopbar(data, macro);
  sections["monitoring-macro-panel"].innerHTML = renderMacroPanel(data, macro);
  sections["monitoring-terminal-summary"].innerHTML = renderTerminalSummary(data);
  sections["monitoring-macro-grid"].innerHTML = renderMacroIndicatorGrid(macro, data);
  sections["monitoring-governance"].innerHTML = renderMonitoringGovernanceBar(data);
  inspectionRegistry.forEach((item, id) => {
    const next = { value: item.current?.value, state: item.current?.marketTone };
    const previous = previousWorkbenchValues.get(id);
    const element = root.querySelector(`[data-workbench-id="${CSS.escape(id)}"]`);
    if (previous && element) {
      animateValueChange(element, previous.value, next.value, { signal: pageController?.signal });
      animateStateChange(element, previous.state, next.state, { signal: pageController?.signal });
    }
    previousWorkbenchValues.set(id, next);
  });
  const selectedId = workbenchState?.getSnapshot().selection?.id;
  if (selectedId) {
    const nextSelection = inspectionRegistry.get(selectedId);
    const nextTrigger = root.querySelector(`[data-workbench-id="${CSS.escape(selectedId)}"]`);
    if (nextSelection) workbenchState.select(nextSelection, { trigger: nextTrigger });
    else {
      workbenchState.clearSelection({ restoreFocus: false });
      (root.querySelector(".monitoring-refresh") || root).focus?.({ preventScroll: true });
    }
  }
  bindMacroGroupToggles();
  bindMonitoringMissingToggle();
  updatePageContext({});
  workbenchUrl?.dataReady({ terminal: !data?.refresh_enqueued });
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
    priority: 5,
  });
}

async function applyCompletedMonitoringTask(bundle, controller, instrumentId, timeframe, depth = 0) {
  const taskKey = bundle?.refresh_task_key;
  if (!bundle?.refresh_enqueued || !taskKey || depth > 1) return;
  try {
    await waitForPrecomputeTask(taskKey, { signal: controller.signal });
    await waitForAbortableDelay(250, controller.signal);
    const refreshed = await api.getMonitoringDashboard(instrumentId, timeframe, {
      force: true,
      signal: controller.signal,
      timeoutMs: 30000,
    });
    if (controller.signal.aborted || activeController !== controller) return;
    applyMonitoringDiff(refreshed);
    lastRenderedBundle = refreshed;
    rememberMonitoringBundle(refreshed, instrumentId, timeframe);
    bindRefreshButton();
    if (refreshed?.refresh_task_key && refreshed.refresh_task_key !== taskKey) {
      await applyCompletedMonitoringTask(refreshed, controller, instrumentId, timeframe, depth + 1);
    }
  } catch (error) {
    if (error?.name === "AbortError") return;
    console.warn("monitoring background refresh failed", error);
    if (activeController === controller) {
      showMonitoringBanner("后台更新未完成，已保留上一份可用快照。", "warning");
      workbenchUrl?.dataReady();
    }
  }
}

function bindRefreshButton() {
  const button = document.querySelector(".monitoring-refresh");
  if (!button || boundRefreshButtons.has(button)) return;
  boundRefreshButtons.add(button);
  button.addEventListener("click", refreshMonitoring, { signal: pageController?.signal });
}

async function refreshMonitoring() {
    const controller = pageController;
    if (!controller || controller.signal.aborted) return;
    const button = document.querySelector(".monitoring-refresh");
    if (refreshInFlight) return;
    refreshInFlight = true;
    button.disabled = true;
    button.textContent = "刷新中";
    const { instrumentId, timeframe } = currentSelection();
    try {
      await api.refreshMacro({ signal: controller.signal }).catch(() => null);
      if (controller.signal.aborted || pageController !== controller) return;
      await api.refreshMonitoringDashboard(instrumentId, timeframe, { timeoutMs: 30000, signal: controller.signal }).catch(() => null);
      if (controller.signal.aborted || pageController !== controller) return;
      const [bundle, macro] = await Promise.all([
        api.getMonitoringDashboard(instrumentId, timeframe, {
          force: true,
          timeoutMs: 30000,
          signal: controller.signal,
        }),
        api.getMacroOverview({
          force: true,
          timeoutMs: 30000,
          signal: controller.signal,
        }).catch(() => null),
      ]);
      if (controller.signal.aborted || pageController !== controller) return;
      applyMonitoringDiff(mergeMacroIntoBundle(bundle, macro));
      bindRefreshButton();
      queueWarmup();
    } catch (error) {
      if (controller.signal.aborted || pageController !== controller) return;
      console.warn("monitoring refresh failed", error);
      const page = document.querySelector(".monitoring-surface");
      if (page) {
        page.insertAdjacentHTML(
          "afterbegin",
          statusBanner("刷新失败，已保留上一份可用快照。", "warning"),
        );
      }
    } finally {
      if (pageController === controller) refreshInFlight = false;
      if (button.isConnected) {
        button.disabled = false;
        button.textContent = "刷新监控";
      }
    }
}

// 2026-08-15: helper that clears the dim class on the five stable section
async function loadDashboard() {
  if (activeController) activeController.abort();
  const controller = new AbortController();
  activeController = controller;
  const { instrumentId, timeframe } = currentSelection();
  const storedBundle = readStoredMonitoringBundle(instrumentId, timeframe);
  if (!hasRenderedMonitoringShell()) {
    if (storedBundle) {
      try {
        applyMonitoringDiff(storedBundle);
        lastRenderedBundle = storedBundle;
        bindRefreshButton();
        showMonitoringBanner("正在读取最近快照", "loading");
      } catch (error) {
        console.warn("monitoring stored snapshot render failed", error);
        setRoot(renderShellFallback("正在读取最近快照", true));
        attachMonitoringShell(document.getElementById("page-root"));
      }
    } else {
      setRoot(renderShellFallback("正在读取最近快照", true));
      attachMonitoringShell(document.getElementById("page-root"));
    }
  } else {
    showMonitoringBanner("正在读取最近快照", "loading");
  }

  let bundle = null;
  const macroPromise = api.getMacroOverview({
    signal: controller.signal,
    timeoutMs: 30000,
  }).catch((error) => {
    if (error?.name !== "AbortError") {
      console.warn("monitoring macro enhancement failed", error);
    }
    return null;
  });
  try {
    bundle = await api.getMonitoringDashboard(instrumentId, timeframe, {
      signal: controller.signal,
      timeoutMs: 30000,
    });
  } catch (error) {
    if (error?.name === "AbortError") {
      return;
    }
    console.warn("monitoring snapshot fetch failed", error);
    workbenchUrl?.dataReady();
    // LKG = a real rendered bundle, not just a warming shell on screen.
    // Cold-start failures must not claim a previous snapshot exists.
    if (lastRenderedBundle && hasRenderedMonitoringShell()) {
      showMonitoringBanner("监控快照读取失败，已保留上一份可用快照。", "warning");
    } else {
      setRoot(renderShellFallback("监控快照暂不可用；可刷新或稍后自动更新。"));
      attachMonitoringShell(document.getElementById("page-root"));
    }
    return;
  }

  try {
    if (controller.signal.aborted || activeController !== controller) return;
    applyMonitoringDiff(bundle);
    lastRenderedBundle = bundle;
    rememberMonitoringBundle(bundle, instrumentId, timeframe);
    bindRefreshButton();
    queueWarmup();
    void applyCompletedMonitoringTask(bundle, controller, instrumentId, timeframe);
    macroPromise.then((macro) => {
      if (!macro || !lastRenderedBundle || controller.signal.aborted || activeController !== controller) return;
      try {
        const enhancedBundle = mergeMacroIntoBundle(lastRenderedBundle, macro);
        applyMonitoringDiff(enhancedBundle);
        lastRenderedBundle = enhancedBundle;
        rememberMonitoringBundle(enhancedBundle, instrumentId, timeframe);
        bindRefreshButton();
      } catch (error) {
        console.error("monitoring macro enhancement render failed", error);
      }
    });
  } catch (error) {
    console.error("monitoring render failed", {
      error,
      bundleStatus: bundle?.status,
      bundleKeys: bundle && Object.keys(bundle),
    });
    if (lastRenderedBundle && hasRenderedMonitoringShell()) {
      showMonitoringBanner("页面更新异常，已保留上一份可用快照。", "warning");
    } else {
      setRoot(renderShellFallback("页面渲染异常；可刷新或稍后自动更新。"));
      attachMonitoringShell(document.getElementById("page-root"));
    }
  }
}

export async function renderMonitoring({ commands } = {}) {
  if (!workbenchState) workbenchState = createWorkbenchState({ scopeId: "monitoring-overview" });
  workbenchUrl = mountWorkbenchUrlState(workbenchState, inspectionRegistry, { fallbackId: "monitoring-refresh" });
  pageController?.abort();
  pageController = new AbortController();
  refreshInFlight = false;
  commands?.register({ id: "monitoring:refresh", label: "刷新当前监控", enabled: () => !refreshInFlight, run: refreshMonitoring });
  commands?.register({ id: "monitoring:inspect-macro", label: "打开宏观研究对象", enabled: () => inspectionRegistry.has("monitoring:macro"), run: () => workbenchState.select(inspectionRegistry.get("monitoring:macro"), { trigger: document.querySelector('[data-workbench-id="monitoring:macro"]') }) });
  commands?.register({ id: "monitoring:close-inspector", label: "关闭当前 Inspector", enabled: () => Boolean(workbenchState?.getSnapshot().selection), run: () => workbenchState.clearSelection() });
  const loadPromise = loadDashboard().catch((error) => {
    console.error("monitoring:load:error", error);
  });
  bindMacroGroupToggles();
  bindMonitoringMissingToggle();
  const guideFab = mountPageGuide("monitoring-overview");
  return {
    async unmount() {
      pageController?.abort();
      pageController = null;
      guideFab.unmount();
      activeController?.abort();
      activeController = null;
      interactionController?.abort();
      interactionController = null;
      workbenchUnsubscribe?.();
      workbenchUnsubscribe = null;
      inspector?.destroy();
      inspector = null;
      workbenchUrl?.destroy();
      workbenchUrl = null;
      workbenchState?.destroy();
      workbenchState = null;
      previousWorkbenchValues.clear();
      inspectionRegistry.clear();
      void loadPromise.catch(() => null);
    },
    async pause() {},
    async resume() {},
  };
}

// 宏观指标分组折叠 — 直接绑定到每个按钮（在渲染后调用）
function bindMacroGroupToggles() {
  document.querySelectorAll(".macro-group-toggle").forEach((btn) => {
    // 避免重复绑定：如果已有 data-bound 标记则跳过
    if (btn.dataset.bound === "1") return;
    btn.dataset.bound = "1";
    btn.addEventListener("click", () => {
      const label = btn.dataset.toggleGroup;
      const group = btn.closest(".macro-indicator-group");
      if (!group || !label) return;
      const body = group.querySelector(".macro-group-cards");
      if (!body) return;
      const wasCollapsed = macroGroupCollapsed.get(label);
      macroGroupCollapsed.set(label, !wasCollapsed);
      group.classList.toggle("is-collapsed", !wasCollapsed);
      body.hidden = !wasCollapsed;
      setDisclosureState(btn, wasCollapsed);
    });
  });
  document.querySelectorAll(".macro-indicator-source-toggle").forEach((btn) => {
    if (btn.dataset.bound === "1") return;
    btn.dataset.bound = "1";
    const detailId = btn.getAttribute("aria-controls");
    if (!detailId) return;
    const detail = document.getElementById(detailId);
    if (!detail) return;
    btn.addEventListener("click", () => {
      const expanded = btn.getAttribute("aria-expanded") === "true";
      const next = !expanded;
      btn.setAttribute("aria-expanded", String(next));
      detail.hidden = !next;
      const label = btn.querySelector("[data-disclosure-label]");
      if (label) {
        label.textContent = next
          ? btn.dataset.disclosureCollapseLabel || "收起来源"
          : btn.dataset.disclosureExpandLabel || "查看来源";
      }
    });
  });
}

function bindMonitoringMissingToggle() {
  const button = document.querySelector("[data-missing-toggle]");
  if (!button || button.dataset.bound === "1") return;
  button.dataset.bound = "1";
  button.addEventListener("click", () => {
    const body = document.getElementById("monitoring-missing-body");
    if (!body) return;
    const nextExpanded = button.getAttribute("aria-expanded") !== "true";
    body.hidden = !nextExpanded;
    setDisclosureState(button, nextExpanded);
  });
}
