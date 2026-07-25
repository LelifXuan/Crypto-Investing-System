import { api } from "../core/api.js";
import {
  escapeHtml,
  formatDateTime,
  formatNumber,
  hydrateKnowledgeTooltips,
  knowledgeTooltip,
  setRoot,
  statusBanner,
} from "../core/dom.js";
import {
  barDataset,
  destroyChartsForPage,
  lineDataset,
  renderChart,
} from "../ui/charts.js";
import { judgementMeta } from "../core/judgement.js?v=semantic-v3";
import { rangeStateLabel } from "../core/rangeState.js";
import { mountPageGuide } from "../ui/pageGuideFab.js";

// Semantic color lock — same series always wears the same color regardless
// of which chart it appears in. Canonical palette shared with analysis.js + structure.js.
// Monet-aligned: pale + muted, sat 25-50%. Within each period-family:
//   short period = brighter + thinner (active, fleeting reference),
//   long period  = deeper + thicker  (stable long-term anchor).
// Combine this with the lineDataset borderWidth choices in analysis.js.
const CHART_COLORS = {
  "BTC 价格": "#2c3849",
  "Spot": "#2c3849",
  "收盘价": "#2c3849",
  "EMA12": "#dcb09a",
  "EMA20": "#cba071",
  "EMA30": "#a89569",
  "EMA50": "#7ba39d",
  "EMA60": "#6a8fa0",
  "EMA120": "#4d6485",
  "EMA200": "#3a5170",
  "VWAP20": "#d5c8e0",
  "VWAP50": "#a594c2",
  "VWAP100": "#5d4e7e",
  "OI": "#6a8fa0",
  "聚合 OI": "#6a8fa0",
  "Open Interest": "#6a8fa0",
  "OI 24h变化": "#6a8fa0",
  "Funding Z": "#8a86b5",
  "Funding": "#8a86b5",
  "Funding Rate": "#8a86b5",
  "Basis": "#b8924a",
  "年化 Basis": "#b8924a",
  "ATM IV": "#9686b9",
  "IV": "#9686b9",
  "Call IV": "#9686b9",
  "Put IV": "#9686b9",
  "Call OI": "#8eb098",
  "Put OI": "#c2725a",
  "Call Wall": "#8eb098",
  "Put Wall": "#c2725a",
  "Max Pain": "#5a6a7c",
  "25D Skew": "#9686b9",
  "Put/Call OI": "#7ba39d",
  "Put/Call Volume": "#b8924a",
  "Call 保护成本": "#8eb098",
  "Put 保护成本": "#c2725a",
  "借记价差成本": "#5a6a7c",
  "成交量": "#b8924a",
  "Volume": "#b8924a",
  "RSI": "#a896c8",
  "MACD": "#7ba39d",
  "信号线": "#dcbe88",
};
const FALLBACK_PALETTE = [
  "#6e9b94", "#c2725a", "#7ba39d", "#9686b9", "#b8924a", "#5a6a7c",
];
const FALLBACK_CHART_IDS = [
  "leverage_pressure_timeline",
  "term_structure",
  "strike_surface",
  "key_levels_history",
  "options_risk_premium_history",
];

// Stable mapping from each decision card id to a knowledge-base term id.
// Each card surfaces a user-facing concept (regime / risk / protection cost);
// the tooltip link uses these term ids so users can click through to the
// knowledge entry. The contract is locked by
// tests/test_btc_derivatives_decision_tooltips.py.
const DECISION_CARD_TERM = {
  market_state: "regime",
  primary_risk: "wall-strength",
  strategy_implication: "protection-cost",
};

let requestController = null;
let dashboard = null;
let autoRefreshAttempted = false;
let pageGuideFab = null;
let hedgePlan = null;
let riskChartMode = "sentiment";
// 2026-07-25: the wall-migration chart (and the rest of the
// dashboard) age every minute, but the page had no auto-refresh —
// users would leave the tab open across a session and see stale
// labels frozen at first load. Drive a cheap cache-first reload
// every AUTO_REFRESH_MS so the chart catches up without manual
// clicks. Manual "刷新" still uses refresh=true (job+force); this
// loop is read-only and aborts cleanly on unmount/pause.
const AUTO_REFRESH_MS = 60_000;
let autoRefreshTimer = null;
let filters = {
  window: "",
  expiryMode: "fixed",
  maturityBucket: "60D",
  selectedExpiry: "",
  strikeRangePct: "30",
};

function number(value, digits = 2) {
  return value === null || value === undefined
    ? "—"
    : formatNumber(Number(value), digits);
}

function percent(value, digits = 2) {
  const numeric = Number(value);
  return Number.isFinite(numeric) ? `${formatNumber(numeric * 100, digits)}%` : "—";
}

function displayState(value) {
  return {
    live: "实时",
    stale: "最近真实缓存",
    data_insufficient: "数据不足",
    fixture: "示例数据",
    healthy: "正常",
    degraded: "受限",
    failed: "不可用",
    circuit_open: "熔断中",
    unknown: "状态未知",
    ok: "可用",
    partial: "部分可用",
  }[value] || "状态未知";
}

function money(value) {
  if (value === null || value === undefined || value === "") return "—";
  const numeric = Number(value);
  return Number.isFinite(numeric) ? `$${formatNumber(numeric, 0)}` : "—";
}

function dashboardQuery() {
  return { ...filters };
}

function allCharts() {
  // 2026-07-23: filter out the legacy per-venue cross-section chart id
  // because it is no longer rendered as a <canvas>; it is replaced by
  // renderFuturesTable() + the standalone aggregate_oi_90d chart. The
  // payload still exists in the API response (for any non-page consumer
  // such as test_btc_derivatives_chart_consolidation.py) but the page
  // does not iterate it as a canvas chart any more.
  const knownCharts = new Set(FALLBACK_CHART_IDS);
  const merged = {
    ...(dashboard?.futures?.charts || {}),
    ...(dashboard?.options?.charts || {}),
  };
  return Object.fromEntries(
    Object.entries(merged).filter(([chartId]) => knownCharts.has(chartId))
  );
}

function syncFiltersFromDashboard() {
  const selection = dashboard?.selection || {};
  const expiryMode = selection.expiry_mode || "constant_maturity";
  filters = {
    window: selection.window || "",
    expiryMode,
    maturityBucket: selection.maturity_bucket || "60D",
    selectedExpiry: expiryMode === "fixed" ? (selection.selected_expiry || "") : "",
    strikeRangePct: selection.strike_range_pct || "30",
  };
}

function confidenceLabel(value) {
  return { high: "高置信度", medium: "中等置信度", low: "低置信度" }[value] || "低置信度";
}

function heroMarketVerdict() {
  if (!dashboard) {
    return "正在读取衍生品快照，等待期货、期权与保护成本证据。";
  }
  const blocks = dashboard?.joint_analysis?.inference_blocks || [];
  const block = (id) => blocks.find((item) => item.id === id) || {};
  const futures = block("futures");
  const options = block("options");
  const hedge = block("hedge_cost");
  const state = dashboard?.snapshot_state || dashboard?.data_quality?.mode;
  if (state === "data_insufficient") {
    return "数据不足，暂不能形成可靠多空判定；先等待真实期货、期权链与保护成本快照。";
  }
  const main = futures.conclusion || options.conclusion || "多空暂不明朗";
  const second = hedge.conclusion && hedge.conclusion !== "保护成本尚待观察"
    ? `，${hedge.conclusion}`
    : "";
  return `${main}${second}。`;
}

