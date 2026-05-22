import { api } from "../core/api.js";
import {
  escapeHtml,
  formatDateTime,
  formatIndicatorName,
  formatNumber,
  observationValue,
  setRoot,
  statusBanner,
} from "../core/dom.js";
import { scheduleIdlePrecompute } from "../core/precompute.js";
import { appState } from "../core/state.js";

let activeController = null;
let refreshInFlight = false;
const queuedKeys = new Set();

const DASH = "—";
const BAD_TEXT_RE = /[\uFFFD\u951f\u934b\u7039\u93c6]/u;
const INVALID_TEXT_VALUES = new Set([
  "unavailable",
  "source_error",
  "pending",
  "pending_release",
  "placeholder",
  "missing",
  "none",
  "null",
  "nan",
]);
const DATA_STATUS_VALUES = new Set([
  "ok",
  "fresh",
  "cached",
  "stale",
  "stale_cache",
  "seed_cache",
  "web_cached",
  "online",
]);
const NON_MAIN_INDICATOR_STATUSES = new Set([
  "auth_missing",
  "disabled",
  "missing",
  "not_configured",
  "not_implemented",
  "parser_error",
  "pending",
  "pending_release",
  "placeholder",
  "proxy_required_unavailable",
  "rate_limited",
  "source_error",
  "unavailable",
  "unavailable_placeholder",
  "web_cached",
]);

const STATUS_TEXT = {
  reading: "正在读取监控快照",
  ready: "监控快照可用",
  fresh: "监控快照可用",
  stale: "监控快照可用，但可能略滞后；后台会继续维护缓存。",
  missing: "暂无监控快照，后台正在准备当前标的与周期的数据。",
  updating: "监控快照正在后台准备，当前先展示可用缓存。",
  error: "监控快照读取异常，已保留可用缓存和降级信息。",
  failed: "监控快照读取失败，已保留页面骨架，可稍后重试。",
};

const SOURCE_LABELS = {
  gateio: "Gate.io",
  fred: "FRED",
  market_events: "市场事件",
  ashare_etf: "A股ETF",
};

const SOURCE_MESSAGES = {
  online: "K 线与技术输入可用，技术、结构和告警会复用本地快照。",
  ok: "数据源在线，当前结果可用于判断。",
  fresh: "最新快照可用。",
  stale_cache: "远端暂不稳定，当前使用最近缓存。",
  stale: "远端暂不稳定，当前使用最近缓存。",
  cached: "当前使用最近缓存。",
  seed_cache: "当前使用内置种子缓存，仅用于保持页面可读。",
  web_cached: "当前使用网页快照缓存，仅作低置信参考。",
  no_data: "该信源暂时没有可用数据。",
  missing: "该信源暂时没有可用数据。",
  not_configured: "该信源未配置，不视为系统故障。",
  auth_missing: "API Key 未配置，不视为系统故障。",
  updating: "后台正在准备该信源快照。",
  pending: "后台正在准备该信源快照。",
  offline: "该信源读取失败，只影响对应数据块。",
  error: "该信源读取失败，只影响对应数据块。",
  source_error: "该信源读取失败，只影响对应数据块。",
  rate_limited: "信源暂时限流，后续会自动重试或使用缓存。",
  unavailable: "行情源暂不可用，等待下次刷新。",
};

const LAYER_LABELS = {
  rates_policy: "利率与政策",
  inflation: "通胀与价格",
  growth_labor: "增长与就业",
  liquidity_credit: "流动性与信用",
  cross_asset_confirmation: "跨资产确认",
  event_window: "事件窗口",
};

