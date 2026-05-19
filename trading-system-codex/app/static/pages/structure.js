import {
  escapeHtml,
  formatDateTime,
  formatNumber,
  knowledgeTooltip,
  setRoot,
  statusChip,
} from "../core/dom.js";
import { scheduleIdlePrecompute } from "../core/precompute.js";
import { api, invalidateCache } from "../core/api.js";
import { appState, getInstrumentMeta, persistState } from "../core/state.js";

const TIMEFRAMES = ["1h", "4h", "1d", "1w", "1M"];
const SYSTEMS = [
  { key: "all", label: "全部系统" },
  { key: "swing", label: "摆动结构" },
  { key: "classic", label: "经典图形" },
  { key: "profile", label: "成交量 / 市场轮廓" },
];

const VIEWPORT_LABELS = {
  focus: "聚焦形态",
  swing: "摆动结构",
  classic: "经典图形",
  context: "结构背景",
  snapshot: "完整快照",
};

const VIEWPORT_CONFIG = {
  "15m": { minBars: 80, maxBars: 240, defaultFocusBars: 160, contextBars: 300, snapshotBars: 480, minPadding: 24, rightPadding: 8 },
  "1h": { minBars: 100, maxBars: 300, defaultFocusBars: 180, contextBars: 360, snapshotBars: 720, minPadding: 24, rightPadding: 8 },
  "4h": { minBars: 80, maxBars: 240, defaultFocusBars: 140, contextBars: 300, snapshotBars: 520, minPadding: 20, rightPadding: 6 },
  "1d": { minBars: 50, maxBars: 160, defaultFocusBars: 90, contextBars: 180, snapshotBars: 260, minPadding: 15, rightPadding: 5 },
  "1w": { minBars: 40, maxBars: 156, defaultFocusBars: 80, contextBars: 156, snapshotBars: 260, minPadding: 10, rightPadding: 4 },
  "1M": { minBars: 40, maxBars: 156, defaultFocusBars: 80, contextBars: 156, snapshotBars: 260, minPadding: 10, rightPadding: 4 },
};

function getStoredViewportMode() {
  try {
    return localStorage.getItem("structureViewportMode") || "focus";
  } catch {
    return "focus";
  }
}

const state = {
  selectedSystem: "all",
  minConfidence: 0.5,
  viewMode: getStoredViewportMode(),
  requestToken: 0,
  recoveryKeys: new Set(),
  bundle: null,
};

if (!VIEWPORT_LABELS[state.viewMode]) {
  state.viewMode = "focus";
}

const BIAS_LABELS = {
  bullish: "偏多",
  weak_bullish: "弱偏多",
  bearish: "偏空",
  weak_bearish: "弱偏空",
  uncertain: "结构分歧 / 不确定",
  neutral: "中性",
  no_clear_structure: "无清晰结构",
};

const STATUS_LABELS = {
  confirmed: "已确认",
  candidate: "候选",
  armed: "待确认",
  invalidated: "失效",
  expired: "过期",
  high: "高",
  medium: "中",
  low: "低",
};

const REGIME_LABELS = {
  trend: "趋势",
  balance: "平衡",
  transition: "过渡",
};

const SYSTEM_LABELS = {
  swing: "摆动结构",
  classic: "经典图形",
  profile: "成交量 / 市场轮廓",
  fused: "综合判断",
};

const CHART_SERIES = {
  price: { label: "价格", color: "rgba(22, 35, 43, 0.38)", dash: "", width: 2.15 },
  swing: { label: "摆动结构", color: "#2563eb", dash: "", width: 2.85 },
  classic: { label: "经典图形", color: "#ea580c", dash: "10 6", width: 2.75 },
  profile: { label: "成交量 / 市场轮廓", color: "#9333ea", dash: "4 7", width: 2.75 },
  fused: { label: "综合判断", color: "#0891b2", dash: "6 5", width: 2.45 },
};

function labelFor(map, value, fallback = "-") {
  return map[value] || value || fallback;
}

function biasTone(value) {
  const text = String(value || "");
  if (text.includes("bull")) return "bullish";
  if (text.includes("bear")) return "bearish";
  return "neutral";
}

function normalizeCandles(payload) {
  if (Array.isArray(payload)) return payload;
  if (Array.isArray(payload?.candles)) return payload.candles;
  return [];
}

function normalizeTextList(items) {
  return Array.isArray(items) ? items.filter(Boolean).map((item) => String(item)) : [];
}

function matchesSelectedSystem(system) {
  return state.selectedSystem === "all" || system === state.selectedSystem;
}

function renderShell() {
  const instrument = getInstrumentMeta(appState.selectedInstrumentId);
  return setRoot(`
    <section class="structure-page structure-page-compact">
      <section class="hero-card structure-toolbar-card">
        <div class="toolbar-grid">
          <label class="field">
            <span>交易品种</span>
            <select id="structure-instrument">
              ${appState.instruments
                .map(
                  (item) =>
                    `<option value="${item.id}" ${item.id === appState.selectedInstrumentId ? "selected" : ""}>${item.code} · ${item.name}</option>`,
                )
                .join("")}
            </select>
          </label>
          <label class="field">
            <span>周期</span>
            <select id="structure-timeframe">
              ${TIMEFRAMES.map(
                (item) => `<option value="${item}" ${item === appState.selectedTimeframe ? "selected" : ""}>${item}</option>`,
              ).join("")}
            </select>
          </label>
          <label class="field">
            <span>系统 ${knowledgeTooltip("Structure System Filter", "tone-neutral")}</span>
            <select id="structure-system">
              ${SYSTEMS.map(
                (item) => `<option value="${item.key}" ${item.key === state.selectedSystem ? "selected" : ""}>${item.label}</option>`,
              ).join("")}
            </select>
          </label>
          <label class="field">
            <span>最低置信度 ${knowledgeTooltip("Minimum Confidence Filter", "tone-neutral")}</span>
            <select id="structure-confidence">
              ${[0, 0.3, 0.5, 0.7]
                .map((item) => `<option value="${item}" ${item === state.minConfidence ? "selected" : ""}>${item.toFixed(2)}+</option>`)
                .join("")}
            </select>
          </label>
          <label class="field">
            <span>视图模式 ${knowledgeTooltip("Overlay View", "tone-neutral")}</span>
            <select id="structure-viewmode">
              <option value="focus" ${state.viewMode === "focus" ? "selected" : ""}>聚焦形态</option>
              <option value="swing" ${state.viewMode === "swing" ? "selected" : ""}>摆动结构</option>
              <option value="classic" ${state.viewMode === "classic" ? "selected" : ""}>经典图形</option>
              <option value="context" ${state.viewMode === "context" ? "selected" : ""}>结构背景</option>
              <option value="snapshot" ${state.viewMode === "snapshot" ? "selected" : ""}>完整快照</option>
            </select>
          </label>
          <div class="field action">
            <button id="structure-refresh" class="primary-button">手动刷新快照</button>
          </div>
        </div>
      </section>

      <section id="structure-statusbar"></section>

      <section class="structure-overview-grid">
        <article class="card structure-main-card">
          <div class="structure-main-head">
            <div>
              <p class="eyebrow">形态叠加图</p>
              <h2>${escapeHtml(instrument.code)} · ${escapeHtml(appState.selectedTimeframe)}</h2>
            </div>
            <div id="structure-chart-bias"></div>
          </div>
          <div id="structure-chart-panel" class="structure-chart-panel loading">正在加载结构快照…</div>
        </article>

        <article class="card structure-summary-card" id="structure-summary-panel"></article>
      </section>

      <section class="card structure-detail-card">
        <div id="structure-detail-panel" class="structure-detail-grid"></div>
      </section>
    </section>
  `);
}

