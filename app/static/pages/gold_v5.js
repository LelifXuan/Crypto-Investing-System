// gold-allocation v5 frontend module.
// Goal: visual alignment with the analysis page (market-analysis).
// Backend payload shape unchanged: /api/v1/gold/workbench returns GoldWorkbenchRead
// (see app/schemas/gold_workbench.py:53 and gold.py:300-502).
//
// This module never mutates state outside page-root, never emits inline
// style attributes on elements, and never emits emoji codepoints
// (static test in tests/test_gold_v5_frontend_static.py).
//
// V5 status-mapping philosophy: status codes drive both chip tone and human label,
// mirroring analysis.js' signalTone/signalLabel without modifying the shared core
// (signalTone / signalLabel live inside analysis.js and are not exported).
//
// statusTone(code) is the V5 chip-tone helper used by chipForStatus(). It
// replaces V4's hard-coded chip-warning ternary on the governance strip.

import { api } from "../core/api.js";
import { escapeHtml, formatNumber, impactChip, setRoot } from "../core/dom.js";
import { barDataset, destroyChartsForPage, lineDataset, renderChart } from "../ui/charts.js";

const CHART_PREFIX = "gold-chart-";

let controller = null;
let latestData = null;

// ----- Status-code tone mapping (V5 replaces V4's hard-coded chip-neutral / chip-warning).
const STATUS_TONE_MAP = {
  EXECUTE: "bullish",
  READY_FIXED_ADD: "bullish",
  STRATEGIC_WITHIN_RANGE: "bullish-soft",
  STRATEGIC_UNDERWEIGHT: "neutral",
  STRATEGIC_OVERWEIGHT_NO_SELL: "neutral",
  WAIT_DRAWDOWN: "neutral",
  SETUP_FORMING: "neutral",
  COOLDOWN: "neutral",
  ALREADY_EXECUTED: "neutral",
  PAUSED_BY_EXPLICIT_PORTFOLIO_POLICY: "warning",
  LIQUIDITY_SHOCK: "warning",
  BLOCKED_INVALID_AMOUNT: "bearish-soft",
  BLOCKED_INVALID_FIXED_AMOUNT: "bearish-soft",
  BLOCKED_STALE_QUOTE: "bearish-soft",
  BLOCKED_INSUFFICIENT_CASH: "bearish-soft",
  BLOCKED_OVERWEIGHT: "bearish-soft",
  BLOCKED_LIQUIDITY_SHOCK: "bearish",
  DATA_DEGRADED: "bearish",
  DEFAULT: "neutral",
};

function toneForStatus(code) {
  return STATUS_TONE_MAP[code] || STATUS_TONE_MAP.DEFAULT;
}

function labelForStatus(code) {
  const m = {
    EXECUTE: "建议执行",
    READY_FIXED_ADD: "建议加仓",
    STRATEGIC_WITHIN_RANGE: "区间内",
    STRATEGIC_UNDERWEIGHT: "低于目标",
    STRATEGIC_OVERWEIGHT_NO_SELL: "高于上限",
    WAIT_DRAWDOWN: "等待回撤",
    SETUP_FORMING: "确认中",
    COOLDOWN: "冷却中",
    ALREADY_EXECUTED: "今日已执行",
    PAUSED_BY_EXPLICIT_PORTFOLIO_POLICY: "策略暂停",
    LIQUIDITY_SHOCK: "流动性冲击",
    BLOCKED_INVALID_AMOUNT: "配置无效",
    BLOCKED_INVALID_FIXED_AMOUNT: "配置无效",
    BLOCKED_STALE_QUOTE: "行情过期",
    BLOCKED_INSUFFICIENT_CASH: "现金不足",
    BLOCKED_OVERWEIGHT: "仓位已满",
    BLOCKED_LIQUIDITY_SHOCK: "流动冲击阻断",
    DATA_DEGRADED: "数据降级",
  };
  return m[code] || "—";
}

