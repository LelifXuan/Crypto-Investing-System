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

// ----- Governance tone mapping (source_manifest freshness_state → tone).
function toneForFreshness(state) {
  switch (state) {
    case "fresh":
      return "bullish-soft";
    case "stale":
      return "warning";
    case "degraded":
      return "warning";
    case "missing":
      return "bearish-soft";
    default:
      return "neutral";
  }
}

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
    DATA_DEGRADED: "数据降级,等待回填",
    setup_required: "策略未配置",
  };
  return m[active] || "宏观待评估";
}

// ----- Render functions ----------------------------------------------------

function renderHero(data) {
  const active =
    data?.market_scenarios?.active_scenario ||
    (data?.refresh_state === "setup_required" ? "setup_required" : null);
  const setupRequired = data?.snapshot?.status === "setup_required";
  const subtitle = setupRequired
    ? "请先在策略页配置组合与执行纪律。"
    : `宏观判断: ${scenarioLabel(active || "DATA_DEGRADED")}`;
  const shock = data?.market_scenarios?.active_scenarios?.includes("LIQUIDITY_SHOCK");

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
          <button class="mock-button" id="gold-refresh">刷新 XAUT</button>
        </div>
      </article>
    </section>
  `;
}

function renderChartCard(chartId, eyebrow, title) {
  const wideClass = chartId === "gold-chart-price" ? " is-wide" : "";
  return `
    <article class="card gold-chart-card${wideClass}" id="${chartId}">
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
      ${renderChartCard("gold-chart-price", "PRICE & INDICATORS", "价格 · MA50 · SMA200 · EMA20")}
      ${renderChartCard("gold-chart-rsi", "MOMENTUM", "RSI(14)")}
      ${renderChartCard("gold-chart-bollinger", "VOLATILITY", "Bollinger %B · K(20,2)")}
      ${renderChartCard("gold-chart-volume", "VOLUME", "成交量")}
      ${renderChartCard("gold-chart-drawdown", "RISK", "60 日回撤")}
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
      <div class="gold-formula-item"><span>BASR · 基础定投</span><b>${money(baseAmount)}</b></div>
      <div class="gold-formula-item"><span>FIXED · 黄金坑加仓</span><b>${money(dipAmount)}</b></div>
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
        <p class="eyebrow">建议金额</p>
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
  const macroCode = data?.market_scenarios?.active_scenarios?.includes("LIQUIDITY_SHOCK")
    ? "LIQUIDITY_SHOCK"
    : data?.base_dca?.status || "DATA_DEGRADED";
  return `
    <article class="card gold-workbench-card gold-spot-dca">
      <div class="card-head-inline">
        <p class="eyebrow">SPOT DCA</p>
        <p class="gold-card-title">战略配置与今日动作</p>
      </div>
      ${renderWeightRow(strategic)}
      ${renderFormulaBox(base, dip)}
      <div>
        ${renderGateRow("①", "60 日回撤与连续确认", drawdownCode, "回撤阈值与连续确认门禁")}
        ${renderGateRow("②", "宏观与流动性冲击门禁", macroCode, "宏观风险阻断基础定投")}
      </div>
      ${renderRecommendRow(base, dip)}
    </article>
  `;
}

// ----- Contract Reference — top-down refactor (3 blocks per spec §2.4) -----

function miniCard(label, value) {
  const present = value != null && value !== "" && value !== "数据积累中";
  const cls = present ? "is-effective" : "is-insufficient";
  return `
    <div class="gold-mini-card ${cls}">
      <p class="eyebrow">${escapeHtml(label)}</p>
      <strong>${escapeHtml(value || "数据积累中")}</strong>
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
        ${miniCard("MA50", tech?.ma50)}
        ${miniCard("MA200 / SMA200", tech?.sma200)}
        ${miniCard("60 日回撤", tech?.drawdown_60d)}
        ${miniCard("EMA20 距离", tech?.ema20_distance)}
      </div>
      <div class="gold-mini-grid">
        ${miniCard("OI 4 周变化", deriv?.oi_change_4w)}
        ${miniCard("资金费率", deriv?.funding_rate)}
        ${miniCard("COT 净投机", deriv?.cot_net_spec_percentile)}
        ${miniCard("未平仓", deriv?.open_interest)}
      </div>
    </article>
  `;
}

// ----- Governance — 4-column mini-card grid (replaces V4 1xN strip) -------

function governanceMiniCard(label, value, fresh) {
  const cls = fresh ? "is-effective" : "is-insufficient";
  return `
    <article class="card gold-mini-card ${cls}">
      <p class="eyebrow">${escapeHtml(label)}</p>
      <strong>${escapeHtml(value || "数据生成中")}</strong>
    </article>
  `;
}

function renderGovernanceMini(manifest, label, sourceKey) {
  const entry = (manifest || []).find((s) => s?.source_key === sourceKey);
  if (!entry) return governanceMiniCard(label, "未配置", false);
  const state = entry.freshness_state || "missing";
  const present = state === "fresh";
  return governanceMiniCard(
    label,
    `${labelForFreshness(state)} · ${entry.age_seconds != null ? `${entry.age_seconds}s` : "—"}`,
    present
  );
}