function formatAxisPrice(value) {
  if (!Number.isFinite(value)) return "-";
  if (Math.abs(value) >= 1000) return formatNumber(value, 0);
  if (Math.abs(value) >= 10) return formatNumber(value, 2);
  return formatNumber(value, 2); // 最多2位小数
}

function formatAxisTime(value, timeframe) {
  const date = new Date(value);
  if (Number.isNaN(date.getTime())) return "";
  if (timeframe === "1h" || timeframe === "4h") {
    return `${date.getMonth() + 1}/${date.getDate()} ${String(date.getHours()).padStart(2, "0")}:00`;
  }
  if (timeframe === "1M") return `${date.getFullYear()}/${date.getMonth() + 1}`;
  return `${date.getMonth() + 1}/${date.getDate()}`;
}

function buildChartScale(candles, width, height, minPrice, maxPrice) {
  const margin = { top: 42, right: 28, bottom: 58, left: 78 };
  const plot = {
    x: margin.left,
    y: margin.top,
    width: width - margin.left - margin.right,
    height: height - margin.top - margin.bottom,
  };
  const rawRange = Math.max(maxPrice - minPrice, Math.abs(maxPrice) * 0.01, 1);
  const paddedMin = minPrice - rawRange * 0.08;
  const paddedMax = maxPrice + rawRange * 0.08;
  const xForIndex = (index) => plot.x + (candles.length > 1 ? (index / (candles.length - 1)) * plot.width : plot.width / 2);
  const yForPrice = (price) => plot.y + plot.height - ((Number(price) - paddedMin) / (paddedMax - paddedMin)) * plot.height;
  return { margin, plot, minPrice: paddedMin, maxPrice: paddedMax, xForIndex, yForPrice };
}

function buildLinePath(points, scale) {
  if (!points.length) return "";
  return points
    .map((point, index) => `${index === 0 ? "M" : "L"} ${scale.xForIndex(index).toFixed(2)} ${scale.yForPrice(Number(point.close ?? 0)).toFixed(2)}`)
    .join(" ");
}

function buildAxisMarkup(candles, scale) {
  const yTicks = Array.from({ length: 5 }, (_, index) => scale.minPrice + ((scale.maxPrice - scale.minPrice) * index) / 4);
  const xTickCount = Math.min(6, candles.length);
  const xTicks = Array.from({ length: xTickCount }, (_, index) => Math.round(((candles.length - 1) * index) / Math.max(xTickCount - 1, 1)));
  const yMarkup = yTicks
    .map((tick) => {
      const y = scale.yForPrice(tick);
      return `
        <line class="structure-svg-grid" x1="${scale.plot.x}" y1="${y.toFixed(2)}" x2="${(scale.plot.x + scale.plot.width).toFixed(2)}" y2="${y.toFixed(2)}"></line>
        <text class="structure-svg-axis" x="${scale.plot.x - 12}" y="${(y + 4).toFixed(2)}" text-anchor="end">${escapeHtml(formatAxisPrice(tick))}</text>
      `;
    })
    .join("");
  const xMarkup = xTicks
    .map((index) => {
      const x = scale.xForIndex(index);
      const label = formatAxisTime(candles[index]?.ts_open, appState.selectedTimeframe);
      return `
        <line class="structure-svg-grid vertical" x1="${x.toFixed(2)}" y1="${scale.plot.y}" x2="${x.toFixed(2)}" y2="${(scale.plot.y + scale.plot.height).toFixed(2)}"></line>
        <text class="structure-svg-axis" x="${x.toFixed(2)}" y="${(scale.plot.y + scale.plot.height + 32).toFixed(2)}" text-anchor="middle">${escapeHtml(label)}</text>
      `;
    })
    .join("");
  return `
    <rect class="structure-svg-bg" x="${scale.plot.x}" y="${scale.plot.y}" width="${scale.plot.width}" height="${scale.plot.height}" rx="16"></rect>
    ${yMarkup}
    ${xMarkup}
    <path class="structure-axis-line" d="M ${scale.plot.x} ${scale.plot.y} V ${scale.plot.y + scale.plot.height} H ${scale.plot.x + scale.plot.width}"></path>
  `;
}

function normalizeTs(value) {
  const ts = new Date(value).getTime();
  return Number.isFinite(ts) ? ts : null;
}

function getGeometryPoints(item) {
  if (Array.isArray(item.points_json)) return item.points_json;
  if (Array.isArray(item.points)) return item.points;
  if (Array.isArray(item.meta_json?.points)) return item.meta_json.points;
  return [];
}

function pointTime(point) {
  return normalizeTs(point?.ts ?? point?.timestamp ?? point?.ts_open ?? point?.time);
}

function nearestCandleIndex(candles, tsValue, fallbackIndex = 0) {
  const target = normalizeTs(tsValue);
  if (target === null || !candles.length) return fallbackIndex;
  let bestIndex = 0;
  let bestDistance = Number.POSITIVE_INFINITY;
  candles.forEach((candle, index) => {
    const ts = normalizeTs(candle.ts_open);
    if (ts === null) return;
    const distance = Math.abs(ts - target);
    if (distance < bestDistance) {
      bestDistance = distance;
      bestIndex = index;
    }
  });
  return bestIndex;
}

function pointPrice(point) {
  const value = Number(point?.price ?? point?.value ?? point?.close ?? point?.level);
  return Number.isFinite(value) ? value : null;
}

function hasExplicitIndex(point) {
  return point && point.index !== undefined && point.index !== null && Number.isFinite(Number(point.index));
}

function firstVisibleTs(candles) {
  return candles.length ? normalizeTs(candles[0]?.ts_open) : null;
}

function localIndexForPoint(point, candles, offset, fallbackIndex = 0) {
  if (hasExplicitIndex(point)) {
    return Math.max(0, Number(point.index) - offset);
  }
  const ts = point?.ts ?? point?.timestamp ?? point?.ts_open ?? point?.time;
  if (ts !== undefined && ts !== null) {
    return nearestCandleIndex(candles, ts, fallbackIndex);
  }
  return fallbackIndex;
}

function visiblePointInViewport(point, candles, offset) {
  if (!candles.length) return false;
  if (hasExplicitIndex(point)) return Number(point.index) >= offset;
  const ts = point?.ts ?? point?.timestamp ?? point?.ts_open ?? point?.time;
  if (ts === undefined || ts === null) return true;
  const pointTs = normalizeTs(ts);
  const startTs = firstVisibleTs(candles);
  if (pointTs === null || startTs === null) return true;
  return pointTs >= startTs;
}

function shouldExtendToLatest(item, role) {
  const meta = item.meta_json || item.meta || {};
  if (meta.extend_to_latest === false) return false;
  if (meta.extend_to_latest === true) return true;
  const levelRoles = new Set(["support", "resistance", "neckline", "profile_poc", "profile_vah", "profile_val"]);
  return levelRoles.has(role) || levelRoles.has(item.kind);
}

function extendOverlayToLatestCandle(mapped, role, candles, scale, item) {
  // overlay extension to latest visible candle
  if (!mapped.length || !candles.length) return mapped;
  if (!shouldExtendToLatest(item, role)) return mapped;
  const latestX = scale.xForIndex(candles.length - 1);
  const extendableRoles = new Set([
    "support",
    "resistance",
    "neckline",
    "upper_boundary",
    "lower_boundary",
    "range_high",
    "range_low",
    "support_zone",
    "resistance_zone",
    "invalidation_line",
  ]);
  if (extendableRoles.has(role)) {
    const last = mapped[mapped.length - 1];
    if (last.x < latestX) return [...mapped, { x: latestX, y: last.y }];
  }
  if (mapped.length >= 2) {
    const prev = mapped[mapped.length - 2];
    const last = mapped[mapped.length - 1];
    if (last.x < latestX && Math.abs(last.x - prev.x) > 0.01) {
      const slope = (last.y - prev.y) / (last.x - prev.x);
      return [...mapped, { x: latestX, y: last.y + slope * (latestX - last.x) }];
    }
  }
  return mapped;
}