function renderHero({ banner = "", freshness = "" } = {}) {
  return `
    <section class="hero-card btc-derivatives-hero">
      <div>
        <p class="eyebrow">BTC DERIVATIVES COCKPIT</p>
        <h1>杠杆、波动率与保护成本</h1>
        <p>${escapeHtml(heroMarketVerdict())}</p>
      </div>
      <div class="btc-hero-actions">
        <span>${escapeHtml(displayState(dashboard?.snapshot_state || dashboard?.data_quality?.mode))}</span>
        <div class="btc-refresh-stack">
          <button class="button compact" id="btc-refresh" type="button">刷新衍生品快照</button>
          ${freshness ? `<small class="btc-refresh-freshness">${escapeHtml(freshness)}</small>` : ""}
        </div>
      </div>
    </section>
    ${banner}
  `;
}

function selectOptions(values, selected, labeler = (value) => value) {
  return values.map((value) => `
    <option value="${escapeHtml(value)}" ${value === selected ? "selected" : ""}>
      ${escapeHtml(labeler(value))}
    </option>
  `).join("");
}

function renderChartToolbar() {
  const expiries = dashboard?.options?.standard_expiries || dashboard?.options?.expiries || [];
  const maturity = dashboard?.maturity_selection || {};
  const sourceText = (maturity.interpolation_sources || [])
    .map((item) => `${item.expiry}（DTE ${item.dte}）`).join(" / ");
  return `
    <form class="card btc-chart-toolbar" id="btc-chart-controls">
      <label>
        <span>时间窗口</span>
        <select name="window">
          ${selectOptions(["", "30D", "90D", "180D", "365D"], filters.window, (value) => ({
            "": "各图默认窗口",
            "30D": "短期 30D",
            "90D": "中期 90D",
            "180D": "长期 180D",
            "365D": "全年 365D",
          })[value])}
        </select>
      </label>
      <label>
        <span>到期模式</span>
        <select name="expiry_mode">
          ${selectOptions(["fixed"], filters.expiryMode, () => "固定到期日")}
        </select>
      </label>
      <label>
        <span>期限桶</span>
        <select name="maturity_bucket">
          ${selectOptions(["30D", "60D", "90D"], filters.maturityBucket)}
        </select>
      </label>
      <label>
        <span>${filters.expiryMode === "fixed" ? "标准到期日" : "恒定期限来源"}</span>
        <select name="selected_expiry" ${filters.expiryMode === "fixed" ? "" : "disabled"}>
          ${selectOptions(expiries, filters.selectedExpiry)}
        </select>
        ${filters.expiryMode === "constant_maturity"
          ? `<small class="btc-expiry-source">${escapeHtml(sourceText || "等待标准到期日数据")}</small>`
          : ""}
      </label>
      <label>
        <span>行权价范围</span>
        <select name="strike_range_pct">
          ${selectOptions(["10", "20", "30", "50", "all"], filters.strikeRangePct, (value) => value === "all" ? "全部" : `±${value}%`)}
        </select>
      </label>
    </form>
  `;
}

function renderDecisionCards() {
  const blocks = dashboard?.joint_analysis?.inference_blocks || [];
  const block = (id) => blocks.find((item) => item.id === id) || {};
  const cards = (dashboard?.cards || []).length
    ? dashboard.cards
    : [
        {
          id: "market_state",
          label: "当前衍生品状态",
          state: block("futures").tone || "neutral",
          confidence: block("futures").confidence || dashboard?.joint_analysis?.confidence || "low",
          conclusion: block("futures").conclusion || "当前数据不足以形成清晰判断",
          basis: block("futures").basis || [],
          implication: block("futures").implication || "等待更多有效数据。",
        },
        {
          id: "primary_risk",
          label: "主要风险",
          state: block("options").tone || "neutral",
          confidence: block("options").confidence || dashboard?.joint_analysis?.confidence || "low",
          conclusion: block("options").conclusion || "当前风险方向尚不清晰",
          basis: [...(block("options").basis || []), ...(block("key_levels").basis || [])],
          implication: [block("options").implication, block("key_levels").implication].filter(Boolean).join(" ") || "等待更多有效数据。",
        },
        {
          id: "strategy_implication",
          label: "策略含义",
          state: block("hedge_cost").tone || "neutral",
          confidence: block("hedge_cost").confidence || dashboard?.joint_analysis?.confidence || "low",
          conclusion: block("hedge_cost").conclusion || "保护成本尚待观察",
          basis: block("hedge_cost").basis || [],
          implication: block("hedge_cost").implication || "等待更多有效数据。",
        },
      ];
  return `
    <section class="btc-decision-grid" aria-label="衍生品结论">
      ${cards.map((card) => `
        <article class="card btc-decision-card" data-card-id="${escapeHtml(card.id)}" data-state="${escapeHtml(card.state)}">
          <div class="btc-card-kicker">
            <span>${knowledgeTooltip(DECISION_CARD_TERM[card.id] || card.id, "tone-neutral", escapeHtml(card.label))}</span>
            <b>${escapeHtml(confidenceLabel(card.confidence))}</b>
          </div>
          ${card.id === "market_state" && dashboard?.joint_analysis?.range_state && dashboard.joint_analysis.range_state !== "NONE"
            ? `<p class="btc-market-state-label">${escapeHtml(card.market_state_label || rangeStateLabel(dashboard.joint_analysis))}</p>`
            : ""}
          <h2>${escapeHtml(card.conclusion || card.summary)}</h2>
          <p class="btc-decision-label">依据</p>
          <div class="btc-evidence-chips">
            ${(card.basis || []).slice(0, 5).map((item) => `<span>${escapeHtml(item)}</span>`).join("") || "<span>暂无有效依据</span>"}
          </div>
        </article>
      `).join("")}
    </section>
  `;
}

function renderIndicatorJudgements() {
  const items = dashboard?.indicator_judgements || [];
  if (!items.length) return "";
  return `
    <section class="card btc-indicator-semantics">
      <div class="btc-section-heading">
        <div><p class="eyebrow">INDICATOR ROLES</p><h2>指标状态与交易作用</h2></div>
        <p>拥挤度、波动和关键价位不会被直接解释为多空方向。</p>
      </div>
      <div class="btc-decision-grid">
        ${items.map((item) => {
          const meta = judgementMeta(item);
          return `
            <article class="btc-decision-card">
              <span>${escapeHtml(meta.axisLabel)}</span>
              <strong>${escapeHtml(meta.stateLabel)}</strong>
              <p>${escapeHtml(item.reason || "等待指标更新。")}</p>
              <small>${escapeHtml(`${meta.effectLabel} · ${meta.dataLabel}`)}</small>
            </article>
          `;
        }).join("")}
      </div>
    </section>
  `;
}

function inferenceBlock(id) {
  return (dashboard?.joint_analysis?.inference_blocks || []).find((block) => block.id === id) || {};
}

function chartInsight(chartId) {
  const map = {
    leverage_pressure_timeline: "杠杆方向",
    term_structure: "期限结构",
    strike_surface: "行权价分布",
    key_levels_history: "墙位迁移",
    options_risk_premium_history: riskChartMode === "hedge_cost"
      ? "保护成本"
      : "期权情绪",
  };
  return map[chartId] || "图表结论";
}

