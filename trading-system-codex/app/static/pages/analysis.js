let api;
let invalidateCache;
let appState;
let getWindowProfile;
let persistState;
let emptyState;
let errorState;
let formatDateTime;
let formatNumber;
let impactChip;
let knowledgeTooltip;
let loadingState;
let setRoot;
let statusBanner;
let statusChip;
let barDataset;
let candleDataset;
let destroyChartsForPage;
let lineDataset;
let renderChart;
let scheduleIdlePrecompute;

async function ensureDeps() {
  if (api && appState && renderChart) {
    return;
  }
  const assetVersion = window.__ASSET_VERSION__ ? `?v=${encodeURIComponent(window.__ASSET_VERSION__)}` : "";
  const [apiModule, stateModule, domModule, chartModule, precomputeModule] = await Promise.all([
    import(`../core/api.js${assetVersion}`),
    import(`../core/state.js${assetVersion}`),
    import(`../core/dom.js${assetVersion}`),
    import(`../ui/charts.js${assetVersion}`),
    import(`../core/precompute.js${assetVersion}`),
  ]);
  ({ api, invalidateCache } = apiModule);
  ({ appState, getWindowProfile, persistState } = stateModule);
  ({
    emptyState,
    errorState,
    formatDateTime,
    formatNumber,
    impactChip,
    knowledgeTooltip,
    loadingState,
    setRoot,
    statusBanner,
    statusChip,
  } = domModule);
  ({ barDataset, candleDataset, destroyChartsForPage, lineDataset, renderChart } = chartModule);
  ({ scheduleIdlePrecompute } = precomputeModule);
}

const MIN_ANALYSIS_CANDLES = {
  "1h": 40,
  "4h": 40,
  "1d": 40,
  "1w": 20,
  "1M": 12,
};

const autoFetchKeys = new Set();

function minCandlesFor(timeframe) {
  return MIN_ANALYSIS_CANDLES[timeframe] || 40;
}

function toNumber(value) {
  return Number(value ?? 0);
}

function ema(values, period) {
  const multiplier = 2 / (period + 1);
  let prev = values[0] ?? 0;
  return values.map((value, index) => {
    if (index === 0) return prev;
    prev = (value - prev) * multiplier + prev;
    return prev;
  });
}

function sma(values, period) {
  return values.map((_, index) => {
    const start = Math.max(0, index - period + 1);
    const window = values.slice(start, index + 1);
    return window.reduce((sum, value) => sum + value, 0) / window.length;
  });
}

function rollingStd(values, period) {
  return values.map((_, index) => {
    const start = Math.max(0, index - period + 1);
    const window = values.slice(start, index + 1);
    const mean = window.reduce((sum, value) => sum + value, 0) / window.length;
    return Math.sqrt(window.reduce((sum, value) => sum + (value - mean) ** 2, 0) / window.length);
  });
}

function rsi(values, period = 14) {
  const output = [50];
  let avgGain = 0;
  let avgLoss = 0;
  for (let index = 1; index < values.length; index += 1) {
    const delta = values[index] - values[index - 1];
    const gain = Math.max(delta, 0);
    const loss = Math.max(-delta, 0);
    if (index <= period) {
      avgGain += gain;
      avgLoss += loss;
      output.push(50);
      continue;
    }
    avgGain = ((avgGain * (period - 1)) + gain) / period;
    avgLoss = ((avgLoss * (period - 1)) + loss) / period;
    const rs = avgLoss === 0 ? 100 : avgGain / avgLoss;
    output.push(100 - (100 / (1 + rs)));
  }
  return output;
}

function macd(values) {
  const fast = ema(values, 12);
  const slow = ema(values, 26);
  const line = fast.map((value, index) => value - slow[index]);
  const signal = ema(line, 9);
  const hist = line.map((value, index) => value - signal[index]);
  return { line, signal, hist };
}

function obv(closes, volumes) {
  const output = [0];
  for (let index = 1; index < closes.length; index += 1) {
    const previous = output[index - 1] || 0;
    if (closes[index] > closes[index - 1]) {
      output.push(previous + (volumes[index] || 0));
    } else if (closes[index] < closes[index - 1]) {
      output.push(previous - (volumes[index] || 0));
    } else {
      output.push(previous);
    }
  }
  return output;
}

function kdj(highs, lows, closes, period = 9) {
  const k = [];
  const d = [];
  const j = [];
  let prevK = 50;
  let prevD = 50;
  for (let index = 0; index < closes.length; index += 1) {
    const start = Math.max(0, index - period + 1);
    const high = Math.max(...highs.slice(start, index + 1));
    const low = Math.min(...lows.slice(start, index + 1));
    const rsv = high === low ? 50 : ((closes[index] - low) / (high - low)) * 100;
    const currentK = (2 * prevK + rsv) / 3;
    const currentD = (2 * prevD + currentK) / 3;
    const currentJ = 3 * currentK - 2 * currentD;
    k.push(currentK);
    d.push(currentD);
    j.push(currentJ);
    prevK = currentK;
    prevD = currentD;
  }
  return { k, d, j };
}

function cci(highs, lows, closes, period = 20) {
  const typical = closes.map((close, index) => (highs[index] + lows[index] + close) / 3);
  return typical.map((value, index) => {
    const start = Math.max(0, index - period + 1);
    const window = typical.slice(start, index + 1);
    const mean = window.reduce((sum, item) => sum + item, 0) / window.length;
    const meanDeviation = window.reduce((sum, item) => sum + Math.abs(item - mean), 0) / window.length;
    return meanDeviation === 0 ? 0 : (value - mean) / (0.015 * meanDeviation);
  });
}

function atr(highs, lows, closes, period = 14) {
  const ranges = highs.map((high, index) => {
    if (index === 0) return high - lows[index];
    return Math.max(
      high - lows[index],
      Math.abs(high - closes[index - 1]),
      Math.abs(lows[index] - closes[index - 1]),
    );
  });
  return sma(ranges, period);
}