function chipForStatus(code, tooltip = "") {
  return impactChip(toneForStatus(code), tooltip, labelForStatus(code));
}

// ----- Governance freshness mapping (source_manifest freshness_state → label/text).
function labelForFreshness(state) {
  switch (state) {
    case "fresh":
      return "已就绪";
    case "stale":
      return "已过期";
    case "degraded":
      return "降级中";
    case "missing":
      return "数据缺失";
    default:
      return "未知";
  }
}

// ----- Numeric helpers
function money(v, d) {
  const n = Number(v);
  return Number.isFinite(n) ? `${formatNumber(n, d || 0)} 元` : "—";
}

// ----- Subtitle / "macro scenario" Chinese label.
function scenarioLabel(active) {
  const m = {
    STRATEGIC_UNDERWEIGHT: "低于目标,触发基础定投",
    STRATEGIC_WITHIN_RANGE: "区间内,按策略执行",
    STRATEGIC_OVERWEIGHT_NO_SELL: "高于上限,默认不卖出",
    MACRO_NEUTRAL: "宏观中性,维持既定纪律",
    DATA_DEGRADED: "数据降级,等待回填",
    setup_required: "策略未配置",
  };
  return m[active] || "宏观待评估";
}

// ----- Render functions ----------------------------------------------------

function renderHero(data) {
  // Backend payload (see gold.py:466-486) ships market_scenarios as both
  //   active_scenario   (string — primary label)
  //   active_scenarios  (string[] — full ordered list, may contain extras
  //                       like LIQUIDITY_SHOCK that override the primary)
  // We read both: active_scenario drives the subtitle; active_scenarios
  // powers the optional LIQUIDITY_SHOCK chip.
  const activeList = data?.market_scenarios?.active_scenarios || [];
  const active =
    activeList[0] || data?.refresh_state === "setup_required"
      ? "setup_required"
      : null;
  const setupRequired = data?.snapshot?.status === "setup_required";
  // An empty active_scenarios with a healthy snapshot means "no special macro
  // scenario right now" — that is neutral, not degraded. Only fall back to
  // DATA_DEGRADED when the snapshot itself is not healthy (error / missing).
  const snapshotOk = data?.snapshot?.status === "ok";
  const subtitle = setupRequired
    ? "请先在策略页配置组合与执行纪律。"
    : `宏观判断: ${scenarioLabel(active || (snapshotOk ? "MACRO_NEUTRAL" : "DATA_DEGRADED"))}`;
  const shock = activeList.includes("LIQUIDITY_SHOCK");

  return `
    <section class="gold-hero">
      <article class="card analysis-hero-card">
        <div class="card-head-inline">
          <div>
            <p class="eyebrow">GOLD ALLOCATION</p>
            <h1 class="gold-page-h1">黄金配置 Workbench</h1>
            <p class="gold-page-sub">${escapeHtml(subtitle)}</p>
            ${
              shock
                ? '<p class="gold-page-sub">' +
                  impactChip("warning", "流动性冲击下固定加仓已阻断", "流动性冲击") +
                  "</p>"
                : ""
            }
          </div>
          <button class="primary-button compact" id="gold-refresh">刷新 XAUT</button>
        </div>
      </article>
    </section>
  `;
}

function renderChartCard(chartId, eyebrow, title) {
  return `
    <article class="card gold-chart-card" id="${chartId}">
      <div class="card-head-inline">
        <p class="eyebrow">${escapeHtml(eyebrow)}</p>
        <p class="gold-card-title">${escapeHtml(title)}</p>
      </div>
      <div class="chart-wrap">
        <canvas id="gold-canvas-${chartId.replace(CHART_PREFIX, "")}"></canvas>
      </div>
    </article>
  `;
}