function viewportConfig() {
  return VIEWPORT_CONFIG[appState.selectedTimeframe] || VIEWPORT_CONFIG["1d"];
}

function calculateViewport(candles, geometry, backendViewport = null) {
  const config = viewportConfig();
  const fullBars = candles.length;
  if (!fullBars) {
    return { candles: [], offset: 0, visibleBars: 0, fullBars: 0, overlayBars: 0, coverage: 0, autoFocused: false };
  }
  const latestIndex = fullBars - 1;
  const latestTs = normalizeTs(candles[latestIndex]?.ts_open);
  const firstTs = normalizeTs(candles[0]?.ts_open);
  const visibleGeometry = (geometry || []).filter((item) => {
    if (item.visible === false) return false;
    const meta = item.meta_json || item.meta || {};
    if (meta.visible_by_default === false) return false;
    const role = meta.role || "";
    if (role === "classic_pattern_path" || role === "pattern_path") return false;
    return true;
  });
  const focusMode = VIEWPORT_LABELS[state.viewMode] ? state.viewMode : "focus";
  const viewportGeometry =
    focusMode === "classic"
      ? visibleGeometry.filter((item) => item.system === "classic")
      : focusMode === "swing"
        ? visibleGeometry.filter((item) => item.system === "swing")
        : visibleGeometry;
  const starts = (viewportGeometry.length ? viewportGeometry : visibleGeometry)
    .flatMap((item) => getGeometryPoints(item).map(pointTime))
    .filter((value) => value !== null && (!latestTs || value <= latestTs) && (!firstTs || value >= firstTs));
  const activeStartTs = backendViewport?.active_start_ts ?? (starts.length ? Math.min(...starts) : null);
  const activeStartIndex =
    activeStartTs === null
      ? null
      : candles.findIndex((item) => {
          const ts = normalizeTs(item.ts_open);
          return ts !== null && ts >= activeStartTs;
        });
  const overlayBars = activeStartIndex === null || activeStartIndex < 0 ? 0 : latestIndex - activeStartIndex + 1;
  const coverage = fullBars ? overlayBars / fullBars : 0;
  const mode = focusMode;
  let displayBars;
  if (mode === "snapshot") {
    displayBars = Math.min(fullBars, config.snapshotBars);
  } else if (mode === "context") {
    displayBars = Math.min(fullBars, config.contextBars);
  } else if (backendViewport?.display_bars) {
    displayBars = Math.min(fullBars, Number(backendViewport.display_bars));
  } else if (overlayBars > 0) {
    const leftPadding = Math.max(Math.round(overlayBars * 0.25), config.minPadding);
    displayBars = Math.min(fullBars, Math.max(config.minBars, Math.min(config.maxBars, overlayBars + leftPadding + config.rightPadding)));
  } else {
    displayBars = Math.min(fullBars, config.defaultFocusBars);
  }
  const startIndex = Math.max(0, latestIndex - displayBars + 1);
  return {
    candles: candles.slice(startIndex),
    offset: startIndex,
    visibleBars: fullBars - startIndex,
    fullBars,
    overlayBars,
    coverage,
    activeStartTs,
    autoFocused: mode === "focus" && coverage > 0 && coverage < 0.45,
  };
}

function visibleGeometryForViewport(geometry, candles, offset) {
  return geometry
    .map((item) => {
      const points = getGeometryPoints(item);
      const filtered = points
        .filter((point, index) => {
          return visiblePointInViewport(point, candles, offset);
        })
        .map((point, index) => {
          const localIndex = localIndexForPoint(point, candles, offset, index);
          const globalIndex = hasExplicitIndex(point) ? Number(point.index) : point?.global_index;
          return { ...point, index: localIndex, global_index: Number.isFinite(Number(globalIndex)) ? Number(globalIndex) : undefined };
        });
      return { ...item, points_json: filtered };
    })
    .filter((item) => getGeometryPoints(item).length > 0);
}

function legendAvailability(geometry) {
  const hasSystem = (system, minPoints = 1) =>
    geometry.some((item) => item.system === system && getGeometryPoints(item).filter((point) => pointPrice(point) !== null).length >= minPoints);
  return {
    price: true,
    swing: hasSystem("swing", 2),
    classic: hasSystem("classic", 2),
    profile: hasSystem("profile", 1),
  };
}

function buildLegendMarkup(availability) {
  const items = Object.entries(CHART_SERIES)
    .filter(([key]) => key !== "fused" && availability[key]);
  return items.map(
    ([key, series], index) => `
      <g transform="translate(${78 + index * 168}, 22)">
        <line x1="0" y1="0" x2="28" y2="0" stroke="${series.color}" stroke-width="3" stroke-dasharray="${series.dash}"></line>
        <text class="structure-svg-axis structure-axis-label" x="36" y="4">${escapeHtml(series.label)}</text>
      </g>
    `).join("");
}

function buildLayerToggleMarkup() {
  return `
    <div class="structure-legend-toggles">
      <label class="legend-toggle" id="toggle-swing"><input type="checkbox" ${overlayLayerState.swing ? "checked" : ""} onchange="toggleOverlayLayer('swing')">摆动骨架</label>
      <label class="legend-toggle" id="toggle-fill"><input type="checkbox" ${overlayLayerState.fill ? "checked" : ""} onchange="toggleOverlayLayer('fill')">图形填充</label>
      <label class="legend-toggle" id="toggle-boundary"><input type="checkbox" ${overlayLayerState.boundary ? "checked" : ""} onchange="toggleOverlayLayer('boundary')">图形边界</label>
      <label class="legend-toggle" id="toggle-candidate"><input type="checkbox" ${overlayLayerState.candidate ? "checked" : ""} onchange="toggleOverlayLayer('candidate')">候选图形</label>
    </div>
  `;
}

const overlayLayerState = { swing: true, fill: true, boundary: true, candidate: false };
window.toggleOverlayLayer = function(layer) {
  overlayLayerState[layer] = !overlayLayerState[layer];
  if (state.bundle?.snapshot) {
    renderChart(state.bundle.snapshot, normalizeCandles(state.bundle.candles || state.bundle.snapshot?.candles || []));
  }
};

function classicPatternCandidates(classicPatterns) {
  if (!classicPatterns || classicPatterns.version !== "classic-pattern-region-v1") return [];
  return [classicPatterns.primary, ...(classicPatterns.candidates || [])].filter(Boolean);
}

function classicPatternPoint(point) {
  return {
    index: Number(point?.index ?? 0),
    time: point?.time,
    ts: point?.time,
    price: Number(point?.price ?? 0),
    label: point?.label || "",
  };
}

function classicPatternTooltip(candidate) {
  const explanation = candidate?.explanation || {};
  if (explanation.tooltip) return explanation.tooltip;
  const levels = (explanation.key_levels || [])
    .slice(0, 4)
    .map((item) => `${item.label} ${formatNumber(item.value, 2)}`)
    .join("；");
  return [
    candidate?.display_name || candidate?.pattern_type || "经典形态",
    explanation.status_text || candidate?.status,
    explanation.direction_text || candidate?.direction_bias,
    `置信度 ${formatNumber(candidate?.confidence ?? 0, 2)}`,
    levels,
  ].filter(Boolean).join("｜");
}

function latestClose(candles) {
  if (!candles.length) return null;
  const value = Number(candles[candles.length - 1]?.close);
  return Number.isFinite(value) ? value : null;
}

