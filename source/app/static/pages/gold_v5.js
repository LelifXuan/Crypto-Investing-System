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
import {
  escapeHtml,
  formatNumber,
  impactChip,
  revealStagger,
  setRoot,
  skeletonPhaseStyle,
} from "../core/dom.js";
import { waitForAbortableDelay, waitForPrecomputeTask } from "../core/precompute.js";
import { barDataset, destroyChartsForPage, getSeriesColor, lineDataset, renderChart } from "../ui/charts.js";
import { renderGovernanceLedger } from "../ui/governanceLedger.js";

const CHART_PREFIX = "gold-chart-";

let controller = null;
let latestData = null;
let loadVersion = 0;
let initialGoldRevealPlayed = false;

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
// Amounts are denominated in the policy's own currency
// (gold_policy_versions.base_currency), so the unit comes from the payload
// rather than a hard-coded 元. The configured policy reports in USD, and
// labelling a USD 500 order "500 元" misstates the size of the action.
const CURRENCY_LABELS = { CNY: "元", RMB: "元" };

function currencyLabel(code) {
  const key = String(code ?? "").trim().toUpperCase();
  if (!key) return "";
  return CURRENCY_LABELS[key] || key;
}

function money(v, d, currency) {
  // null / "" mean "no amount yet". Number(null) is 0, so without this guard a
  // missing amount rendered as a real "0" order instead of "—" — the same
  // coercion rule monitoring.js's macroDisplayValue documents.
  if (v === null || v === undefined || v === "") return "—";
  const n = Number(v);
  if (!Number.isFinite(n)) return "—";
  const amount = formatNumber(n, d || 0);
  const label = currencyLabel(currency);
  return label ? `${amount} ${label}` : amount;
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
    ? "尚未配置组合策略。请在下方表单填写并保存，保存后本页自动刷新。"
    : `宏观判断: ${scenarioLabel(active || (snapshotOk ? "MACRO_NEUTRAL" : "DATA_DEGRADED"))}`;
  const shock = activeList.includes("LIQUIDITY_SHOCK");

  return `
    <section class="gold-hero">
      <article class="card analysis-hero-card">
        <div class="card-head-inline">
          <div>
            <p class="eyebrow">GOLD ALLOCATION</p>
            <h2 class="page-display-title">黄金配置 Workbench</h2>
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
        <canvas id="gold-canvas-${chartId.replace(CHART_PREFIX, "")}" role="img" aria-label="${escapeHtml(title)}"></canvas>
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

function renderFormulaBox(base, dip, currency) {
  // V4 had inline font-size:10px labels; V5 spec bumps to 13/18 (styles.css .gold-formula-item).
  const baseAmount = base?.amount;
  const dipAmount = dip?.amount;
  return `
    <div class="gold-formula-box">
      <div class="gold-formula-item"><span>基础定投</span><b>${money(baseAmount, 0, currency)}</b></div>
      <div class="gold-formula-item"><span>回撤加仓</span><b>${money(dipAmount, 0, currency)}</b></div>
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

function renderRecommendRow(base, dip, currency) {
  const code = base?.status === "EXECUTE"
    ? "EXECUTE"
    : (dip?.status === "READY_FIXED_ADD" ? "READY_FIXED_ADD" : base?.status);
  return `
    <div class="gold-recommend-row">
      <div>
        <p class="eyebrow">TODAY</p>
        <span class="gold-recommend-label">今日建议金额</span>
        <div class="gold-recommend-amount">${money(base?.amount, 0, currency)}</div>
      </div>
      <span class="chip">${chipForStatus(code, "今日最优基础动作")}</span>
    </div>
  `;
}

function renderSpotDca(data) {
  const strategic = data?.strategic_allocation || {};
  const base = data?.base_dca || {};
  const dip = data?.dip_add || {};
  const currency = data?.portfolio?.base_currency;
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
        ${renderRecommendRow(base, dip, currency)}
        ${renderWeightRow(strategic)}
      </div>
      <div class="gold-dca-detail-grid">
        ${renderFormulaBox(base, dip, currency)}
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
  return {
    label,
    value: entry ? labelForFreshness(state) : "未配置",
    detail: entry ? formatSourceAge(entry.age_seconds) : "尚未接入数据源",
    state,
  };
}

function governanceSnapshotItem(observed) {
  const ready = !!observed && observed !== "—";
  return {
    label: "快照时间",
    value: ready ? observed : "等待快照",
    detail: ready ? "UTC · 当前研究快照" : "尚未生成有效快照",
    state: ready ? "fresh" : "missing",
    slot: "snapshot",
  };
}

function renderGovernance(data) {
  const manifest = data?.source_manifest || [];
  const observed = data?.snapshot?.observed_at || "—";
  const sourceKeys = ["gold_policy", "gold_spot_quote", "gold_derivatives"];
  const readyCount = sourceKeys.filter((sourceKey) => (
    manifest.find((entry) => entry?.source_key === sourceKey)?.freshness_state === "fresh"
  )).length;
  const items = [
    governanceSourceItem(manifest, "策略配置", "gold_policy"),
    governanceSourceItem(manifest, "XAUT 行情", "gold_spot_quote"),
    governanceSourceItem(manifest, "衍生品", "gold_derivatives"),
    governanceSnapshotItem(observed),
  ];
  return renderGovernanceLedger({
    variant: "gold",
    readyCount,
    totalCount: items.length,
    items,
  });
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
    <section class="gold-cockpit-header" aria-label="黄金配置决策概览">
      ${renderHero(data)}
      <section class="gold-workbench-grid">
        ${renderSpotDca(data)}
        ${renderContractRef(data)}
      </section>
    </section>
    ${hasChartSeries ? renderChartGrid() : renderChartGridEmptyState(data)}
    ${renderGovernance(data)}
    ${renderPolicyForm(data)}
  `;
}

// ----- Policy form — the write path for gold_policy_versions ----------------

function policyField(name, label, value, attrs = "") {
  // step="any": spot_price taught us that type=number defaults to step=1 and
  // browsers reject any decimal as "not a valid value". Policy money fields
  // are floats on the wire, so every numeric input carries step="any".
  return `
    <label><span>${escapeHtml(label)}</span><input name="${name}" type="number" step="any" value="${escapeHtml(String(value ?? ""))}" ${attrs}></label>
  `;
}

function renderPolicyForm(data) {
  const portfolio = data?.portfolio || {};
  const strategic = data?.strategic_allocation || {};
  const base = data?.base_dca || {};
  const dip = data?.dip_add || {};
  const current = {
    base_currency: portfolio.base_currency || "USD",
    portfolio_total: portfolio.portfolio_total || "",
    gold_current_value: portfolio.gold_current_value || "",
    available_cash: portfolio.available_cash || "",
    target_min: strategic.target_min || "",
    target_max: strategic.target_max || "",
    base_dca_amount: base.amount || "",
    fixed_dip_add_amount: dip.amount && dip.amount !== "0" ? dip.amount : "",
    cooldown_days: dip.cooldown_until ? "" : "14",
    quote_max_age_seconds: "300",
    confirmations_required: dip.confirmations?.required || "3",
    drawdown_threshold: dip.drawdown_threshold || "0.08",
  };
  const hasPolicy = !!(data?.snapshot?.status === "ok" || portfolio.policy_id);
  return `
    <section class="card gold-policy-form-card" aria-label="组合策略配置">
      <div class="card-head-inline">
        <div>
          <p class="eyebrow">POLICY</p>
          <p class="gold-card-title">${hasPolicy ? "组合策略（保存即生成新版本）" : "组合策略（首次配置）"}</p>
        </div>
        ${hasPolicy ? `<span class="chip">${impactChip("neutral", "当前版本", "版本 " + escapeHtml(String(portfolio.policy_version ?? "—")))}</span>` : ""}
      </div>
      <form class="gold-policy-form" id="gold-policy-form" novalidate>
        <fieldset class="gold-policy-section">
          <legend>组合</legend>
          ${policyField("portfolio_total", "组合总值", current.portfolio_total, "min=\"1\" required")}
          ${policyField("gold_current_value", "当前黄金市值", current.gold_current_value, "min=\"0\" required")}
          ${policyField("available_cash", "可用现金（可选）", current.available_cash, "min=\"0\"")}
          <label><span>计价币种</span><input name="base_currency" value="${escapeHtml(current.base_currency)}" maxlength="16" required></label>
        </fieldset>
        <fieldset class="gold-policy-section">
          <legend>目标权重带</legend>
          ${policyField("target_min", "下限（0-1）", current.target_min, "min=\"0\" max=\"1\" required")}
          ${policyField("target_max", "上限（0-1）", current.target_max, "min=\"0\" max=\"1\" required")}
        </fieldset>
        <fieldset class="gold-policy-section">
          <legend>执行纪律</legend>
          ${policyField("base_dca_amount", "基础定投金额", current.base_dca_amount, "min=\"1\" required")}
          ${policyField("fixed_dip_add_amount", "回撤加仓金额", current.fixed_dip_add_amount, "min=\"1\" required")}
          ${policyField("cooldown_days", "加仓冷却天数", current.cooldown_days, "min=\"0\" max=\"365\"")}
          ${policyField("quote_max_age_seconds", "行情最大延迟秒", current.quote_max_age_seconds, "min=\"30\" max=\"86400\"")}
          ${policyField("confirmations_required", "确认数", current.confirmations_required, "min=\"1\" max=\"10\"")}
          ${policyField("drawdown_threshold", "回撤阈值（0-1）", current.drawdown_threshold, "min=\"0\" max=\"1\"")}
        </fieldset>
        <div class="gold-policy-actions">
          <button class="button" type="submit"><span>保存策略</span></button>
          <p class="gold-policy-hint" data-policy-hint>保存即追加新版本，历史版本保留；保存后本页自动刷新。</p>
        </div>
      </form>
    </section>
  `;
}

function readPolicyForm(form) {
  const get = (name) => form.elements.namedItem(name)?.value;
  const num = (name) => {
    const raw = String(get(name) ?? "").trim();
    return raw === "" ? null : Number(raw);
  };
  return {
    base_currency: String(get("base_currency") ?? "USD").trim() || "USD",
    portfolio_total: num("portfolio_total"),
    gold_current_value: num("gold_current_value"),
    available_cash: num("available_cash"),
    target_min: num("target_min"),
    target_max: num("target_max"),
    base_dca_amount: num("base_dca_amount"),
    fixed_dip_add_amount: num("fixed_dip_add_amount"),
    cooldown_days: num("cooldown_days") ?? 14,
    quote_max_age_seconds: num("quote_max_age_seconds") ?? 300,
    confirmations_required: num("confirmations_required") ?? 3,
    drawdown_threshold: num("drawdown_threshold") ?? 0.08,
  };
}

function validatePolicyForm(values) {
  // Client-side mirror of GoldPolicyWriteRequest: fail fast with a readable
  // message instead of round-tripping a 422. The backend remains the gate.
  const errors = [];
  const money = (key, label, { min = 0, required = true } = {}) => {
    const value = values[key];
    if (value === null) {
      if (required) errors.push(`${label}必填`);
      return;
    }
    if (!Number.isFinite(value)) errors.push(`${label}必须是数字`);
    else if (value < min) errors.push(`${label}不能小于 ${min}`);
  };
  money("portfolio_total", "组合总值", { min: 1 });
  money("gold_current_value", "当前黄金市值");
  if (values.available_cash !== null && !(values.available_cash >= 0)) errors.push("可用现金不能为负");
  money("target_min", "目标下限");
  money("target_max", "目标上限");
  money("base_dca_amount", "基础定投金额", { min: 1 });
  money("fixed_dip_add_amount", "回撤加仓金额", { min: 1 });
  if (values.target_min !== null && values.target_max !== null && values.target_min > values.target_max) {
    errors.push("目标下限不能大于上限");
  }
  if (
    values.portfolio_total !== null && values.gold_current_value !== null
    && values.gold_current_value > values.portfolio_total
  ) {
    errors.push("当前黄金市值不能超过组合总值");
  }
  return errors;
}

function bindGoldPolicyForm() {
  const form = document.getElementById("gold-policy-form");
  if (!form || form.dataset.bound === "true") return;
  form.dataset.bound = "true";
  form.addEventListener("submit", async (event) => {
    event.preventDefault();
    const hint = form.querySelector("[data-policy-hint]");
    const values = readPolicyForm(form);
    const errors = validatePolicyForm(values);
    if (errors.length) {
      if (hint) hint.textContent = errors[0];
      return;
    }
    if (hint) hint.textContent = "正在保存…";
    try {
      const saved = await api.saveGoldPolicy(values, { signal: controller.signal, timeoutMs: 12000 });
      if (hint) hint.textContent = `已保存为版本 ${saved?.version ?? "新"}，正在刷新…`;
      await loadData({ force: true });
    } catch (error) {
      if (error?.name === "AbortError") return;
      const detail = error?.detail || error?.message || "保存失败，请稍后重试";
      if (hint) hint.textContent = String(detail);
    }
  }, { signal: controller.signal });
}

function renderGoldLoading() {
  const rows = Array.from({ length: 6 }, () => `
    <div class="gold-loading-row" aria-hidden="true">
      <span class="gold-loading-dot"></span>
      <span class="gold-loading-copy"><i></i><i></i><i></i></span>
    </div>
  `).join("");
  return `
    <article class="card gold-data-loading" role="status" aria-label="正在接入黄金配置数据">
      <div class="gold-loading-head">
        <div>
          <p class="eyebrow">GOLD DATA PIPELINE</p>
          <h2>正在接入黄金配置数据</h2>
        </div>
        <span>同步策略、XAUT 行情与衍生品快照</span>
      </div>
      <div class="gold-loading-grid">${rows}</div>
    </article>
  `;
}

function phaseGoldLoadingSkeleton() {
  document.querySelectorAll(".gold-loading-copy i").forEach((element, index) => {
    const declaration = skeletonPhaseStyle(index);
    const delay = declaration.match(/--skeleton-delay:\s*([^;]+)/)?.[1];
    if (delay) element.style.setProperty("--skeleton-delay", delay);
  });
}

// ----- Data fetching + chart wiring --------------------------------------

function isActiveLoad(version, signal) {
  return !signal?.aborted && controller?.signal === signal && loadVersion === version;
}

function bindGoldRefreshButton() {
  const refreshBtn = document.getElementById("gold-refresh");
  if (!refreshBtn || refreshBtn.dataset.bound === "true") return;
  refreshBtn.dataset.bound = "true";
  refreshBtn.addEventListener("click", () => loadData({ force: true, requestCoreRefresh: true }), {
    signal: controller.signal,
  });
}

async function renderGoldSnapshot(data, version, signal) {
  if (!isActiveLoad(version, signal)) return;
  latestData = data;
  setRoot(renderShell(data), { pageTransition: true });
  applyPostMountStyles();
  replayPageEnter();
  bindGoldRefreshButton();
  bindGoldPolicyForm();
  const chartToken = data?.chart_series_or_chart_token;
  if (chartToken?.path && (chartToken.count || 0) > 0) {
    try {
      await renderGoldCharts(data, signal);
    } catch (err) {
      if (err?.name !== "AbortError") console.warn("[gold_v5] chart render failed", err);
    }
  }
  if (!initialGoldRevealPlayed && isActiveLoad(version, signal)) {
    const root = document.getElementById("page-root");
    if (root) {
      revealStagger(root);
      initialGoldRevealPlayed = true;
    }
  }
}

function mergeDerivatives(data, derivatives) {
  const hasData = ["oi_change_4w", "funding_rate", "cot_net_spec_percentile", "open_interest"]
    .some((key) => derivatives?.[key] != null);
  const manifest = [...(data?.source_manifest || [])];
  const index = manifest.findIndex((entry) => entry?.source_key === "gold_derivatives");
  const entry = {
    source_key: "gold_derivatives",
    freshness_state: hasData ? "fresh" : "missing",
    age_seconds: hasData ? 0 : null,
  };
  if (index >= 0) manifest[index] = { ...manifest[index], ...entry };
  else manifest.push(entry);
  return { ...data, derivatives: derivatives || {}, source_manifest: manifest };
}

function patchDerivatives(data, version, signal) {
  if (!isActiveLoad(version, signal)) return;
  latestData = data;
  const contract = document.querySelector(".gold-contract-ref");
  const governance = document.querySelector(".gold-governance");
  if (contract) contract.outerHTML = renderContractRef(data);
  if (governance) governance.outerHTML = renderGovernance(data);
  applyPostMountStyles();
}

async function loadDerivativesEnhancement(baseData, version, signal) {
  try {
    const derivatives = await api.getGoldDerivatives({ signal, timeoutMs: 25000 });
    if (!isActiveLoad(version, signal)) return;
    patchDerivatives(mergeDerivatives(latestData || baseData, derivatives), version, signal);
  } catch (error) {
    if (error?.name !== "AbortError") console.warn("[gold_v5] derivatives enhancement failed", error);
  }
}

async function refreshGoldCore(baseData, version, signal, forceRefresh = false) {
  const token = baseData?.chart_series_or_chart_token;
  const needsCoreData = baseData?.technical_summary?.price == null || !(token?.count > 0);
  if (!needsCoreData && !forceRefresh) return;
  try {
    const receipt = await api.precomputeHint({
      current_page: "gold-allocation",
      instrument_id: "xaut-usdt-perp",
      timeframe: "1d",
      view_window: "default",
      visible: true,
      candidates: ["analysis"],
      reason: "gold_workbench_cold_read",
      priority: 2,
    }, { signal });
    const taskKey = receipt?.queued_keys?.find((key) => key.startsWith("analysis:"));
    if (!taskKey) return;
    await waitForPrecomputeTask(taskKey, { signal });
    await waitForAbortableDelay(250, signal);
    const refreshed = await api.getGoldWorkbench({ force: true, signal, timeoutMs: 8000 });
    await renderGoldSnapshot(refreshed, version, signal);
  } catch (error) {
    if (error?.name !== "AbortError") console.warn("[gold_v5] XAUT background refresh failed", error);
  }
}

async function loadData({ force = false, requestCoreRefresh = false } = {}) {
  const version = ++loadVersion;
  const signal = controller?.signal;
  // 2026-08-15: dim the existing shell before kicking off the workbench
  // fetch. First call (warming shell mount) has no content yet so the
  try {
    if (typeof api.getGoldWorkbench !== "function") {
      throw new Error("api.getGoldWorkbench is not wired in app/static/core/api.js");
    }
    const data = await api.getGoldWorkbench({ force, signal, timeoutMs: 8000 });
    // Render the full shell (hero + workbench cards + governance) even when
    // chart data is missing, so verify_pages' real-content selectors
    // (.gold-workbench-grid / .gold-governance-grid) still match and the
    // user sees an explicit empty state instead of a dead page.
    await renderGoldSnapshot(data, version, signal);
    void loadDerivativesEnhancement(data, version, signal);
    if (requestCoreRefresh || data?.technical_summary?.price == null) {
      void refreshGoldCore(data, version, signal, requestCoreRefresh);
    }
  } catch (err) {
    if (err?.name === "AbortError" || !isActiveLoad(version, signal)) return;
    console.warn("[gold_v5] workbench unavailable:", err && err.message ? err.message : err);
    setRoot(renderShell({ snapshot: { status: "error" }, detail: String((err && err.message) || err) }), { pageTransition: true });
    applyPostMountStyles();
    replayPageEnter();
    bindGoldRefreshButton();
    bindGoldPolicyForm();
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

async function renderGoldCharts(data, signal) {
  destroyChartsForPage("gold");
  const candles = await fetchChartSeries(data?.chart_series_or_chart_token, signal);
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
        lineDataset("XAUT", priceSeries, getSeriesColor("XAUT"), { borderWidth: 1.6 }),
        lineDataset("MA50", maSeries(candles, 50), getSeriesColor("MA50"), { borderWidth: 1.2, borderDash: [4, 3] }),
        lineDataset("SMA200", maSeries(candles, 200), getSeriesColor("SMA200"), { borderWidth: 1.2, borderDash: [6, 3] }),
        lineDataset("EMA20", emaSeries(candles, 20), getSeriesColor("EMA20-Gold"), { borderWidth: 1.2, borderDash: [2, 2] }),
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
        // The VEGAS short line is EMA12, not the raw close (analysis.js:1551
        // and the 知识百科 VEGAS entry both read EMA12 as the line that
        // crosses 快轨/慢轨). Price already has its own TREND card above.
        lineDataset("EMA12", emaSeries(candles, 12), getSeriesColor("EMA12"), { borderWidth: 1.6 }),
        lineDataset("快轨 144", emaSeries(candles, 144), getSeriesColor("MA50"), { borderWidth: 1.8 }),
        lineDataset("快轨 169", emaSeries(candles, 169), getSeriesColor("MA50"), { fill: "-1", backgroundColor: "rgba(91, 138, 131, 0.10)", borderWidth: 1.8 }),
        lineDataset("慢轨 576", emaSeries(candles, 576), getSeriesColor("EMA20-Gold"), { borderDash: [7, 4], borderWidth: 1.7 }),
        lineDataset("慢轨 676", emaSeries(candles, 676), getSeriesColor("EMA20-Gold"), { fill: "-1", backgroundColor: "rgba(124, 95, 176, 0.08)", borderDash: [7, 4], borderWidth: 1.7 }),
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
        lineDataset("MACD", macd.line, getSeriesColor("MA50"), { borderWidth: 1.8 }),
        lineDataset("信号线", macd.signal, getSeriesColor("SMA200"), { borderDash: [6, 4], borderWidth: 1.6 }),
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
      datasets: [lineDataset("%B", bollingerPctB(candles, 20, 2), getSeriesColor("%B"), { borderWidth: 1.2 })],
    },
    options: { responsive: true, maintainAspectRatio: false, scales: { y: { min: -0.2, max: 1.2 } } },
  });
  renderInto("rsi", {
    type: "line",
    axisProfile: "oscillator",
    data: {
      labels,
      datasets: [lineDataset("RSI14", rsiSeries(candles, 14), getSeriesColor("RSI14"), { borderWidth: 1.4 })],
    },
    options: { responsive: true, maintainAspectRatio: false, scales: { y: { min: 0, max: 100 } } },
  });
}

async function fetchChartSeries(token, signal) {
  // token is { snapshot_id, path, count }; the chart endpoint
  // (GET /api/v1/gold/workbench/charts/{snapshot_id}) returns the candles
  // bound to this workbench snapshot: { snapshot_id, observed_at, candles }.
  if (!token?.snapshot_id) return [];
  try {
    const res = await api.getGoldWorkbenchCharts(token.snapshot_id, { signal });
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
  initialGoldRevealPlayed = false;
  // Use a conspicuous ingestion state instead of rendering zero-like strategy
  // cards while the first immutable snapshot is still unavailable.
  setRoot(renderGoldLoading());
  phaseGoldLoadingSkeleton();
  await loadData();
  applyPostMountStyles();
  bindGoldRefreshButton();
  bindGoldPolicyForm();
  // Return a controller so the SPA router (main.js normalizeController)
  // calls unmount() on navigation — previously the page returned undefined
  // and the abort controller / charts were never torn down.
  return { unmount };
}

export function unmount() {
  controller?.abort?.();
  controller = null;
  loadVersion += 1;
  destroyChartsForPage("gold");
  latestData = null;
}

export const ready = true;