function renderChartGrid() {
  return `
    <section class="gold-chart-grid">
      ${renderChartCard("gold-chart-price", "TREND", "EMA 均线结构")}
      ${renderChartCard("gold-chart-vegas", "STRUCTURE", "VEGAS 通道")}
      ${renderChartCard("gold-chart-macd", "MOMENTUM", "MACD")}
      ${renderChartCard("gold-chart-volume", "VOLUME", "成交量")}
      ${renderChartCard("gold-chart-bollinger", "VOLATILITY", "BOLL · %B(20,2)")}
      ${renderChartCard("gold-chart-rsi", "MOMENTUM", "RSI(14)")}
    </section>
  `;
}

// ----- Spot DCA — top-down refactor (4 stacked blocks per spec §2.3) -------

function renderWeightRow(strategic) {
  const state = strategic?.allocation_state || "DATA_DEGRADED";
  const cur = Number(strategic?.current_weight);
  const max = Number(strategic?.target_max);
  const fill = Number.isFinite(cur) && Number.isFinite(max) && max > 0 ? Math.min(100, (cur / max) * 100) : 0;
  // We cannot inject <script> via innerHTML — browsers won't execute it.
  // Encode the fill percentage into a data-fill attribute and let the
  // post-mount pass in renderGoldV5() apply it via CSS custom property.
  return `
    <div class="gold-weight-row">
      <div class="gold-card-title">当前 / 目标</div>
      <div class="gold-weight-bar"><div class="gold-weight-fill" data-fill="${fill.toFixed(1)}"></div></div>
      <span class="chip">${chipForStatus(state, "策略权重带:低于区间触发基础定投")}</span>
    </div>
  `;
}

function renderFormulaBox(base, dip) {
  // V4 had inline font-size:10px labels; V5 spec bumps to 13/18 (styles.css .gold-formula-item).
  const baseAmount = base?.amount;
  const dipAmount = dip?.amount;
  return `
    <div class="gold-formula-box">
      <div class="gold-formula-item"><span>基础定投</span><b>${money(baseAmount)}</b></div>
      <div class="gold-formula-item"><span>回撤加仓</span><b>${money(dipAmount)}</b></div>
    </div>
  `;
}

function renderGateRow(num, label, chipCode, hint) {
  return `
    <div class="gold-gate-row">
      <div>
        <span class="gold-gate-num">${num}</span>
        <span class="gold-card-title">${escapeHtml(label)}</span>
      </div>
      <span class="chip">${chipForStatus(chipCode, hint)}</span>
    </div>
  `;
}

function renderRecommendRow(base, dip) {
  const code = base?.status === "EXECUTE"
    ? "EXECUTE"
    : (dip?.status === "READY_FIXED_ADD" ? "READY_FIXED_ADD" : base?.status);
  return `
    <div class="gold-recommend-row">
      <div>
        <p class="eyebrow">TODAY</p>
        <span class="gold-recommend-label">今日建议金额</span>
        <div class="gold-recommend-amount">${money(base?.amount)}</div>
      </div>
      <span class="chip">${chipForStatus(code, "今日最优基础动作")}</span>
    </div>
  `;
}

function renderSpotDca(data) {
  const strategic = data?.strategic_allocation || {};
  const base = data?.base_dca || {};
  const dip = data?.dip_add || {};
  const drawdownCode = dip?.status || "WAIT_DRAWDOWN";
  // Macro/liquidity gate: explicit LIQUIDITY_SHOCK from market_scenarios
  // wins; otherwise we use base_dca.status as a proxy for "macro permits
  // execution". Falling through to DATA_DEGRADED (when both are missing)
  // is intentionally conservative — false-positive here would let a setup
  // with no data through to a chip-event "正常" tone, which is misleading.
  const macroCode = data?.market_scenarios?.active_scenarios?.includes("LIQUIDITY_SHOCK")
    ? "LIQUIDITY_SHOCK"
    : data?.base_dca?.status || "DATA_DEGRADED";
  return `
    <article class="card gold-workbench-card gold-spot-dca">
      <div class="card-head-inline">
        <p class="eyebrow">SPOT DCA</p>
        <p class="gold-card-title">战略配置与今日动作</p>
      </div>
      <div class="gold-dca-overview">
        ${renderRecommendRow(base, dip)}
        ${renderWeightRow(strategic)}
      </div>
      <div class="gold-dca-detail-grid">
        ${renderFormulaBox(base, dip)}
        <div class="gold-dca-gates">
          ${renderGateRow("①", "回撤确认", drawdownCode, "60 日回撤阈值与连续确认门禁")}
          ${renderGateRow("②", "宏观门禁", macroCode, "宏观与流动性风险阻断基础定投")}
        </div>
      </div>
    </article>
  `;
}

