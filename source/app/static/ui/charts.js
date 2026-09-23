const chartRegistry = new Map();
let candlestickPluginRegistered = false;
let adaptiveAxisPluginRegistered = false;
let referenceLinePluginRegistered = false;
let expiryAnchorsPluginRegistered = false;
let weeklyBarsPluginRegistered = false;

/* === §16.C — Token-driven chart theme ============================
   Read once from `:root` via getComputedStyle. If the document isn't
   ready (e.g. SSR / unit test bootstrap), fall back to the existing
   hardcoded values. Auditors: see source/docs/UI_UX_AUDIT_2026-07-31.md §16.C
   for the audit trail and the original line-by-line palette review. */
const CHART_THEME_FALLBACK = Object.freeze({
  legend: "#4b5961",
  tooltipBg: "rgba(21, 35, 42, 0.92)",
  tooltipBorder: "rgba(255, 255, 255, 0.06)",
  tooltipFg1: "#f8fafc",
  tooltipFg2: "#e2e8f0",
  axis: "#627078",
  gridX: "rgba(23, 34, 39, 0.042)",
  gridY: "rgba(23, 34, 39, 0.05)",
  referenceLine: "rgba(83, 99, 108, 0.72)",
  referenceLabel: "#53636c",
  expiryLine: "rgba(83, 99, 108, 0.45)",
  expiryLabel: "rgba(48, 84, 130, 0.85)",
  dotPutWall: "#c2725a",
  dotMaxPain: "#5a6a7c",
  dotCallWall: "#8eb098",
  dotStroke: "#ffffff",
  upStroke: "#16a34a",
  downStroke: "#dc2626",
  upFill: "rgba(124, 155, 138, 0.32)",
  downFill: "rgba(194, 114, 90, 0.30)",
});

function _readCssVar(name, fallback) {
  try {
    if (typeof document === "undefined") return fallback;
    const v = getComputedStyle(document.documentElement).getPropertyValue(name).trim();
    return v || fallback;
  } catch (_err) {
    return fallback;
  }
}

const CHART_THEME = Object.freeze({
  legend:         _readCssVar("--chart-legend",         CHART_THEME_FALLBACK.legend),
  tooltipBg:      _readCssVar("--chart-tooltip-bg",     CHART_THEME_FALLBACK.tooltipBg),
  tooltipBorder:  _readCssVar("--chart-tooltip-border", CHART_THEME_FALLBACK.tooltipBorder),
  tooltipFg1:     _readCssVar("--chart-tooltip-fg-1",   CHART_THEME_FALLBACK.tooltipFg1),
  tooltipFg2:     _readCssVar("--chart-tooltip-fg-2",   CHART_THEME_FALLBACK.tooltipFg2),
  axis:           _readCssVar("--chart-axis",           CHART_THEME_FALLBACK.axis),
  gridX:          _readCssVar("--chart-grid-x",         CHART_THEME_FALLBACK.gridX),
  gridY:          _readCssVar("--chart-grid-y",         CHART_THEME_FALLBACK.gridY),
  referenceLine:  _readCssVar("--chart-reference-line", CHART_THEME_FALLBACK.referenceLine),
  referenceLabel: _readCssVar("--chart-reference-label", CHART_THEME_FALLBACK.referenceLabel),
  expiryLine:     _readCssVar("--chart-expiry-line",    CHART_THEME_FALLBACK.expiryLine),
  expiryLabel:    _readCssVar("--chart-expiry-label",   CHART_THEME_FALLBACK.expiryLabel),
  dotPutWall:     _readCssVar("--chart-dot-put-wall",   CHART_THEME_FALLBACK.dotPutWall),
  dotMaxPain:     _readCssVar("--chart-dot-max-pain",   CHART_THEME_FALLBACK.dotMaxPain),
  dotCallWall:    _readCssVar("--chart-dot-call-wall",  CHART_THEME_FALLBACK.dotCallWall),
  dotStroke:      _readCssVar("--chart-dot-stroke",     CHART_THEME_FALLBACK.dotStroke),
  upStroke:       _readCssVar("--chart-up-stroke",      CHART_THEME_FALLBACK.upStroke),
  downStroke:     _readCssVar("--chart-down-stroke",    CHART_THEME_FALLBACK.downStroke),
  upFill:         _readCssVar("--chart-up-fill",        CHART_THEME_FALLBACK.upFill),
  downFill:       _readCssVar("--chart-down-fill",      CHART_THEME_FALLBACK.downFill),
});

// expose for test runs (readback probe in tests/_visual_c_chart_theme_readback.py)
if (typeof globalThis !== "undefined") {
  globalThis.__CHART_THEME__ = CHART_THEME;
}

/* === §13.2 #4 — Series palette (single source of truth) ==========
   2026-08-27: chart series colors used to be hardcoded inside every page
   (analysis.js, gold_v5.js, structure.js, btc_derivatives.js). They now
   declare their values in editorial.css (:root) as `--series-*` tokens.
   Page JS must call `getSeriesColor(label)` instead of writing the hex
   inline. The fallback below mirrors the editorial values verbatim so
   SSR / unit tests can resolve without a live :root.

   Key → token mapping is exposed via SERIES_LABELS so a Chinese/English
   label from any page (e.g. "BTC 价格", "EMA12", "XAUT", "MA50",
   "swing_backbone") resolves to the same hex without per-page code.

   Audit reference: docs/design-guidelines.md §7.9 (charts) and §13.2 #4
   (token-ownership debt closed). */