function chartCard(chartId, layout = {}) {
  const chart = allCharts()[chartId] || {};
  const hasData = chart.status === "ok" && Number(chart.metadata?.data_points || 0) > 0;
  const span = Number(layout.span) || 12;
  const density = layout.density || "standard";
  const metadata = chart.metadata || {};
  const sourceLabel = (metadata.providers || []).join(" / ");
  const windowLabel = metadata.actual_window === "current"
    ? "当前横截面"
    : metadata.actual_window || "";
  const riskModeControls = chartId === "options_risk_premium_history"
    ? `
      <div class="btc-chart-mode" role="group" aria-label="期权风险图显示模式">
        <button type="button" data-risk-chart-mode="sentiment" class="${riskChartMode === "sentiment" ? "is-active" : ""}">情绪</button>
        <button type="button" data-risk-chart-mode="hedge_cost" class="${riskChartMode === "hedge_cost" ? "is-active" : ""}">保护成本</button>
      </div>
    `
    : "";
  return `
    <article class="card btc-chart-card btc-card-span-${span} btc-chart-density-${escapeHtml(density)}${hasData ? "" : " is-empty"}">
      <div class="btc-chart-head">
        <div>
          <p class="eyebrow">图表</p>
          <h2>${escapeHtml(chart.title || chartId)}</h2>
          ${windowLabel ? `<small>${escapeHtml(windowLabel)} · ${number(metadata.data_points, 0)} 个数据点${sourceLabel ? ` · 来源 ${escapeHtml(sourceLabel)}` : ""}</small>` : ""}
        </div>
        <div class="btc-chart-head-actions">
          ${riskModeControls}
          <p class="btc-chart-insight">${escapeHtml(hasData ? chartInsight(chartId) : "数据不足")}</p>
        </div>
      </div>
      <div class="chart-wrap btc-chart-wrap">
        ${hasData ? `<canvas id="btc-chart-${escapeHtml(chartId)}" aria-label="${escapeHtml(chart.title || chartId)}"></canvas>` : `<div class="btc-chart-empty">${escapeHtml(chart.empty_reason || "暂无数据")}</div>`}
      </div>
    </article>
  `;
}

function fallbackSections() {
  return [
    { id: "summary", title: "总览", charts: ["leverage_pressure_timeline"] },
    {
      id: "futures",
      title: "期货 / 永续",
      // 2026-07-23: the per-venue cross-section snapshot is now rendered as
      // a HTML table by renderCrowdingTable() and a standalone 90D OI
      // line chart by renderAggregateOiChart() — both injected into this
      // section by renderChartSections(). Only term_structure remains as
      // a <canvas> chart.
      charts: ["term_structure"],
      auxRenderers: ["crowding_table", "aggregate_oi_90d"],
    },
    {
      id: "options",
      title: "期权结构",
      charts: [
        "key_levels_history",
        "options_risk_premium_history",
        "strike_surface",
      ],
    },
  ];
}

function sectionInterpretation(sectionId) {
  if (sectionId === "summary") {
    return inferenceBlock("futures").implication || "当前杠杆层尚未提供明确增量。";
  }
  if (sectionId === "futures") {
    return inferenceBlock("futures").conclusion || "比较交易所拥挤与期限结构。";
  }
  if (sectionId === "options") {
    const options = inferenceBlock("options").conclusion;
    const levels = inferenceBlock("key_levels").conclusion;
    return [options, levels].filter(Boolean).join("；") || "观察期权情绪、关键价位与保护成本。";
  }
  return "";
}

// 2026-07-23: the previous cross-section chart (one bar per venue
// overlaid with line series for funding/basis) was broken on render:
// mixed-axis confusion between venue names and date strings because
// formatXAxisTick parsed labels as dates. It is now replaced by:
//   1. renderFuturesTable()  — a per-venue HTML table (see further below).
//   2. renderAggregateOiChart() — a standalone 90D single-series line
//      chart sourced from the existing leverage_pressure_timeline payload
//      (the 聚合 OI dataset). The dataset is already in the API response,
//      so no backend changes were needed.
function renderAggregateOiChart(d) {
  const source = d?.futures?.charts?.leverage_pressure_timeline;
  if (!source) return "";
  const labels = Array.isArray(source.labels) ? source.labels : [];
  const oiSeries = (source.datasets || []).find((item) => item.label === "聚合 OI");
  if (!oiSeries || !Array.isArray(oiSeries.data) || !labels.length) return "";
  const metadata = source.metadata || {};
  const windowLabel = metadata.actual_window || "90D";
  const sourceLabel = (metadata.providers || []).join(" / ");
  const canvasId = "btc-chart-aggregate_oi_90d";
  return `
    <article class="card btc-chart-card btc-aggregate-oi-card">
      <header class="btc-card-head">
        <div>
          <p class="eyebrow">AGGREGATE OI · ${escapeHtml(String(windowLabel))}</p>
          <h3>聚合持仓 OI</h3>
        </div>
        <p>来源 ${escapeHtml(sourceLabel || "—")}</p>
      </header>
      <div class="btc-chart-canvas-wrap">
        <canvas id="${canvasId}"></canvas>
      </div>
    </article>
  `;
}

function renderChartSections() {
  const sections = dashboard?.chart_layout?.sections || fallbackSections();
  const cards = dashboard?.chart_layout?.cards || {};
  const knownCharts = new Set(FALLBACK_CHART_IDS);
  return sections.map((section) => {
    const auxParts = (section.auxRenderers || []).map((key) => {
      if (key === "crowding_table") return renderFuturesTable();
      if (key === "aggregate_oi_90d") return renderAggregateOiChart(dashboard);
      return "";
    }).join("");
    return `
    <section class="btc-chart-section" data-chart-section="${escapeHtml(section.id)}">
      <div class="btc-section-heading">
        <div>
          <p class="eyebrow">${escapeHtml(section.id)}</p>
          <h2>${escapeHtml(section.title)}</h2>
        </div>
        <p>${escapeHtml(sectionInterpretation(section.id))}</p>
      </div>
      ${auxParts}
      <div class="btc-dashboard-grid">
        ${(section.charts || [])
          .filter((chartId) => knownCharts.has(chartId) && allCharts()[chartId])
          .map((chartId) => chartCard(chartId, cards[chartId]))
          .join("")}
      </div>
    </section>
  `;
  }).join("");
}

function renderFuturesTable() {
  const rows = dashboard?.futures?.rows || [];
  return `
    <div class="btc-table-wrap">
      <table class="btc-table">
        <thead><tr><th>交易所 / 合约</th><th>标记价</th><th>OI</th><th>OI 变化</th><th>Funding</th><th>Basis</th></tr></thead>
        <tbody>
          ${rows.map((row) => `
            <tr>
              <td><strong>${escapeHtml(row.exchange)}</strong><small>${escapeHtml(row.instrument)}</small></td>
              <td>${money(row.mark_price)}</td>
              <td>${money(row.open_interest_usd)}</td>
              <td>${percent(row.oi_change_pct)}</td>
              <td>${percent(row.funding_rate, 4)}</td>
              <td>${percent(row.basis_pct)}</td>
            </tr>
          `).join("") || '<tr><td colspan="6">期货数据不足</td></tr>'}
        </tbody>
      </table>
    </div>
  `;
}