// ----- Contract Reference — top-down refactor (3 blocks per spec §2.4) -----

function miniCard(label, value, kind = "raw") {
  // kind: "price" → 2dp · "ratio" → percent with 2dp (+/-, signed)
  //       "percent" → 2dp no sign · "integer" → 0dp · "raw" → unchanged.
  // Numbers from the backend arrive as decimal strings (drawdown,
  // ema20_distance) or float dumps (funding rate, oi_change_4w). The
  // old implementation dumped the raw string into the DOM, which
  // produced ``-0.004886184782353185`` on screen — readable as a
  // typo, not as a percent. We coerce to Number and pick a sensible
  // precision per metric family. Strings we cannot parse fall back
  // to the original rendering.
  const present = value != null && value !== "" && value !== "数据积累中";
  const cls = present ? "is-effective" : "is-insufficient";
  let display;
  if (!present) {
    display = "数据积累中";
  } else {
    const num = Number(value);
    if (!Number.isFinite(num)) {
      display = String(value);
    } else if (kind === "price") {
      display = formatNumber(num, 2);
    } else if (kind === "ratio") {
      display = `${num >= 0 ? "+" : ""}${formatNumber(num * 100, 2)}%`;
    } else if (kind === "percent") {
      display = `${formatNumber(num * 100, 2)}%`;
    } else if (kind === "integer") {
      display = formatNumber(num, 0);
    } else {
      display = String(value);
    }
  }
  return `
    <div class="gold-mini-card ${cls}">
      <p class="eyebrow">${escapeHtml(label)}</p>
      <strong>${escapeHtml(display)}</strong>
    </div>
  `;
}

function renderPriceBanner(tech) {
  return `
    <div class="gold-price-banner">
      <div class="gold-price-value">${tech?.price != null ? formatNumber(Number(tech.price), 2) : "—"}</div>
      <span class="chip">${impactChip(
        tech?.updated_at ? "bullish-soft" : "bearish-soft",
        tech?.updated_at ? "最新行情已就绪" : "行情过期",
        tech?.updated_at ? "已收盘" : "等待"
      )}</span>
    </div>
  `;
}

function renderContractRef(data) {
  const tech = data?.technical_summary || {};
  const deriv = data?.derivatives || {};
  return `
    <article class="card gold-workbench-card gold-contract-ref">
      <div class="card-head-inline">
        <p class="eyebrow">CONTRACT REFERENCE</p>
        <p class="gold-card-title">合约参考</p>
      </div>
      ${renderPriceBanner(tech)}
      <div class="gold-mini-grid">
        ${miniCard("MA50", tech?.ma50, "price")}
        ${miniCard("MA200 / SMA200", tech?.sma200, "price")}
        ${miniCard("60 日回撤", tech?.drawdown_60d, "ratio")}
        ${miniCard("EMA20 距离", tech?.ema20_distance, "ratio")}
        ${miniCard("OI 4 周变化", deriv?.oi_change_4w, "ratio")}
        ${miniCard("资金费率", deriv?.funding_rate, "ratio")}
        ${miniCard("COT 净投机", deriv?.cot_net_spec_percentile, "raw")}
        ${miniCard("未平仓", deriv?.open_interest, "integer")}
      </div>
    </article>
  `;
}

// ----- Governance — compact source ledger --------------------------------