function wilderSmooth(values, period) {
  const output = [];
  let smoothed = 0;
  for (let index = 0; index < values.length; index += 1) {
    const value = Number(values[index] || 0);
    if (index < period) {
      smoothed += value;
      output.push(index === period - 1 ? smoothed : 0);
      continue;
    }
    smoothed = smoothed - (smoothed / period) + value;
    output.push(smoothed);
  }
  return output;
}

function adx(highs, lows, closes, period = 14) {
  const trueRanges = [];
  const plusDm = [];
  const minusDm = [];

  for (let index = 0; index < closes.length; index += 1) {
    if (index === 0) {
      trueRanges.push(highs[index] - lows[index]);
      plusDm.push(0);
      minusDm.push(0);
      continue;
    }
    const upMove = highs[index] - highs[index - 1];
    const downMove = lows[index - 1] - lows[index];
    trueRanges.push(Math.max(
      highs[index] - lows[index],
      Math.abs(highs[index] - closes[index - 1]),
      Math.abs(lows[index] - closes[index - 1]),
    ));
    plusDm.push(upMove > downMove && upMove > 0 ? upMove : 0);
    minusDm.push(downMove > upMove && downMove > 0 ? downMove : 0);
  }

  const smoothedTr = wilderSmooth(trueRanges, period);
  const smoothedPlusDm = wilderSmooth(plusDm, period);
  const smoothedMinusDm = wilderSmooth(minusDm, period);
  const plusDi = smoothedPlusDm.map((value, index) => {
    const trValue = smoothedTr[index] || 0;
    return trValue === 0 ? 0 : (value / trValue) * 100;
  });
  const minusDi = smoothedMinusDm.map((value, index) => {
    const trValue = smoothedTr[index] || 0;
    return trValue === 0 ? 0 : (value / trValue) * 100;
  });
  const dx = plusDi.map((value, index) => {
    const denominator = value + minusDi[index];
    return denominator === 0 ? 0 : (Math.abs(value - minusDi[index]) / denominator) * 100;
  });
  const adxValues = [];
  let prevAdx = 0;
  for (let index = 0; index < dx.length; index += 1) {
    if (index < (period * 2) - 2) {
      adxValues.push(0);
      continue;
    }
    if (index === (period * 2) - 2) {
      const initial = dx.slice(period - 1, (period * 2) - 1);
      prevAdx = initial.reduce((sum, value) => sum + value, 0) / initial.length;
      adxValues.push(prevAdx);
      continue;
    }
    prevAdx = ((prevAdx * (period - 1)) + dx[index]) / period;
    adxValues.push(prevAdx);
  }
  return { adxValues, plusDi, minusDi };
}

function bbands(values, period = 20, multiplier = 2) {
  const middle = sma(values, period);
  const std = rollingStd(values, period);
  const upper = middle.map((value, index) => value + (std[index] * multiplier));
  const lower = middle.map((value, index) => value - (std[index] * multiplier));
  const width = upper.map((value, index) => value - lower[index]);
  return { upper, middle, lower, width };
}

function buildLabels(candles, timeframe) {
  return candles.map((item) => {
    const ts = new Date(item.ts_open);
    if (timeframe === "1h" || timeframe === "4h") {
      return `${ts.getMonth() + 1}/${ts.getDate()} ${String(ts.getHours()).padStart(2, "0")}:00`;
    }
    return `${ts.getFullYear()}/${ts.getMonth() + 1}/${ts.getDate()}`;
  });
}

function trendInterpretation(close, ema30Value, ema60Value, ema120Value, rsiValue) {
  if (close > ema30Value && ema30Value > ema60Value && ema60Value > ema120Value) return "偏多，价格站在 EMA30/60/120 之上。";
  if (close < ema30Value && ema30Value < ema60Value && ema60Value < ema120Value) return "偏空，价格位于均线体系下方。";
  if (rsiValue >= 60) return "中性偏多，趋势仍偏向多头。";
  if (rsiValue <= 40) return "中性偏空，结构尚未明显修复。";
  return "整理状态，等待方向确认。";
}

function rsiInterpretation(value) {
  if (value >= 75) return "超买风险，动量很强但追高回撤风险上升。";
  if (value >= 60) return "偏多，RSI 处于强势区但尚未极端。";
  if (value > 45) return "中性，情绪未到极端区。";
  if (value > 30) return "偏空，反弹动能仍不足。";
  return "超卖修复，空头惯性较强但存在技术修复弹性。";
}

function macdInterpretation(histValue, lineValue, signalValue, previousHistValue = 0) {
  const slope = histValue - previousHistValue;
  if (histValue > 0 && lineValue > 0 && slope > 0) return "偏多，MACD 在零轴上方增强，多头动能占优。";
  if (histValue > 0 && lineValue > signalValue) return "中性偏多，MACD 仍在零轴上方但柱状值扩张放缓。";
  if (histValue < 0 && lineValue < 0 && slope < 0) return "偏空，MACD 在零轴下方增强，空头动能占优。";
  if (histValue < 0 && slope > 0) return "中性偏空，零轴下方空头动能收敛，处于修复阶段。";
  return "中性，动量切换尚不明确。";
}

function vegasInterpretation(close, ema12Value, fastLow, fastHigh, slowLow) {
  if (close > fastHigh && ema12Value > fastHigh) return "偏多，价格与 EMA12 共同站上快轨。";
  if (close < slowLow && ema12Value < fastLow) return "偏空，价格跌出慢轨下沿。";
  if (close >= fastLow && close <= fastHigh) return "中性，价格回到快轨内部。";
  return "观望，通道结构尚未形成一致方向。";
}

function volatilityInterpretation(widthPct, atrValue) {
  if (widthPct >= 12 || atrValue >= 2500) return "事件型，波动明显扩张，仓位宜更保守。";
  if (widthPct >= 9 || atrValue >= 1800) return "扩张，波动高于常态，突破和假突破概率同时上升。";
  if (widthPct <= 6 && atrValue <= 1200) return "压缩，波动处于收敛区，等待方向释放。";
  return "常态，波动处于正常区间。";
}