function currentPriceGuide(snapshot, candles) {
  const close = latestClose(candles);
  const primary = snapshot?.classic_patterns?.primary;
  const levels = primary?.levels || {};
  if (close === null || !primary || primary.renderable === false) {
    return {
      state: "price_only",
      label: "仅展示价格走势",
      close,
      message: appState.selectedTimeframe === "1M"
        ? "月线样本不足时，当前先展示价格走势；结构判断等待更多 K 线确认。"
        : "当前没有可用的经典形态边界，先观察价格与摆动结构。",
    };
  }

  const breakout = Number(levels.breakout_confirm);
  const breakdown = Number(levels.breakdown_confirm);
  const invalidation = Number(levels.invalidation);
  const upper = Number(levels.resistance_line ?? levels.resistance ?? levels.upper_boundary ?? levels.breakout_confirm);
  const lower = Number(levels.support_line ?? levels.support ?? levels.lower_boundary ?? levels.breakdown_confirm);
  const direction = primary.direction_bias || "neutral";

  if (Number.isFinite(invalidation) && ((direction === "bullish" && close < invalidation) || (direction === "bearish" && close > invalidation))) {
    return { state: "invalidated", label: "经典图形失效", close, level: invalidation, message: "最新收盘价已经触发经典图形失效位，旧形态不再作为入场依据；综合结论仍会参考摆动结构与市场轮廓。" };
  }
  if (Number.isFinite(breakout) && close > breakout) {
    return { state: "breakout", label: "经典图形上破", close, level: breakout, message: "最新收盘价站上经典图形突破确认位，后续重点观察回踩是否守住突破位；这不等同于综合系统已经转强。" };
  }
  if (Number.isFinite(breakdown) && close < breakdown) {
    return { state: "breakdown", label: "经典图形下破", close, level: breakdown, message: "最新收盘价跌破经典图形下沿确认位，旧区间支撑已被破坏。系统已结合综合结构方向给出具体执行权限判断。" };
  }
  if (Number.isFinite(upper) && Number.isFinite(lower) && close <= upper && close >= lower) {
    return { state: "inside", label: "位于形态内部", close, level: null, message: "价格仍在形态区间内部，需等待收盘突破或跌破后再确认方向。" };
  }
  return { state: "retest", label: "回踩确认中", close, level: Number.isFinite(upper) ? upper : lower, message: "价格已离开主要形态区域，需观察是否回踩边界并重新获得确认。" };
}

function buildCurrentPriceGuideMarkup(guide, textDecision) {
  if (!guide) return "";
  const levelText = Number.isFinite(guide.level) ? `关键位 ${formatNumber(guide.level, 2)}` : "";
  const closeText = Number.isFinite(guide.close) ? `最新收盘 ${formatNumber(guide.close, 2)}` : "";
  const decision = textDecision || {};
  const headline = decision.headline || guide.label || "当前价格位置";
  const message = decision.message || guide.message || "";
  const permissionLabel = decision.permission_label || "";
  const nextTrigger = decision.next_trigger || "";
  const tone = decision.tone || guide.state || "neutral";
  return `
    <div class="structure-price-guide guide-${escapeHtml(tone)}">
      <strong>${escapeHtml(headline)}</strong>
      <span>${escapeHtml([closeText, levelText].filter(Boolean).join(" ｜ "))}</span>
      <p>${escapeHtml(message)}</p>
      ${nextTrigger ? `<p class="muted">下一触发：${escapeHtml(nextTrigger)}</p>` : ""}
      ${permissionLabel ? `<span class="status-chip chip-neutral">执行权限：${escapeHtml(permissionLabel)}</span>` : ""}
      ${decision.dominant_evidence && decision.dominant_evidence.length ? `<p class="muted compact">抵消来源：${escapeHtml(decision.dominant_evidence.join(" + "))}</p>` : ""}
      ${decision.opposing_evidence && decision.opposing_evidence.length ? `<p class="muted compact">负面来源：${escapeHtml(decision.opposing_evidence.join(" + "))}</p>` : ""}
    </div>
  `;
}

function suppressBrokenClassicOverlay(guide) {
  return false;
}

function suppressInvalidatedChannelOverlay(item, guide) {
  if (!["breakout", "breakdown", "invalidated"].includes(guide?.state)) return false;
  const meta = item.meta_json || item.meta || {};
  const patternType = meta.pattern_type || item.pattern_type || item.structure_type;
  if (patternType !== "channel") return false;
  const role = meta.role || "";
  return role === "pattern_region" || role === "upper_boundary" || role === "lower_boundary";
}

function buildGuideMarkerMarkup(guide, scale) {
  if (!Number.isFinite(guide?.level)) return "";
  const y = scale.yForPrice(guide.level);
  if (!Number.isFinite(y)) return "";
  const color = guide.state === "breakout" ? "#0f8f7d" : "#c66622";
  return `
    <line x1="${scale.plot.x}" y1="${y.toFixed(2)}" x2="${(scale.plot.x + scale.plot.width).toFixed(2)}" y2="${y.toFixed(2)}" stroke="${color}" stroke-width="2" stroke-dasharray="7 5" opacity="0.82"></line>
    <text class="structure-svg-axis structure-guide-label" x="${(scale.plot.x + scale.plot.width - 6).toFixed(2)}" y="${(y - 8).toFixed(2)}" text-anchor="end">${escapeHtml(guide.label || "关键位")}</text>
  `;
}

function combinedBiasLabel(overallBias, guide) {
  const base = labelFor(BIAS_LABELS, overallBias);
  if (guide?.state === "breakdown") return `${base} · 图形下破`;
  if (guide?.state === "breakout") return `${base} · 图形上破`;
  if (guide?.state === "invalidated") return `${base} · 图形失效`;
  return base;
}

function classicPatternsToGeometry(classicPatterns) {
  return classicPatternCandidates(classicPatterns).filter((candidate) => candidate?.renderable !== false).flatMap((candidate) => {
    const role = candidate.display_role || "candidate";
    const region = candidate.region || {};
    const fillToken = region.fill_token || "patternNeutral";
    const tooltip = classicPatternTooltip(candidate);
    const regionGeometry = {
      system: "classic",
      kind: "region",
      status: candidate.status,
      visible: true,
      points_json: (region.polygon_points || []).map(classicPatternPoint),
      labels_json: [candidate.display_name || candidate.pattern_type],
      meta_json: {
        role: "pattern_region",
        display_role: role,
        pattern_type: candidate.pattern_type,
        confidence: candidate.confidence,
        fill_token: fillToken,
        fill_alpha: region.fill_alpha,
        boundary_alpha: region.boundary_alpha,
        tooltip,
        visible_by_default: role === "primary",
      },
    };
    const lineGeometry = (candidate.lines || []).map((line) => ({
      system: "classic",
      kind: line.role || "boundary",
      status: candidate.status,
      visible: true,
      points_json: (line.points || []).map(classicPatternPoint),
      labels_json: [line.label || line.role || "边界"],
      meta_json: {
        role: line.role,
        display_role: role,
        pattern_type: candidate.pattern_type,
        confidence: line.confidence ?? candidate.confidence,
        tooltip,
        visible_by_default: role === "primary",
        extend_to_latest: false,
      },
    }));
    return [regionGeometry, ...lineGeometry];
  });
}