const MACRO_TITLE_FALLBACKS = {
  effr: "美国有效联邦基金利率",
  sofr: "SOFR 隔夜融资利率",
  us03m_yield: "美国3个月国债收益率",
  us02y_yield: "美国2年期国债收益率",
  us10y_yield: "美国10年期国债收益率",
  us30y_yield: "美国30年期国债收益率",
  us10y_2y_spread: "美债10Y-2Y利差",
  us10y_3m_spread: "美债10Y-3M利差",
  cpi_yoy: "美国CPI同比",
  cpi_mom: "美国CPI环比",
  core_cpi_yoy: "美国核心CPI同比",
  core_cpi_mom: "美国核心CPI环比",
  pce_yoy: "美国PCE同比",
  core_pce_yoy: "美国核心PCE同比",
  breakeven_5y: "美国5年通胀预期",
  breakeven_10y: "美国10年通胀预期",
  wti_oil: "WTI原油",
  nfp: "美国非农就业",
  unemployment_rate: "美国失业率",
  average_hourly_earnings_yoy: "美国平均时薪同比",
  initial_claims: "美国初请失业金人数",
  continuing_claims: "美国续请失业金人数",
  jolts_openings: "JOLTS职位空缺",
  gdp_qoq: "美国GDP环比",
  fed_balance_sheet: "美联储资产负债表",
  reverse_repo: "隔夜逆回购余额",
  bank_reserves: "美国银行准备金",
  m2: "美国M2货币供应",
  hy_spread: "美国高收益债利差",
  investment_grade_spread: "投资级信用利差",
  financial_conditions: "金融条件指数",
  dxy: "美元指数 DXY",
  real_yield_10y: "美国10年实际利率",
  gold: "黄金",
  vix: "VIX波动率",
  qqq: "纳斯达克100 ETF",
  spy: "标普500 ETF",
  hyg: "高收益债 ETF",
  usd_cny: "美元兑人民币",
  fomc_event_window: "FOMC事件窗口",
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
  obv_slope: "OBV 斜率",
  obv_change_5: "OBV 5期变化",
  kdj_j: "KDJ J",
  cci_20: "CCI 20",
  volume: "成交量",
};

const MISSING_REASON_LABELS = {
  sync_missing: "同步未运行或缓存未命中",
  cache_missing: "同步未运行或缓存未命中",
  dependency_missing: "缺依赖指标",
  auth_missing: "API 未配置",
  not_configured: "API 未配置",
  source_error: "网络或源错误",
  rate_limited: "网络或限流失败",
  network_error: "网络或限流失败",
  pending_release: "等待官方发布",
  market_source_missing: "待接入行情源",
  not_implemented: "待接入行情源",
  placeholder: "仅占位",
  unavailable_placeholder: "仅占位",
  disabled: "未启用",
  missing: "暂无数据",
};

const TECHNICAL_HINTS = {
  bullish: "指标偏向多头。",
  weak_bullish: "指标略偏多。",
  bearish: "指标偏向空头。",
  weak_bearish: "指标略偏空。",
  positive_hist: "柱值转强，动能偏多。",
  negative_hist: "柱值转弱，动能偏空。",
  compressed: "波动收缩，等待方向释放。",
  developing_trend: "趋势正在形成。",
  strong_trend: "趋势强度较高。",
  overbought: "处于偏热区域。",
  oversold: "处于偏冷区域。",
  normal: "处于常态区间。",
  neutral: "暂未给出方向。",
  inactive: "事件尚未触发。",
};

const MACRO_DISPLAY_LABELS = {
  effr: "EFFR 美国有效联邦基金利率",
  sofr: "SOFR 隔夜融资利率",
  us03m_yield: "US3M 美国3个月国债收益率",
  us02y_yield: "US2Y 美国2年期国债收益率",
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
  breakeven_5y: "美国5年通胀预期",
  breakeven_10y: "美国10年通胀预期",
  wti_oil: "WTI原油",
  nfp: "US NFP 美国非农就业",
  unemployment_rate: "美国失业率",
  average_hourly_earnings_yoy: "美国平均时薪同比",
  initial_claims: "美国初请失业金人数",
  continuing_claims: "美国续请失业金人数",
  jolts_openings: "JOLTS职位空缺",
  gdp_qoq: "美国GDP环比",
  fed_balance_sheet: "美联储资产负债表",
  reverse_repo: "隔夜逆回购余额",
  bank_reserves: "美国银行准备金",
  m2: "美国M2货币供应",
  hy_spread: "美国高收益债利差",
  investment_grade_spread: "IG SPREAD 美国投资级信用利差",
  financial_conditions: "金融条件指数",
  dxy: "DXY 美元指数",
  real_yield_10y: "美国10年实际利率",
  gold: "黄金",
  vix: "VIX波动率",
  qqq: "QQQ 纳斯达克100 ETF",
  spy: "SPY 标普500 ETF",
  hyg: "HYG 高收益债ETF",
  usd_cny: "USD/CNY 美元兑人民币",
  fomc_event_window: "FOMC事件窗口",
};