function formatSourceAge(seconds) {
  const value = Number(seconds);
  if (!Number.isFinite(value) || value < 0) return "更新时间待确认";
  if (value < 60) return `${Math.round(value)} 秒前更新`;
  if (value < 3600) return `${Math.round(value / 60)} 分钟前更新`;
  if (value < 86400) return `${Math.round(value / 3600)} 小时前更新`;
  return `${Math.round(value / 86400)} 天前更新`;
}

function governanceSourceItem(manifest, label, sourceKey) {
  const entry = (manifest || []).find((s) => s?.source_key === sourceKey);
  const state = entry?.freshness_state || "missing";
  return `
    <article class="gold-governance-item" data-state="${escapeHtml(state)}">
      <div class="gold-governance-label">
        <span class="gold-governance-dot" aria-hidden="true"></span>
        <span>${escapeHtml(label)}</span>
      </div>
      <strong>${escapeHtml(entry ? labelForFreshness(state) : "未配置")}</strong>
      <small>${escapeHtml(entry ? formatSourceAge(entry.age_seconds) : "尚未接入数据源")}</small>
    </article>
  `;
}

function governanceSnapshotItem(observed) {
  const ready = !!observed && observed !== "—";
  return `
    <article class="gold-governance-item gold-governance-snapshot" data-state="${ready ? "fresh" : "missing"}">
      <div class="gold-governance-label">
        <svg viewBox="0 0 16 16" aria-hidden="true"><circle cx="8" cy="8" r="5.5"/><path d="M8 4.5v3.8l2.4 1.4"/></svg>
        <span>快照时间</span>
      </div>
      <strong>${escapeHtml(ready ? observed : "等待快照")}</strong>
      <small>${ready ? "UTC · 当前研究快照" : "尚未生成有效快照"}</small>
    </article>
  `;
}

function renderGovernance(data) {
  const manifest = data?.source_manifest || [];
  const observed = data?.snapshot?.observed_at || "—";
  const sourceKeys = ["gold_policy", "gold_spot_quote", "gold_derivatives"];
  const readyCount = sourceKeys.filter((sourceKey) => (
    manifest.find((entry) => entry?.source_key === sourceKey)?.freshness_state === "fresh"
  )).length;
  return `
    <section class="card gold-governance" aria-labelledby="gold-governance-title">
      <div class="gold-governance-head">
        <p class="eyebrow">DATA GOVERNANCE</p>
        <h2 id="gold-governance-title">数据就绪与快照</h2>
        <p><strong>${readyCount}/${sourceKeys.length}</strong> 个数据源当前可用</p>
      </div>
      <div class="gold-governance-grid">
        ${governanceSourceItem(manifest, "策略配置", "gold_policy")}
        ${governanceSourceItem(manifest, "XAUT 行情", "gold_spot_quote")}
        ${governanceSourceItem(manifest, "衍生品", "gold_derivatives")}
        ${governanceSnapshotItem(observed)}
      </div>
    </section>
  `;
}

// ----- Top-level render ----------------------------------------------------

function renderChartGridEmptyState(data) {
  const isError = !data || data.status === "error" || data.detail;
  const title = isError ? "图表数据源不可达" : "图表正在准备";
  const message = isError
    ? "工作台数据接口未返回图表序列。请检查 /api/v1/gold/workbench 服务状态，或稍后手动刷新。"
    : "图表数据尚未到达；后台正在准备。等图表序列就绪后将自动渲染。";
  return `
    <section class="gold-chart-grid gold-chart-grid-empty" role="status" aria-live="polite">
      <div class="card gold-chart-card is-empty">
        <div class="card-head-inline">
          <p class="eyebrow">CHARTS</p>
          <p class="gold-card-title">${escapeHtml(title)}</p>
        </div>
        <div class="gold-chart-empty-body">
          <p>${escapeHtml(message)}</p>
        </div>
      </div>
    </section>
  `;
}

