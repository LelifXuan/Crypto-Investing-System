const chartRegistry = new Map();
let candlestickPluginRegistered = false;
let adaptiveAxisPluginRegistered = false;
let referenceLinePluginRegistered = false;

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

function formatXAxisTick(value, labels = []) {
  const raw = labels?.[value] ?? value;
  const text = String(raw ?? "");
  const date = new Date(text);
  if (!Number.isNaN(date.getTime()) && /T|\d{4}-\d{2}-\d{2}/.test(text)) {
    const month = String(date.getMonth() + 1).padStart(2, "0");
    const day = String(date.getDate()).padStart(2, "0");
    const hour = String(date.getHours()).padStart(2, "0");
    const minute = String(date.getMinutes()).padStart(2, "0");
    return `${month}-${day} ${hour}:${minute}`;
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
            color: "#627078",
            font: { size: 11, weight: "500" },
            callback: (value) => formatChartValue(value, spec.value_format || spec.unit),
          },
          grid: {
            color: "rgba(23, 34, 39, 0.05)",
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

function sanitizeDatasets(datasets) {
  return (datasets || []).map((dataset) => ({
    ...dataset,
    data: sanitizeChartSeries(dataset?.data),
    candles: dataset?.renderAsCandles
      ? (dataset.candles || []).map(sanitizeCandle)
      : dataset?.candles,
  }));
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
        const index = labels.findIndex(
          (label) => Number(label) === Number(annotation.x),
        );
        if (index < 0) return;
        const x = xScale.getPixelForValue(index);
        if (!Number.isFinite(x)) return;
        start = { x, y: chartArea.top };
        end = { x, y: chartArea.bottom };
      } else {
        return;
      }
      ctx.save();
      ctx.strokeStyle = annotation.color || "rgba(83, 99, 108, 0.72)";
      ctx.lineWidth = 1.2;
      ctx.setLineDash(annotation.dash || [5, 5]);
      ctx.beginPath();
      ctx.moveTo(start.x, start.y);
      ctx.lineTo(end.x, end.y);
      ctx.stroke();
      if (annotation.label) {
        ctx.setLineDash([]);
        ctx.fillStyle = annotation.color || "#53636c";
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
        const stroke = bullish ? (dataset.upStrokeColor || "#0f766e") : (dataset.downStrokeColor || "#b45309");
        const fill = bullish ? (dataset.upColor || "rgba(15,118,110,0.18)") : (dataset.downColor || "rgba(180,83,9,0.22)");
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
          color: "#4b5961",
          boxWidth: 22,
          boxHeight: 8,
          padding: 16,
          font: { family: "IBM Plex Sans, Noto Sans SC, sans-serif", size: 12, weight: "600" },
        },
      },
      tooltip: {
        backgroundColor: "rgba(21, 35, 42, 0.92)",
        borderColor: "rgba(255,255,255,0.06)",
        borderWidth: 1,
        cornerRadius: 14,
        padding: 12,
        titleColor: "#f8fafc",
        bodyColor: "#e2e8f0",
        displayColors: true,
      },
    },
    scales: {
      x: {
        ticks: {
          color: "#627078",
          maxRotation: 0,
          autoSkip: true,
          autoSkipPadding: 18,
          font: { size: 11, weight: "500" },
          callback(value) {
            return formatXAxisTick(value, this.chart?.data?.labels || []);
          },
        },
        grid: { color: "rgba(23, 34, 39, 0.042)" },
      },
      y: {
        ticks: { color: "#627078", font: { size: 11, weight: "500" } },
        grid: { color: "rgba(23, 34, 39, 0.05)" },
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
    upStrokeColor: "#0f766e",
    upColor: "rgba(15, 118, 110, 0.16)",
    downStrokeColor: "#c35a1d",
    downColor: "rgba(195, 90, 29, 0.22)",
    ...extra,
  };
}