function text(value, fallback = DASH) {
  if (value === null || value === undefined || value === "") return fallback;
  if (typeof value === "object") {
    return value.label || value.name || value.status || value.message || fallback;
  }
  return String(value);
}

function cleanText(value, fallback = DASH) {
  const raw = text(value, fallback).trim();
  if (!raw || raw === DASH || BAD_TEXT_RE.test(raw)) return fallback;
  return raw;
}

function normalizeStatus(value) {
  return cleanText(value, "neutral").toLowerCase().replace(/\s+/g, "_");
}

function formatCompactNumber(value, digits = 2) {
  if (value === null || value === undefined || value === "" || typeof value === "object") {
    return DASH;
  }
  const numeric = Number(value);
  if (!Number.isFinite(numeric)) return cleanText(value, DASH);
  return formatNumber(numeric, digits);
}

function macroCompleteness(macro) {
  const raw = macro?.data_completeness;
  if (typeof raw === "number") return raw;
  if (raw && typeof raw === "object") {
    if (raw.percent !== undefined) return Number(raw.percent) || 0;
    if (raw.ratio !== undefined) return (Number(raw.ratio) || 0) * 100;
    if (raw.effective_count !== undefined && raw.total_count) {
      return (Number(raw.effective_count) / Number(raw.total_count)) * 100;
    }
  }
  return 0;
}

function macroEffectiveCount(macro) {
  const raw = macro?.data_completeness;
  if (raw && typeof raw === "object") {
    return Number(raw.effective_count ?? raw.scored_count ?? 0) || 0;
  }
  return Number(macro?.scored_indicator_count ?? macro?.effective_indicator_count ?? 0) || 0;
}

function macroTotalCount(macro) {
  const raw = macro?.data_completeness;
  if (raw && typeof raw === "object") {
    return Number(raw.total_count ?? 0) || 0;
  }
  return Number(macro?.total_indicator_count ?? 0) || flattenMacroIndicators(macro).length || 0;
}

function displayObservationValue(value) {
  if (value === null || value === undefined || value === "") return DASH;
  if (typeof value === "object") {
    return observationValue(value.value_num ?? value.value_text ?? value.value ?? DASH);
  }
  return observationValue(value);
}

function confidenceLabel(value) {
  return (
    {
      high: "较高",
      medium: "中等",
      low: "不足",
      insufficient: "不足",
    }[normalizeStatus(value)] || cleanText(value, "不足")
  );
}

function signalMeta(value) {
  const state = normalizeStatus(value);
  const mapping = {
    bullish: { label: "看多", className: "chip-bullish" },
    weak_bullish: { label: "偏多", className: "chip-bullish" },
    positive: { label: "看多", className: "chip-bullish" },
    positive_hist: { label: "偏强", className: "chip-bullish" },
    strong: { label: "偏强", className: "chip-bullish" },
    strong_trend: { label: "偏强", className: "chip-bullish" },
    developing_trend: { label: "偏强", className: "chip-bullish" },
    rising: { label: "上行", className: "chip-bullish" },
    upside: { label: "上行", className: "chip-bullish" },
    bearish: { label: "看空", className: "chip-bearish" },
    weak_bearish: { label: "偏空", className: "chip-bearish" },
    negative: { label: "看空", className: "chip-bearish" },
    negative_hist: { label: "偏弱", className: "chip-bearish" },
    weak: { label: "偏弱", className: "chip-bearish" },
    weak_trend: { label: "偏弱", className: "chip-bearish" },
    falling: { label: "下行", className: "chip-bearish" },
    downside: { label: "下行", className: "chip-bearish" },
    tight: { label: "收紧", className: "chip-bearish" },
    steepening: { label: "曲线趋陡", className: "chip-bullish" },
    overbought: { label: "偏热", className: "chip-event" },
    oversold: { label: "偏冷", className: "chip-event" },
    active: { label: "事件", className: "chip-event" },
    source_error: { label: "异常", className: "chip-event" },
    rate_limited: { label: "限流", className: "chip-event" },
    compressed: { label: "收缩", className: "chip-neutral" },
    normal: { label: "正常", className: "chip-neutral" },
    neutral: { label: "中性", className: "chip-neutral" },
    inactive: { label: "未触发", className: "chip-neutral" },
    observe: { label: "观望", className: "chip-neutral" },
    wait: { label: "观望", className: "chip-neutral" },
  };
  return mapping[state] || { label: cleanText(value, "中性"), className: "chip-neutral" };
}