function renderShell(data) {
  // Chart capability gate: only emit the 5 chart cards when the workbench
  // response actually carries a chart token with a non-zero candle count.
  // Without the gate, 5 empty <canvas> elements render on every cold load —
  // and when the API returns an error the canvases sit empty forever with no
  // user-visible message.
  const chartToken = data && data.chart_series_or_chart_token;
  const hasChartSeries = !!(chartToken && chartToken.path && (chartToken.count || 0) > 0);
  return `
    ${renderHero(data)}
    <section class="gold-workbench-grid">
      ${renderSpotDca(data)}
      ${renderContractRef(data)}
    </section>
    ${hasChartSeries ? renderChartGrid() : renderChartGridEmptyState(data)}
    ${renderGovernance(data)}
  `;
}

// ----- Data fetching + chart wiring --------------------------------------

async function loadData() {
  try {
    if (typeof api.getGoldWorkbench !== "function") {
      throw new Error("api.getGoldWorkbench is not wired in app/static/core/api.js");
    }
    const data = await api.getGoldWorkbench();
    latestData = data;
    // Render the full shell (hero + workbench cards + governance) even when
    // chart data is missing, so verify_pages' real-content selectors
    // (.gold-workbench-grid / .gold-governance-grid) still match and the
    // user sees an explicit empty state instead of a dead page.
    setRoot(renderShell(data));
    applyPostMountStyles();
    // The SPA router's enter animation plays against the warming shell
    // (its 300ms cleanup long expired while the 5-6s workbench request
    // settled), so replay the transition against the real content to
    // avoid a hard visual cut when the data lands.
    replayPageEnter();
    const chartToken = data && data.chart_series_or_chart_token;
    if (chartToken && chartToken.path && (chartToken.count || 0) > 0) {
      renderGoldCharts(data).catch((err) => console.warn("[gold_v5] chart render failed", err));
    }
  } catch (err) {
    console.warn("[gold_v5] workbench unavailable:", err && err.message ? err.message : err);
    setRoot(renderShell({ snapshot: { status: "error" }, detail: String((err && err.message) || err) }));
    applyPostMountStyles();
    replayPageEnter();
  }
}

/**
 * Replay the SPA page-enter transition against freshly rendered content.
 * main.js applies `.page-transition` once per boot right after the warming
 * shell mounts, then removes it after ~300ms. The workbench request takes
 * seconds, so the real content swap would otherwise be a hard cut. Re-adding
 * the class here (mirroring main.js's reflow + cleanup) fades the new shell in.
 */
function replayPageEnter() {
  const root = document.getElementById("page-root");
  if (!root || root.childElementCount === 0) return;
  void root.offsetWidth; // force reflow so the 'from' keyframe plays
  root.classList.add("page-transition");
  setTimeout(() => root.classList.remove("page-transition"), 300);
}