const SERIES_FALLBACK = Object.freeze({
  // Generic price series (analysis + btc-derivatives)
  price:               "#2c3849",
  spot:                "#2c3849",
  "BTC 价格":          "#2c3849",
  收盘价:              "#2c3849",
  // EMA family
  EMA12:               "#dcb09a",
  EMA20:               "#a89569",
  EMA20_Alt:           "#cba071",  // btc-derivatives 用,区别于 analysis EMA20
  EMA30:               "#a89569",
  EMA50:               "#7ba39d",
  EMA60:               "#6a8fa0",
  EMA120:              "#4d6485",
  EMA200:              "#3a5170",
  // VWAP family
  VWAP20:              "#d5c8e0",
  VWAP50:              "#a594c2",
  VWAP100:             "#5d4e7e",
  // Oscillators
  RSI:                 "#a896c8",
  MACD:                "#7ba39d",
  "MACD柱":            "#6e9b94",  // analysis 用
  "MACD柱_正":         "rgba(124, 155, 138, 0.55)",
  "MACD柱_负":         "rgba(194, 114, 90, 0.55)",
  "信号线":            "#dcbe88",
  // Funding / IV / basis (btc-derivatives)
  Funding:             "#8a86b5",
  "Funding Z":         "#8a86b5",
  "Funding Rate":      "#8a86b5",
  Basis:               "#b8924a",
  "年化 Basis":        "#b8924a",
  IV:                  "#9686b9",
  "ATM IV":            "#9686b9",
  "Call IV":           "#9686b9",
  "Put IV":            "#9686b9",
  "25D Skew":          "#9686b9",
  "Put/Call OI":       "#7ba39d",
  "Put/Call Volume":   "#b8924a",
  // OI / walls (btc-derivatives)
  OI:                  "#6a8fa0",
  "聚合 OI":           "#6a8fa0",
  "Open Interest":     "#6a8fa0",
  "OI 24h变化":        "#6a8fa0",
  "Call OI":           "#8eb098",
  "Put OI":            "#c2725a",
  "Call Wall":         "#8eb098",
  "Put Wall":          "#c2725a",
  "Call 保护成本":     "#8eb098",
  "Put 保护成本":      "#c2725a",
  "借记价差成本":      "#5a6a7c",
  "Max Pain":          "#5a6a7c",
  // Volume
  "成交量":            "#b8924a",
  Volume:              "#b8924a",
  // Vegas fast/slow (analysis + gold_v5)
  Vegas_Fast:          "#6e9b94",
  Vegas_Slow:          "#5d4e7e",
  // Gold-allocation 专属
  XAUT:                "#1f1b16",
  MA50:                "#5b8a83",
  SMA200:              "#b07558",
  "EMA20-Gold":        "#7c5fb0",  // gold 专属紫
  "%B":                "#b07558",
  RSI14:               "#5b8a83",
  // Market-structure 基础(CHART_SERIES 已 token 化,这里保留 alias)
  swing:               "#2563eb",
  classic:             "#b8924a",
  profile:             "#9686b9",
  fused:               "#6a7587",
  // Market-structure 派生
  swing_live_leg:      "#3b82f6",
  neckline:            "#e67e22",
  upper_boundary:      "#e74c3c",
  resistance:          "#e74c3c",
  lower_boundary:      "#27ae60",
  support:             "#27ae60",
  pattern_zone:        "#6366f1",
  // Pattern fill base alphas (alpha 由 fill_alpha 控制)
  // CSS source of truth lives in editorial.css :root (--pattern-fill-*);
  // these literals are SSR/legacy fallbacks. See docs/design-guidelines.md
  // §7.9 for the chart palette contract.
  pattern_bullish_base:   "rgba(39, 174, 96, 0.12)",
  pattern_bearish_base:   "rgba(231, 76, 60, 0.12)",
  pattern_neutral_base:   "rgba(99, 102, 241, 0.12)",
  pattern_mixed_base:     "rgba(230, 126, 34, 0.12)",
});

const CHART_SERIES = Object.freeze({
  price:               _readCssVar("--series-price",               SERIES_FALLBACK.price),
  spot:                _readCssVar("--series-price",               SERIES_FALLBACK.spot),
  "BTC 价格":          _readCssVar("--series-price",               SERIES_FALLBACK["BTC 价格"]),
  收盘价:              _readCssVar("--series-price",               SERIES_FALLBACK.收盘价),
  EMA12:               _readCssVar("--series-ema-short",           SERIES_FALLBACK.EMA12),
  EMA20:               _readCssVar("--series-ema-mid",             SERIES_FALLBACK.EMA20),
  EMA20_Alt:           _readCssVar("--series-ema-mid-alt",         SERIES_FALLBACK.EMA20_Alt),
  EMA30:               _readCssVar("--series-ema-mid",             SERIES_FALLBACK.EMA30),
  EMA50:               _readCssVar("--series-ema-long",            SERIES_FALLBACK.EMA50),
  EMA60:               _readCssVar("--series-ema-long",            SERIES_FALLBACK.EMA60),
  EMA120:              _readCssVar("--series-ema-long-deep",       SERIES_FALLBACK.EMA120),
  EMA200:              _readCssVar("--series-ema-long-deepest",    SERIES_FALLBACK.EMA200),
  VWAP20:              _readCssVar("--series-vwap-light",          SERIES_FALLBACK.VWAP20),
  VWAP50:              _readCssVar("--series-vwap-mid",            SERIES_FALLBACK.VWAP50),
  VWAP100:             _readCssVar("--series-vwap-deep",           SERIES_FALLBACK.VWAP100),
  RSI:                 _readCssVar("--series-rsi",                 SERIES_FALLBACK.RSI),
  MACD:                SERIES_FALLBACK.MACD,        /* shared across btc + analysis + gold; varies by page, kept in fallback */
  Funding:             _readCssVar("--series-funding",             SERIES_FALLBACK.Funding),
  "Funding Z":         _readCssVar("--series-funding",             SERIES_FALLBACK["Funding Z"]),
  "Funding Rate":      _readCssVar("--series-funding",             SERIES_FALLBACK["Funding Rate"]),
  Basis:               _readCssVar("--series-basis",               SERIES_FALLBACK.Basis),
  IV:                  _readCssVar("--series-iv",                  SERIES_FALLBACK.IV),
  "ATM IV":            _readCssVar("--series-iv",                  SERIES_FALLBACK["ATM IV"]),
  "Call IV":           _readCssVar("--series-iv",                  SERIES_FALLBACK["Call IV"]),
  "Put IV":            _readCssVar("--series-iv",                  SERIES_FALLBACK["Put IV"]),
  "25D Skew":          _readCssVar("--series-iv",                  SERIES_FALLBACK["25D Skew"]),
  "Call OI":           _readCssVar("--series-call-wall",           SERIES_FALLBACK["Call OI"]),
  "Put OI":            _readCssVar("--series-put-wall",            SERIES_FALLBACK["Put OI"]),
  "Call Wall":         _readCssVar("--series-call-wall",           SERIES_FALLBACK["Call Wall"]),
  "Put Wall":          _readCssVar("--series-put-wall",            SERIES_FALLBACK["Put Wall"]),
  "Call 保护成本":     _readCssVar("--series-call-wall",           SERIES_FALLBACK["Call 保护成本"]),
  "Put 保护成本":      _readCssVar("--series-put-wall",            SERIES_FALLBACK["Put 保护成本"]),
  "借记价差成本":      _readCssVar("--series-max-pain",            SERIES_FALLBACK["借记价差成本"]),
  "Max Pain":          _readCssVar("--series-max-pain",            SERIES_FALLBACK["Max Pain"]),
  OI:                  _readCssVar("--series-ema-long",            SERIES_FALLBACK.OI),
  "聚合 OI":           _readCssVar("--series-ema-long",            SERIES_FALLBACK["聚合 OI"]),
  "Open Interest":     _readCssVar("--series-ema-long",            SERIES_FALLBACK["Open Interest"]),
  "OI 24h变化":        _readCssVar("--series-ema-long",            SERIES_FALLBACK["OI 24h变化"]),
  "Put/Call OI":       _readCssVar("--series-ema-long",            SERIES_FALLBACK["Put/Call OI"]),
  "Put/Call Volume":   SERIES_FALLBACK["Put/Call Volume"],
  "成交量":            SERIES_FALLBACK["成交量"],
  Volume:              SERIES_FALLBACK.Volume,
  Vegas_Fast:          SERIES_FALLBACK.Vegas_Fast,   /* page-specific; kept in fallback */
  Vegas_Slow:          SERIES_FALLBACK.Vegas_Slow,   /* page-specific; kept in fallback */
  XAUT:                _readCssVar("--series-xaut",                SERIES_FALLBACK.XAUT),
  MA50:                SERIES_FALLBACK.MA50,         /* gold-v5 warm green; not editorial semantic */
  SMA200:              SERIES_FALLBACK.SMA200,       /* gold-v5 warm brown */
  "EMA20-Gold":        SERIES_FALLBACK["EMA20-Gold"], /* gold-v5 violet */
  "%B":                SERIES_FALLBACK["%B"],
  RSI14:               SERIES_FALLBACK.RSI14,        /* gold-v5 warm green */
  swing:               _readCssVar("--series-swing",               SERIES_FALLBACK.swing),
  classic:             _readCssVar("--series-classic",             SERIES_FALLBACK.classic),
  profile:             _readCssVar("--series-profile",             SERIES_FALLBACK.profile),
  fused:               _readCssVar("--series-fused",               SERIES_FALLBACK.fused),
  swing_live_leg:      _readCssVar("--series-swing-live",          SERIES_FALLBACK.swing_live_leg),
  neckline:            _readCssVar("--series-pattern-neckline",    SERIES_FALLBACK.neckline),
  upper_boundary:      _readCssVar("--series-pattern-resistance",  SERIES_FALLBACK.upper_boundary),
  resistance:          _readCssVar("--series-pattern-resistance",  SERIES_FALLBACK.resistance),
  lower_boundary:      _readCssVar("--series-pattern-support",     SERIES_FALLBACK.lower_boundary),
  support:             _readCssVar("--series-pattern-support",     SERIES_FALLBACK.support),
  pattern_zone:        _readCssVar("--series-pattern-zone",        SERIES_FALLBACK.pattern_zone),
  pattern_bullish_base:  _readCssVar("--pattern-fill-bullish",     SERIES_FALLBACK.pattern_bullish_base),
  pattern_bearish_base:  _readCssVar("--pattern-fill-bearish",     SERIES_FALLBACK.pattern_bearish_base),
  pattern_neutral_base:  _readCssVar("--pattern-fill-neutral",     SERIES_FALLBACK.pattern_neutral_base),
  pattern_mixed_base:    _readCssVar("--pattern-fill-mixed",       SERIES_FALLBACK.pattern_mixed_base),
});