function macroBiasMeta(scoreOrBias) {
  if (typeof scoreOrBias === "number") {
    if (scoreOrBias >= 65) return { label: "偏多", className: "chip-bullish" };
    if (scoreOrBias <= 35) return { label: "偏空", className: "chip-bearish" };
    return { label: "中性", className: "chip-neutral" };
  }
  return signalMeta(scoreOrBias || "neutral");
}

function sourceStatusMeta(status) {
  const mapping = {
    online: { label: "在线", className: "chip-bullish" },
    ok: { label: "在线", className: "chip-bullish" },
    fresh: { label: "在线", className: "chip-bullish" },
    stale_cache: { label: "使用缓存", className: "chip-event" },
    stale: { label: "使用缓存", className: "chip-event" },
    cached: { label: "使用缓存", className: "chip-event" },
    seed_cache: { label: "种子缓存", className: "chip-event" },
    web_cached: { label: "网页缓存", className: "chip-event" },
    no_data: { label: "无数据", className: "chip-event" },
    missing: { label: "无数据", className: "chip-event" },
    not_configured: { label: "未配置", className: "chip-neutral" },
    auth_missing: { label: "未配置", className: "chip-neutral" },
    updating: { label: "后台准备中", className: "chip-neutral" },
    pending: { label: "后台准备中", className: "chip-neutral" },
    offline: { label: "离线", className: "chip-bearish" },
    error: { label: "离线", className: "chip-bearish" },
    source_error: { label: "离线", className: "chip-bearish" },
    unavailable: { label: "暂不可用", className: "chip-bearish" },
    rate_limited: { label: "限流", className: "chip-event" },
  };
  return mapping[normalizeStatus(status)] || { label: "未知", className: "chip-neutral" };
}

function normalizeSourceStatus(raw) {
  const source = raw && typeof raw === "object" ? raw : {};
  return Object.entries(SOURCE_LABELS).map(([key, label]) => {
    const value = source[key];
    const item = value && typeof value === "object" ? value : { status: value || "updating" };
    const status = normalizeStatus(item.status || "updating");
    const fallbackMessage = SOURCE_MESSAGES[status] || "状态暂不可用。";
    return {
      key,
      label,
      status,
      message: cleanText(item.message, fallbackMessage),
      updatedAt: item.updated_at || item.snapshot_at,
      lastError: item.last_error || item.error_message,
    };
  });
}

function macroTitle(item) {
  const key = item?.indicator_key || item?.indicator_id;
  return cleanText(
    MACRO_DISPLAY_LABELS[key] ||
      item?.display_label ||
      item?.label ||
      item?.name_cn ||
      item?.name ||
      item?.indicator_name,
    MACRO_TITLE_FALLBACKS[key] || cleanText(key, "宏观指标"),
  );
}

function flattenMacroIndicators(macro) {
  const fromLayers = Array.isArray(macro?.layers)
    ? macro.layers.flatMap((layer) =>
        (layer.indicators || []).map((item) => ({
          ...item,
          layer_key: item.layer_key || layer.layer_key,
          layer_label: item.layer_label || layer.label,
        })),
      )
    : [];
  const direct = Array.isArray(macro?.indicators) ? macro.indicators : [];
  const rows = direct.length ? direct : fromLayers;
  const seen = new Set();
  return rows.filter((item) => {
    const key = item?.indicator_key || item?.indicator_id || item?.label || item?.name;
    if (!key || seen.has(key)) return false;
    seen.add(key);
    return true;
  });
}

function hasIndicatorValue(item) {
  const status = normalizeStatus(item?.status || item?.source_status);
  if (NON_MAIN_INDICATOR_STATUSES.has(status)) return false;
  if (item?.value_num !== null && item?.value_num !== undefined && item.value_num !== "") {
    return Number.isFinite(Number(item.value_num));
  }
  const raw = String(item?.value_text ?? item?.latest_value ?? "").trim();
  if (!raw || INVALID_TEXT_VALUES.has(raw.toLowerCase())) return false;
  return !BAD_TEXT_RE.test(raw);
}