function adxInterpretation(adxValue, plusDiValue, minusDiValue) {
  const spread = Math.abs(plusDiValue - minusDiValue);
  if (adxValue >= 30 && plusDiValue > minusDiValue) return "强趋势偏多，ADX 高位且 +DI 明显占优。";
  if (adxValue >= 30 && minusDiValue > plusDiValue) return "强趋势偏空，ADX 高位且 -DI 明显占优。";
  if (adxValue >= 22 && plusDiValue > minusDiValue && spread >= 3) return "趋势成形偏多，+DI 领先但仍需价格确认。";
  if (adxValue >= 22 && minusDiValue > plusDiValue && spread >= 3) return "趋势成形偏空，-DI 领先但仍需价格确认。";
  if (adxValue < 18) return "趋势弱，ADX 偏低，当前更接近震荡。";
  return "中性，趋势强度正在酝酿但方向不够清晰。";
}

function obvInterpretation(obvValues, closeValues) {
  const latest = obvValues.at(-1) || 0;
  const baseline = sma(obvValues, 20).at(-1) || latest;
  const recent = obvValues.length > 6 ? latest - (obvValues.at(-6) || latest) : 0;
  const priceRecent = closeValues.length > 6 ? (closeValues.at(-1) || 0) - (closeValues.at(-6) || 0) : 0;
  if (latest > baseline && recent > 0 && priceRecent >= 0) return "偏多，量能与价格同步确认上行。";
  if (latest < baseline && recent < 0 && priceRecent <= 0) return "偏空，量能与价格同步走弱。";
  if (recent > 0 && priceRecent < 0) return "中性偏多，OBV 回升但价格尚未跟随，存在潜在吸筹。";
  if (recent < 0 && priceRecent > 0) return "中性偏空，价格上行但 OBV 背离，追涨质量不足。";
  if (recent > 0) return "中性偏多，OBV 短线回升但趋势仍需确认。";
  if (recent < 0) return "中性偏空，OBV 短线走弱但尚未破坏主结构。";
  return "中性，量能累积方向暂不明确。";
}

function kdjInterpretation(kValue, dValue, jValue, prevKValue = kValue, prevDValue = dValue) {
  const goldenCross = prevKValue <= prevDValue && kValue > dValue;
  const deadCross = prevKValue >= prevDValue && kValue < dValue;
  if (jValue >= 95) return "超买风险，J 值极端偏高，短线追涨需谨慎。";
  if (jValue <= 5) return "超卖修复，J 值极端偏低，存在反弹弹性。";
  if (goldenCross && kValue >= 50) return "偏多，KDJ 金叉并进入强势区。";
  if (deadCross && kValue <= 50) return "偏空，KDJ 死叉并进入弱势区。";
  if (kValue > dValue && kValue >= 55) return "中性偏多，K 线位于 D 线上方但非新金叉。";
  if (kValue < dValue && kValue <= 45) return "中性偏空，K 线位于 D 线下方且动能偏弱。";
  return "中性，KDJ 尚未形成明确动能方向。";
}

function cciInterpretation(value) {
  if (value >= 200) return "过热回撤风险，价格偏离均值过远。";
  if (value >= 100) return "强势扩张，价格处于偏多扩张区。";
  if (value <= -200) return "超跌修复，价格偏离过深，反弹弹性上升。";
  if (value <= -100) return "弱势扩张，价格处于偏空扩张区。";
  return "中性，价格仍在常态波动范围内。";
}

function marketImpact(text) {
  if (text.includes("超买风险") || text.includes("过热") || text.includes("事件型")) return "event";
  if (text.includes("强趋势偏多") || text.includes("偏多") || text.includes("强势扩张")) return "bullish";
  if (text.includes("强趋势偏空") || text.includes("偏空") || text.includes("弱势扩张")) return "bearish";
  if (text.includes("事件")) return "event";
  return "neutral";
}

function marketImpactLabel(text) {
  if (text.includes("超买风险") || text.includes("过热")) return "风险";
  if (text.includes("超卖修复")) return "修复";
  if (text.includes("事件型")) return "事件型";
  if (text.includes("扩张，") || text.includes("压缩") || text.includes("常态")) return "波动环境";
  if (text.includes("强趋势偏多")) return "强偏多";
  if (text.includes("强趋势偏空")) return "强偏空";
  if (text.includes("趋势成形偏多") || text.includes("中性偏多")) return "中性偏多";
  if (text.includes("趋势成形偏空") || text.includes("中性偏空")) return "中性偏空";
  if (text.includes("偏多") || text.includes("强势扩张")) return "偏多";
  if (text.includes("偏空") || text.includes("弱势扩张")) return "偏空";
  return "中性";
}

function useSeries(values, fallback, expectedLength) {
  return Array.isArray(values) && values.length === expectedLength ? values.map((item) => (item === null ? null : Number(item))) : fallback;
}

function useSeriesOrBuild(values, buildFallback, expectedLength) {
  if (Array.isArray(values) && values.length === expectedLength) {
    return values.map((item) => (item === null ? null : Number(item)));
  }
  return buildFallback();
}