function renderOptionChain() {
  const rows = dashboard?.options?.chain || [];
  return `
    <div class="btc-table-wrap">
      <table class="btc-table btc-option-chain">
        <thead><tr><th>Call OI</th><th>Call IV</th><th>Call Δ</th><th>行权价</th><th>Put Δ</th><th>Put IV</th><th>Put OI</th></tr></thead>
        <tbody>
          ${rows.map((row) => `
            <tr>
              <td>${number(row.call?.open_interest, 0)}</td>
              <td>${percent(row.call?.iv)}</td>
              <td>${number(row.call?.delta, 2)}</td>
              <td><strong>${money(row.strike)}</strong></td>
              <td>${number(row.put?.delta, 2)}</td>
              <td>${percent(row.put?.iv)}</td>
              <td>${number(row.put?.open_interest, 0)}</td>
            </tr>
          `).join("") || '<tr><td colspan="7">当前到期日无期权链数据</td></tr>'}
        </tbody>
      </table>
    </div>
  `;
}

function renderKeyLevelStrip() {
  const cards = dashboard?.options?.key_level_cards || [];
  return `
    <section class="btc-level-strip">
      ${cards.map((card) => {
        const value = card.id === "constant_maturity"
          ? escapeHtml(card.value || "—")
          : money(card.value);
        const relative = card.distance_pct === null || card.distance_pct === undefined
          ? ""
          : `${card.distance_pct >= 0 ? "高于" : "低于"}现价 ${percent(Math.abs(card.distance_pct))}`;
        return `
          <article class="btc-level-card">
            <div class="btc-level-title">
              <span>${escapeHtml(card.label)}</span>
              ${knowledgeTooltip(card.knowledge_term, "tone-neutral", card.subtitle)}
            </div>
            <strong>${value}</strong>
            <small>${escapeHtml([relative, card.movement].filter(Boolean).join(" · "))}</small>
            <p>${escapeHtml(card.current_meaning)}</p>
          </article>
        `;
      }).join("") || "<article class=\"btc-level-card\"><p>当前链数据不足</p></article>"}
    </section>
  `;
}

function optionDirectionLabel(value) {
  return {
    UPSIDE_DEMAND: "上行需求",
    DOWNSIDE_PROTECTION: "下行保护",
    BALANCED: "方向平衡",
    TERM_DIVERGENCE: "期限分化",
    DATA_INSUFFICIENT: "数据不足",
  }[value] || "状态待确认";
}

function maturityBandLabel(value) {
  return { near_term: "近月", medium_term: "中期", far_term: "远月" }[value] || "期限待确认";
}

function renderMaturityLadder() {
  const rows = dashboard?.options?.maturity_ladder || [];
  const direction = dashboard?.options?.metrics?.options_direction || {};
  const protection = dashboard?.options?.metrics?.protection_cost_regime || {};
  if (!rows.length) return "";
  return `
    <section class="card btc-maturity-ladder">
      <div class="btc-section-heading">
        <div>
          <p class="eyebrow">STANDARD EXPIRIES</p>
          <h2>标准到期日期限矩阵</h2>
        </div>
        <p>${escapeHtml(direction.label || "期权方向数据不足")} · ${escapeHtml(protection.label || "保护成本待评估")}</p>
      </div>
      <p class="btc-maturity-summary">${escapeHtml(direction.primary_reason || "按标准月度与季度到期日比较近远期限，不跨到期日直接累加持仓。")}</p>
      ${(direction.term_conflicts || []).length
        ? `<div class="btc-term-conflicts">${direction.term_conflicts.map((item) => `<span>${escapeHtml(item)}</span>`).join("")}</div>`
        : ""}
      <div class="btc-table-wrap" tabindex="0" aria-label="标准到期日期限矩阵，可横向滚动">
        <table class="btc-table btc-maturity-table">
          <thead><tr>
            <th>期限</th><th>到期日</th><th>DTE</th><th>方向需求</th>
            <th>Put Wall</th><th>Max Pain</th><th>Call Wall</th>
            <th>25D RR</th><th>ATM IV</th><th>Put保护成本</th><th>数据</th>
          </tr></thead>
          <tbody>${rows.map((row) => {
            const skew = row.skew_25d || {};
            const cost = row.protection_cost || {};
            const directionState = skew.status !== "ok"
              ? "DATA_INSUFFICIENT"
              : Number(skew.put_call_skew) >= 0.03
              ? "DOWNSIDE_PROTECTION"
              : Number(skew.put_call_skew) <= -0.03
              ? "UPSIDE_DEMAND"
              : "BALANCED";
            return `<tr>
              <td><b>${escapeHtml(maturityBandLabel(row.maturity_band))}</b><small>${row.cycle === "QUARTERLY" ? "季度" : "月度"}</small></td>
              <td>${escapeHtml(row.expiry)}</td>
              <td>${number(row.dte, 0)}</td>
              <td><span class="btc-term-state" data-state="${escapeHtml(directionState)}">${escapeHtml(optionDirectionLabel(directionState))}</span></td>
              <td>${money(row.put_wall)}<small>${percent(row.put_wall_concentration)} 集中度</small></td>
              <td>${money(row.max_pain)}</td>
              <td>${money(row.call_wall)}<small>${percent(row.call_wall_concentration)} 集中度</small></td>
              <td>${skew.status === "ok" ? percent(skew.put_call_skew) : "数据不足"}<small>${escapeHtml(skew.delta_source === "model_estimate" ? "模型Delta" : skew.delta_source === "provider" ? "交易所Delta" : "Delta缺失")}</small></td>
              <td>${percent(row.atm_iv)}</td>
              <td>${percent(cost.put_protection_cost_pct)}<small>${escapeHtml(cost.liquidity_status === "usable" ? "流动性可用" : "流动性降级")}</small></td>
              <td>${escapeHtml(row.data_status === "ok" ? "可用" : "部分可用")}</td>
            </tr>`;
          }).join("")}</tbody>
        </table>
      </div>
      <p class="btc-maturity-note">期权墙只表示各期限内部的持仓集中区；保护成本绝对变化只进入风险判断，不单独生成多空方向。</p>
    </section>
  `;
}