function buildOverlayMarkup(geometry, candles, scale) {
  return geometry
    .slice()
    .sort((left, right) => {
      const leftRole = (left.meta_json || {}).role || "";
      const rightRole = (right.meta_json || {}).role || "";
      const layer = (item, role) => {
        if (item.kind === "region" || role === "pattern_region") return 0;
        if (item.system === "classic") return 1;
        if (item.system === "swing") return 2;
        return 3;
      };
      return layer(left, leftRole) - layer(right, rightRole);
    })
    .map((item) => {
      if (item.system === "profile") return "";
      const meta = item.meta_json || {};
      const role = meta.role || "";

      if (item.system === "classic" && (item.kind === "pattern_path" || role === "classic_pattern_path")) {
        return "";
      }

      const isRegion = item.kind === "region" || role === "pattern_region";
      const isClassicBoundary = role === "upper_boundary" || role === "lower_boundary" || role === "neckline" || role === "resistance" || role === "support";
      const isSwing = role === "swing_backbone" || role === "swing_zigzag" || item.kind === "swing_zigzag";
      const isCandidate = (meta.display_role === "candidate" || role === "candidate");

      if (isRegion && !overlayLayerState.fill) return "";
      if (isSwing && !overlayLayerState.swing) return "";
      if (isClassicBoundary && !overlayLayerState.boundary) return "";
      if (isCandidate && !overlayLayerState.candidate) return "";

      let strokeColor = (CHART_SERIES[item.system] || CHART_SERIES.fused).color;
      let strokeWidth = 2.0;
      let strokeDash = "";
      let opacity = 1.0;

      if (role === "swing_backbone" || role === "swing_zigzag" || item.kind === "swing_zigzag") {
        opacity = 0.75;
        strokeWidth = 2.2;
        strokeColor = "#2563eb";
      } else if (role === "swing_live_leg" || item.kind === "swing_live_leg") {
        opacity = 0.62;
        strokeWidth = 2.0;
        strokeColor = "#3b82f6";
        strokeDash = "6 5";
      } else if (role === "neckline") {
        strokeColor = "#e67e22";
        strokeWidth = 2.5;
        strokeDash = "6,3";
      } else if (role === "upper_boundary" || role === "resistance") {
        strokeColor = "#e74c3c";
        strokeWidth = 2.2;
        strokeDash = "5,3";
      } else if (role === "lower_boundary" || role === "support") {
        strokeColor = "#27ae60";
        strokeWidth = 2.2;
        strokeDash = "5,3";
      } else       if (role === "pattern_zone" || item.kind === "zone") {
        opacity = 0.15;
        strokeColor = "#6366f1";
      }

      if (item.kind === "region" || role === "pattern_region") {
        const fillToken = meta.fill_token || "patternNeutral";
        const fillAlpha = Number(meta.fill_alpha ?? 0.12);
        const boundaryAlpha = Number(meta.boundary_alpha ?? 0.85);
        const fillColors = {
          patternBullish: `rgba(39,174,96,${fillAlpha})`,
          patternBearish: `rgba(231,76,60,${fillAlpha})`,
          patternNeutral: `rgba(99,102,241,${fillAlpha})`,
          patternMixed: `rgba(230,126,34,${fillAlpha})`,
        };
        const fillColor = fillColors[fillToken] || fillColors.patternNeutral;
        const points = getGeometryPoints(item);
        const polyPoints = points
          .map((point) => {
            const explicitIndex = Number(point.index);
            const tsValue = point.ts ?? point.timestamp ?? point.ts_open ?? point.time ?? 0;
            const candleIndex = hasExplicitIndex(point)
              ? Math.max(0, Math.min(candles.length - 1, explicitIndex))
              : nearestCandleIndex(candles, tsValue, 0);
            const price = pointPrice(point);
            return { x: scale.xForIndex(candleIndex), y: price === null ? 0 : scale.yForPrice(price) };
          })
          .filter((p) => Number.isFinite(p.x) && Number.isFinite(p.y));
        if (polyPoints.length < 3) return "";
        const polyCoords = polyPoints.map((p) => `${p.x.toFixed(1)},${p.y.toFixed(1)}`).join(" ");
        const title = meta.tooltip || meta.pattern_type || "";
        return `<polygon points="${polyCoords}" fill="${fillColor}" stroke="${strokeColor}" stroke-width="1.2" opacity="${boundaryAlpha}"${strokeDash ? ` stroke-dasharray="${strokeDash}"` : ""}><title>${escapeHtml(title)}</title></polygon>`;
      }

      const points = getGeometryPoints(item);
      let mapped = points
        .map((point, index) => {
          const explicitIndex = Number(point.index);
          const tsValue = point.ts ?? point.timestamp ?? point.ts_open ?? point.time ?? index;
          const candleIndex = hasExplicitIndex(point)
            ? Math.max(0, Math.min(candles.length - 1, explicitIndex))
            : nearestCandleIndex(candles, tsValue, typeof tsValue === 'number' && tsValue < candles.length ? tsValue : index);
          const price = pointPrice(point);
          return { x: scale.xForIndex(candleIndex), y: price === null ? NaN : scale.yForPrice(price) };
        })
        .filter((point) => Number.isFinite(point.x) && Number.isFinite(point.y));
      mapped = extendOverlayToLatestCandle(mapped, role, candles, scale, item);
      if (!mapped.length) return "";

      if (mapped.length === 1) {
        return `<circle cx="${mapped[0].x.toFixed(2)}" cy="${mapped[0].y.toFixed(2)}" r="5" fill="${strokeColor}" stroke="#fff8ed" stroke-width="${strokeWidth}" opacity="${opacity}" />`;
      }

      const path = mapped
        .map((point, index) => `${index === 0 ? "M" : "L"} ${point.x.toFixed(2)} ${point.y.toFixed(2)}`)
        .join(" ");
      const title = meta.tooltip ? `<title>${escapeHtml(meta.tooltip)}</title>` : "";
      return `<path d="${path}" fill="none" stroke="${strokeColor}" stroke-width="${strokeWidth}" opacity="${opacity}"${strokeDash ? ` stroke-dasharray="${strokeDash}"` : ""} stroke-linecap="round" stroke-linejoin="round">${title}</path>`;
    })
    .join("");
}

function buildMarketProfileMarkup(geometry, scale) {
  const profile = geometry.filter((item) => item.system === "profile");
  const levels = [];
  profile.forEach((item) => {
    getGeometryPoints(item).forEach((point) => {
      const price = pointPrice(point);
      if (price !== null) levels.push({ price, label: point.label || point.kind || item.structure_type || "profile" });
    });
  });
  const uniqueLevels = [...new Map(levels.map((item) => [`${item.label}:${item.price}`, item])).values()].slice(0, 8);
  if (!uniqueLevels.length) return "";
  return uniqueLevels
    .map((item) => {
      const y = scale.yForPrice(item.price);
      if (!Number.isFinite(y)) return "";
      const label = String(item.label).toUpperCase().includes("VAH")
        ? "VAH"
        : String(item.label).toUpperCase().includes("VAL")
          ? "VAL"
          : String(item.label).toUpperCase().includes("POC")
            ? "POC"
            : "Profile";
      const opacity = label === "POC" ? 0.85 : 0.5;
      return `
        <line x1="${scale.plot.x}" y1="${y.toFixed(2)}" x2="${(scale.plot.x + scale.plot.width).toFixed(2)}" y2="${y.toFixed(2)}" stroke="${CHART_SERIES.profile.color}" stroke-width="${label === "POC" ? 2.4 : 1.6}" stroke-dasharray="8 7" opacity="${opacity}"></line>
        <text class="structure-svg-axis structure-profile-label" x="${(scale.plot.x + scale.plot.width - 6).toFixed(2)}" y="${(y - 6).toFixed(2)}" text-anchor="end">${escapeHtml(label)}</text>
      `;
    })
    .join("");
}