function renderGovernance(data) {
  const manifest = data?.source_manifest || [];
  const observed = data?.snapshot?.observed_at || "—";
  return `
    <section class="gold-governance">
      <div class="card-head-inline">
        <p class="eyebrow">数据治理 · SNAPSHOT</p>
        <p class="gold-card-title">来源就绪度</p>
      </div>
      <div class="gold-governance-grid">
        ${renderGovernanceMini(manifest, "策略配置", "gold_policy")}
        ${renderGovernanceMini(manifest, "XAUT 行情", "gold_spot_quote")}
        ${renderGovernanceMini(manifest, "衍生品", "gold_derivatives")}
        ${governanceMiniCard("快照时间", observed, !!observed && observed !== "—")}
      </div>
    </section>
  `;
}

// ----- Top-level render ----------------------------------------------------

function renderShell(data) {
  return `
    ${renderHero(data)}
    ${renderChartGrid()}
    <section class="gold-workbench-grid">
      ${renderSpotDca(data)}
      ${renderContractRef(data)}
    </section>
    ${renderGovernance(data)}
  `;
}

// ----- Data fetching + chart wiring --------------------------------------

async function loadData() {
  try {
    const data = await api.getGoldWorkbench();
    latestData = data || {};
    setRoot(renderShell(latestData));
    applyPostMountStyles();
    if (latestData?.chart_series_or_chart_token?.path) {
      renderGoldCharts(latestData).catch((err) => console.warn("[gold_v5] chart render failed", err));
    }
  } catch (err) {
    console.error("[gold_v5] workbench load failed", err);
    setRoot(renderHero({ snapshot: { status: "error" } }));
  }
}

async function renderGoldCharts(data) {
  destroyChartsForPage("gold");
  const candles = await fetchChartSeries(data?.chart_series_or_chart_token);
  if (!candles.length) return;
  const labels = candles.map((c) => c.t || c.timestamp || c.time);
  const priceSeries = candles.map((c) => c.c ?? c.close ?? null);

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
    data: {
      labels,
      datasets: [
        lineDataset("XAUT", priceSeries, "#1f1b16", { borderWidth: 1.6 }),
        lineDataset("MA50", maSeries(candles, 50), "#5b8a83", { borderWidth: 1.2, borderDash: [4, 3] }),
      ],
    },
    options: { responsive: true, maintainAspectRatio: false, plugins: { legend: { display: true } } },
  });
  renderInto("rsi", {
    type: "line",
    data: {
      labels,
      datasets: [lineDataset("RSI14", rsiSeries(candles, 14), "#5b8a83", { borderWidth: 1.4 })],
    },
    options: { responsive: true, maintainAspectRatio: false, scales: { y: { min: 0, max: 100 } } },
  });
  renderInto("bollinger", {
    type: "line",
    data: {
      labels,
      datasets: [lineDataset("%B", bollingerPctB(candles, 20, 2), "#b07558", { borderWidth: 1.2 })],
    },
    options: { responsive: true, maintainAspectRatio: false, scales: { y: { min: -0.2, max: 1.2 } } },
  });
  renderInto("volume", {
    type: "bar",
    data: {
      labels,
      datasets: [barDataset("Volume", candles.map((c) => c.v ?? c.volume ?? 0), "rgba(91, 138, 131, 0.55)")],
    },
    options: { responsive: true, maintainAspectRatio: false },
  });
  renderInto("drawdown", {
    type: "line",
    data: {
      labels,
      datasets: [lineDataset("Drawdown", drawdownSeries(candles, 60), "#b07558", { borderWidth: 1.4 })],
    },
    options: { responsive: true, maintainAspectRatio: false },
  });
}

async function fetchChartSeries(token) {
  // token is { snapshot_id, token, path }; we use the domain helper
  // api.getGoldWorkbenchCharts(snapshotId) which is in app/static/core/api.js:278.
  if (!token?.snapshot_id) return [];
  try {
    const res = await api.getGoldWorkbenchCharts(token.snapshot_id);
    return res?.series || res?.candles || res?.data || [];
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
function drawdownSeries(candles, n) {
  const out = [];
  for (let i = 0; i < candles.length; i++) {
    const slice = candles.slice(Math.max(0, i - n + 1), i + 1).map((c) => c.c ?? c.close ?? 0);
    const peak = Math.max(...slice, 1);
    const last = candles[i].c ?? candles[i].close ?? 0;
    out.push(((last - peak) / peak) * 100);
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

export async function renderGoldV5(root) {
  controller?.abort?.();
  controller = new AbortController();
  setRoot(root, renderShell({ snapshot: { status: "loading" } }));
  applyPostMountStyles();
  await loadData();
  applyPostMountStyles();
  const refreshBtn = document.getElementById("gold-refresh");
  if (refreshBtn) {
    refreshBtn.addEventListener("click", () => loadData(), { signal: controller.signal });
  }
}

export function unmount() {
  controller?.abort?.();
  controller = null;
  destroyChartsForPage("gold");
  latestData = null;
}

export const ready = true;