function renderOptionsWallSignal() {
  const signal = dashboard?.options?.metrics?.options_wall_signal || {};
  const levels = signal.levels || {};
  const rows = [
    ["call_wall", "Call Wall"],
    ["put_wall", "Put Wall"],
    ["max_pain", "Max Pain"],
  ];
  const confidence = confidenceLabel(signal.confidence || "low");
  const status = signal.status_label || signal.summary || "关键价位样本不足";
  const spotChange = signal.spot_change_pct === null || signal.spot_change_pct === undefined
    ? "现价变化：历史不足"
    : `现价变化：昨日 ${money(signal.previous_spot_price)} → 当前 ${money(signal.spot_price)}（${percent(signal.spot_change_pct)}）`;
  const expiryContext = signal.expiry_context || {};
  const expiryLabels = (expiryContext.labels || []).join(" · ");
  const expiryLine = [
    expiryContext.selected_expiry ? `到期日 ${expiryContext.selected_expiry}` : "",
    expiryContext.source_dte === null || expiryContext.source_dte === undefined ? "" : `DTE ${expiryContext.source_dte}`,
    expiryLabels,
  ].filter(Boolean).join(" · ");
  return `
    <section class="card btc-wall-signal-card" data-tone="${escapeHtml(signal.bias || "neutral")}">
      <div class="btc-section-heading">
        <div>
          <p class="eyebrow">期权结构</p>
          <h2>期权关键价位结构</h2>
        </div>
        <p>${escapeHtml(status)} · 置信度：${escapeHtml(confidence)}</p>
      </div>
      <div class="btc-wall-signal-context">
        <span>${escapeHtml(spotChange)}</span>
        ${expiryLine ? `<span>${escapeHtml(expiryLine)}</span>` : ""}
      </div>
      <div class="btc-wall-signal-grid">
        ${rows.map(([key, label]) => {
          const item = levels[key] || {};
          const value = item.value === null || item.value === undefined ? "—" : money(item.value);
          const previous = item.previous_value === null || item.previous_value === undefined
            ? "历史不足"
            : `昨日 ${money(item.previous_value)} → 当前 ${value}`;
          const distance = item.distance_pct === null || item.distance_pct === undefined
            ? "距现价：—"
            : `距现价：${percent(item.distance_pct)}`;
          const shift = item.shift_pct === null || item.shift_pct === undefined
            ? "迁移：历史不足"
            : `迁移：${percent(item.shift_pct)}`;
          return `
            <article>
              <span>${escapeHtml(label)}</span>
              <strong>${value}</strong>
              <small>${escapeHtml(previous)}</small>
              <small>${escapeHtml(distance)} · ${escapeHtml(shift)}</small>
              <p>${escapeHtml(item.explanation || "当前链数据不足，暂不形成方向判断。")}</p>
            </article>
          `;
        }).join("")}
      </div>
      <p class="btc-wall-signal-summary">${escapeHtml(signal.summary || "等待 Call Wall、Put Wall 与 Max Pain 的有效迁移证据。")}</p>
      ${signal.risk_note ? `<small class="btc-wall-signal-note">${escapeHtml(signal.risk_note)}</small>` : ""}
    </section>
  `;
}

function renderDetailsDrawer() {
  return `
    <details class="btc-details-drawer">
      <summary>
        <span>原始市场明细</span>
        <small>期货合约与 ${escapeHtml(filters.selectedExpiry || "当前到期日")} 期权链</small>
      </summary>
      <div class="btc-details-grid">
        <article class="card btc-table-card">
          <h2>期货 / 永续明细</h2>
          ${renderFuturesTable()}
        </article>
        <article class="card btc-table-card">
          <h2>期权链</h2>
          ${renderOptionChain()}
        </article>
      </div>
    </details>
  `;
}

function renderEvidenceLayer() {
  const analysis = dashboard?.joint_analysis || {};
  const blocks = analysis.inference_blocks || [];
  return `
    <section class="card btc-evidence-layer">
      <div class="btc-section-heading">
        <div><p class="eyebrow">市场推定</p><h2>多空证据层</h2></div>
        <p>综合结论置信度：${escapeHtml(confidenceLabel(analysis.confidence))}</p>
      </div>
      <div class="btc-inference-grid">
        ${blocks.map((block) => `
          <article data-tone="${escapeHtml(block.tone || "neutral")}">
            <span>${escapeHtml(block.title)}</span>
            <h3>${escapeHtml(block.conclusion || "当前数据不足以形成清晰判断")}</h3>
            <p class="btc-inference-basis"><strong>依据：</strong>${escapeHtml((block.basis || []).join("；") || "暂无有效依据")}</p>
            <p><strong>影响：</strong>${escapeHtml(block.implication || "等待更多有效数据。")}</p>
            <small>结论置信度：${escapeHtml(confidenceLabel(block.confidence))}</small>
          </article>
        `).join("")}
      </div>
      ${(analysis.conflicts || []).map((item) => `<p class="btc-warning">${escapeHtml(item)}</p>`).join("")}
    </section>
  `;
}

function renderHedgePlanner() {
  const context = dashboard?.hedge_context || {};
  return `
    <section class="btc-bottom-group btc-protection-group">
      <div class="btc-section-heading">
        <div><p class="eyebrow">有限风险保护</p><h2>网格与现货保护规划</h2></div>
        <p>根据当前 IV、关键价位与保护成本，比较有限风险保护和降低敞口。</p>
      </div>
      <div class="btc-bottom-group-body btc-hedge-layout">
        <form class="card btc-hedge-grid" id="btc-hedge-form">
          <label><span>组合类型</span><select name="portfolio_type"><option value="short_grid">空网格</option><option value="long_grid">多网格</option><option value="spot_only">现货</option><option value="neutral_grid">中性网格</option></select></label>
          <label><span>现价</span><input name="spot_price" type="number" min="1" value="${escapeHtml(String(context.spot_price || 61200))}" required></label>
          <label><span>网格下沿</span><input name="grid_lower" type="number" min="1" value="45000"></label>
          <label><span>网格上沿</span><input name="grid_upper" type="number" min="1" value="62000"></label>
          <label><span>净名义金额 USD</span><input name="net_notional_usd" type="number" min="0" value="5000"></label>
          <label><span>保护预算 USD</span><input name="hedge_budget_usd" type="number" min="0" value="150"></label>
          <label><span>到期期限</span><select name="preferred_expiry_bucket"><option>30D</option><option selected>60D</option><option>90D</option></select></label>
          <label><span>有限风险价差</span><select name="allow_debit_spread"><option value="true">允许</option><option value="false">不使用</option></select></label>
          <button class="button" type="submit">生成保护方案</button>
        </form>
        ${renderHedgePlan()}
      </div>
    </section>
  `;
}

function renderAuditGroup() {
  return `
    <section class="btc-bottom-group btc-audit-group">
      <div class="btc-section-heading">
        <div><p class="eyebrow">明细审计</p><h2>原始市场明细</h2></div>
        <p>把期货、永续与期权链明细收进可展开区域，供复核和追溯使用。</p>
      </div>
      <div class="btc-bottom-group-body">
        ${renderDetailsDrawer()}
      </div>
    </section>
  `;
}

function renderHedgePlan() {
  if (!hedgePlan) {
    return `
      <article class="card btc-hedge-result">
        <p class="eyebrow">方案</p>
        <h2>填写现货或网格敞口</h2>
        <p>系统会比较买入保护、借记价差与降低网格敞口，只输出有限风险动作，不执行下单。</p>
      </article>
    `;
  }
  return `
    <article class="card btc-hedge-result">
      <p class="eyebrow">方案</p>
      <h2>${escapeHtml(hedgePlan.label)}</h2>
      <p>${escapeHtml(hedgePlan.explanation)}</p>
      <div class="btc-plan-metrics">
        <span>建议动作 <b>${escapeHtml(hedgePlan.label)}</b></span>
        <span>保护区 <b>${escapeHtml(hedgePlan.protection_zone || "—")}</b></span>
        <span>预计成本 <b>${money(hedgePlan.estimated_premium_usd)}</b></span>
        <span>预算 <b>${hedgePlan.budget_ok === null ? "未判断" : hedgePlan.budget_ok ? "范围内" : "超预算"}</b></span>
      </div>
      ${(hedgePlan.warnings || []).map((item) => `<p class="btc-warning">${escapeHtml(item)}</p>`).join("")}
    </article>
  `;
}