function macroUnit(item) {
  const unit = cleanText(item?.unit || item?.value_unit, "");
  return unit === "%" || unit === "pp" ? unit : "";
}

function appendMacroUnit(value, unit) {
  if (!value || value === DASH || !unit) return value;
  if (value.endsWith("%") || value.endsWith("pp")) return value;
  return `${value}${unit}`;
}

function macroDisplayValue(item) {
  const unit = macroUnit(item);
  if (item?.value_num !== null && item?.value_num !== undefined && item.value_num !== "") {
    return appendMacroUnit(formatCompactNumber(item.value_num, 2), unit);
  }
  const raw = String(item?.value_text ?? item?.latest_value ?? "").trim();
  if (!raw || INVALID_TEXT_VALUES.has(raw.toLowerCase()) || BAD_TEXT_RE.test(raw)) return DASH;
  const numeric = Number(raw);
  return Number.isFinite(numeric)
    ? appendMacroUnit(formatCompactNumber(numeric, 2), unit)
    : cleanText(raw, DASH);
}

function macroSignalMeta(item) {
  const signal = [item?.direction_label, item?.signal_state, item?.impact, item?.direction]
    .map((value) => normalizeStatus(value))
    .find((value) => value && !DATA_STATUS_VALUES.has(value));
  if (signal) return signalMeta(signal);
  if (item?.is_scored && item?.value_num !== null && item?.value_num !== undefined) {
    return macroBiasMeta(Number(item.value_num));
  }
  return signalMeta("neutral");
}

function missingReason(item) {
  const candidates = [
    item?.reason_code,
    item?.status_reason,
    item?.reason,
    item?.fallback_level,
    item?.status,
    item?.source_status,
  ];
  const raw = candidates.map((value) => normalizeStatus(value)).find((value) => value && value !== "neutral");
  return MISSING_REASON_LABELS[raw] || "暂无数据";
}

function groupMissingRows(rows) {
  const groups = new Map();
  rows.forEach((item) => {
    const reason = missingReason(item);
    const group = groups.get(reason) || [];
    group.push(item);
    groups.set(reason, group);
  });
  return [...groups.entries()];
}

function technicalRows(data) {
  const rows = Array.isArray(data?.technical_observations) ? data.technical_observations : [];
  return rows
    .map((item) => ({
      key: item.indicator_key || item.metric || item.name,
      label:
        TECHNICAL_LABELS[item.indicator_key] ||
        formatIndicatorName(item.indicator_key || item.metric || item.name || "指标"),
      value: item.value_num ?? item.value_text ?? item.value ?? item,
      signal: item.signal_state || item.state || "neutral",
      hint: item.comment || item.message || TECHNICAL_HINTS[normalizeStatus(item.signal_state)] || "最新技术观测。",
    }))
    .filter((item) => item.key);
}

function macroAvailableRows(macro) {
  return flattenMacroIndicators(macro).filter((item) => hasIndicatorValue(item));
}

function macroMissingRows(macro) {
  return flattenMacroIndicators(macro).filter((item) => !hasIndicatorValue(item));
}

function renderTopbar(data, macro) {
  const techCount = Number(data?.technical_indicator_count || technicalRows(data).length || 0);
  const scored = macroEffectiveCount(macro);
  const total = macroTotalCount(macro);
  const missing = Math.max(0, total - scored);
  return `
    <section class="monitoring-surface monitoring-topbar">
      <div class="monitoring-topbar-grid">
        <div class="monitoring-topbar-item wide">
        <span class="eyebrow">MONITORING</span>
        <h2>监控总览</h2>
        <p>${escapeHtml(cleanText(data?.status_message, "汇总宏观、技术与信源状态。"))}</p>
        </div>
        <div class="monitoring-topbar-item score"><small>宏观总分</small><strong>${formatCompactNumber(macro?.total_score ?? macro?.score, 0)}</strong></div>
        <div class="monitoring-topbar-item"><small>置信度</small><strong>${escapeHtml(confidenceLabel(macro?.confidence))}</strong></div>
        <div class="monitoring-topbar-item"><small>完整度</small><strong>${formatCompactNumber(macroCompleteness(macro), 0)}%</strong></div>
        <div class="monitoring-topbar-item"><small>技术指标</small><strong>${formatCompactNumber(techCount, 0)} 项</strong></div>
        <div class="monitoring-topbar-item"><small>主要缺口</small><strong>${formatCompactNumber(missing, 0)} 项</strong></div>
        <button id="monitoring-refresh" class="button compact" type="button">刷新监控</button>
      </div>
    </section>
  `;
}