function renderChart(snapshot, candles) {
  const chartPanel = document.getElementById("structure-chart-panel");
  const chartBias = document.getElementById("structure-chart-bias");
  const contractGeometry = classicPatternsToGeometry(snapshot.classic_patterns);
  const rawGeometry = contractGeometry.length
    ? (snapshot.geometry || []).filter((item) => item.system !== "classic").concat(contractGeometry)
    : (snapshot.geometry || []);
  const geometry = rawGeometry.filter((item) => {
    const confidence = Number(item.meta_json?.confidence ?? item.meta?.confidence ?? 1);
    return matchesSelectedSystem(item.system) && confidence >= state.minConfidence;
  });

  if (!candles.length) {
    chartPanel.className = "structure-chart-panel empty";
    chartPanel.innerHTML = `<div class="empty-state">暂无可绘制的结构图。</div>`;
    return;
  }

  const backendViewport = snapshot.pattern_overlay?.viewport || snapshot.pattern_overlay?.pattern_overlay?.viewport || null;
  const viewport = calculateViewport(candles, geometry, backendViewport);
  const visibleCandles = viewport.candles.length ? viewport.candles : candles;
  const priceGuide = currentPriceGuide(snapshot, visibleCandles);
  chartBias.innerHTML = `<span class="impact-chip impact-${biasTone(snapshot.overall?.overall_bias)}">${escapeHtml(
    combinedBiasLabel(snapshot.overall?.overall_bias, priceGuide),
  )}</span>`;
  const rawVisibleGeometry = visibleGeometryForViewport(geometry, visibleCandles, viewport.offset);
  const visibleGeometry = rawVisibleGeometry.filter((item) => {
    if (suppressInvalidatedChannelOverlay(item, priceGuide)) return false;
    if (!suppressBrokenClassicOverlay(priceGuide) || item.system !== "classic") return true;
    const role = item.meta_json?.role || "";
    return role !== "pattern_region" && role !== "upper_boundary" && role !== "lower_boundary";
  });
  const availability = legendAvailability(visibleGeometry);
  const candlePrices = visibleCandles
    .flatMap((item) => [Number(item.high ?? item.close), Number(item.low ?? item.close), Number(item.close)])
    .filter((value) => Number.isFinite(value));
  if (!candlePrices.length) {
    chartPanel.className = "structure-chart-panel empty";
    chartPanel.innerHTML = `<div class="empty-state">当前 K 线价格无效，暂时无法绘制结构图。</div>`;
    return;
  }
  const candleMin = Math.min(...candlePrices);
  const candleMax = Math.max(...candlePrices);
  const candleSpan = Math.max(candleMax - candleMin, Math.abs(candleMax) * 0.01, 1);
  const overlayMin = candleMin - candleSpan * 0.5;
  const overlayMax = candleMax + candleSpan * 0.5;
  const overlayPrices = visibleGeometry
    .flatMap((item) => getGeometryPoints(item).map(pointPrice))
    .filter((value) => value !== null && value >= overlayMin && value <= overlayMax);
  const prices = [...candlePrices, ...overlayPrices];
  const minPrice = Math.min(...prices);
  const maxPrice = Math.max(...prices);
  const width = 1040;
  const height = 520;
  const scale = buildChartScale(visibleCandles, width, height, minPrice, maxPrice);
  const pricePath = buildLinePath(visibleCandles, scale);
  const overlayMarkup = buildOverlayMarkup(visibleGeometry, visibleCandles, scale);
  const profileMarkup = buildMarketProfileMarkup(visibleGeometry, scale);
  const guideMarkerMarkup = buildGuideMarkerMarkup(priceGuide, scale);
  const overlayCount = visibleGeometry.filter((item) => item.system !== "profile").length;
  const profileCount = visibleGeometry.filter((item) => item.system === "profile").length;
  const classicCount = visibleGeometry.filter((item) => item.system === "classic").length;
  const coverageLabel = viewport.coverage ? `${(viewport.coverage * 100).toFixed(1)}%` : "-";

  chartPanel.className = "structure-chart-panel";
  chartPanel.innerHTML = `
    <svg viewBox="0 0 ${width} ${height}" class="structure-chart-svg" role="img" aria-label="形态结构图">
      ${buildAxisMarkup(visibleCandles, scale)}
      ${buildLegendMarkup(availability)}
      <path d="${pricePath}" fill="none" stroke="${CHART_SERIES.price.color}" stroke-width="${CHART_SERIES.price.width}" stroke-linecap="round" stroke-linejoin="round"></path>
      ${profileMarkup}
      ${overlayMarkup}
      ${guideMarkerMarkup}
    </svg>
    ${buildCurrentPriceGuideMarkup(priceGuide, snapshot.overall?.text_decision)}
    ${buildLayerToggleMarkup()}
    <div class="structure-chart-meta">
      <span>快照版本：${escapeHtml(snapshot.snapshot_version || "-")}</span>
      <span>视图：${escapeHtml(VIEWPORT_LABELS[state.viewMode] || VIEWPORT_LABELS.focus)}</span>
      <span>可见 K 线：${visibleCandles.length}/${candles.length}</span>
      <span>结构线：${overlayCount}</span>
      <span>图形：${classicCount}</span>
      <span>市场轮廓：${profileCount ? "POC/VAH/VAL" : "未绘制"}</span>
      <span>覆盖率：${coverageLabel}</span>
      ${viewport.autoFocused ? `<span>已自动聚焦：当前形态仅覆盖完整快照的 ${coverageLabel}</span>` : ""}
    </div>
  `;
}

function renderSummary(snapshot) {
  const overall = snapshot.overall || {};
  const systems = Array.isArray(snapshot.systems) ? snapshot.systems : [];
  const panel = document.getElementById("structure-summary-panel");
  const orderedSystems = ["swing", "classic", "profile"].map((key) => systems.find((item) => item.system === key) || null);

  panel.innerHTML = `
    <div class="structure-summary-grid">
      <article class="structure-summary-tile structure-summary-overall">
        <div class="structure-summary-head">
          <div>
            <p class="eyebrow">综合判断</p>
            <h3 class="structure-summary-title">${escapeHtml(labelFor(BIAS_LABELS, overall.overall_bias))}</h3>
          </div>
          ${overall.conflict_state ? `<div class="warning-banner structure-mini-warning">系统之间存在方向冲突，结论已做降级处理。</div>` : ""}
        </div>
        <div class="metric-grid metric-grid-compact structure-summary-metrics">
          <div class="metric-box"><span>综合分数</span><strong>${escapeHtml(formatNumber(overall.overall_score ?? overall.score ?? 0, 2))}</strong></div>
          <div class="metric-box"><span>综合置信度</span><strong>${escapeHtml(formatNumber(overall.overall_confidence ?? overall.confidence ?? 0, 2))}</strong></div>
          <div class="metric-box"><span>市场状态</span><strong>${escapeHtml(labelFor(REGIME_LABELS, overall.regime))}</strong></div>
          <div class="metric-box"><span>权重模板</span><strong>${escapeHtml(overall.weight_template || "-")}</strong></div>
        </div>
        ${
          overall.meaning
            ? `<div class="structure-copy structure-summary-copy">
                <p>${escapeHtml(overall.meaning)}</p>
                ${overall.need_confirmation ? `<p>${escapeHtml(overall.need_confirmation)}</p>` : ""}
                ${overall.invalidation ? `<p>${escapeHtml(overall.invalidation)}</p>` : ""}
                ${overall.suggested_mode ? `<p>${escapeHtml(overall.suggested_mode)}</p>` : ""}
              </div>`
            : ""
        }
      </article>

      ${orderedSystems
        .map((system) => {
          if (!system) {
            return `
              <article class="structure-summary-tile structure-system-merge">
                <div class="structure-system-merge-head">
                  <div>
                    <p class="eyebrow">系统结果</p>
                    <strong>待补齐</strong>
                  </div>
                  ${statusChip("快照补全中")}
                </div>
                <div class="structure-inline-metrics">
                  <span>有效分 -</span>
                  <span>权重 -</span>
                  <span>贡献 -</span>
                  <span>证据 -</span>
                </div>
                <ul class="plain-list compact">
                  <li>该系统卡片暂未落入当前快照，页面会自动尝试补刷新。</li>
                </ul>
              </article>
            `;
          }
          const reasons = normalizeTextList(system.top_reasons || system.drivers_json).slice(0, 2);
          return `
            <article class="structure-summary-tile structure-system-merge">
              <div class="structure-system-merge-head">
                <div>
                  <p class="eyebrow">${escapeHtml(labelFor(SYSTEM_LABELS, system.system))}</p>
                  <strong class="structure-system-title">${escapeHtml(labelFor(BIAS_LABELS, system.direction || system.bias))}</strong>
                </div>
                ${statusChip(labelFor(STATUS_LABELS, system.status || "confirmed"))}
              </div>
              <div class="structure-inline-metrics">
                <span>有效分 ${escapeHtml(formatNumber(system.effective_score ?? system.score ?? 0, 2))}</span>
                <span>权重 ${escapeHtml(formatNumber(system.weight ?? 0, 2))}</span>
                <span>贡献 ${escapeHtml(formatNumber(system.weighted_contribution ?? 0, 2))}</span>
                <span>证据 ${escapeHtml(String(system.evidence_count ?? 0))}</span>
              </div>
              <ul class="plain-list compact">
                ${(reasons.length ? reasons : ["暂无额外说明"]).map((item) => `<li>${escapeHtml(item)}</li>`).join("")}
              </ul>
            </article>
          `;
        })
        .join("")}
    </div>
  `;
}