function renderLiveSourceStatus() {
  const quality = dashboard?.data_quality || {};
  const providers = dashboard?.source_status || quality.providers || [];
  const snapshotState = dashboard?.snapshot_state || quality.mode || "data_insufficient";
  const stateMessage = snapshotState === "stale"
    ? `正在使用最近真实缓存，数据时间 ${formatDateTime(dashboard?.data_timestamp)}`
    : snapshotState === "data_insufficient"
      ? "当前没有可用实时数据，也没有 15 分钟内的真实缓存。"
      : "当前展示实时公开数据。";
  return `
    <section class="card btc-data-quality">
      <div class="btc-section-heading">
        <div><p class="eyebrow">数据质量</p><h2>数据源状态</h2></div>
        <div class="btc-quality-actions">
          <span class="btc-quality-badge" data-state="${escapeHtml(snapshotState)}">${escapeHtml(displayState(snapshotState))}</span>
          <button id="btc-probe-sources" class="secondary-button" type="button">一键探测数据源</button>
        </div>
      </div>
      <p class="${snapshotState === "live" ? "" : "btc-fixture-warning"}">${escapeHtml(stateMessage)}</p>
      <details class="btc-source-details">
        <summary>查看数据源明细、缺失字段与方法警告</summary>
        <div class="btc-provider-grid">
          ${providers.map((item) => `
            <article class="btc-provider-card" data-status="${escapeHtml(item.status || "unknown")}">
              <div><strong>${escapeHtml(item.provider || item.name || "unknown")}</strong><span>${escapeHtml(displayState(item.status))}</span></div>
              <p>${escapeHtml((item.capabilities || []).join(" / ") || "能力未知")}</p>
              <small>延迟 ${item.latency_ms == null ? "—" : `${Math.round(item.latency_ms)}ms`} · 最近成功 ${escapeHtml(formatDateTime(item.last_success_at))}</small>
              ${item.last_error ? `<small class="btc-provider-error">${escapeHtml(item.last_error)}</small>` : ""}
              ${item.circuit_open_until ? `<small>熔断至 ${escapeHtml(formatDateTime(item.circuit_open_until))}</small>` : ""}
            </article>
          `).join("") || "<p>暂无数据源健康记录，可点击探测。</p>"}
        </div>
        <details class="btc-quality-details">
          <summary>查看缺失字段、陈旧快照与方法警告</summary>
          <div class="btc-quality-grid">
            <article><h3>缺失字段</h3><p>${escapeHtml((quality.missing_fields || []).join(" / ") || "无")}</p></article>
            <article><h3>陈旧快照</h3><p>${escapeHtml((quality.stale_snapshots || []).join(" / ") || "无")}</p></article>
            <article><h3>历史积累</h3><p>${quality.history_available ? "可用" : "真实样本积累中"}</p></article>
          </div>
          <ul>${(quality.warnings || []).map((item) => `<li>${escapeHtml(item)}</li>`).join("")}</ul>
        </details>
      </details>
      <small>生成时间：${escapeHtml(formatDateTime(dashboard?.generated_at))}</small>
    </section>
  `;
}

function renderDataQuality() {
  return renderLiveSourceStatus();
}

function renderGovernanceGroup() {
  return `
    <section class="btc-bottom-group btc-governance-group">
      <div class="btc-section-heading">
        <div><p class="eyebrow">数据与边界</p><h2>数据源状态与方法边界</h2></div>
        <p>集中查看数据可用性、缺失字段、方法限制和不执行下单的边界。</p>
      </div>
      <div class="btc-bottom-group-body btc-governance-grid">
        ${renderDataQuality()}
        ${renderMethodNotes()}
      </div>
    </section>
  `;
}

function renderMethodNotes() {
  return `
    <details class="btc-method-notes">
      <summary>风险提示与方法边界</summary>
      <div>
        <p>最大痛点用于观察持仓分布迁移，不作为价格预测。</p>
        <p>期权墙用于观察持仓集中与对冲敏感区，不作为确定支撑或阻力。</p>
        <p>页面不执行下单，不推荐裸卖期权，也不把比例价差描述为安全对冲。</p>
      </div>
    </details>
  `;
}

function renderPageShell(banner = "", freshness = "") {
  return `
    <div class="btc-derivatives-page">
      ${renderHero({ banner, freshness })}
      ${renderDecisionCards()}
      ${renderIndicatorJudgements()}
      ${renderChartToolbar()}
      ${renderMaturityLadder()}
      ${renderKeyLevelStrip()}
      ${renderOptionsWallSignal()}
      ${renderChartSections()}
      ${renderEvidenceLayer()}
      ${renderHedgePlanner()}
      ${renderAuditGroup()}
      ${renderGovernanceGroup()}
    </div>
  `;
}

function datasetVisibleInRiskMode(label) {
  const hedgeCostLabels = new Set(["Call 保护成本", "Put 保护成本", "借记价差成本"]);
  return riskChartMode === "hedge_cost"
    ? hedgeCostLabels.has(label)
    : !hedgeCostLabels.has(label);
}

function interpolateChartLabel(start, end, ratio) {
  const startDate = new Date(start);
  const endDate = new Date(end);
  if (!Number.isNaN(startDate.getTime()) && !Number.isNaN(endDate.getTime())) {
    return new Date(
      startDate.getTime() + (endDate.getTime() - startDate.getTime()) * ratio,
    ).toISOString();
  }
  return `${start} / ${end}`;
}

export function expandFundingZeroCrossings(labels, datasets) {
  const funding = (datasets || []).find((dataset) => dataset.label === "Funding Z");
  if (!funding) return { labels: labels || [], datasets: datasets || [] };
  const expandedLabels = [];
  const expandedData = (datasets || []).map(() => []);
  (labels || []).forEach((label, index) => {
    expandedLabels.push(label);
    datasets.forEach((dataset, datasetIndex) => {
      expandedData[datasetIndex].push(dataset.data?.[index] ?? null);
    });
    if (index >= labels.length - 1) return;
    const start = Number(funding.data?.[index]);
    const end = Number(funding.data?.[index + 1]);
    if (!Number.isFinite(start) || !Number.isFinite(end) || start * end >= 0) return;
    const ratio = Math.abs(start) / (Math.abs(start) + Math.abs(end));
    expandedLabels.push(interpolateChartLabel(label, labels[index + 1], ratio));
    datasets.forEach((dataset, datasetIndex) => {
      const left = Number(dataset.data?.[index]);
      const right = Number(dataset.data?.[index + 1]);
      expandedData[datasetIndex].push(
        dataset.label === "Funding Z"
          ? 0
          : Number.isFinite(left) && Number.isFinite(right)
            ? left + (right - left) * ratio
            : null,
      );
    });
  });
  return {
    labels: expandedLabels,
    datasets: datasets.map((dataset, index) => ({ ...dataset, data: expandedData[index] })),
  };
}

export function splitFundingZSeries(values) {
  return {
    positive: (values || []).map((value) => {
      const numeric = Number(value);
      return Number.isFinite(numeric) && numeric >= 0 ? numeric : null;
    }),
    negative: (values || []).map((value) => {
      const numeric = Number(value);
      return Number.isFinite(numeric) && numeric <= 0 ? numeric : null;
    }),
  };
}