async function renderGoldCharts(data) {
  destroyChartsForPage("gold");
  const candles = await fetchChartSeries(data?.chart_series_or_chart_token);
  if (!candles.length) return;
  // Backend candle rows are { ts_open, open, high, low, close, volume }
  // (ISO-string ts_open serves as the x-axis label; see the workbench chart
  // endpoint in gold.py). Map defensively so legacy shapes still work.
  const labels = candles.map((c) => String(c.ts_open || c.ts || c.timestamp || c.time || ""));
  const priceSeries = candles.map((c) => Number(c.close ?? c.c ?? 0));

  // renderChart signature: renderChart(key, canvas, config) — canvas must be
  // a real DOM element. analysis.js:1242-1256 follows the same pattern.
  const renderInto = (key, config) => {
    const canvas = document.getElementById(`gold-canvas-${key}`);
    if (!canvas) {
      console.warn(`[gold_v5] canvas not found for ${key}`);
      return;
    }
    renderChart(key, canvas, config);
  };

  renderInto("price", {
    type: "line",
    axisProfile: "price",
    data: {
      labels,
      datasets: [
        lineDataset("XAUT", priceSeries, "#1f1b16", { borderWidth: 1.6 }),
        lineDataset("MA50", maSeries(candles, 50), "#5b8a83", { borderWidth: 1.2, borderDash: [4, 3] }),
        lineDataset("SMA200", maSeries(candles, 200), "#b07558", { borderWidth: 1.2, borderDash: [6, 3] }),
        lineDataset("EMA20", emaSeries(candles, 20), "#7c5fb0", { borderWidth: 1.2, borderDash: [2, 2] }),
      ],
    },
    options: { responsive: true, maintainAspectRatio: false, plugins: { legend: { display: true } } },
  });
  renderInto("vegas", {
    type: "line",
    axisProfile: "price",
    data: {
      labels,
      datasets: [
        lineDataset("XAUT", priceSeries, "#1f1b16", { borderWidth: 1.2 }),
        lineDataset("快轨 144", emaSeries(candles, 144), "#5b8a83", { borderWidth: 1.8 }),
        lineDataset("快轨 169", emaSeries(candles, 169), "#5b8a83", { fill: "-1", backgroundColor: "rgba(91, 138, 131, 0.10)", borderWidth: 1.8 }),
        lineDataset("慢轨 576", emaSeries(candles, 576), "#7c5fb0", { borderDash: [7, 4], borderWidth: 1.7 }),
        lineDataset("慢轨 676", emaSeries(candles, 676), "#7c5fb0", { fill: "-1", backgroundColor: "rgba(124, 95, 176, 0.08)", borderDash: [7, 4], borderWidth: 1.7 }),
      ],
    },
    options: { responsive: true, maintainAspectRatio: false },
  });
  const macd = macdSeries(candles, 12, 26, 9);
  renderInto("macd", {
    type: "bar",
    axisProfile: "centeredZero",
    data: {
      labels,
      datasets: [
        barDataset("柱状图", macd.hist, macd.hist.map((value) => value >= 0 ? "rgba(91, 138, 131, 0.55)" : "rgba(176, 117, 88, 0.48)"), { borderRadius: 2 }),
        lineDataset("MACD", macd.line, "#5b8a83", { borderWidth: 1.8 }),
        lineDataset("信号线", macd.signal, "#b8924a", { borderDash: [6, 4], borderWidth: 1.6 }),
      ],
    },
    options: { responsive: true, maintainAspectRatio: false },
  });
  renderInto("volume", {
    type: "bar",
    axisProfile: "volume",
    data: {
      labels,
      datasets: [barDataset("Volume", candles.map((c) => c.v ?? c.volume ?? 0), "rgba(91, 138, 131, 0.55)")],
    },
    options: { responsive: true, maintainAspectRatio: false },
  });
  renderInto("bollinger", {
    type: "line",
    axisProfile: "ratio",
    data: {
      labels,
      datasets: [lineDataset("%B", bollingerPctB(candles, 20, 2), "#b07558", { borderWidth: 1.2 })],
    },
    options: { responsive: true, maintainAspectRatio: false, scales: { y: { min: -0.2, max: 1.2 } } },
  });
  renderInto("rsi", {
    type: "line",
    axisProfile: "oscillator",
    data: {
      labels,
      datasets: [lineDataset("RSI14", rsiSeries(candles, 14), "#5b8a83", { borderWidth: 1.4 })],
    },
    options: { responsive: true, maintainAspectRatio: false, scales: { y: { min: 0, max: 100 } } },
  });
}

async function fetchChartSeries(token) {
  // token is { snapshot_id, path, count }; the chart endpoint
  // (GET /api/v1/gold/workbench/charts/{snapshot_id}) returns the candles
  // bound to this workbench snapshot: { snapshot_id, observed_at, candles }.
  if (!token?.snapshot_id) return [];
  try {
    const res = await api.getGoldWorkbenchCharts(token.snapshot_id);
    return res?.candles || res?.series || res?.data || [];
  } catch (err) {
    console.warn("[gold_v5] chart series fetch failed", err);
    return [];
  }
}