function calcAnalysis(candles, bundle = null) {
  const closes = candles.map((item) => toNumber(item.close));
  const highs = candles.map((item) => toNumber(item.high));
  const lows = candles.map((item) => toNumber(item.low));
  const volumes = candles.map((item) => toNumber(item.volume));
  const core = bundle?.core_indicator_series || {};
  const secondary = bundle?.secondary_indicator_series || {};
  let computedMacd = null;
  let computedAtr = null;
  let computedAdx = null;
  let computedBoll = null;
  let computedKdj = null;
  const ensureMacd = () => (computedMacd ||= macd(closes));
  const ensureAtr = () => (computedAtr ||= atr(highs, lows, closes, 14));
  const ensureAdx = () => (computedAdx ||= adx(highs, lows, closes, 14));
  const ensureBoll = () => (computedBoll ||= bbands(closes, 20, 2));
  const ensureKdj = () => (computedKdj ||= kdj(highs, lows, closes, 9));
  return {
    closes,
    volumes,
    ema12: useSeriesOrBuild(core.ema_12, () => ema(closes, 12), closes.length),
    ema30: useSeriesOrBuild(core.ema_30, () => ema(closes, 30), closes.length),
    ema60: useSeriesOrBuild(core.ema_60, () => ema(closes, 60), closes.length),
    ema120: useSeriesOrBuild(core.ema_120, () => ema(closes, 120), closes.length),
    vegasFastLow: ema(closes, 144),
    vegasFastHigh: ema(closes, 169),
    vegasSlowLow: ema(closes, 576),
    vegasSlowHigh: ema(closes, 676),
    rsiValues: useSeriesOrBuild(core.rsi_14, () => rsi(closes, 14), closes.length),
    macdValues: {
      line: useSeriesOrBuild(core.macd_line, () => ensureMacd().line, closes.length),
      signal: useSeriesOrBuild(core.macd_signal, () => ensureMacd().signal, closes.length),
      hist: useSeriesOrBuild(core.macd_hist, () => ensureMacd().hist, closes.length),
    },
    atrValues: useSeriesOrBuild(core.atr_14, () => ensureAtr(), closes.length),
    adxValues: {
      adxValues: useSeriesOrBuild(secondary.adx_14, () => ensureAdx().adxValues, closes.length),
      plusDi: useSeriesOrBuild(secondary.plus_di, () => ensureAdx().plusDi, closes.length),
      minusDi: useSeriesOrBuild(secondary.minus_di, () => ensureAdx().minusDi, closes.length),
    },
    boll: {
      upper: useSeriesOrBuild(secondary.bbands_upper, () => ensureBoll().upper, closes.length),
      middle: useSeriesOrBuild(secondary.bbands_middle, () => ensureBoll().middle, closes.length),
      lower: useSeriesOrBuild(secondary.bbands_lower, () => ensureBoll().lower, closes.length),
      width: useSeriesOrBuild(secondary.bbands_width, () => ensureBoll().width, closes.length),
      percentB: useSeriesOrBuild(
        secondary.percent_b,
        () => {
          const built = ensureBoll();
          return closes.map((value, index) => {
            const range = built.upper[index] - built.lower[index];
            return range === 0 ? 0 : (value - built.lower[index]) / range;
          });
        },
        closes.length,
      ),
    },
    obvValues: useSeriesOrBuild(secondary.obv, () => obv(closes, volumes), closes.length),
    kdjValues: {
      k: useSeriesOrBuild(secondary.kdj_k, () => ensureKdj().k, closes.length),
      d: useSeriesOrBuild(secondary.kdj_d, () => ensureKdj().d, closes.length),
      j: useSeriesOrBuild(secondary.kdj_j, () => ensureKdj().j, closes.length),
    },
    cciValues: useSeriesOrBuild(secondary.cci_20, () => cci(highs, lows, closes, 20), closes.length),
  };
}

function sliceSeries(values, limit) {
  return Array.isArray(values) ? values.slice(-limit) : values;
}

function sliceAnalysisForDisplay(analysis, limit) {
  return {
    ...analysis,
    closes: sliceSeries(analysis.closes, limit),
    volumes: sliceSeries(analysis.volumes, limit),
    ema12: sliceSeries(analysis.ema12, limit),
    ema30: sliceSeries(analysis.ema30, limit),
    ema60: sliceSeries(analysis.ema60, limit),
    ema120: sliceSeries(analysis.ema120, limit),
    vegasFastLow: sliceSeries(analysis.vegasFastLow, limit),
    vegasFastHigh: sliceSeries(analysis.vegasFastHigh, limit),
    vegasSlowLow: sliceSeries(analysis.vegasSlowLow, limit),
    vegasSlowHigh: sliceSeries(analysis.vegasSlowHigh, limit),
    rsiValues: sliceSeries(analysis.rsiValues, limit),
    atrValues: sliceSeries(analysis.atrValues, limit),
    obvValues: sliceSeries(analysis.obvValues, limit),
    cciValues: sliceSeries(analysis.cciValues, limit),
    macdValues: {
      line: sliceSeries(analysis.macdValues.line, limit),
      signal: sliceSeries(analysis.macdValues.signal, limit),
      hist: sliceSeries(analysis.macdValues.hist, limit),
    },
    adxValues: {
      adxValues: sliceSeries(analysis.adxValues.adxValues, limit),
      plusDi: sliceSeries(analysis.adxValues.plusDi, limit),
      minusDi: sliceSeries(analysis.adxValues.minusDi, limit),
    },
    boll: {
      upper: sliceSeries(analysis.boll.upper, limit),
      middle: sliceSeries(analysis.boll.middle, limit),
      lower: sliceSeries(analysis.boll.lower, limit),
      width: sliceSeries(analysis.boll.width, limit),
      percentB: sliceSeries(analysis.boll.percentB, limit),
    },
    kdjValues: {
      k: sliceSeries(analysis.kdjValues.k, limit),
      d: sliceSeries(analysis.kdjValues.d, limit),
      j: sliceSeries(analysis.kdjValues.j, limit),
    },
  };
}

function normalizeOhlcCandles(candles) {
  return candles.map((item) => ({
    ...item,
    open: Number(item.open),
    high: Number(item.high),
    low: Number(item.low),
    close: Number(item.close),
  })).filter((item) => [item.open, item.high, item.low, item.close].every(Number.isFinite));
}

