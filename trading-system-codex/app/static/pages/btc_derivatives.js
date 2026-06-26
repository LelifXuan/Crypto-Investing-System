import { api } from "../core/api.js";
import {
  escapeHtml,
  formatDateTime,
  formatNumber,
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

const CHART_COLORS = [
  "#0f766e",
  "#c35a1d",
  "#2563eb",
  "#8b5cf6",
  "#b7791f",
  "#64748b",
];
const FALLBACK_CHART_IDS = [
  "leverage_pressure_timeline",
  "exchange_crowding_snapshot",
  "term_structure",
  "strike_surface",
  "key_levels_history",
  "options_risk_premium_history",
];

let requestController = null;
let dashboard = null;
let hedgePlan = null;
let riskChartMode = "sentiment";
let filters = {
  window: "",
  expiryMode: "constant_maturity",
  maturityBucket: "60D",
  selectedExpiry: "",
  strikeRangePct: "30",
};

function number(value, digits = 2) {
  return value === null || value === undefined
    ? "-"
    : formatNumber(Number(value), digits);
}

function percent(value, digits = 2) {
  const numeric = Number(value);
  return Number.isFinite(numeric) ? `${formatNumber(numeric * 100, digits)}%` : "-";
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
  return {
    ...(dashboard?.futures?.charts || {}),
    ...(dashboard?.options?.charts || {}),
  };
}

function syncFiltersFromDashboard() {
  const selection = dashboard?.selection || {};
  filters = {
    window: selection.window || "",
    expiryMode: selection.expiry_mode || "constant_maturity",
    maturityBucket: selection.maturity_bucket || "60D",
    selectedExpiry: selection.selected_expiry || "",
    strikeRangePct: selection.strike_range_pct || "30",
  };
}

function renderHero(banner = "") {
  return `
    <section class="hero-card btc-derivatives-hero">
      <div>
        <p class="eyebrow">BTC DERIVATIVES COCKPIT</p>
        <h1>杠杆、波动率与保护决策</h1>
        <p>观察当前市场的杠杆进入、拥挤程度、保护需求与关键持仓价位迁移。</p>
      </div>
      <div class="btc-hero-actions">
        <span>${escapeHtml(displayState(dashboard?.snapshot_state || dashboard?.data_quality?.mode))}</span>
        <button class="button compact" id="btc-refresh" type="button">刷新衍生品快照</button>
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
  const expiries = dashboard?.options?.expiries || [];
  return `
    <form class="card btc-chart-toolbar" id="btc-chart-controls">
      <label>
        <span>时间窗口</span>
        <select name="window">
          ${selectOptions(["", "30D", "90D", "180D", "365D"], filters.window, (value) => ({
            "": "全部图表默认",
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
          ${selectOptions(["constant_maturity", "fixed"], filters.expiryMode, (value) => value === "fixed" ? "固定到期日" : "Constant Maturity")}
        </select>
      </label>
      <label>
        <span>期限桶</span>
        <select name="maturity_bucket">
          ${selectOptions(["30D", "60D", "90D"], filters.maturityBucket)}
        </select>
      </label>
      <label>
        <span>期权链到期日</span>
        <select name="selected_expiry">
          ${selectOptions(expiries, filters.selectedExpiry)}
        </select>
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
  const cards = dashboard?.cards || [];
  const confidenceLabel = { high: "高置信度", medium: "中等置信度", low: "低置信度" };
  return `
    <section class="btc-decision-grid" aria-label="衍生品决策摘要">
      ${cards.map((card) => `
        <article class="card btc-decision-card" data-state="${escapeHtml(card.state)}">
          <div class="btc-card-kicker">
            <span>${escapeHtml(card.label)}</span>
            <b>${escapeHtml(confidenceLabel[card.confidence] || "低置信度")}</b>
          </div>
          <h2>${escapeHtml(card.conclusion || card.summary)}</h2>
          <p class="btc-decision-label">依据</p>
          <div class="btc-evidence-chips">
            ${(card.basis || []).slice(0, 5).map((item) => `<span>${escapeHtml(item)}</span>`).join("") || "<span>暂无有效依据</span>"}
          </div>
          <p class="btc-decision-impact"><strong>影响：</strong>${escapeHtml(card.implication || "等待更多有效数据。")}</p>
        </article>
      `).join("")}
    </section>
  `;
}

function chartCard(chartId, layout = {}) {
  const chart = allCharts()[chartId] || {};
  const span = Number(layout.span) || 12;
  const density = layout.density || "standard";
  const metadata = chart.metadata || {};
  const sourceLabel = (metadata.providers || []).join(" / ");
  const updatedLabel = metadata.updated_at ? formatDateTime(metadata.updated_at) : "";
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
    <article class="card btc-chart-card btc-card-span-${span} btc-chart-density-${escapeHtml(density)}">
      <div class="btc-chart-head">
        <div>
          <p class="eyebrow">CHART</p>
          <h2>${escapeHtml(chart.title || chartId)}</h2>
          ${windowLabel ? `<small>${escapeHtml(windowLabel)} · ${number(metadata.data_points, 0)} 个数据点</small>` : ""}
        </div>
        <div class="btc-chart-head-actions">
          ${sourceLabel ? `<small>来源 ${escapeHtml(sourceLabel)} · ${escapeHtml(updatedLabel)} · ${escapeHtml(displayState(metadata.quality))}</small>` : ""}
          ${riskModeControls}
          <span>${chart.status === "ok" ? "可用" : "数据不足"}</span>
        </div>
      </div>
      <div class="chart-wrap btc-chart-wrap">
        <canvas id="btc-chart-${escapeHtml(chartId)}" aria-label="${escapeHtml(chart.title || chartId)}"></canvas>
        ${chart.status !== "ok" ? `<div class="btc-chart-empty">${escapeHtml(chart.empty_reason || "暂无数据")}</div>` : ""}
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
      charts: ["exchange_crowding_snapshot", "term_structure"],
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

function renderChartSections() {
  const sections = dashboard?.chart_layout?.sections || fallbackSections();
  const cards = dashboard?.chart_layout?.cards || {};
  const knownCharts = new Set(FALLBACK_CHART_IDS);
  return sections.map((section) => `
    <section class="btc-chart-section" data-chart-section="${escapeHtml(section.id)}">
      <div class="btc-section-heading">
        <div>
          <p class="eyebrow">${escapeHtml(section.id)}</p>
          <h2>${escapeHtml(section.title)}</h2>
        </div>
        ${section.id === "summary" ? "<p>先识别杠杆压力，再检查期限、关键行权价与保护成本。</p>" : ""}
      </div>
      <div class="btc-dashboard-grid">
        ${(section.charts || [])
          .filter((chartId) => knownCharts.has(chartId) && allCharts()[chartId])
          .map((chartId) => chartCard(chartId, cards[chartId]))
          .join("")}
      </div>
    </section>
  `).join("");
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
  const confidenceLabel = { high: "高", medium: "中等", low: "低" };
  return `
    <section class="card btc-evidence-layer">
      <div class="btc-section-heading">
        <div><p class="eyebrow">MARKET INFERENCE</p><h2>当前市场推定</h2></div>
        <p>综合置信度：${escapeHtml(confidenceLabel[analysis.confidence] || "低")}</p>
      </div>
      <div class="btc-inference-grid">
        ${blocks.map((block) => `
          <article data-tone="${escapeHtml(block.tone || "neutral")}">
            <span>${escapeHtml(block.title)}</span>
            <h3>${escapeHtml(block.conclusion || "当前数据不足以形成清晰判断")}</h3>
            <p class="btc-inference-basis"><strong>依据：</strong>${escapeHtml((block.basis || []).join("；") || "暂无有效依据")}</p>
            <p><strong>影响：</strong>${escapeHtml(block.implication || "等待更多有效数据。")}</p>
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
    <section class="btc-section">
      <div class="btc-section-heading">
        <div><p class="eyebrow">FINITE-RISK HEDGE</p><h2>网格与现货保护规划</h2></div>
        <p>结合当前 IV、关键价位与保护成本，比较有限风险保护和降低敞口。</p>
      </div>
      <div class="btc-hedge-layout">
        <form class="card btc-hedge-grid" id="btc-hedge-form">
          <label><span>组合类型</span><select name="portfolio_type"><option value="short_grid">空网格</option><option value="long_grid">多网格</option><option value="spot_only">现货</option><option value="neutral_grid">中性网格</option></select></label>
          <label><span>现价</span><input name="spot_price" type="number" min="1" value="${escapeHtml(String(context.spot_price || 61200))}" required></label>
          <label><span>网格下沿</span><input name="grid_lower" type="number" min="1" value="45000"></label>
          <label><span>网格上沿</span><input name="grid_upper" type="number" min="1" value="62000"></label>
          <label><span>净名义金额 USD</span><input name="net_notional_usd" type="number" min="0" value="5000"></label>
          <label><span>保护预算 USD</span><input name="hedge_budget_usd" type="number" min="0" value="150"></label>
          <label><span>到期桶</span><select name="preferred_expiry_bucket"><option>30D</option><option selected>60D</option><option>90D</option></select></label>
          <label><span>有限风险价差</span><select name="allow_debit_spread"><option value="true">允许</option><option value="false">不使用</option></select></label>
          <button class="button" type="submit">生成保护方案</button>
        </form>
        ${renderHedgePlan()}
      </div>
    </section>
  `;
}

function renderHedgePlan() {
  if (!hedgePlan) {
    return `
      <article class="card btc-hedge-result">
        <p class="eyebrow">PLAN</p>
        <h2>填写你的现货或网格暴露</h2>
        <p>系统将根据当前 IV、关键墙位和保护成本，比较买入保护、借记价差与降低网格敞口。</p>
      </article>
    `;
  }
  return `
    <article class="card btc-hedge-result">
      <p class="eyebrow">PLAN</p>
      <h2>${escapeHtml(hedgePlan.label)}</h2>
      <p>${escapeHtml(hedgePlan.explanation)}</p>
      <div class="btc-plan-metrics">
        <span>建议动作 <b>${escapeHtml(hedgePlan.label)}</b></span>
        <span>保护区 <b>${escapeHtml(hedgePlan.protection_zone || "-")}</b></span>
        <span>预计成本 <b>${money(hedgePlan.estimated_premium_usd)}</b></span>
        <span>预算 <b>${hedgePlan.budget_ok === null ? "未判断" : hedgePlan.budget_ok ? "范围内" : "超预算"}</b></span>
      </div>
      ${(hedgePlan.warnings || []).map((item) => `<p class="btc-warning">${escapeHtml(item)}</p>`).join("")}
    </article>
  `;
}

function renderDataQuality() {
  const quality = dashboard?.data_quality || {};
  const fixtureWarning = quality.mode === "fixture"
    ? "当前为示例数据，仅用于页面与计算测试，不能用于真实交易判断。"
    : "";
  return `
    <section class="card btc-data-quality">
      <div class="btc-section-heading">
        <div><p class="eyebrow">DATA QUALITY</p><h2>数据质量</h2></div>
        <p>${escapeHtml(quality.status || "data_insufficient")} · ${escapeHtml(quality.mode || "unknown")} · 历史${quality.history_available ? "可用" : "不足"}</p>
      </div>
      ${fixtureWarning ? `<p class="btc-fixture-warning">${escapeHtml(fixtureWarning)}</p>` : ""}
      <details class="btc-quality-details">
        <summary>查看 Provider、缺失字段与陈旧快照</summary>
        <div class="btc-quality-grid">
          <article><h3>Provider</h3><p>${escapeHtml((quality.providers || []).map((item) => item.name).join(" / ") || "无")}</p></article>
          <article><h3>缺失字段</h3><p>${escapeHtml((quality.missing_fields || []).join(" / ") || "无")}</p></article>
          <article><h3>陈旧快照</h3><p>${escapeHtml((quality.stale_snapshots || []).join(" / ") || "无")}</p></article>
        </div>
        <ul>${(quality.warnings || []).map((item) => `<li>${escapeHtml(item)}</li>`).join("")}</ul>
      </details>
      <small>生成时间：${escapeHtml(formatDateTime(dashboard?.generated_at))}</small>
    </section>
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
        <div><p class="eyebrow">DATA QUALITY</p><h2>数据源状态</h2></div>
        <div class="btc-quality-actions">
          <span class="btc-quality-badge" data-state="${escapeHtml(snapshotState)}">${escapeHtml(displayState(snapshotState))}</span>
          <button id="btc-probe-sources" class="secondary-button" type="button">一键探测数据源</button>
        </div>
      </div>
      <p class="${snapshotState === "live" ? "" : "btc-fixture-warning"}">${escapeHtml(stateMessage)}</p>
      <div class="btc-provider-grid">
        ${providers.map((item) => `
          <article class="btc-provider-card" data-status="${escapeHtml(item.status || "unknown")}">
            <div><strong>${escapeHtml(item.provider || item.name || "unknown")}</strong><span>${escapeHtml(displayState(item.status))}</span></div>
            <p>${escapeHtml((item.capabilities || []).join(" / ") || "能力未知")}</p>
            <small>延迟 ${item.latency_ms == null ? "—" : `${Math.round(item.latency_ms)}ms`} · 最近成功 ${escapeHtml(formatDateTime(item.last_success_at))}</small>
            ${item.last_error ? `<small class="btc-provider-error">${escapeHtml(item.last_error)}</small>` : ""}
            ${item.circuit_open_until ? `<small>熔断至 ${escapeHtml(formatDateTime(item.circuit_open_until))}</small>` : ""}
          </article>
        `).join("") || "<p>尚无数据源健康记录，可点击探测。</p>"}
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
      <small>生成时间：${escapeHtml(formatDateTime(dashboard?.generated_at))}</small>
    </section>
  `;
}

function renderMethodNotes() {
  return `
    <details class="btc-method-notes">
      <summary>方法与边界</summary>
      <div>
        <p>最大痛点用于观察持仓分布迁移，不作为价格预测。</p>
        <p>期权墙用于观察持仓集中与对冲敏感区，不作为确定支撑或阻力。</p>
        <p>页面不执行下单，不推荐裸卖期权，也不把比例价差描述为安全对冲。</p>
      </div>
    </details>
  `;
}

function renderPageShell(banner = "") {
  return `
    <div class="btc-derivatives-page">
      ${renderHero(banner)}
      ${renderDecisionCards()}
      ${renderChartToolbar()}
      ${renderKeyLevelStrip()}
      ${renderChartSections()}
      ${renderEvidenceLayer()}
      ${renderHedgePlanner()}
      ${renderDetailsDrawer()}
      ${renderLiveSourceStatus()}
      ${renderMethodNotes()}
    </div>
  `;
}

function datasetVisibleInRiskMode(label) {
  const hedgeCostLabels = new Set(["Call保护成本", "Put保护成本", "借记价差成本"]);
  return riskChartMode === "hedge_cost"
    ? hedgeCostLabels.has(label)
    : !hedgeCostLabels.has(label);
}

function renderSingleChart(chartId) {
  const chart = allCharts()[chartId];
  if (!chart || chart.status !== "ok") return;
  const canvas = document.getElementById(`btc-chart-${chartId}`);
  const datasets = (chart.datasets || []).map((dataset, index) => {
    const color = CHART_COLORS[index % CHART_COLORS.length];
    const extra = {
      yAxisID: dataset.y_axis_id || "y",
      valueFormat: dataset.value_format,
      unit: dataset.unit,
      ...(dataset.style || {}),
    };
    const rendered = dataset.chart_type === "bar"
      ? barDataset(dataset.label, dataset.data, color, extra)
      : lineDataset(dataset.label, dataset.data, color, extra);
    if (chartId === "options_risk_premium_history") {
      rendered.hidden = !datasetVisibleInRiskMode(dataset.label);
      rendered.modeHidden = rendered.hidden;
    }
    return rendered;
  });
  renderChart(`btc-derivatives-${chartId}`, canvas, {
    type: chart.type === "mixed" ? "line" : chart.type,
    axes: chart.axes || {},
    annotations: chart.annotations || [],
    data: { labels: chart.labels || [], datasets },
    options: chartId === "options_risk_premium_history"
      ? {
          plugins: {
            legend: {
              labels: {
                filter: (item, data) =>
                  !data.datasets[item.datasetIndex]?.modeHidden,
              },
            },
          },
        }
      : {},
  });
}

function renderCharts() {
  Object.keys(allCharts()).forEach(renderSingleChart);
}

function updateFiltersFromControls(form) {
  const values = new FormData(form);
  filters = {
    window: String(values.get("window") || ""),
    expiryMode: String(values.get("expiry_mode") || "constant_maturity"),
    maturityBucket: String(values.get("maturity_bucket") || "60D"),
    selectedExpiry: String(values.get("selected_expiry") || ""),
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
    setRoot(`<div class="btc-derivatives-page">${renderHero(statusBanner("正在读取衍生品快照", "loading"))}</div>`);
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
  }
  syncFiltersFromDashboard();
  destroyChartsForPage("btc-derivatives-");
  setRoot(renderPageShell(refresh ? statusBanner("衍生品快照已刷新", "neutral") : ""));
  bindEvents();
  renderCharts();
}

export async function renderBtcDerivatives() {
  const ready = loadDashboard().catch((error) => {
    if (error?.name !== "AbortError") showError(error);
  });
  return {
    ready,
    unmount() {
      requestController?.abort();
      destroyChartsForPage("btc-derivatives-");
    },
    pause() {},
    resume() {},
  };
}