// expose for test runs (readback probe in tests/test_chart_series_token_consistency.py)
if (typeof globalThis !== "undefined") {
  globalThis.__CHART_SERIES__ = CHART_SERIES;
}

const SERIES_FALLBACK_COLOR = "#5a6a7c";  /* neutral gray, matches --series-max-pain */

export function getSeriesColor(label, rotationFallback = null) {
  if (!label || typeof label !== "string") {
    return rotationFallback
      ? (SERIES_FALLBACK[rotationFallback] || SERIES_FALLBACK_COLOR)
      : SERIES_FALLBACK_COLOR;
  }
  if (CHART_SERIES[label]) return CHART_SERIES[label];
  if (SERIES_FALLBACK[label]) return SERIES_FALLBACK[label];
  if (rotationFallback && SERIES_FALLBACK[rotationFallback]) {
    return SERIES_FALLBACK[rotationFallback];
  }
  return SERIES_FALLBACK_COLOR;
}

/**
 * Build a rgba fill by composing a token's rgb prefix with a runtime alpha.
 * Used by market-structure page for pattern fills (alpha varies per draw).
 *
 * @param {"pattern_bullish_base" | "pattern_bearish_base" | "pattern_neutral_base" | "pattern_mixed_base"} tokenKey
 * @param {number} alpha - 0..1, will be clamped to that range
 * @returns {string} rgba(...) string; falls back to token value if the
 *   stored string is already a non-comma-prefixed color.
 */
