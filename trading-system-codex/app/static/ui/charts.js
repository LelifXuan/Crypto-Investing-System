const chartRegistry = new Map();
let candlestickPluginRegistered = false;

function renderChartError(canvas, message) {
  const host = canvas?.closest(".chart-wrap");
  if (!host) return;
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
        ticks: { color: "#627078", maxRotation: 0, autoSkip: true, font: { size: 11, weight: "500" } },
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
    const existing = chartRegistry.get(key);
    const nextOptions = {
      ...baseOptions(),
      ...(config.options || {}),
    };
    if (existing && existing.canvas === canvas) {
      existing.config.type = config.type;
      existing.data = config.data;
      existing.options = nextOptions;
      existing.update();
      return existing;
    }
    destroyChart(key);
    const chart = new window.Chart(canvas, {
      ...config,
      options: nextOptions,
    });
    chartRegistry.set(key, chart);
    return chart;
  } catch (error) {
    console.error("chart:render:error", key, error);
    renderChartError(canvas, "图表渲染失败，请刷新页面后重试。");
    return null;
  }
}

export function lineDataset(label, data, color, extra = {}) {
  return {
    type: "line",
    label,
    data,
    borderColor: color,
    backgroundColor: color,
    borderWidth: 2.4,
    pointRadius: 0,
    pointHoverRadius: 4,
    pointHitRadius: 18,
    tension: 0.18,
    fill: false,
    ...extra,
  };
}

export function barDataset(label, data, color, extra = {}) {
  return {
    type: "bar",
    label,
    data,
    backgroundColor: color,
    borderColor: color,
    borderWidth: 1,
    borderRadius: 10,
    maxBarThickness: 18,
    ...extra,
  };
}

export function candleDataset(label, candles, extra = {}) {
  return {
    type: "line",
    label,
    data: candles.map((item) => {
      const close = Number(item.close ?? 0);
      return Number.isFinite(close) ? close : null;
    }),
    borderColor: "rgba(0,0,0,0)",
    backgroundColor: "rgba(0,0,0,0)",
    pointRadius: 0,
    pointHoverRadius: 0,
    borderWidth: 0,
    tension: 0,
    fill: false,
    renderAsCandles: true,
    candles,
    upStrokeColor: "#0f766e",
    upColor: "rgba(15, 118, 110, 0.16)",
    downStrokeColor: "#c35a1d",
    downColor: "rgba(195, 90, 29, 0.22)",
    ...extra,
  };
}