function macroLayerRows(macro) {
  const contributionMap =
    macro?.layer_contributions && !Array.isArray(macro.layer_contributions)
      ? macro.layer_contributions
      : {};
  const layers = Array.isArray(macro?.layers) ? macro.layers : [];
  if (layers.length) {
    return layers.map((layer) => ({
      key: layer.layer_key,
      label: layer.label_cn || layer.label || LAYER_LABELS[layer.layer_key] || layer.layer_key,
      score: layer.score ?? layer.layer_score ?? 50,
      contribution: contributionMap[layer.layer_key] ?? layer.contribution ?? 0,
      valid: layer.effective_count ?? layer.valid_count ?? layer.scored_count ?? 0,
      total: layer.total_count ?? layer.indicator_count ?? (layer.indicators || []).length,
    }));
  }
  if (Array.isArray(macro?.layer_contributions)) {
    return macro.layer_contributions.map((layer) => ({
      key: layer.layer_key,
      label: layer.label || LAYER_LABELS[layer.layer_key] || "分层",
      score: layer.score ?? 50,
      contribution: layer.contribution ?? 0,
      valid: layer.valid_count ?? 0,
      total: layer.total_count ?? 0,
    }));
  }
  return Object.entries(contributionMap).map(([key, value]) => ({
    key,
    label: LAYER_LABELS[key] || key,
    score: 50 + Number(value || 0),
    contribution: value,
    valid: 0,
    total: 0,
  }));
}

function renderMacroSummary(macro) {
  const layerCards = macroLayerRows(macro)
    .slice(0, 6)
    .map((layer) => {
      return `
        <article class="macro-layer-chip">
          <strong>${escapeHtml(cleanText(layer.label, "分层"))}</strong>
          <b>${formatCompactNumber(layer.score, 0)}</b>
          <small>贡献 ${formatCompactNumber(layer.contribution, 2)} · 有效 ${formatCompactNumber(layer.valid, 0)}/${formatCompactNumber(layer.total, 0)}</small>
        </article>
      `;
    })
    .join("");
  const bias = signalMeta(macro?.operation_bias || macro?.score_bias || "neutral");
  return `
    <section class="monitoring-panel monitoring-macro-panel">
      <div class="monitoring-panel-head">
        <div>
          <span class="eyebrow">MACRO</span>
          <h3>宏观判断</h3>
        </div>
        <span class="chip ${bias.className}">${escapeHtml(bias.label)}</span>
      </div>
      <div class="macro-score-block">
        <b>${formatCompactNumber(macro?.total_score ?? macro?.score, 0)}</b>
        <div>
          <strong>${escapeHtml(cleanText(macro?.score_band, "中性震荡"))}</strong>
          <p>${escapeHtml(cleanText(macro?.summary, "宏观总分以可评分指标计算。"))}</p>
        </div>
      </div>
      <div class="macro-mini-metrics">
        <span><small>置信度</small><b>${escapeHtml(confidenceLabel(macro?.confidence))}</b></span>
        <span><small>完整度</small><b>${formatCompactNumber(macroCompleteness(macro), 0)}%</b></span>
        <span><small>倾向</small><b>${escapeHtml(bias.label)}</b></span>
      </div>
      <div class="macro-layer-strip">${layerCards || `<p class="muted">暂无分层贡献。</p>`}</div>
    </section>
  `;
}