export function getPatternFill(tokenKey, alpha) {
  const safeAlpha = Math.max(0, Math.min(1, Number(alpha) || 0.12));
  const base = CHART_SERIES[tokenKey] || SERIES_FALLBACK[tokenKey] || SERIES_FALLBACK.pattern_bullish_base;
  // Extract rgb(r, g, b) or rgba(r, g, b, a) prefix; if the token is a hex,
  // convert via a one-shot rgb regex. This keeps pattern fills fully
  // token-driven without leaking the legacy `rgba(...,${fillAlpha})`
  // template string.
  const rgbMatch = base.match(/rgba?\(\s*(\d+)\s*,\s*(\d+)\s*,\s*(\d+)/);
  if (rgbMatch) {
    return `rgba(${rgbMatch[1]}, ${rgbMatch[2]}, ${rgbMatch[3]}, ${safeAlpha})`;
  }
  const hexMatch = base.match(/^#([0-9a-fA-F]{6})$/);
  if (hexMatch) {
    const v = hexMatch[1];
    const r = parseInt(v.slice(0, 2), 16);
    const g = parseInt(v.slice(2, 4), 16);
    const b = parseInt(v.slice(4, 6), 16);
    return `rgba(${r}, ${g}, ${b}, ${safeAlpha})`;
  }
  return base;
}

function finiteChartNumber(value) {
  if (value === null || value === undefined || value === "") return null;
  const numeric = Number(value);
  return Number.isFinite(numeric) ? numeric : null;
}

export function sanitizeChartSeries(values) {
  if (!Array.isArray(values)) return [];
  return values.map(finiteChartNumber);
}

function sanitizeCandle(candle) {
  if (!candle || typeof candle !== "object") return null;
  const open = finiteChartNumber(candle.open);
  const high = finiteChartNumber(candle.high);
  const low = finiteChartNumber(candle.low);
  const close = finiteChartNumber(candle.close);
  if (![open, high, low, close].every(Number.isFinite)) return null;
  return { ...candle, open, high, low, close };
}

export function collectFiniteDatasetValues(datasets) {
  const values = [];
  (datasets || []).forEach((dataset) => {
    sanitizeChartSeries(dataset?.data).forEach((value) => {
      if (value !== null) values.push(value);
    });
    if (dataset?.renderAsCandles) {
      (dataset.candles || []).forEach((candle) => {
        const clean = sanitizeCandle(candle);
        if (clean) values.push(clean.open, clean.high, clean.low, clean.close);
      });
    }
  });
  return values;
}

function paddedDomain(values, paddingRatio) {
  if (!values.length) return {};
  const min = Math.min(...values);
  const max = Math.max(...values);
  const reference = Math.max(Math.abs(min), Math.abs(max), 1);
  const range = Math.max(max - min, reference * 0.01, 1e-9);
  const padding = range * paddingRatio;
  return { min: min - padding, max: max + padding };
}

export function buildAdaptiveAxisOptions(profile = "generic", datasets = [], options = {}) {
  const values = [
    ...collectFiniteDatasetValues(datasets),
    ...(options.extraValues || []).map(finiteChartNumber).filter(Number.isFinite),
  ];
  const baseline = finiteChartNumber(options.baseline);
  if (baseline !== null) values.push(baseline);
  if (profile === "oscillator") {
    return { min: 0, max: 100, ticks: { stepSize: 10 } };
  }
  if (profile === "volume") {
    const max = values.length ? Math.max(...values, 0) : 0;
    return {
      min: 0,
      max: max > 0 ? max * 1.08 : 1,
      ticks: { value_format: "integer" },
    };
  }
  if (profile === "centeredZero") {
    const maxAbs = values.length ? Math.max(...values.map((value) => Math.abs(value))) : 0;
    const bound = Math.max(maxAbs * 1.12, 1e-9);
    return { min: -bound, max: bound };
  }
  if (profile === "skew") {
    const maxAbs = values.length ? Math.max(...values.map((value) => Math.abs(value))) : 0;
    const bound = Math.max(maxAbs * 1.15, 0.01);
    return { min: -bound, max: bound };
  }
  if (profile === "percent") {
    if (!values.length) return {};
    return paddedDomain(values, options.paddingRatio ?? 0.08);
  }
  if (profile === "ratio") {
    if (!values.length) return {};
    const min = Math.min(...values, 1);
    const max = Math.max(...values, 1);
    const padding = Math.max((max - min) * 0.12, 0.05);
    return { min: min - padding, max: max + padding };
  }
  return paddedDomain(
    values,
    options.paddingRatio ?? (profile === "price" ? 0.08 : 0.06),
  );
}

export function formatChartValue(value, valueFormat = "raw") {
  const numeric = finiteChartNumber(value);
  if (numeric === null) return "-";
  if (valueFormat === "price") {
    return `$${numeric.toLocaleString("zh-CN", { maximumFractionDigits: 0 })}`;
  }
  if (valueFormat === "compact_usd") {
    const absolute = Math.abs(numeric);
    if (absolute >= 1e9) return `$${(numeric / 1e9).toFixed(1)}B`;
    if (absolute >= 1e6) return `$${(numeric / 1e6).toFixed(1)}M`;
    return `$${numeric.toLocaleString("zh-CN", { maximumFractionDigits: 0 })}`;
  }
  if (valueFormat === "percent") return `${(numeric * 100).toFixed(2)}%`;
  if (valueFormat === "ratio") return numeric.toFixed(2);
  if (valueFormat === "zscore") return `${numeric >= 0 ? "+" : ""}${numeric.toFixed(2)}`;
  if (valueFormat === "integer") return numeric.toLocaleString("zh-CN", { maximumFractionDigits: 0 });
  return numeric.toLocaleString("zh-CN", { maximumFractionDigits: 4 });
}

function isDateOnlyLabel(text) {
  return /^\d{4}-\d{2}-\d{2}$/.test(String(text || ""));
}

function formatXAxisTick(value, labels = []) {
  const raw = labels?.[value] ?? value;
  const text = String(raw ?? "");
  if (isDateOnlyLabel(text)) {
    const [, month, day] = text.match(/^\d{4}-(\d{2})-(\d{2})$/) || [];
    return `${month}-${day}`;
  }
  const date = new Date(text);
  if (!Number.isNaN(date.getTime()) && /T/.test(text)) {
    const parts = Object.fromEntries(
      new Intl.DateTimeFormat("zh-CN", {
        timeZone: "Asia/Shanghai",
        month: "2-digit",
        day: "2-digit",
        hour: "2-digit",
        minute: "2-digit",
        hourCycle: "h23",
      }).formatToParts(date).map((part) => [part.type, part.value]),
    );
    return `${parts.month}-${parts.day} ${parts.hour}:${parts.minute}`;
  }
  const numeric = finiteChartNumber(text);
  if (numeric !== null && Math.abs(numeric) >= 1000) {
    return `$${Math.round(numeric / 1000)}k`;
  }
  return text.length > 14 ? `${text.slice(0, 12)}…` : text;
}

export function buildAdaptiveScaleOptionsForAxes(
  axes = {},
  datasets = [],
  annotations = [],
) {
  return Object.fromEntries(
    Object.entries(axes).map(([axisId, spec]) => {
      const axisDatasets = (datasets || []).filter(
        (dataset) => (dataset.yAxisID || dataset.y_axis_id || "y") === axisId,
      );
      const hasVisibleData = axisDatasets.some(
        (dataset) => collectFiniteDatasetValues([dataset]).length > 0,
      );
      const annotationValues = !hasVisibleData || spec.include_annotations === false
        ? []
        : (annotations || [])
          .filter(
            (annotation) =>
              annotation.type === "horizontalLine"
              && (annotation.axis_id || "y") === axisId,
          )
          .map((annotation) => annotation.y);
      const domain = buildAdaptiveAxisOptions(
        spec.profile || "generic",
        axisDatasets,
        {
          extraValues: annotationValues,
          baseline: hasVisibleData ? spec.baseline : null,
          paddingRatio: spec.padding_ratio,
        },
      );
      return [
        axisId,
        {
          type: "linear",
          position: spec.position || "left",
          display: hasVisibleData,
          min: domain.min,
          max: domain.max,
          ticks: {
            display: spec.display_ticks !== false,
            color: CHART_THEME.axis,
            font: { size: 11, weight: "500" },
            // 2026-08-05: opt-in custom tick formatter. When the caller
            // supplies ``spec.tick_callback`` it fully overrides the
            // ``value_format``/``unit`` pipeline, letting dual-axis
            // charts (e.g. ashare_etf yield view) emit currency labels
            // (``¥1.5万``) that ``formatChartValue`` cannot produce.
            callback: spec.tick_callback
              || ((value) => formatChartValue(value, spec.value_format || spec.unit)),
          },
          grid: {
            color: CHART_THEME.gridY,
            drawOnChartArea: spec.grid !== false,
          },
        },
      ];
    }),
  );
}

function hideDefaultYAxis() {
  return {
    y: {
      display: false,
      grid: { display: false },
      ticks: { display: false },
    },
  };
}

function deepMerge(base, override) {
  if (!override || typeof override !== "object" || Array.isArray(override)) {
    return override === undefined ? base : override;
  }
  const output = { ...(base || {}) };
  Object.entries(override).forEach(([key, value]) => {
    output[key] = value && typeof value === "object" && !Array.isArray(value)
      ? deepMerge(output[key], value)
      : value;
  });
  return output;
}

export function sanitizeDatasets(datasets) {
  return (datasets || []).map((dataset) => {
    // The backend writes the per-axis binding as `y_axis_id` (snake_case, to
    // match the JSON schema). Chart.js reads `dataset.yAxisID` at render time,
    // so we translate here. Existing yAxisID wins to keep render behaviour
    // deterministic when both fields are set (e.g. tests, future plugins).
    const yAxisID = dataset.yAxisID || dataset.y_axis_id || undefined;
    return {
      ...dataset,
      ...(yAxisID ? { yAxisID } : {}),
      data: sanitizeChartSeries(dataset?.data),
      candles: dataset?.renderAsCandles
        ? (dataset.candles || []).map(sanitizeCandle)
        : dataset?.candles,
    };
  });
}

const adaptiveAxisPlugin = {
  id: "adaptiveAxis",
  defaults: { profile: "generic", axes: null, annotations: [] },
  beforeUpdate(chart) {
    const profile = chart.options.plugins?.adaptiveAxis?.profile || "generic";
    const axes = chart.options.plugins?.adaptiveAxis?.axes || null;
    const annotations = chart.options.plugins?.adaptiveAxis?.annotations || [];
    const visibleDatasets = chart.data.datasets.filter(
      (_dataset, index) => chart.isDatasetVisible(index),
    );
    if (axes && Object.keys(axes).length) {
      const scaleOptions = buildAdaptiveScaleOptionsForAxes(
        axes,
        visibleDatasets,
        annotations,
      );
      Object.entries(scaleOptions).forEach(([axisId, axis]) => {
        const scale = chart.options.scales?.[axisId];
        if (!scale) return;
        scale.display = axis.display;
        if (Number.isFinite(axis.min)) scale.min = axis.min;
        else delete scale.min;
        if (Number.isFinite(axis.max)) scale.max = axis.max;
        else delete scale.max;
      });
    } else {
      const axis = buildAdaptiveAxisOptions(profile, visibleDatasets);
      const y = chart.options.scales?.y;
      if (y) {
        if (Number.isFinite(axis.min)) y.min = axis.min;
        else delete y.min;
        if (Number.isFinite(axis.max)) y.max = axis.max;
        else delete y.max;
        if (Number.isFinite(axis.ticks?.stepSize)) {
          y.ticks.stepSize = axis.ticks.stepSize;
        } else {
          delete y.ticks.stepSize;
        }
      }
      if (chart.canvas?.dataset) {
        chart.canvas.dataset.axisProfile = profile;
        chart.canvas.dataset.axisMin = Number.isFinite(axis.min) ? String(axis.min) : "";
        chart.canvas.dataset.axisMax = Number.isFinite(axis.max) ? String(axis.max) : "";
      }
    }
    const x = chart.options.scales?.x;
    if (x) {
      x.ticks.maxTicksLimit = Math.max(
        4,
        Math.min(10, Math.floor((chart.width || 720) / 120)),
      );
    }
  },
};

// Resolve `annotation.x` to a pixel position on the x scale.
//
// These x axes are Chart.js category scales, so getPixelForValue() takes an
// index (fractional is supported), not a value. The axes here are also
// irregular: the strike_surface grid runs "62000.0", "64000.0", "66000.0",
// then 1000-wide steps. An annotation that did not land exactly on a label
// used to be dropped, so the "Spot" line — spot 86010.14 against a strike grid
// — never rendered at all, while the walls did only because walls are reported
// at strikes by definition.
//
// Resolve an exact label match first (date annotations, and wall prices that
// already sit on a strike; string equality is tried before numeric because the
// old ``Number(label) === Number(annotation.x)`` comparison returned
// NaN===NaN → false for every ISO date label), then interpolate between the
// two bracketing numeric labels. Values outside the labelled range return null
// rather than being clamped to an edge the user would misread as a real level.
function resolveReferenceLineX(chart, xScale, rawValue) {
  const labels = chart.data.labels || [];
  const exactIndex = labels.findIndex((label) => String(label) === String(rawValue));
  if (exactIndex >= 0) return xScale.getPixelForValue(exactIndex);
  const value = Number(rawValue);
  if (!Number.isFinite(value)) return null;
  const numericMatch = labels.findIndex((label) => Number(label) === value);
  if (numericMatch >= 0) return xScale.getPixelForValue(numericMatch);
  let lower = -1;
  let upper = -1;
  labels.forEach((label, index) => {
    const numeric = Number(label);
    if (!Number.isFinite(numeric) || numeric === value) return;
    if (numeric < value) {
      if (lower < 0 || numeric > Number(labels[lower])) lower = index;
    } else if (upper < 0 || numeric < Number(labels[upper])) {
      upper = index;
    }
  });
  if (lower < 0 || upper < 0) return null;
  const low = Number(labels[lower]);
  const high = Number(labels[upper]);
  const fraction = high === low ? 0 : (value - low) / (high - low);
  return xScale.getPixelForValue(lower + fraction);
}

// referenceLines label placement.
// Every vertical line anchors its label at chartArea.top + 12, so two
// annotations sitting on nearby strikes printed on top of each other — on the
// strike_surface chart Max Pain ($79k) and Call Wall ($80k) collapsed into one
// unreadable string. Keep the boxes already drawn in this pass and drop a
// colliding label one text line lower.
const REFERENCE_LABEL_FONT = "600 10px IBM Plex Sans, Noto Sans SC, sans-serif";
const REFERENCE_LABEL_LINE_HEIGHT = 12;
const REFERENCE_LABEL_MAX_ROWS = 4;

function referenceLabelRectsOverlap(a, b) {
  return a.left < b.right && b.left < a.right && a.top < b.bottom && b.top < a.bottom;
}

// Returns the baseline y to draw at and records the box it occupies.
// ctx.font must already be set — the width is measured for the collision test.
function reserveReferenceLabelY(ctx, text, left, baseY, placed) {
  const right = left + ctx.measureText(text).width;
  let y = baseY;
  for (let row = 0; row < REFERENCE_LABEL_MAX_ROWS; row += 1) {
    const rect = { left, right, top: y - 9, bottom: y + 3 };
    if (!placed.some((other) => referenceLabelRectsOverlap(rect, other))) {
      placed.push(rect);
      return y;
    }
    y += REFERENCE_LABEL_LINE_HEIGHT;
  }
  // Cap at REFERENCE_LABEL_MAX_ROWS: past that the label drifts into the plot.
  placed.push({ left, right, top: y - 9, bottom: y + 3 });
  return y;
}

const referenceLines = {
  id: "referenceLines",
  afterDatasetsDraw(chart) {
    const config = chart.options.plugins?.referenceLines || {};
    const placedLabels = [];
    (config.annotations || []).forEach((annotation) => {
      const { ctx, chartArea, scales } = chart;
      let start;
      let end;
      if (annotation.type === "horizontalLine") {
        const scale = scales[annotation.axis_id || "y"];
        if (!scale || scale.options.display === false) return;
        const y = scale.getPixelForValue(Number(annotation.y));
        if (!Number.isFinite(y)) return;
        start = { x: chartArea.left, y };
        end = { x: chartArea.right, y };
      } else if (annotation.type === "verticalLine") {
        const xScale = scales.x;
        if (!xScale) return;
        const x = resolveReferenceLineX(chart, xScale, annotation.x);
        if (!Number.isFinite(x)) return;
        start = { x, y: chartArea.top };
        end = { x, y: chartArea.bottom };
      } else {
        return;
      }
      ctx.save();
      ctx.strokeStyle = annotation.color || CHART_THEME.referenceLine;
      ctx.lineWidth = 1.2;
      ctx.setLineDash(annotation.dash || [5, 5]);
      ctx.beginPath();
      ctx.moveTo(start.x, start.y);
      ctx.lineTo(end.x, end.y);
      ctx.stroke();
      if (annotation.label) {
        ctx.setLineDash([]);
        ctx.fillStyle = annotation.color || CHART_THEME.referenceLabel;
        ctx.font = REFERENCE_LABEL_FONT;
        const labelLeft = Math.min(start.x + 5, chartArea.right - 72);
        const labelY = reserveReferenceLabelY(
          ctx,
          String(annotation.label),
          labelLeft,
          Math.max(chartArea.top + 12, start.y - 5),
          placedLabels,
        );
        ctx.fillText(annotation.label, labelLeft, labelY);
      }
      ctx.restore();
    });
  },
};

// 2026-07-27: standard-expiry overlay for the wall-migration chart.
// Each row of the maturity_ladder (maturity_band + expiry ts + put_wall /
// max_pain / call_wall) becomes a vertical dashed line on the chart
// plus three coloured dots placed at the corresponding price levels.
// This lets users cross-reference the historical wall-migration lines
// with the per-expiry rows in the standard-expiry matrix without
// bouncing between two views.
const expiryAnchors = {
  id: "expiryAnchors",
  afterDatasetsDraw(chart) {
    const anchors = chart.options.plugins?.expiryAnchors?.items || [];
    if (!anchors.length) return;
    const { ctx, chartArea, scales } = chart;
    const xScale = scales.x;
    const yScale = scales.y;
    if (!xScale || !yScale) return;
    const xValues = chart.data.labels || [];
    const xMin = xScale.min ?? (xValues.length ? Number(xValues[0]) : null);
    const xMax = xScale.max ?? (xValues.length ? Number(xValues[xValues.length - 1]) : null);
    anchors.forEach((anchor) => {
      const ts = Number(anchor.ts ?? anchor.expiry_ts);
      if (!Number.isFinite(ts)) return;
      if (Number.isFinite(xMin) && ts < xMin) return;
      if (Number.isFinite(xMax) && ts > xMax) return;
      const x = xScale.getPixelForValue(ts);
      if (!Number.isFinite(x)) return;
      // Vertical dashed line.
      ctx.save();
      ctx.strokeStyle = CHART_THEME.expiryLine;
      ctx.lineWidth = 1;
      ctx.setLineDash([4, 5]);
      ctx.beginPath();
      ctx.moveTo(x, chartArea.top);
      ctx.lineTo(x, chartArea.bottom);
      ctx.stroke();
      ctx.setLineDash([]);
      // Top-of-chart label, e.g. "60D".
      if (anchor.label) {
        ctx.fillStyle = CHART_THEME.expiryLabel;
        ctx.font = "600 10px IBM Plex Sans, Noto Sans SC, sans-serif";
        ctx.fillText(String(anchor.label), x + 4, chartArea.top + 12);
      }
      // Three dots: put_wall / max_pain / call_wall.
      const dotSpec = [
        { key: "put_wall",  color: CHART_THEME.dotPutWall },
        { key: "max_pain",  color: CHART_THEME.dotMaxPain },
        { key: "call_wall", color: CHART_THEME.dotCallWall },
      ];
      dotSpec.forEach(({ key, color }) => {
        const v = Number(anchor[key]);
        if (!Number.isFinite(v)) return;
        const y = yScale.getPixelForValue(v);
        if (!Number.isFinite(y)) return;
        ctx.fillStyle = color;
        ctx.strokeStyle = CHART_THEME.dotStroke;
        ctx.lineWidth = 1.2;
        ctx.beginPath();
        ctx.arc(x, y, 4.2, 0, Math.PI * 2);
        ctx.fill();
        ctx.stroke();
      });
      ctx.restore();
    });
  },
};

function renderChartError(canvas, message, detail = "") {
  const host = canvas?.closest(".chart-wrap");
  if (!host) return;
  host.dataset.chartError = String(detail || "").slice(0, 500);
  host.innerHTML = `<div class="error-state chart-error-state">${message}</div>`;
}

const candlestickOverlayPlugin = {
  id: "candlestickOverlay",
  afterDatasetsDraw(chart) {
    const { ctx, scales } = chart;
    const xScale = scales.x;
    const yScale = scales.y;
    if (!xScale || !yScale) return;

    chart.data.datasets.forEach((dataset) => {
      if (!dataset?.renderAsCandles || !Array.isArray(dataset.candles)) return;
      const candleWidth = Math.max(4, Math.min(14, ((xScale.width || chart.chartArea.width) / Math.max(dataset.candles.length, 1)) * 0.58));
      ctx.save();
      dataset.candles.forEach((candle, index) => {
        const open = Number(candle.open);
        const high = Number(candle.high);
        const low = Number(candle.low);
        const close = Number(candle.close);
        if (![open, high, low, close].every(Number.isFinite)) return;

        const x = xScale.getPixelForValue(index);
        if (!Number.isFinite(x)) return;
        const yOpen = yScale.getPixelForValue(open);
        const yHigh = yScale.getPixelForValue(high);
        const yLow = yScale.getPixelForValue(low);
        const yClose = yScale.getPixelForValue(close);
        if (![yOpen, yHigh, yLow, yClose].every(Number.isFinite)) return;
        const bullish = close >= open;
        const stroke = bullish ? (dataset.upStrokeColor || CHART_THEME.upStroke) : (dataset.downStrokeColor || CHART_THEME.downStroke);
        const fill = bullish ? (dataset.upColor || CHART_THEME.upFill) : (dataset.downColor || CHART_THEME.downFill);
        const bodyTop = Math.min(yOpen, yClose);
        const bodyHeight = Math.max(Math.abs(yClose - yOpen), 1.5);

        ctx.strokeStyle = stroke;
        ctx.fillStyle = fill;
        ctx.lineWidth = 1.4;

        ctx.beginPath();
        ctx.moveTo(x, yHigh);
        ctx.lineTo(x, yLow);
        ctx.stroke();

        ctx.beginPath();
        ctx.rect(x - candleWidth / 2, bodyTop, candleWidth, bodyHeight);
        ctx.fill();
        ctx.stroke();
      });
      ctx.restore();
    });
  },
};

// §Weekly overlay — one vertical bar per ISO-week x-position. Bar height
// is clamped to live inside the strategy-market-value fill area
// (top edge = strategy-market-value curve, bottom edge = y=0). Bar
// colour is chosen by the strategy-vs-lump-sum return-pct delta:
//   diffPct >= +threshold → upFill    (strategy beats lump-sum)
//   diffPct <= -threshold → downFill  (strategy lags lump-sum)
//   otherwise             → evenFill  (within dead-zone)
//
// Items shape (passed by the caller via chart.options.plugins.weeklyBars.items):
//   { x: <label matching chart.data.labels>, strategyValue: number, diffPct: number }
//
// The plugin auto-derives strategyValue from chart.data.datasets[0].data
// when not provided, so callers only need to pass { x, diffPct }.
const weeklyBarsPlugin = {
  id: "weeklyBars",
  afterDatasetsDraw(chart) {
    const cfg = chart.options.plugins?.weeklyBars || {};
    const items = cfg.items || [];
    if (!items.length) return;
    const { ctx, chartArea, scales } = chart;
    const xScale = scales.x;
    const yScale = scales.y;
    if (!xScale || !yScale) return;
    const labels = chart.data.labels || [];
    const strategyData = chart.data.datasets?.[0]?.data || [];
    const threshold = Number.isFinite(cfg.threshold) ? cfg.threshold : 0.005; // ±0.5%
    const barWidthFraction = Number.isFinite(cfg.barWidth) ? cfg.barWidth : 0.7;
    const upFill = cfg.upFill || CHART_THEME.upFill;
    const downFill = cfg.downFill || CHART_THEME.downFill;
    const evenFill = cfg.evenFill || CHART_THEME.gridX;
    // A raw-value axis may intentionally zoom above zero. In that case the
    // pixel for y=0 sits below chartArea.bottom; using it directly lets the
    // overlay bars paint across x-axis labels and the legend. Treat the
    // visible chart edge as the baseline, matching Chart.js' clipped fill.
    const rawBaseline = yScale.getPixelForValue(0);
    const yBaseline = Math.max(
      chartArea.top,
      Math.min(chartArea.bottom, rawBaseline),
    );

    ctx.save();
    ctx.beginPath();
    ctx.rect(
      chartArea.left,
      chartArea.top,
      chartArea.right - chartArea.left,
      chartArea.bottom - chartArea.top,
    );
    ctx.clip();
    items.forEach((item) => {
      if (!item) return;
      // Match by string (ISO date / ISO week label) first, fall back to numeric.
      let idx = labels.findIndex((l) => String(l) === String(item.x));
      if (idx < 0) idx = labels.findIndex((l) => Number(l) === Number(item.x));
      if (idx < 0) return;
      const xCenter = xScale.getPixelForValue(idx);
      if (!Number.isFinite(xCenter)) return;
      // Derive category width from neighbouring x positions so the bar
      // width adapts to whatever x-axis granularity is in use (month /
      // week / custom).
      const xPrev = xScale.getPixelForValue(idx - 0.5);
      const xNext = xScale.getPixelForValue(idx + 0.5);
      const categoryWidth = Math.max(
        2,
        Number.isFinite(xNext) && Number.isFinite(xPrev) ? xNext - xPrev : 12,
      );
      const barWidth = Math.max(2, categoryWidth * barWidthFraction);

      // Bar height: top edge follows the strategy curve at this x
      // position, bottom edge anchors to the y=0 baseline. The bar
      // therefore lives entirely INSIDE the strategy-market-value fill
      // area (which is exactly the user-requested constraint).
      const strategyValue = Number(
        item.strategyValue ?? strategyData[idx],
      );
      if (!Number.isFinite(strategyValue)) return;
      const yTop = yScale.getPixelForValue(strategyValue);
      if (!Number.isFinite(yTop)) return;
      const clippedYTop = Math.max(
        chartArea.top,
        Math.min(chartArea.bottom, yTop),
      );
      const top = Math.min(clippedYTop, yBaseline);
      const height = Math.max(Math.abs(clippedYTop - yBaseline), 1.5);

      const diff = Number(item.diffPct);
      let fill = evenFill;
      if (Number.isFinite(diff)) {
        if (diff >= threshold) fill = upFill;
        else if (diff <= -threshold) fill = downFill;
      }

      ctx.fillStyle = fill;
      ctx.fillRect(xCenter - barWidth / 2, top, barWidth, height);
    });
    ctx.restore();
  },
};

function baseOptions() {
  return {
    responsive: true,
    maintainAspectRatio: false,
    interaction: { mode: "index", intersect: false },
    // 2026-08-17: Chart.js animations add visual noise + GPU compositor
    // work on every data swap. For routine dashboard refreshes
    // (background fetches, dropdown changes) the new data replaces the
    // old in a single tick — animation makes the chart appear to "shake"
    // rather than update. We keep animations opt-in for first-render
    // pages by calling .update('show') only on initial mount; subsequent
    // .update() calls inherit this default of zero duration.
    animation: { duration: 0 },
    plugins: {
      legend: {
        labels: {
          color: CHART_THEME.legend,
          boxWidth: 22,
          boxHeight: 8,
          padding: 16,
          font: { family: "IBM Plex Sans, Noto Sans SC, sans-serif", size: 12, weight: "600" },
        },
      },
      // User-facing timestamps on this app are Beijing time without suffix.
      // See the policy comment in app/static/core/dom.js#formatDateTime.
      tooltip: {
        backgroundColor: CHART_THEME.tooltipBg,
        borderColor: CHART_THEME.tooltipBorder,
        borderWidth: 1,
        cornerRadius: 14,
        padding: 12,
        titleColor: CHART_THEME.tooltipFg1,
        bodyColor: CHART_THEME.tooltipFg2,
        displayColors: true,
        callbacks: {
          title(items) {
            const raw = items?.[0]?.label || "";
            if (!/T/.test(raw)) return raw;
            const date = new Date(raw);
            if (Number.isNaN(date.getTime())) return raw;
            const formatted = new Intl.DateTimeFormat("zh-CN", {
              timeZone: "Asia/Shanghai",
              year: "numeric",
              month: "2-digit",
              day: "2-digit",
              hour: "2-digit",
              minute: "2-digit",
              hourCycle: "h23",
            }).format(date);
            return formatted;
          },
        },
      },
    },
    scales: {
      x: {
        ticks: {
          color: CHART_THEME.axis,
          maxRotation: 0,
          autoSkip: true,
          autoSkipPadding: 18,
          font: { size: 11, weight: "500" },
          callback(value) {
            return formatXAxisTick(value, this.chart?.data?.labels || []);
          },
        },
        grid: { color: CHART_THEME.gridX },
      },
      y: {
        ticks: { color: CHART_THEME.axis, font: { size: 11, weight: "500" } },
        grid: { color: CHART_THEME.gridY },
      },
    },
  };
}

export function destroyChart(key) {
  const existing = chartRegistry.get(key);
  if (existing) {
    existing.destroy();
    chartRegistry.delete(key);
  }
}

export function destroyChartsForPage(prefix) {
  [...chartRegistry.keys()]
    .filter((key) => key.startsWith(prefix))
    .forEach((key) => destroyChart(key));
}

/** Keep responsive Chart.js canvases in sync when a docked inspector changes
 * the workspace width without a window resize. The observer is page-scoped
 * and must be disconnected from the page controller's unmount hook. */
export function observeChartsForPage(container, prefix, { signal } = {}) {
  if (!container || typeof ResizeObserver === "undefined") return { disconnect() {} };
  if (signal?.aborted) return { disconnect() {} };
  let frame = null;
  let disconnected = false;
  const disconnect = () => {
    if (disconnected) return;
    disconnected = true;
    observer.disconnect();
    if (frame !== null) cancelAnimationFrame(frame);
    frame = null;
    signal?.removeEventListener("abort", disconnect);
  };
  const observer = new ResizeObserver(() => {
    if (disconnected) return;
    if (frame !== null) cancelAnimationFrame(frame);
    frame = requestAnimationFrame(() => {
      frame = null;
      [...chartRegistry.entries()]
        .filter(([key]) => key.startsWith(prefix))
        .forEach(([, chart]) => chart.resize());
    });
  });
  observer.observe(container);
  signal?.addEventListener("abort", disconnect, { once: true });
  return {
    disconnect,
  };
}

export function renderChart(key, canvas, config) {
  if (!canvas) {
    console.error("chart:render:error", key, "canvas not found");
    return null;
  }
  if (!window.Chart) {
    console.error("chart:render:error", key, "Chart.js missing");
    renderChartError(canvas, "图表库未加载，当前图表无法显示。");
    return null;
  }
  try {
    if (!candlestickPluginRegistered) {
      window.Chart.register(candlestickOverlayPlugin);
      candlestickPluginRegistered = true;
    }
    if (!adaptiveAxisPluginRegistered) {
      window.Chart.register(adaptiveAxisPlugin);
      adaptiveAxisPluginRegistered = true;
    }
    if (!referenceLinePluginRegistered) {
      window.Chart.register(referenceLines);
      referenceLinePluginRegistered = true;
    }
    if (!expiryAnchorsPluginRegistered) {
      window.Chart.register(expiryAnchors);
      expiryAnchorsPluginRegistered = true;
    }
    if (!weeklyBarsPluginRegistered) {
      window.Chart.register(weeklyBarsPlugin);
      weeklyBarsPluginRegistered = true;
    }
    const existing = chartRegistry.get(key);
    const datasets = sanitizeDatasets(config.data?.datasets);
    const data = { ...(config.data || {}), datasets };
    const axisProfile = config.axisProfile || "generic";
    const axes = config.axes || null;
    const adaptiveOptions = axes && Object.keys(axes).length
      ? {
          plugins: {
            adaptiveAxis: {
              profile: axisProfile,
              axes,
              annotations: config.annotations || [],
            },
            referenceLines: { annotations: config.annotations || [] },
          },
          scales: {
            ...hideDefaultYAxis(),
            ...buildAdaptiveScaleOptionsForAxes(
              axes,
              datasets.filter((dataset) => !dataset.hidden),
              config.annotations || [],
            ),
          },
        }
      : {
          plugins: { adaptiveAxis: { profile: axisProfile } },
          scales: { y: buildAdaptiveAxisOptions(axisProfile, datasets) },
        };
    const nextOptions = deepMerge(
      deepMerge(baseOptions(), adaptiveOptions),
      config.options || {},
    );
    if (existing && existing.canvas === canvas) {
      existing.config.type = config.type;
      existing.data = data;
      existing.options = nextOptions;
      existing.update();
      return existing;
    }
    // 2026-07-27: forward expiry-anchor items (from
    // buildMaturityExpiryAnchors) into chart options so the
    // expiryAnchors plugin can render them on the canvas.
    if (Array.isArray(config.expiryAnchors) && config.expiryAnchors.length) {
      nextOptions.plugins = nextOptions.plugins || {};
      nextOptions.plugins.expiryAnchors = { items: config.expiryAnchors };
    }
    // Forward weekly-bars overlay items (one vertical bar per ISO-week
    // x-position, coloured by strategy-vs-lump-sum return-pct delta)
    // into chart options so the weeklyBars plugin can render them on
    // the canvas.
    if (Array.isArray(config.weeklyBars) && config.weeklyBars.length) {
      nextOptions.plugins = nextOptions.plugins || {};
      nextOptions.plugins.weeklyBars = {
        items: config.weeklyBars,
        ...(config.weeklyBarsOptions || {}),
      };
    }
    destroyChart(key);
    const chart = new window.Chart(canvas, {
      ...config,
      data,
      options: nextOptions,
    });
    chartRegistry.set(key, chart);
    return chart;
  } catch (error) {
    console.error("chart:render:error", key, error);
    renderChartError(canvas, "图表渲染失败，请刷新页面后重试。", error?.stack || error);
    return null;
  }
}

function colorWithAlpha(color, opacity) {
  const alpha = Math.max(0, Math.min(Number(opacity), 1));
  const hex = String(color || "").match(/^#([0-9a-f]{6})$/i);
  if (hex) {
    const value = Number.parseInt(hex[1], 16);
    return `rgba(${value >> 16}, ${(value >> 8) & 255}, ${value & 255}, ${alpha})`;
  }
  const rgb = String(color || "").match(
    /^rgba?\(\s*([\d.]+)\s*,\s*([\d.]+)\s*,\s*([\d.]+)/i,
  );
  if (rgb) return `rgba(${rgb[1]}, ${rgb[2]}, ${rgb[3]}, ${alpha})`;
  return color;
}

export function lineDataset(label, data, color, extra = {}) {
  const { opacity, ...style } = extra;
  const borderColor = opacity === undefined ? color : colorWithAlpha(color, opacity);
  const backgroundColor = opacity === undefined
    ? color
    : colorWithAlpha(color, Math.min(Number(opacity), 0.45));
  return {
    type: "line",
    label,
    data: sanitizeChartSeries(data),
    borderColor,
    backgroundColor,
    borderWidth: 2.4,
    pointRadius: 0,
    pointHoverRadius: 4,
    pointHitRadius: 18,
    tension: 0.18,
    fill: false,
    ...style,
  };
}

export function barDataset(label, data, color, extra = {}) {
  const { opacity, ...style } = extra;
  const borderColor = opacity === undefined ? color : colorWithAlpha(color, opacity);
  const backgroundColor = opacity === undefined
    ? color
    : colorWithAlpha(color, Math.min(Number(opacity), 0.45));
  return {
    type: "bar",
    label,
    data: sanitizeChartSeries(data),
    backgroundColor,
    borderColor,
    borderWidth: 1,
    borderRadius: 10,
    maxBarThickness: 18,
    ...style,
  };
}

export function candleDataset(label, candles, extra = {}) {
  const sanitizedCandles = (candles || []).map(sanitizeCandle);
  return {
    type: "line",
    label,
    data: sanitizedCandles.map((item) => item?.close ?? null),
    borderColor: "rgba(0,0,0,0)",
    backgroundColor: "rgba(0,0,0,0)",
    pointRadius: 0,
    pointHoverRadius: 0,
    borderWidth: 0,
    tension: 0,
    fill: false,
    renderAsCandles: true,
    candles: sanitizedCandles,
    // upStrokeColor / upColor / downStrokeColor / downColor intentionally
    // omitted; the candlestick plugin falls back to CHART_THEME.{upStroke,
    // upFill, downStroke, downFill} when these are undefined. Callers that
    // need a divergent palette may still override via `extra`.
    ...extra,
  };
}