function finiteSeriesPointCount(values) {
  return (values || []).reduce((count, value) => {
    if (value === null || value === undefined || value === "") return count;
    return Number.isFinite(Number(value)) ? count + 1 : count;
  }, 0);
}

// 2026-07-23: single-series line chart for the 聚合 OI 90D view.
// Sourced from dashboard.futures.charts.leverage_pressure_timeline, but
// rendered separately because allCharts() does not include this derived
// chart (it would conflict with the 3-dataset time-series chart on the
// summary section).
function renderAggregateOiSingleChart() {
  const source = dashboard?.futures?.charts?.leverage_pressure_timeline;
  if (!source) return;
  const labels = Array.isArray(source.labels) ? source.labels : [];
  const oiSeries = (source.datasets || []).find((item) => item.label === "聚合 OI");
  if (!oiSeries || !Array.isArray(oiSeries.data) || !labels.length) return;
  const canvas = document.getElementById("btc-chart-aggregate_oi_90d");
  if (!canvas) return;
  const color = CHART_COLORS["聚合 OI"] ?? FALLBACK_PALETTE[0];
  const dataset = lineDataset(
    "聚合 OI",
    oiSeries.data,
    color,
    {
      yAxisID: "y_oi",
      valueFormat: oiSeries.value_format || "compact_usd",
      unit: oiSeries.unit || "USD",
      fill: true,
      tension: 0.18,
    },
  );
  renderChart(
    "btc-derivatives-aggregate_oi_90d",
    canvas,
    {
      type: "line",
      axes: {
        y_oi: {
          profile: "volume",
          position: "left",
          unit: "USD",
          padding_ratio: 0.08,
        },
      },
      annotations: [],
      data: { labels, datasets: [dataset] },
      options: {},
    },
  );
}

function renderSingleChart(chartId) {
  const chart = allCharts()[chartId];
  if (!chart || chart.status !== "ok" || Number(chart.metadata?.data_points || 0) <= 0) return;
  const canvas = document.getElementById(`btc-chart-${chartId}`);
  const expanded = expandFundingZeroCrossings(chart.labels || [], chart.datasets || []);
  const datasets = expanded.datasets.flatMap((dataset, index) => {
    const color = CHART_COLORS[dataset.label] ?? FALLBACK_PALETTE[index % FALLBACK_PALETTE.length];
    const extra = {
      yAxisID: dataset.y_axis_id || "y",
      valueFormat: dataset.value_format,
      unit: dataset.unit,
      ...(dataset.style || {}),
    };
    if (dataset.chart_type !== "bar" && finiteSeriesPointCount(dataset.data) === 1) {
      extra.pointRadius = Math.max(Number(extra.pointRadius) || 0, 4);
      extra.pointHoverRadius = Math.max(Number(extra.pointHoverRadius) || 0, 6);
      extra.pointHitRadius = Math.max(Number(extra.pointHitRadius) || 0, 18);
    }
    const rendered = dataset.chart_type === "bar"
      ? barDataset(dataset.label, dataset.data, color, extra)
      : lineDataset(dataset.label, dataset.data, color, extra);
    if (chartId === "options_risk_premium_history") {
      rendered.hidden = !datasetVisibleInRiskMode(dataset.label);
      rendered.modeHidden = rendered.hidden;
    }
    if (dataset.label !== "Funding Z") return [rendered];
    const split = splitFundingZSeries(dataset.data);
    const positive = lineDataset(dataset.label, split.positive, color, {
      ...extra,
      borderDash: [],
      spanGaps: false,
    });
    const negative = lineDataset(dataset.label, split.negative, color, {
      ...extra,
      borderDash: [6, 4],
      spanGaps: false,
    });
    negative.fundingZLegendDuplicate = true;
    positive._fundingZSibling = [positive, negative];
    negative._fundingZSibling = [positive, negative];
    positive._fundingZSiblingRef = positive;
    negative._fundingZSiblingRef = negative;
    return [positive, negative];
  });
  // Resolve the actual datasetIndex assigned by flatMap → Chart.js so the
  // legend.onClick hook can flip both Funding Z siblings together.
  datasets.forEach((entry, datasetIndex) => {
    entry.__index = datasetIndex;
  });
  const legendFilter = (item, data) =>
    !data.datasets[item.datasetIndex]?.modeHidden
    && !data.datasets[item.datasetIndex]?.fundingZLegendDuplicate;
  renderChart(`btc-derivatives-${chartId}`, canvas, {
    type: chart.type === "mixed" ? "line" : chart.type,
    axes: chart.axes || {},
    annotations: chart.annotations || [],
    data: { labels: expanded.labels, datasets },
    options: {
      scales: expanded.labels.length === 1
        ? { x: { offset: true } }
        : {},
      plugins: {
        legend: {
          labels: {
            filter: legendFilter,
          },
          // 2026-07-25: Funding Z is split into positive/negative
          // datasets; the legend filter only hides the duplicate
          // label, but a click on the visible entry would otherwise
          // only toggle the positive dataset, leaving the dashed
          // negative line still drawn. We override onClick so the
          // sibling is flipped in lock-step.
          onClick(e, legendItem, legend) {
            const chart = legend.chart;
            const ds = chart.data.datasets[legendItem.datasetIndex];
            if (ds && ds._fundingZSibling && ds._fundingZSibling.length > 1) {
              const siblings = ds._fundingZSibling;
              // If any sibling is currently visible, the user's intent
              // on clicking the legend entry is to hide the line. If all
              // are already hidden, the intent is to show it again.
              const anyVisible = siblings.some(
                (sibling) => sibling.__index !== undefined
                  && chart.isDatasetVisible(sibling.__index),
              );
              const next = !anyVisible;
              for (const sibling of siblings) {
                if (sibling.__index !== undefined) {
                  chart.setDatasetVisibility(sibling.__index, next);
                }
              }
              chart.update();
              return;
            }
            // Default Chart.js click: toggle just this dataset.
            const idx = legendItem.datasetIndex;
            if (typeof idx !== "number") return;
            chart.setDatasetVisibility(idx, !chart.isDatasetVisible(idx));
            chart.update();
          },
        },
      },
    },
  });
}

function renderCharts() {
  Object.keys(allCharts()).forEach(renderSingleChart);
  // 2026-07-23: the new aggregate_oi_90d chart is derived from
  // leverage_pressure_timeline (single dataset) and not in allCharts();
  // render it explicitly so it picks up the canvas we emitted in
  // renderAggregateOiChart().
  if (document.getElementById("btc-chart-aggregate_oi_90d")) {
    renderAggregateOiSingleChart();
  }
}

function updateRiskChartHeaderInsight() {
  const card = document
    .querySelector('[data-risk-chart-mode="hedge_cost"]')
    ?.closest(".btc-chart-card");
  const insight = card?.querySelector(".btc-chart-insight");
  if (insight) {
    insight.textContent = chartInsight("options_risk_premium_history");
  }
}

function updateFiltersFromControls(form) {
  const values = new FormData(form);
  filters = {
    window: String(values.get("window") || ""),
    expiryMode: String(values.get("expiry_mode") || "fixed"),
    maturityBucket: String(values.get("maturity_bucket") || "60D"),
    selectedExpiry: String(values.get("expiry_mode") || "fixed") === "fixed"
      ? String(values.get("selected_expiry") || "")
      : "",
    strikeRangePct: String(values.get("strike_range_pct") || "30"),
  };
}

