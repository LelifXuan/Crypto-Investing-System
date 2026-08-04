const chartRegistry = new Map();
let candlestickPluginRegistered = false;
let adaptiveAxisPluginRegistered = false;
let referenceLinePluginRegistered = false;
let expiryAnchorsPluginRegistered = false;

/* === §16.C — Token-driven chart theme ============================
   Read once from `:root` via getComputedStyle. If the document isn't
   ready (e.g. SSR / unit test bootstrap), fall back to the existing
   hardcoded values. Auditors: see docs/UI_UX_AUDIT_2026-07-31.md §16.C
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
    return { min: 0, max: max > 0 ? max * 1.08 : 1 };
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

const referenceLines = {
  id: "referenceLines",
  afterDatasetsDraw(chart) {
    const config = chart.options.plugins?.referenceLines || {};
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
        const labels = chart.data.labels || [];
        // Accept both numeric indices (legacy callers passing index strings)
        // and date/string labels. The previous implementation did
        // ``Number(label) === Number(annotation.x)`` which always returned
        // NaN===NaN → false for ISO date labels, silently dropping every
        // string-x annotation. Try string equality first, then numeric.
        let index = labels.findIndex(
          (label) => String(label) === String(annotation.x),
        );
        if (index < 0) {
          index = labels.findIndex(
            (label) => Number(label) === Number(annotation.x),
          );
        }
        if (index < 0) return;
        const x = xScale.getPixelForValue(index);
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
        ctx.font = "600 10px IBM Plex Sans, Noto Sans SC, sans-serif";
        ctx.fillText(
          annotation.label,
          Math.min(start.x + 5, chartArea.right - 72),
          Math.max(chartArea.top + 12, start.y - 5),
        );
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

function baseOptions() {
  return {
    responsive: true,
    maintainAspectRatio: false,
    interaction: { mode: "index", intersect: false },
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