function renderTechnicalSummary(data) {
  const rows = technicalRows(data);
  const cards = rows
    .slice(0, 18)
    .map((item) => {
      const meta = signalMeta(item.signal);
      return `
        <article class="technical-chip">
          <div>
            <strong>${escapeHtml(item.label)}</strong>
            <span>${escapeHtml(displayObservationValue(item.value))}</span>
          </div>
          <span class="chip ${meta.className}">${escapeHtml(meta.label)}</span>
          <small>${escapeHtml(cleanText(item.hint, "最新技术观测。"))}</small>
        </article>
      `;
    })
    .join("");
  return `
    <section class="monitoring-panel">
      <div class="monitoring-panel-head">
        <div>
          <span class="eyebrow">TECHNICAL</span>
          <h3>技术观测</h3>
        </div>
        <span class="chip chip-neutral">${formatCompactNumber(rows.length, 0)} 项</span>
      </div>
      <div class="technical-chip-grid">${cards || `<p class="muted">技术快照后台准备中。</p>`}</div>
    </section>
  `;
}

function renderSourceStatus(data) {
  const rows = normalizeSourceStatus(data?.source_status);
  const items = rows
    .map((item) => {
      const meta = sourceStatusMeta(item.status);
      return `
        <article class="monitoring-source-row">
          <div>
            <strong>${escapeHtml(item.label)}</strong>
            <p>${escapeHtml(item.message)}</p>
          </div>
          <span class="chip ${meta.className}">${escapeHtml(meta.label)}</span>
        </article>
      `;
    })
    .join("");
  return `
    <section class="monitoring-panel">
      <div class="monitoring-panel-head">
        <div>
          <span class="eyebrow">SOURCES</span>
          <h3>信源状态</h3>
        </div>
      </div>
      <div class="monitoring-source-list">${items}</div>
    </section>
  `;
}

function renderMacroIndicatorGrid(macro) {
  const rows = macroAvailableRows(macro);
  const cards = rows
    .map((item) => {
      const meta = macroSignalMeta(item);
      const source = cleanText(item.source_provider || item.source || item.provider_key, "来源待确认");
      const updatedAt = item.updated_at || item.observation_ts || item.as_of;
      return `
        <article class="macro-indicator-card">
          <div class="macro-indicator-topline">
            <strong>${escapeHtml(macroTitle(item))}</strong>
            <span class="chip ${meta.className}">${escapeHtml(meta.label)}</span>
          </div>
          <span class="macro-indicator-value">${escapeHtml(macroDisplayValue(item))}</span>
          <p>${escapeHtml(cleanText(item.layer_label || LAYER_LABELS[item.layer_key], "宏观"))} · ${escapeHtml(source)} · ${escapeHtml(formatDateTime(updatedAt) || DASH)}</p>
          <small>${escapeHtml(meta.label)}影响</small>
        </article>
      `;
    })
    .join("");
  return `
    <div class="macro-indicator-grid">${cards || `<p class="muted">暂无可用宏观指标。</p>`}</div>
  `;
}

function renderMissingDrawer(macro) {
  const rows = macroMissingRows(macro);
  if (!rows.length) return "";
  const groups = groupMissingRows(rows)
    .map(([reason, items]) => {
      const names = items
        .slice(0, 18)
        .map((item) => `<span>${escapeHtml(macroTitle(item))}</span>`)
        .join("");
      const suffix = items.length > 18 ? `<span>另 ${items.length - 18} 项</span>` : "";
      return `
        <article>
          <strong>${escapeHtml(reason)} · ${items.length} 项</strong>
          <p class="macro-missing-tags">${names}${suffix}</p>
        </article>
      `;
    })
    .join("");
  return `
    <details class="macro-hidden-details">
      <summary>未获取指标 ${rows.length} 项</summary>
      <div class="macro-hidden-groups">${groups}</div>
    </details>
  `;
}

function renderMacroDetails(macro) {
  const visibleCount = macroAvailableRows(macro).length;
  return `
    <section class="monitoring-surface monitoring-detail-panel">
      <div class="monitoring-panel-head">
        <div>
          <span class="eyebrow">MACRO DETAIL</span>
          <h2>宏观指标明细</h2>
          <p>默认展示有真实值或可评分的指标，未获取项按原因折叠。</p>
        </div>
        <span class="chip chip-neutral">${formatCompactNumber(visibleCount, 0)} 项可见</span>
      </div>
      ${renderMacroIndicatorGrid(macro)}
      ${renderMissingDrawer(macro)}
    </section>
  `;
}