function bindEvents() {
  document.getElementById("btc-refresh")?.addEventListener("click", () => {
    loadDashboard({ refresh: true }).catch(handleLoadError);
  });
  document.getElementById("btc-probe-sources")?.addEventListener("click", async (event) => {
    const button = event.currentTarget;
    button.disabled = true;
    button.textContent = "探测中…";
    try {
      await api.probeBtcDerivativesSources({ timeoutMs: 45000 });
      await loadDashboard({ refresh: true });
    } catch (error) {
      handleLoadError(error);
    } finally {
      button.disabled = false;
      button.textContent = "一键探测数据源";
    }
  });
  document.getElementById("btc-chart-controls")?.addEventListener("change", (event) => {
    updateFiltersFromControls(event.currentTarget);
    loadDashboard().catch(handleLoadError);
  });
  document.querySelectorAll("[data-risk-chart-mode]").forEach((button) => {
    button.addEventListener("click", () => {
      riskChartMode = button.dataset.riskChartMode || "sentiment";
      document.querySelectorAll("[data-risk-chart-mode]").forEach((item) => {
        item.classList.toggle(
          "is-active",
          item.dataset.riskChartMode === riskChartMode,
        );
      });
      updateRiskChartHeaderInsight();
      renderSingleChart("options_risk_premium_history");
    });
  });
  document.getElementById("btc-hedge-form")?.addEventListener("submit", async (event) => {
    event.preventDefault();
    const form = new FormData(event.currentTarget);
    const valueOrNull = (name) => {
      const value = Number(form.get(name));
      return Number.isFinite(value) && value > 0 ? value : null;
    };
    const payload = {
      portfolio_type: form.get("portfolio_type"),
      underlying: "BTC",
      spot_price: valueOrNull("spot_price"),
      grid_lower: valueOrNull("grid_lower"),
      grid_upper: valueOrNull("grid_upper"),
      net_notional_usd: Number(form.get("net_notional_usd") || 0),
      hedge_budget_usd: Number(form.get("hedge_budget_usd") || 0),
      preferred_expiry_bucket: form.get("preferred_expiry_bucket"),
      allow_debit_spread: form.get("allow_debit_spread") === "true",
      iv_state: dashboard?.hedge_context?.iv_state,
      liquidity_state: dashboard?.hedge_context?.liquidity_state,
    };
    try {
      hedgePlan = await api.planBtcDerivativeHedge(payload);
      setRoot(renderPageShell(statusBanner("有限风险保护方案已更新", "neutral")));
      bindEvents();
      renderCharts();
    } catch (error) {
      showError(error);
    }
  });
}

function handleLoadError(error) {
  if (error?.name !== "AbortError") {
    showError(error);
  }
}

async function waitForRefreshJob(receipt, signal) {
  if (!receipt?.job_id) return receipt;
  let state = receipt;
  for (let attempt = 0; attempt < 80; attempt += 1) {
    if (state.status === "success") return state;
    if (state.status === "failed" || state.status === "missing") {
      throw new Error(state.error || "刷新任务失败");
    }
    const delay = Math.max(250, Number(state.poll_after_ms) || 750);
    await new Promise((resolve, reject) => {
      const timer = setTimeout(resolve, delay);
      signal?.addEventListener("abort", () => {
        clearTimeout(timer);
        reject(new DOMException("Aborted", "AbortError"));
      }, { once: true });
    });
    state = await api.getRefreshJob(receipt.job_id, { signal });
  }
  throw new Error("刷新任务等待超时");
}

function showError(error) {
  console.error("btc derivatives page failed", error);
  setRoot(renderPageShell(statusBanner("衍生品数据读取失败，请稍后重试", "error")));
  bindEvents();
  renderCharts();
}

async function loadDashboard({ refresh = false } = {}) {
  requestController?.abort();
  requestController = new AbortController();
  if (!dashboard) {
    setRoot(`<div class="btc-derivatives-page">${renderHero({ banner: statusBanner("正在读取衍生品快照", "loading") })}</div>`);
  }
  if (refresh) {
    const receipt = await api.refreshBtcDerivativesDashboard(
      dashboardQuery(),
      { signal: requestController.signal },
    );
    await waitForRefreshJob(receipt, requestController.signal);
    dashboard = await api.getBtcDerivativesDashboard(
      dashboardQuery(),
      { signal: requestController.signal, force: true },
    );
  } else {
    dashboard = await api.getBtcDerivativesDashboard(
      dashboardQuery(),
      { signal: requestController.signal },
    );
    // Auto-fetch when initial read returns data_insufficient (matches analysis.js
    // pattern for the technical indicator page). Only attempt once per page load
    // to avoid loops; subsequent user clicks on the refresh button still work.
    if (dashboard?.snapshot_state === "data_insufficient" && !autoRefreshAttempted) {
      autoRefreshAttempted = true;
      const banner = statusBanner("首次加载自动拉取衍生品实时数据", "info");
      setRoot(`<div class="btc-derivatives-page">${renderHero({ banner })}</div>`);
      try {
        const receipt = await api.refreshBtcDerivativesDashboard(
          dashboardQuery(),
          { signal: requestController.signal },
        );
        await waitForRefreshJob(receipt, requestController.signal);
        dashboard = await api.getBtcDerivativesDashboard(
          dashboardQuery(),
          { signal: requestController.signal, force: true },
        );
      } catch (refreshError) {
        if (refreshError?.name !== "AbortError") {
          console.warn("btc-derivatives:auto-refresh:failed", refreshError);
        }
      }
    }
  }
  syncFiltersFromDashboard();
  destroyChartsForPage("btc-derivatives-");
  setRoot(renderPageShell("", refresh ? "衍生品快照已刷新" : ""));
  await hydrateKnowledgeTooltips(document.getElementById("page-root"));
  bindEvents();
  renderCharts();
}

export async function renderBtcDerivatives() {
  autoRefreshAttempted = false;
  if (!pageGuideFab) {
    pageGuideFab = mountPageGuide("btc-derivatives");
  }
  const ready = loadDashboard().catch((error) => {
    if (error?.name !== "AbortError") showError(error);
  });
  scheduleAutoRefresh();
  return {
    ready,
    unmount() {
      clearAutoRefresh();
      if (pageGuideFab) {
        pageGuideFab.unmount();
        pageGuideFab = null;
      }
      requestController?.abort();
      destroyChartsForPage("btc-derivatives-");
    },
    pause() {
      clearAutoRefresh();
    },
    resume() {
      scheduleAutoRefresh();
    },
  };
}

function clearAutoRefresh() {
  if (autoRefreshTimer) {
    clearTimeout(autoRefreshTimer);
    autoRefreshTimer = null;
  }
}

function scheduleAutoRefresh() {
  if (autoRefreshTimer) return;
  autoRefreshTimer = setTimeout(async () => {
    autoRefreshTimer = null;
    if (typeof document !== "undefined" && document.hidden) {
      scheduleAutoRefresh();
      return;
    }
    try {
      await loadDashboard();
    } catch (error) {
      if (error?.name !== "AbortError") {
        console.warn("btc-derivatives:auto-refresh", error);
      }
    } finally {
      scheduleAutoRefresh();
    }
  }, AUTO_REFRESH_MS);
}