function heroTemplate() {
  return `
    <section class="analysis-hero-grid">
      <article class="card analysis-hero-card">
        <div class="analysis-hero-top">
          <div>
            <p class="eyebrow">MARKET ANALYSIS</p>
            <h2>行情与指标一体视图 ${knowledgeTooltip("Market Analysis Workspace / 技术指标页", "tone-neutral")}</h2>
            <p class="section-summary" id="analysis-summary"></p>
          </div>
          <div class="toolbar compact-toolbar">
            <select id="analysis-timeframe">
              ${["1h", "4h", "1d", "1w", "1M"].map((item) => `<option value="${item}" ${item === appState.selectedTimeframe ? "selected" : ""}>${item}</option>`).join("")}
            </select>
            <select id="analysis-window">
              <option value="short" ${appState.selectedViewWindow === "short" ? "selected" : ""}>短窗</option>
              <option value="default" ${appState.selectedViewWindow === "default" ? "selected" : ""}>默认</option>
              <option value="long" ${appState.selectedViewWindow === "long" ? "selected" : ""}>长窗</option>
            </select>
            <button id="analysis-refresh">刷新分析</button>
          </div>
        </div>
        <div class="instrument-switcher">
          ${appState.instruments.map((item) => `
            <button class="instrument-pill ${item.id === appState.selectedInstrumentId ? "is-active" : ""}" data-instrument-id="${item.id}">
              <strong>${item.code}</strong>
              <span>${item.name}</span>
            </button>
          `).join("")}
        </div>
      </article>
      <article class="card realtime-card">
        <div class="card-head-inline">
          <div>
            <p class="eyebrow">REAL-TIME MARK</p>
            <h2>实时标记价 ${knowledgeTooltip("Mark / Index / Deviation", "tone-bullish", "5 分钟自动刷新，切回页面时会立即补读。", { extra: "页面中的实时标记价 5 分钟自动刷新，切回页面时会立即补读。" })}</h2>
          </div>
          ${statusChip("Live", "chip-bullish")}
        </div>
        <p class="live-price" id="analysis-mark-price">-</p>
        <div class="status-grid">
          <div class="mini-card">
            <span>最近刷新</span>
            <strong id="analysis-mark-updated">-</strong>
            <small id="analysis-mark-next">-</small>
          </div>
          <div class="mini-card">
            <span>最近收盘</span>
            <strong id="analysis-mark-close">-</strong>
            <small id="analysis-mark-aux">-</small>
          </div>
        </div>
      </article>
    </section>
    <section id="analysis-statusbar"></section>
    <section class="grid cols-4" id="analysis-signal-cards"></section>
    <section class="analysis-chart-grid">
      <article class="card">
        <div class="section-head">
          <div><p class="eyebrow">TREND</p><h2>价格与 EMA</h2></div>
          <p class="section-summary" id="analysis-window-copy"></p>
        </div>
        <div class="chart-wrap"><canvas id="analysis-price-chart"></canvas></div>
      </article>
      <article class="card">
        <div class="section-head">
          <div><p class="eyebrow">STRUCTURE</p><h2>Vegas 通道</h2></div>
          <p class="section-summary" id="analysis-vegas-copy"></p>
        </div>
        <div class="chart-wrap"><canvas id="analysis-vegas-chart"></canvas></div>
      </article>
      <article class="card">
        <div class="section-head">
          <div><p class="eyebrow">VOLATILITY</p><h2>BOLL</h2></div>
          <p class="section-summary" id="analysis-boll-copy"></p>
        </div>
        <div class="chart-wrap"><canvas id="analysis-boll-chart"></canvas></div>
      </article>
      <article class="card">
        <div class="section-head">
          <div><p class="eyebrow">MOMENTUM</p><h2>RSI</h2></div>
          <p class="section-summary" id="analysis-rsi-copy"></p>
        </div>
        <div class="chart-wrap"><canvas id="analysis-rsi-chart"></canvas></div>
      </article>
      <article class="card">
        <div class="section-head">
          <div><p class="eyebrow">VOLUME</p><h2>成交量</h2></div>
          <p class="section-summary" id="analysis-volume-copy"></p>
        </div>
        <div class="chart-wrap"><canvas id="analysis-volume-chart"></canvas></div>
      </article>
      <article class="card">
        <div class="section-head">
          <div><p class="eyebrow">MOMENTUM</p><h2>MACD</h2></div>
          <p class="section-summary" id="analysis-macd-copy"></p>
        </div>
        <div class="chart-wrap"><canvas id="analysis-macd-chart"></canvas></div>
      </article>
    </section>
  `;
}