function maSeries(candles, n) {
  return candles.map((_, i) => {
    const slice = candles.slice(Math.max(0, i - n + 1), i + 1).map((c) => c.c ?? c.close ?? 0);
    return slice.reduce((s, x) => s + x, 0) / slice.length;
  });
}
function emaSeries(candles, n) {
  const k = 2 / (n + 1);
  const out = [];
  let prev = candles[0]?.c ?? candles[0]?.close ?? 0;
  for (let i = 0; i < candles.length; i++) {
    const price = candles[i]?.c ?? candles[i]?.close ?? 0;
    if (i === 0) {
      out.push(prev);
    } else {
      prev = price * k + prev * (1 - k);
      out.push(prev);
    }
  }
  return out;
}

function macdSeries(candles, fastPeriod, slowPeriod, signalPeriod) {
  const fast = emaSeries(candles, fastPeriod);
  const slow = emaSeries(candles, slowPeriod);
  const line = fast.map((value, index) => value - slow[index]);
  const k = 2 / (signalPeriod + 1);
  const signal = [];
  let previous = line[0] || 0;
  line.forEach((value, index) => {
    previous = index === 0 ? value : value * k + previous * (1 - k);
    signal.push(previous);
  });
  return { line, signal, hist: line.map((value, index) => value - signal[index]) };
}
function rsiSeries(candles, n) {
  const out = [];
  for (let i = 0; i < candles.length; i++) {
    if (i < n) { out.push(null); continue; }
    let gain = 0, loss = 0;
    for (let j = i - n + 1; j <= i; j++) {
      const cur = candles[j].c ?? candles[j].close ?? 0;
      const prev = candles[j - 1]?.c ?? candles[j - 1]?.close ?? 0;
      const d = cur - prev;
      if (d >= 0) gain += d; else loss -= d;
    }
    if (loss === 0) { out.push(100); continue; }
    const rs = gain / loss;
    out.push(100 - 100 / (1 + rs));
  }
  return out;
}
function bollingerPctB(candles, n, k) {
  const out = [];
  for (let i = 0; i < candles.length; i++) {
    if (i < n) { out.push(null); continue; }
    const slice = candles.slice(i - n + 1, i + 1).map((c) => c.c ?? c.close ?? 0);
    const mean = slice.reduce((s, x) => s + x, 0) / n;
    const sd = Math.sqrt(slice.reduce((s, x) => s + (x - mean) ** 2, 0) / n) || 1;
    const last = candles[i].c ?? candles[i].close ?? 0;
    out.push((last - (mean - k * sd)) / (2 * k * sd));
  }
  return out;
}
// ----- Post-mount styling helper (avoids inline style attributes) ----------

function applyPostMountStyles() {
  // Apply weight-bar fill width from data-fill attribute set during rendering.
  // We avoid inline style= attributes by using --gold-weight-pct custom property.
  document.querySelectorAll(".gold-weight-fill[data-fill]").forEach((el) => {
    const v = Number(el.getAttribute("data-fill"));
    if (Number.isFinite(v)) el.style.setProperty("--gold-weight-pct", v + "%");
  });
}

// ----- Lifecycle --------------------------------------------------------

export async function renderGoldV5() {
  controller?.abort?.();
  controller = new AbortController();
  // The warming shell is structurally complete so SPA navigation gets an
  // immediate stable workspace while the workbench request settles.
  setRoot(renderShell({ snapshot: { status: "loading" }, chart_series_or_chart_token: null }));
  applyPostMountStyles();
  await loadData();
  applyPostMountStyles();
  const refreshBtn = document.getElementById("gold-refresh");
  if (refreshBtn) {
    refreshBtn.addEventListener("click", () => loadData(), { signal: controller.signal });
  }
  // Return a controller so the SPA router (main.js normalizeController)
  // calls unmount() on navigation — previously the page returned undefined
  // and the abort controller / charts were never torn down.
  return { unmount };
}

export function unmount() {
  controller?.abort?.();
  controller = null;
  destroyChartsForPage("gold");
  latestData = null;
}

export const ready = true;
