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
  const expiries = dashboard?.options?.expiries || [];
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
          ${selectOptions(["constant_maturity", "fixed"], filters.expiryMode, (value) => value === "fixed" ? "固定到期日" : "恒定期限")}
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
        <article class="card btc-decision-card" data-state="${escapeHtml(card.state)}">
          <div class="btc-card-kicker">
            <span>${escapeHtml(card.label)}</span>
            <b>${escapeHtml(confidenceLabel(card.confidence))}</b>
          </div>
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

function inferenceBlock(id) {
  return (dashboard?.joint_analysis?.inference_blocks || []).find((block) => block.id === id) || {};
}

function chartInsight(chartId) {
  const map = {
    leverage_pressure_timeline: "杠杆方向",
    exchange_crowding_snapshot: "交易所拥挤",
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
    <article class="card btc-chart-card btc-card-span-${span} btc-chart-density-${escapeHtml(density)}">
      <div class="btc-chart-head">
        <div>
          <p class="eyebrow">图表</p>
          <h2>${escapeHtml(chart.title || chartId)}</h2>
          ${windowLabel ? `<small>${escapeHtml(windowLabel)} · ${number(metadata.data_points, 0)} 个数据点${sourceLabel ? ` · 来源 ${escapeHtml(sourceLabel)}` : ""}</small>` : ""}
        </div>
        <div class="btc-chart-head-actions">
          ${riskModeControls}
          <p class="btc-chart-insight">${escapeHtml(chartInsight(chartId))}</p>
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
        <p>${escapeHtml(sectionInterpretation(section.id))}</p>
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
      ${renderChartToolbar()}
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
  }
  syncFiltersFromDashboard();
  destroyChartsForPage("btc-derivatives-");
  setRoot(renderPageShell("", refresh ? "衍生品快照已刷新" : ""));
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