function renderCurrentStructures(items) {
  if (!items.length) return `<div class="empty-state">当前没有活跃结构。</div>`;
  return `
    <div class="structure-detail-list">
      ${items
        .map((item) => {
          const reasons = normalizeTextList(item.reasoning_json).slice(0, 2);
          return `
            <article class="structure-mini-card">
              <div class="list-card-head">
                <strong>${escapeHtml(item.display_name || item.structure_type || "-")}</strong>
                ${statusChip(labelFor(STATUS_LABELS, item.lifecycle_status || item.status || "confirmed"))}
              </div>
              <p>${escapeHtml(item.summary || "暂无摘要说明。")}</p>
              ${
                reasons.length
                  ? `<ul class="plain-list compact">${reasons.map((reason) => `<li>${escapeHtml(reason)}</li>`).join("")}</ul>`
                  : ""
              }
            </article>
          `;
        })
        .join("")}
    </div>
  `;
}

function renderEventHistory(items) {
  if (!items.length) return `<div class="empty-state">近期没有结构事件。</div>`;
  return `
    <div class="structure-detail-list">
      ${items
        .slice(0, 8)
        .map(
          (item) => `
            <article class="structure-mini-card">
              <div class="list-card-head">
                <strong>${escapeHtml(labelFor(SYSTEM_LABELS, item.system))}</strong>
                ${statusChip(labelFor(STATUS_LABELS, item.status || "confirmed"))}
              </div>
              <p>${escapeHtml(item.event_name || "-")}</p>
              <small>${escapeHtml(formatDateTime(item.event_ts))}</small>
            </article>
          `,
        )
        .join("")}
    </div>
  `;
}

function renderAlertHistory(items) {
  if (!items.length) return `<div class="empty-state">近期没有结构告警。</div>`;
  return `
    <div class="structure-detail-list">
      ${items
        .slice(0, 6)
        .map(
          (item) => `
            <article class="structure-mini-card">
              <div class="list-card-head">
                <strong>${escapeHtml(item.title || item.alert_name || "-")}</strong>
                ${statusChip(labelFor(STATUS_LABELS, item.severity || "medium"))}
              </div>
              <p>${escapeHtml(item.message || "暂无详细说明。")}</p>
              <small>${escapeHtml(formatDateTime(item.triggered_at))}</small>
            </article>
          `,
        )
        .join("")}
    </div>
  `;
}

function renderDiagnostics(snapshot, diagnostics) {
  const effectiveDiagnostics = diagnostics || snapshot.diagnostics || {};
  const notes = normalizeTextList(effectiveDiagnostics.notes);
  return `
    <article class="structure-detail-section structure-detail-block is-hidden">
      <div class="list-card-head">
        <strong>检测诊断</strong>
        ${statusChip("只读快照")}
      </div>
      <div class="structure-inline-metrics">
        <span>加载 K 线 ${escapeHtml(String(effectiveDiagnostics.candles_loaded ?? 0))}</span>
        <span>几何数量 ${escapeHtml(String(effectiveDiagnostics.geometry_count ?? 0))}</span>
        <span>事件数量 ${escapeHtml(String(effectiveDiagnostics.event_count ?? 0))}</span>
        <span>告警数量 ${escapeHtml(String(effectiveDiagnostics.alert_count ?? 0))}</span>
      </div>
      ${
        notes.length
          ? `<ul class="plain-list compact">${notes.slice(0, 3).map((note) => `<li>${escapeHtml(note)}</li>`).join("")}</ul>`
          : `<p class="structure-copy">当前快照未返回额外诊断备注。</p>`
      }
      <p class="structure-copy">回测时请只使用已确认的 pivot、breakout 与 value area 信号，避免把候选形态直接当成最终结论。</p>
    </article>
  `;
}

function renderDetailPanel(payload) {
  const detailPanel = document.getElementById("structure-detail-panel");
  const systemFilter = state.selectedSystem;
  const snapshot = payload.snapshot || {};
  const activeItems = (snapshot.active_items || []).filter((item) => systemFilter === "all" || item.system === systemFilter);
  const events = (payload.events || []).filter((item) => systemFilter === "all" || item.system === systemFilter);
  const alerts = (payload.alerts || []).filter((item) => {
    if (systemFilter === "all") return true;
    const system = item.event_payload_json?.system || item.event_payload_json?.event?.system;
    return !system || system === systemFilter;
  });

  detailPanel.innerHTML = `
    <article class="structure-detail-section structure-detail-block">
      <div class="list-card-head">
        <strong>当前结构</strong>
        ${statusChip(systemFilter === "all" ? "全部系统" : labelFor(SYSTEM_LABELS, systemFilter))}
      </div>
      ${renderCurrentStructures(activeItems)}
    </article>

    <article class="structure-detail-section structure-detail-block">
      <div class="list-card-head">
        <strong>近期事件</strong>
        ${statusChip(`${events.length} 条`)}
      </div>
      ${renderEventHistory(events)}
    </article>

    <article class="structure-detail-section structure-detail-block">
      <div class="list-card-head">
        <strong>告警历史</strong>
        ${statusChip(`${alerts.length} 条`)}
      </div>
      ${renderAlertHistory(alerts)}
    </article>

  `;
  detailPanel.querySelectorAll(".structure-detail-section").forEach((section, index) => {
    if (index > 0) section.classList.add("is-hidden");
  });
}