function monitoringStatusMessage(bundle) {
  const status = bundle?.status || bundle?.cache_state || "ready";
  const message = bundle?.status_message || STATUS_TEXT[status] || STATUS_TEXT.ready;
  const tone = status === "error" || status === "failed" ? "warning" : status === "stale" ? "info" : "success";
  return statusBanner(cleanText(message, STATUS_TEXT.ready), tone);
}

function extractData(bundle) {
  return bundle?.data || bundle || {};
}

function extractMacro(data) {
  return data?.macro_overview || data?.macro || {};
}

function mergeMacroIntoBundle(bundle, macro) {
  const data = extractData(bundle);
  if (!macro) return { ...(bundle || {}), data };
  return { ...(bundle || {}), data: { ...data, macro_overview: macro } };
}

function renderShellFallback(message = "监控页暂时只能展示降级状态。") {
  return `
    <div class="page-section">
      ${statusBanner(message, "warning")}
      <section class="monitoring-surface">
        <h2>监控总览</h2>
        <p class="muted">后台准备中，稍后会回填宏观、技术与信源状态。</p>
      </section>
    </div>
  `;
}

function renderDashboard(bundle) {
  const data = extractData(bundle);
  const macro = extractMacro(data);
  return `
    <div class="page-section monitoring-page">
      ${monitoringStatusMessage(bundle)}
      ${renderTopbar(data, macro)}
      <section class="monitoring-surface monitoring-summary-surface">
        <div class="monitoring-snapshot-grid">
          ${renderMacroSummary(macro)}
          ${renderTechnicalSummary(data)}
          ${renderSourceStatus(data)}
        </div>
      </section>
      ${renderMacroDetails(macro)}
    </div>
  `;
}

function currentSelection() {
  return {
    instrumentId: appState.selectedInstrumentId || "btc-usdt-perp",
    timeframe: appState.selectedTimeframe || "1d",
  };
}

function bindRefreshButton() {
  const button = document.getElementById("monitoring-refresh");
  if (!button) return;
  button.addEventListener("click", async () => {
    if (refreshInFlight) return;
    refreshInFlight = true;
    button.disabled = true;
    button.textContent = "刷新中";
    try {
      await api.refreshMacro();
      const { instrumentId, timeframe } = currentSelection();
      const [bundle, macro] = await Promise.all([
        api.refreshMonitoringDashboard(instrumentId, timeframe, { timeoutMs: 30000 }),
        api.getMacroOverview({ force: true, timeoutMs: 30000 }),
      ]);
      setRoot(renderDashboard(mergeMacroIntoBundle(bundle, macro)));
      bindRefreshButton();
      queueWarmup();
    } catch (error) {
      console.warn("monitoring refresh failed", error);
      button.textContent = "刷新失败";
      button.disabled = false;
      const notice = document.querySelector(".monitoring-page");
      if (notice) {
        notice.insertAdjacentHTML(
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

function queueWarmup() {
  const { instrumentId, timeframe } = currentSelection();
  const key = `${instrumentId}:${timeframe}`;
  if (queuedKeys.has(key)) return;
  queuedKeys.add(key);
  scheduleIdlePrecompute({
    current_page: "monitoring-overview",
    instrument_id: instrumentId,
    timeframe,
    reason: "monitoring_page_view",
    priority: 2,
    visible: true,
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
      api
        .getMacroOverview({ signal: activeController.signal, timeoutMs: 30000 })
        .catch(() => null),
    ]);
  } catch (error) {
    if (error?.name === "AbortError") return;
    console.warn("monitoring snapshot fetch failed", error);
    setRoot(renderShellFallback("监控快照读取失败，后台仍会继续准备数据。"));
    return;
  }
  try {
    setRoot(renderDashboard(mergeMacroIntoBundle(bundle, macro)));
    bindRefreshButton();
    queueWarmup();
  } catch (error) {
    console.error("monitoring render failed", {
      error,
      bundleStatus: bundle?.status,
      bundleKeys: bundle && Object.keys(bundle),
      dataKeys: bundle?.data && Object.keys(bundle.data),
      macroKeys: macro && Object.keys(macro),
    });
    setRoot(renderShellFallback("页面渲染异常，已保留监控页骨架；请查看控制台详情。"));
  }
}

export async function renderMonitoring() {
  await loadDashboard();
}