export async function renderAnalysis() {
  await ensureDeps();
  setRoot(heroTemplate());
  const timeframeSelect = document.getElementById("analysis-timeframe");
  const windowSelect = document.getElementById("analysis-window");
  let timer = null;
  let bundleRetryTimer = null;
  let activeController = null;

  function clearBundleRetry() {
    if (bundleRetryTimer) {
      window.clearTimeout(bundleRetryTimer);
      bundleRetryTimer = null;
    }
  }

  function scheduleBundleRetry() {
    clearBundleRetry();
    bundleRetryTimer = window.setTimeout(() => {
      loadAll(true).catch((error) => console.warn("analysis:bundle-retry:error", error));
    }, 4000);
  }

  function renderAnalysisStatus(message, tone = "neutral") {
    const el = document.getElementById("analysis-statusbar");
    if (el) el.innerHTML = statusBanner(message, tone);
  }

  function setRefreshBusy(isBusy, label = "刷新分析") {
    const button = document.getElementById("analysis-refresh");
    if (!button) return;
    button.disabled = isBusy;
    button.textContent = isBusy ? label : "刷新分析";
  }

  async function loadAll(force = false) {
    clearBundleRetry();
    const profile = getWindowProfile(appState.selectedTimeframe, appState.selectedViewWindow);
    const requestLimit = Math.min(profile.calcBars, 1000);
    const fetchKey = `${appState.selectedInstrumentId}:${appState.selectedTimeframe}`;
    const minCandles = minCandlesFor(appState.selectedTimeframe);
    let liveFetched = false;
    renderAnalysisStatus("正在读取缓存", "loading");
    setRefreshBusy(true, force ? "计算中" : "读取中");
    if (force) {
      invalidateCache("/marketdata/candles");
      invalidateCache("/market-prices/marks/latest");
    }
    try {
      activeController?.abort();
      activeController = new AbortController();
      const bundle = await api.getAnalysisBundle(
        appState.selectedInstrumentId,
        appState.selectedTimeframe,
        appState.selectedViewWindow,
        { force, signal: activeController.signal },
      );
      if (bundle.status === "missing" || bundle.status === "stale" || bundle.status === "refreshing") {
        await scheduleIdlePrecompute({
          page: "market-analysis",
          instrumentId: appState.selectedInstrumentId,
          timeframe: appState.selectedTimeframe === "1M" ? "30d" : appState.selectedTimeframe,
          viewWindow: appState.selectedViewWindow,
          reason: force ? "analysis_manual_reload" : "analysis_bundle_read",
          priority: force ? 2 : 4,
        });
      }
      let candlesPayload = { candles: bundle.candles || [] };
      let markPayload = bundle.mark || null;
      let allCandles = normalizeOhlcCandles(candlesPayload.candles || []);
      const shouldAutoFetch = false;
      if (false && (force || shouldAutoFetch)) {
        autoFetchKeys.add(fetchKey);
        liveFetched = true;
        renderAnalysisStatus("本地暂无数据，正在从 Gate.io 拉取 K 线", "loading");
        setRefreshBusy(true, "拉取中");
        const livePayload = await api.getCandles(
          appState.selectedInstrumentId,
          appState.selectedTimeframe,
          requestLimit,
          { preferLive: true, force: true },
        );
        allCandles = normalizeOhlcCandles(livePayload.candles || []);
        invalidateCache("/marketdata/candles");
        candlesPayload = livePayload;
        renderAnalysisStatus("正在计算指标", "loading");
        setRefreshBusy(true, "计算中");
        try {
          await api.refreshTechnical(appState.selectedInstrumentId, appState.selectedTimeframe === "1M" ? "30d" : appState.selectedTimeframe, {
            fetchLimit: Math.min(profile.calcBars, 1000),
          });
        } catch (error) {
          console.warn("analysis:technical-refresh:error", error);
        }
        try {
          markPayload = await api.getLatestMark(appState.selectedInstrumentId, { preferLive: true, force: true });
        } catch (error) {
          console.warn("analysis:mark-refresh:error", error);
        }
      }
      if (!allCandles.length) {
        if (bundle.status === "missing" || bundle.status === "stale" || bundle.status === "refreshing") {
          document.getElementById("analysis-summary").textContent = "后台正在准备当前标的与周期的数据";
          document.getElementById("analysis-mark-price").textContent = "-";
          document.getElementById("analysis-mark-updated").textContent = "-";
          document.getElementById("analysis-mark-next").textContent = "等待后台预计算";
          document.getElementById("analysis-mark-close").textContent = "-";
          document.getElementById("analysis-mark-aux").textContent = "-";
          document.getElementById("analysis-window-copy").textContent = `图表展示最近 ${profile.visibleBars} 根 K 线，指标计算使用 ${profile.calcBars} 根 K 线样本`;
          document.getElementById("analysis-vegas-copy").textContent = "快照生成后将自动回填 Vegas 通道。";
          document.getElementById("analysis-boll-copy").textContent = "快照生成后将自动回填布林与波动结构。";
          document.getElementById("analysis-rsi-copy").textContent = "快照生成后将自动回填动量读数。";
          document.getElementById("analysis-volume-copy").textContent = "快照生成后将自动回填成交量与量能判断。";
          document.getElementById("analysis-macd-copy").textContent = "快照生成后将自动回填 MACD 与趋势结构。";
          document.getElementById("analysis-signal-cards").innerHTML = loadingState(
            bundle.status === "stale" ? "快照略有滞后，后台正在刷新" : "暂无快照，已加入预计算队列",
          );
          document.getElementById("analysis-price-chart").innerHTML = emptyState("后台正在准备图表数据");
          document.getElementById("analysis-vegas-chart").innerHTML = emptyState("等待快照回填后渲染 Vegas 通道");
          document.getElementById("analysis-boll-chart").innerHTML = emptyState("等待快照回填后渲染波动结构");
          document.getElementById("analysis-rsi-chart").innerHTML = emptyState("等待快照回填后渲染 RSI");
          document.getElementById("analysis-volume-chart").innerHTML = emptyState("等待快照回填后渲染成交量");
          document.getElementById("analysis-macd-chart").innerHTML = emptyState("等待快照回填后渲染 MACD");
          renderAnalysisStatus(
            bundle.status === "stale" ? "快照可用，但可能略滞后；后台正在准备最新数据" : "暂无快照，已加入预计算队列",
            bundle.status === "stale" ? "warning" : "loading",
          );
          scheduleBundleRetry();
          return {
            status: bundle.status,
            data: { candles: [], mark: markPayload, bundle },
            refreshed: false,
            error: null,
          };
        }
        document.getElementById("analysis-summary").textContent =
          bundle.status_message || "暂无快照，后台正在准备当前标的与周期的数据";
        document.getElementById("analysis-signal-cards").innerHTML = emptyState(
          "暂无快照，已加入预计算队列",
        );
        renderAnalysisStatus("暂无快照，后台准备中", "loading");
        return {
          status: "missing",
          data: { candles: [], mark: markPayload, bundle },
          refreshed: false,
          error: null,
        };
      }
      const calcCandles = allCandles.slice(-profile.calcBars);
      const candles = calcCandles.slice(-profile.visibleBars);
    const analysis = sliceAnalysisForDisplay(calcAnalysis(calcCandles, bundle), profile.visibleBars);
    const labels = buildLabels(candles, appState.selectedTimeframe);
    const close = analysis.closes.at(-1) || 0;
    const trendText = trendInterpretation(close, analysis.ema30.at(-1), analysis.ema60.at(-1), analysis.ema120.at(-1), analysis.rsiValues.at(-1));
    const rsiText = rsiInterpretation(analysis.rsiValues.at(-1) || 0);
    const macdText = macdInterpretation(
      analysis.macdValues.hist.at(-1) || 0,
      analysis.macdValues.line.at(-1) || 0,
      analysis.macdValues.signal.at(-1) || 0,
      analysis.macdValues.hist.at(-2) || 0,
    );
    const adxValue = analysis.adxValues.adxValues.at(-1) || 0;
    const plusDiValue = analysis.adxValues.plusDi.at(-1) || 0;
    const minusDiValue = analysis.adxValues.minusDi.at(-1) || 0;
    const adxText = adxInterpretation(adxValue, plusDiValue, minusDiValue);
    const bollWidth = analysis.boll.width.at(-1) || 0;
    const bollWidthPct = (bollWidth / (analysis.boll.middle.at(-1) || 1)) * 100;
    const volText = volatilityInterpretation(bollWidthPct, analysis.atrValues.at(-1) || 0);
    const vegasText = vegasInterpretation(close, analysis.ema12.at(-1) || 0, analysis.vegasFastLow.at(-1) || 0, analysis.vegasFastHigh.at(-1) || 0, analysis.vegasSlowLow.at(-1) || 0);
    const obvText = obvInterpretation(analysis.obvValues, analysis.closes);
    const kValue = analysis.kdjValues.k.at(-1) || 0;
    const dValue = analysis.kdjValues.d.at(-1) || 0;
    const jValue = analysis.kdjValues.j.at(-1) || 0;
    const kdjText = kdjInterpretation(kValue, dValue, jValue, analysis.kdjValues.k.at(-2) || kValue, analysis.kdjValues.d.at(-2) || dValue);
    const cciValue = analysis.cciValues.at(-1) || 0;
    const cciText = cciInterpretation(cciValue);
    const latestCandle = candles.at(-1);

    document.getElementById("analysis-summary").textContent = `${trendText.replace("。", "")} ${rsiText}`;
    document.getElementById("analysis-window-copy").textContent = `图表展示最近 ${profile.visibleBars} 根 K 线，指标计算使用 ${profile.calcBars} 根 K 线样本`;
    document.getElementById("analysis-vegas-copy").textContent = vegasText;
    document.getElementById("analysis-boll-copy").textContent = volText;
    document.getElementById("analysis-rsi-copy").textContent = rsiText;
    document.getElementById("analysis-volume-copy").textContent = candles.length >= 2 && analysis.volumes.at(-1) > analysis.volumes.at(-2) * 1.2
      ? "放量，结构突破与波动扩张更值得关注。"
      : "量能平稳，暂未出现明显异常放大。";
    document.getElementById("analysis-macd-copy").textContent = macdText;

    document.getElementById("analysis-mark-price").textContent = formatNumber(markPayload?.mark_price ?? close);
    document.getElementById("analysis-mark-updated").textContent = formatDateTime(markPayload?.ts_event);
    document.getElementById("analysis-mark-next").textContent = "5 分钟自动刷新";
    document.getElementById("analysis-mark-close").textContent = formatNumber(close);
    document.getElementById("analysis-mark-aux").textContent = latestCandle ? `${formatNumber(latestCandle.low)} - ${formatNumber(latestCandle.high)}` : "-";

    document.getElementById("analysis-signal-cards").innerHTML = [
      { eyebrow: "TREND", title: "趋势信号", value: formatNumber(analysis.ema30.at(-1)), label: "EMA 30", desc: trendText },
      { eyebrow: "TREND", title: "趋势强度", value: `${formatNumber(adxValue, 1)} / ${formatNumber(plusDiValue, 1)} / ${formatNumber(minusDiValue, 1)}`, label: "ADX / +DI / -DI", desc: adxText },
      { eyebrow: "MOMENTUM", title: "MACD 柱状值", value: formatNumber(analysis.macdValues.hist.at(-1)), label: "MACD", desc: macdText },
      { eyebrow: "MOMENTUM", title: "动量信号", value: formatNumber(analysis.rsiValues.at(-1)), label: "RSI", desc: rsiText },
      { eyebrow: "VOLATILITY", title: "波动信号", value: `${formatNumber(bollWidth)} / ${formatNumber(analysis.atrValues.at(-1))}`, label: "BOLL 宽度 / ATR", desc: volText },
      { eyebrow: "VOLUME", title: "OBV 量能", value: formatNumber(analysis.obvValues.at(-1), 0), label: "OBV", desc: obvText },
      { eyebrow: "MOMENTUM", title: "KDJ 动能", value: `${formatNumber(kValue, 1)} / ${formatNumber(dValue, 1)} / ${formatNumber(jValue, 1)}`, label: "K / D / J", desc: kdjText },
      { eyebrow: "MOMENTUM", title: "CCI 偏离", value: formatNumber(cciValue, 1), label: "CCI 20", desc: cciText },
    ].map((item) => `
      <article class="card signal-card">
        <p class="eyebrow">${item.eyebrow}</p>
        <div class="card-head-inline">
          <strong>${item.title}</strong>
          ${impactChip(marketImpact(item.desc), "", marketImpactLabel(item.desc))}
        </div>
        <p class="signal-value">${item.value}</p>
        <small class="signal-label">${item.label}</small>
        <p class="signal-copy">${item.desc}</p>
      </article>
    `).join("");

    renderChart("analysis-price", document.getElementById("analysis-price-chart"), {
      type: "line",
      data: {
        labels,
        datasets: [
          lineDataset("收盘价", analysis.closes, "#16232b", { borderWidth: 3.1 }),
          lineDataset("EMA30", analysis.ema30, "#0f766e", { borderWidth: 2.5 }),
          lineDataset("EMA60", analysis.ema60, "#2563eb", { borderDash: [8, 6], borderWidth: 2.15 }),
          lineDataset("EMA120", analysis.ema120, "#c17827", { borderDash: [3, 5], borderWidth: 2.05 }),
        ],
      },
    });

    renderChart("analysis-vegas", document.getElementById("analysis-vegas-chart"), {
      type: "line",
      data: {
        labels,
        datasets: [
          lineDataset("EMA12", analysis.ema12, "#d97706", { borderWidth: 2.3 }),
          lineDataset("快轨", analysis.vegasFastLow, "rgba(15,118,110,0.92)", { borderWidth: 2.15 }),
          lineDataset("快轨", analysis.vegasFastHigh, "rgba(15,118,110,0.92)", { fill: "-1", backgroundColor: "rgba(15,118,110,0.1)", borderWidth: 2.15 }),
          lineDataset("慢轨", analysis.vegasSlowLow, "rgba(195,90,29,0.88)", { borderDash: [7, 5], borderWidth: 2.05 }),
          lineDataset("慢轨", analysis.vegasSlowHigh, "rgba(195,90,29,0.88)", { fill: "-1", backgroundColor: "rgba(195,90,29,0.08)", borderDash: [7, 5], borderWidth: 2.05 }),
        ],
      },
      options: {
        plugins: {
          legend: { labels: { filter: (item) => ["EMA12", "快轨", "慢轨"].includes(item.text) } },
        },
      },
    });

    renderChart("analysis-boll", document.getElementById("analysis-boll-chart"), {
      type: "line",
      data: {
        labels,
        datasets: [
          candleDataset("K 线", candles, { order: 0 }),
          lineDataset("上轨", analysis.boll.upper, "rgba(193,120,39,0.92)", { order: 1, borderDash: [10, 6], borderWidth: 2.1 }),
          lineDataset("中轨", analysis.boll.middle, "rgba(89,104,113,0.8)", { order: 1, borderDash: [4, 6], borderWidth: 1.8 }),
          lineDataset("下轨", analysis.boll.lower, "rgba(37,99,235,0.88)", { order: 1, borderDash: [10, 6], borderWidth: 2.1 }),
        ],
      },
      options: {
        plugins: {
          legend: {
            labels: {
              filter: (item) => ["K 线", "上轨", "中轨", "下轨"].includes(item.text),
            },
          },
          tooltip: {
            callbacks: {
              label(context) {
                if (context.dataset.renderAsCandles) {
                  const candle = candles[context.dataIndex];
                  if (!candle) return "K 线";
                  return [
                    `开 ${formatNumber(candle.open)}`,
                    `高 ${formatNumber(candle.high)}`,
                    `低 ${formatNumber(candle.low)}`,
                    `收 ${formatNumber(candle.close)}`,
                  ];
                }
                return `${context.dataset.label}: ${formatNumber(context.parsed.y)}`;
              },
            },
          },
        },
      },
    });

    renderChart("analysis-rsi", document.getElementById("analysis-rsi-chart"), {
      type: "line",
      data: { labels, datasets: [lineDataset("RSI", analysis.rsiValues, "#c35a1d", { borderWidth: 2.25 })] },
    });

    renderChart("analysis-volume", document.getElementById("analysis-volume-chart"), {
      type: "bar",
      data: { labels, datasets: [barDataset("成交量", analysis.volumes, "rgba(183,121,31,0.72)")] },
    });

    renderChart("analysis-macd", document.getElementById("analysis-macd-chart"), {
      type: "bar",
      data: {
        labels,
        datasets: [
          barDataset("柱状图", analysis.macdValues.hist, analysis.macdValues.hist.map((value) => value >= 0 ? "rgba(15,118,110,0.45)" : "rgba(180,83,9,0.45)")),
          lineDataset("MACD", analysis.macdValues.line, "#0f766e", { borderWidth: 2.25 }),
          lineDataset("信号线", analysis.macdValues.signal, "#2563eb", { borderDash: [7, 5], borderWidth: 2.05 }),
        ],
      },
    });
      renderAnalysisStatus(
        allCandles.length < minCandles ? "样本较少，已使用可用 K 线进行降级分析" : liveFetched ? "数据已就绪" : "",
        allCandles.length < minCandles ? "warning" : "success",
      );
      return {
        status: bundle.status || "ready",
        data: { candles: candlesPayload.candles || [], mark: markPayload, bundle },
        refreshed: Boolean(bundle.refreshed),
        error: null,
      };
    } catch (error) {
      if (error?.name === "AbortError" || error?.name === "TimeoutError") {
        return { status: "aborted", data: null, refreshed: liveFetched, error: null };
      }
      console.error("analysis:load:error", error);
      document.getElementById("analysis-summary").textContent = "拉取失败，可手动重试";
      document.getElementById("analysis-mark-price").textContent = "-";
      document.getElementById("analysis-mark-updated").textContent = "-";
      document.getElementById("analysis-mark-next").textContent = "请手动刷新";
      document.getElementById("analysis-signal-cards").innerHTML = errorState(String(error.message || error));
      renderAnalysisStatus("拉取失败，可手动重试", "danger");
      return { status: "error", data: null, refreshed: liveFetched, error };
    } finally {
      setRefreshBusy(false);
    }
  }

  async function refreshMarkOnly() {
    if (document.hidden) return;
    invalidateCache("/market-prices/marks/latest");
    const markPayload = await api.getLatestMark(appState.selectedInstrumentId, {
      preferLive: true,
      force: true,
    });
    if (markPayload) {
      document.getElementById("analysis-mark-price").textContent = formatNumber(markPayload.mark_price);
      document.getElementById("analysis-mark-updated").textContent = formatDateTime(markPayload.ts_event);
      document.getElementById("analysis-mark-next").textContent = "5 分钟自动刷新";
    }
  }

  document.querySelectorAll("[data-instrument-id]").forEach((button) => {
    button.addEventListener("click", async () => {
      appState.selectedInstrumentId = button.dataset.instrumentId;
      persistState();
      await renderAnalysis();
    });
  });

  timeframeSelect.addEventListener("change", async (event) => {
    appState.selectedTimeframe = event.target.value;
    persistState();
    await renderAnalysis();
  });

  windowSelect.addEventListener("change", async (event) => {
    appState.selectedViewWindow = event.target.value;
    persistState();
    await renderAnalysis();
  });

  document.getElementById("analysis-refresh").addEventListener("click", async () => {
    setRefreshBusy(true, "刷新中");
    await api.refreshAnalysisBundle(
      appState.selectedInstrumentId,
      appState.selectedTimeframe,
      appState.selectedViewWindow,
    );
    await loadAll(true);
  });

  await loadAll();
  timer = window.setInterval(refreshMarkOnly, 300000);
  document.addEventListener("visibilitychange", refreshMarkOnly);

  return () => {
    if (timer) window.clearInterval(timer);
    clearBundleRetry();
    destroyChartsForPage?.("analysis-");
    document.removeEventListener("visibilitychange", refreshMarkOnly);
  };
}