function renderFromBundle(bundle) {
  if (!bundle) {
    return;
  }
  updateChartTitle();
  state.bundle = bundle;
  const candles = normalizeCandles(bundle.candles);
  const snapshot = bundle.snapshot || null;
  if (!snapshot) {
    const chartPanel = document.getElementById("structure-chart-panel");
    const summaryPanel = document.getElementById("structure-summary-panel");
    const detailPanel = document.getElementById("structure-detail-panel");
    if (candles.length) {
      const fallbackSnapshot = {
        active_items: [],
        systems: [],
        geometry: [],
        diagnostics: {},
        overall: {
          overall_bias: "uncertain",
          score: 0,
          confidence: 0,
          meaning: appState.selectedTimeframe === "1M"
            ? "月线样本不足，当前仅展示价格走势；结构判断等待更多 K 线。"
            : "结构快照暂不可用，当前先展示价格走势。",
        },
        snapshot_version: `${appState.selectedTimeframe}-price-only`,
      };
      renderChart(fallbackSnapshot, candles);
      renderSummary(fallbackSnapshot);
      if (detailPanel) {
        detailPanel.innerHTML = `
          <article class="structure-detail-section structure-detail-block">
            <div class="list-card-head">
              <strong>检测诊断</strong>
              ${statusChip("价格降级图")}
            </div>
            <p class="structure-copy">${escapeHtml(bundle.status_message || fallbackSnapshot.overall.meaning)}</p>
          </article>
        `;
      }
      renderStatus(bundle.status_message || fallbackSnapshot.overall.meaning, bundle.cache_state === "missing" ? "warning" : "neutral");
      return;
    }
    if (chartPanel) {
      chartPanel.className = "structure-chart-panel empty";
      chartPanel.innerHTML = `<div class="empty-state">当前还没有可用的结构快照，请先手动刷新。</div>`;
    }
    if (summaryPanel) {
      summaryPanel.innerHTML = `
        <article class="structure-summary-tile">
          <p class="eyebrow">缓存状态</p>
          <h3>${escapeHtml(bundle.cache_state === "missing" ? "缺少快照" : "暂无结构结果")}</h3>
          <p class="structure-copy">${escapeHtml(bundle.status_message || "当前仅能展示缓存行情，请手动刷新结构快照。")}</p>
        </article>
      `;
    }
    if (detailPanel) {
      detailPanel.innerHTML = `
        <article class="structure-detail-section structure-detail-block">
          <div class="list-card-head">
            <strong>检测诊断</strong>
            ${statusChip("只读缓存")}
          </div>
          <p class="structure-copy">${escapeHtml(bundle.status_message || "尚未生成结构快照。")}</p>
        </article>
      `;
    }
    renderStatus(bundle.status_message || "当前尚无结构快照，请手动刷新。", bundle.cache_state === "missing" ? "warning" : "neutral");
    return;
  }
  const safeSnapshot = {
    active_items: [],
    systems: [],
    geometry: [],
    diagnostics: {},
    overall: {},
    ...snapshot,
  };
  renderChart(safeSnapshot, candles);
  renderSummary(safeSnapshot);
  renderDetailPanel({
    snapshot: safeSnapshot,
    events: bundle.events || [],
    alerts: bundle.alerts || [],
    diagnostics: bundle.diagnostics,
  });
  const lastCandleTs = candles[candles.length - 1]?.ts_open;
  const scopeLabel = state.selectedSystem === "all" ? "综合判断" : labelFor(SYSTEM_LABELS, state.selectedSystem);
  renderStatus(
    bundle.status_message ||
      `快照时间：${formatDateTime(safeSnapshot.generated_at || safeSnapshot.overall?.last_updated_at)} ｜ 最新价格时间：${formatDateTime(lastCandleTs)} ｜ 当前范围：${scopeLabel}`,
    bundle.is_stale ? "warning" : "neutral",
  );
}

function renderStatus(message, tone = "neutral") {
  const el = document.getElementById("structure-statusbar");
  el.innerHTML = message ? `<div class="status-banner status-${tone}">${escapeHtml(message)}</div>` : "";
}

function updateChartTitle() {
  const titleNode = document.querySelector(".structure-main-head h2");
  if (!titleNode) return;
  const instrument = getInstrumentMeta(appState.selectedInstrumentId);
  titleNode.textContent = `${instrument.code} · ${appState.selectedTimeframe}`;
}

function attachEvents(loadData) {
  const handlers = [];
  const listen = (selector, eventName, handler) => {
    const node = document.querySelector(selector);
    if (!node) return;
    node.addEventListener(eventName, handler);
    handlers.push(() => node.removeEventListener(eventName, handler));
  };

  listen("#structure-instrument", "change", async (event) => {
    appState.selectedInstrumentId = event.target.value;
    persistState();
    await loadData();
  });

  listen("#structure-timeframe", "change", async (event) => {
    appState.selectedTimeframe = event.target.value;
    persistState();
    await loadData();
  });

  listen("#structure-system", "change", async (event) => {
    state.selectedSystem = event.target.value;
    renderFromBundle(state.bundle);
  });

  listen("#structure-confidence", "change", async (event) => {
    state.minConfidence = Number(event.target.value || 0);
    renderFromBundle(state.bundle);
  });

  listen("#structure-viewmode", "change", async (event) => {
    state.viewMode = VIEWPORT_LABELS[event.target.value] ? event.target.value : "focus";
    localStorage.setItem("structureViewportMode", state.viewMode);
    renderFromBundle(state.bundle);
  });

  listen("#structure-refresh", "click", async () => {
    const button = document.getElementById("structure-refresh");
    if (button) {
      button.disabled = true;
      button.textContent = "生成中";
    }
    try {
      renderStatus("正在拉取 K 线并生成结构快照", "loading");
      invalidateCache("/marketdata/candles");
      invalidateCache("/market-prices/marks/latest");
      await api.refreshStructure(appState.selectedInstrumentId, appState.selectedTimeframe);
      await loadData({ forceRefresh: true });
    } finally {
      if (button) {
        button.disabled = false;
        button.textContent = "手动刷新快照";
      }
    }
  });

  return () => handlers.forEach((dispose) => dispose());
}

export async function renderStructure() {
  renderShell();
  let disposed = false;
  let activeController = null;
  const detachEvents = attachEvents(loadData);

  async function loadData({ forceRefresh = false } = {}) {
    const requestToken = ++state.requestToken;
    const instrumentId = appState.selectedInstrumentId;
    const timeframe = appState.selectedTimeframe;
    const limit = timeframe === "1h" ? 220 : 180;

    updateChartTitle();
    renderStatus("正在加载结构快照…", "info");

    try {
      activeController?.abort();
      activeController = new AbortController();
      let bundle = await api.getStructureBundle(instrumentId, timeframe, {
        includeGeometry: true,
        candlesLimit: limit,
        force: forceRefresh,
        signal: activeController.signal,
      });

      const recoveryKey = `${instrumentId}:${timeframe}`;
      const candles = normalizeCandles(bundle.candles);
      if (
        !forceRefresh &&
        !state.recoveryKeys.has(recoveryKey) &&
        (bundle.cache_state === "missing" || candles.length === 0)
      ) {
        state.recoveryKeys.add(recoveryKey);
        renderStatus("正在拉取 K 线并生成结构快照", "loading");
        await scheduleIdlePrecompute({
          page: "market-structure",
          instrumentId,
          timeframe: timeframe === "1M" ? "30d" : timeframe,
          reason: "structure_bundle_read",
          priority: 3,
        });
      }

      if (disposed || requestToken !== state.requestToken) return;
      renderFromBundle(bundle);
    } catch (error) {
      if (error?.name === "AbortError" || error?.name === "TimeoutError") {
        return;
      }
      if (disposed) return;

      console.error("structure:renderer:error", error);
      document.getElementById("structure-chart-panel").className = "structure-chart-panel error";
      document.getElementById("structure-chart-panel").innerHTML = `<div class="error-state">形态结构加载失败。<br>${escapeHtml(String(error.message || error))}</div>`;
      document.getElementById("structure-summary-panel").innerHTML = `
        <article class="structure-summary-tile">
          <p class="eyebrow">加载失败</p>
          <h3>结构快照暂时不可用</h3>
          <p class="structure-copy">${escapeHtml(String(error.message || error))}</p>
        </article>
      `;
      document.getElementById("structure-detail-panel").innerHTML = `
        <article class="list-card structure-detail-block">
          <strong>数据暂不可用</strong>
          <p class="structure-copy">请稍后重试，或点击“手动刷新快照”。</p>
        </article>
      `;
      renderStatus("结构快照读取失败，请稍后重试。", "danger");
    }
  }

  await loadData();

  return () => {
    disposed = true;
    detachEvents?.();
  };
}
