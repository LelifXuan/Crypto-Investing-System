import { api } from "../core/api.js";
import { escapeHtml, formatDateTime, formatNumber, setRoot, statusBanner } from "../core/dom.js";
import { mountDropdown } from "../ui/dropdown.js";

const STORAGE_KEY = "ashare.etf.dca.rebalance.v1";

const HALO_ETFS = [
  { symbol: "563010.SH", code: "563010", name: "电信ETF", bucket: "HALO", role: "防御红利 / 数字基础设施", targetWeight: 0.105 },
  { symbol: "512660.SH", code: "512660", name: "军工ETF", bucket: "HALO", role: "事件驱动 / 高弹性进攻", targetWeight: 0.084 },
  { symbol: "516950.SH", code: "516950", name: "基建ETF", bucket: "HALO", role: "稳增长 / 政策驱动", targetWeight: 0.105 },
  { symbol: "512400.SH", code: "512400", name: "有色金属ETF", bucket: "HALO", role: "资源周期 / 高波动进攻", targetWeight: 0.084 },
  { symbol: "159930.SZ", code: "159930", name: "能源ETF", bucket: "HALO", role: "资源周期 / 红利周期", targetWeight: 0.112 },
  { symbol: "561560.SH", code: "561560", name: "电力ETF", bucket: "HALO", role: "公用事业 / 稳定现金流", targetWeight: 0.120 },
];

const CASHFLOW_ETF = {
  symbol: "159201.SZ",
  code: "159201",
  name: "现金流ETF",
  bucket: "CASHFLOW",
  role: "防御底仓 / 现金流因子",
  fixedMonthlyDca: true,
};

const QUOTE_ETFS = [...HALO_ETFS, CASHFLOW_ETF];

const HALO_SYMBOLS = new Set(HALO_ETFS.map((item) => item.symbol));
const CASHFLOW_SYMBOL = CASHFLOW_ETF.symbol;

let activeController = null;
let planController = null;
let latestPayload = null;
let latestPlan = null;
let debounceTimer = null;
let state = readSavedState();

function defaultState() {
  return {
    mode: "monthly_dca",
    cashToInvest: 5000,
    positions: Object.fromEntries(
      HALO_ETFS.map((item) => [item.symbol, { shares: 0, costPrice: 0, currentPrice: "" }]),
    ),
  };
}

function readSavedState() {
  try {
    const parsed = JSON.parse(window.localStorage?.getItem(STORAGE_KEY) || "null");
    const base = defaultState();
    if (!parsed || typeof parsed !== "object") return base;
    const savedPositions =
      parsed.positions && typeof parsed.positions === "object" ? parsed.positions : {};
    const filteredPositions = Object.fromEntries(
      Object.entries(savedPositions).filter(([symbol]) => HALO_SYMBOLS.has(symbol)),
    );
    return {
      ...base,
      mode: parsed.mode === "quarterly_rebalance" ? "quarterly_rebalance" : "monthly_dca",
      cashToInvest: Number.isFinite(Number(parsed.cashToInvest)) ? Number(parsed.cashToInvest) : base.cashToInvest,
      positions: {
        ...base.positions,
        ...filteredPositions,
      },
    };
  } catch {
    return defaultState();
  }
}

function saveState() {
  try {
    window.localStorage?.setItem(STORAGE_KEY, JSON.stringify(state));
  } catch {
    // Local storage can be disabled; the planner remains usable for this session.
  }
}

function allQuotes(payload = latestPayload) {
  return (payload?.groups || []).flatMap((group) => group.items || []);
}

function quoteBySymbol(payload = latestPayload) {
  const output = new Map();
  allQuotes(payload).forEach((item) => {
    const suffix = item.market === "SH" ? ".SH" : ".SZ";
    output.set(`${item.code}${suffix}`, item);
  });
  return output;
}

function currentPriceFor(item) {
  const quote = quoteBySymbol().get(item.symbol);
  return Number(quote?.last_price || quote?.prev_close || 0);
}

function priceSourceLabel(item) {
  const quote = quoteForDefinition(item);
  if (quote?.last_price != null) return "最新价";
  if (quote?.prev_close != null) return "昨收价";
  return "等待行情";
}

function money(value, digits = 2) {
  const number = Number(value);
  if (!Number.isFinite(number)) return "-";
  return formatNumber(number, digits);
}

function pct(value) {
  const number = Number(value);
  if (!Number.isFinite(number)) return "-";
  return `${formatNumber(number * 100, 2)}%`;
}

function amountText(value) {
  const number = Number(value);
  if (!Number.isFinite(number)) return "-";
  if (Math.abs(number) >= 100000000) return `${formatNumber(number / 100000000, 2)} 亿`;
  if (Math.abs(number) >= 10000) return `${formatNumber(number / 10000, 2)} 万`;
  return formatNumber(number, 2);
}

function sideLabel(side) {
  return { BUY: "买入", SELL: "卖出", HOLD: "不操作" }[side] || "不操作";
}

function sideClass(side) {
  return { BUY: "chip-bullish", SELL: "chip-bearish", HOLD: "chip-neutral" }[side] || "chip-neutral";
}

const ETF_STATE_TEXT_CLASS = {
  ON_TARGET: "etf-state-color--on-target",
  UNDERWEIGHT: "etf-state-color--underweight",
  OVERWEIGHT: "etf-state-color--overweight",
  BUY_PLANNED: "etf-state-color--buy",
  SELL_PLANNED: "etf-state-color--sell",
  NO_ADD: "etf-state-color--neutral",
  LOT_BLOCKED: "etf-state-color--blocked",
  CASH_LEFT: "etf-state-color--blocked",
  DATA_STALE: "etf-state-color--warning",
  INPUT_MISSING: "etf-state-color--blocked",
};

function etfStateTextClass(state) {
  return ETF_STATE_TEXT_CLASS[state] || "";
}

function modeLabel(mode = state.mode) {
  return mode === "quarterly_rebalance" ? "季度再平衡" : "月度定投";
}

function sourceStatusLabel(payload) {
  if (!payload) return "读取中";
  if (payload.source_status === "ok" && payload.cache_status === "live") return "实时行情";
  if (payload.cache_status === "stale") return "缓存行情";
  if (payload.source_status === "partial") return "部分可用";
  if (payload.source_status === "error") return "行情暂不可用";
  return "行情可用";
}

function renderShell() {
  setRoot(`
    <section id="etf-overview"></section>
    <section id="etf-quote-deck"></section>
    <section id="etf-workbench"></section>
  `);
}

function renderOverview() {
  const orders = latestPlan?.orders || [];
  const summary = latestPlan?.deviation_summary || {};
  const cash = latestPlan?.cash || {};
  const generatedAt = latestPayload?.generated_at ? formatDateTime(latestPayload.generated_at) : "-";
  return `
    <section class="card etf-execution-bar">
      <div class="etf-execution-title">
        <div>
          <p class="eyebrow">A-SHARE ETF</p>
          <h2>A股ETF 定投与再平衡</h2>
        </div>
        <div class="etf-action-row">
          <button type="button" class="primary-action" id="etf-refresh-button">刷新行情</button>
        </div>
      </div>
      <div class="etf-control-strip">
        <label>
          <span>执行模式</span>
          <button class="dropdown"
                  data-dropdown-id="etf-mode"
                  data-dropdown-size="compact"
                  type="button"
                  aria-haspopup="listbox"
                  aria-expanded="false">
            <span class="dropdown-icon" data-slot="icon" hidden></span>
            <span class="dropdown-label">${escapeHtml(modeLabel())}</span>
            <span class="dropdown-arrow" aria-hidden="true"><svg viewBox="0 0 10 10" width="11" height="11"><path d="M2 4l3 3 3-3" fill="none" stroke="currentColor" stroke-width="1.4" stroke-linecap="round" stroke-linejoin="round"/></svg></span>
          </button>
        </label>
        <label>
          <span>可投现金</span>
          <input id="etf-cash" type="number" min="0" step="100" value="${escapeHtml(state.cashToInvest)}" />
        </label>
        <span><small>订单数</small><strong>${orders.length}</strong></span>
        <span><small>剩余现金</small><strong>${money(cash.cash_left ?? state.cashToInvest)}</strong></span>
        <span><small>执行后最大偏离</small><strong>${pct(summary.after_max_abs_deviation)}</strong></span>
        <span><small>行情状态</small><strong>${escapeHtml(sourceStatusLabel(latestPayload))}</strong></span>
        <span><small>更新时间</small><strong>${escapeHtml(generatedAt)}</strong></span>
      </div>
      <div id="etf-status"></div>
    </section>
  `;
}

function localPosition(symbol) {
  return state.positions[symbol] || { shares: 0, costPrice: 0, currentPrice: "" };
}

function renderExecutionRows() {
  const planRows = new Map((latestPlan?.rows || []).map((row) => [row.symbol, row]));
  return HALO_ETFS.map((item) => {
    const saved = localPosition(item.symbol);
    const row = planRows.get(item.symbol);
    const price = currentPriceFor(item);
    const action = row?.action || "HOLD";
    return `
      <tr>
        <td>
          <strong>${escapeHtml(item.name)}</strong>
        </td>
        <td><input class="etf-cell-input" data-field="shares" data-symbol="${escapeHtml(item.symbol)}" type="number" min="0" step="100" value="${escapeHtml(saved.shares ?? 0)}" /></td>
        <td><input class="etf-cell-input" data-field="costPrice" data-symbol="${escapeHtml(item.symbol)}" type="number" min="0" step="0.001" value="${escapeHtml(saved.costPrice ?? 0)}" /></td>
        <td><span class="etf-locked-price">${price ? money(price, 3) : "-"}</span></td>
        <td class="etf-action-cell"><span class="status-chip ${sideClass(action)}">${sideLabel(action)}</span></td>
        <td class="etf-number-cell">${row?.trade_shares ? formatNumber(row.trade_shares, 0) : "-"}</td>
        <td class="etf-number-cell">${row?.estimated_trade_amount ? money(row.estimated_trade_amount) : "-"}</td>
        <td class="etf-number-cell">${pct(row?.before_weight)}</td>
        <td class="etf-number-cell">${pct(row?.target_weight ?? item.targetWeight)}</td>
        <td class="etf-number-cell ${etfStateTextClass(row?.state)}">${pct(row?.after_deviation)}</td>
      </tr>
    `;
  }).join("");
}

function renderPlanSummary() {
  const summary = latestPlan?.deviation_summary || {};
  const cash = latestPlan?.cash || {};
  const portfolio = latestPlan?.portfolio || {};
  const warnings = latestPlan?.warnings || [];
  return `
    <aside class="card etf-plan-summary">
      <div class="section-head compact-head">
        <div>
          <p class="eyebrow">PLAN · HALO</p>
          <h2>${modeLabel()}</h2>
        </div>
        <span class="status-chip chip-neutral">${(latestPlan?.orders || []).length} 笔</span>
      </div>
      <p class="etf-scope-note">现金流ETF按固定月投执行，不纳入本计划。</p>
      ${warnings.length > 0 ? renderWarnings(warnings) : ""}
      <div class="etf-summary-grid">
        <span><small>执行前总偏离</small><strong>${pct(summary.before_total_abs_deviation)}</strong></span>
        <span><small>执行后总偏离</small><strong>${pct(summary.after_total_abs_deviation)}</strong></span>
        <span><small>改善幅度</small><strong>${pct(summary.improvement_total_abs_deviation)}</strong></span>
        <span><small>现金占比</small><strong>${pct(cash.cash_weight_after)}</strong></span>
        <span><small>换手金额</small><strong>${money(portfolio.turnover_amount)}</strong></span>
        <span><small>交易笔数</small><strong>${formatNumber(portfolio.trade_count || 0, 0)}</strong></span>
      </div>
    </aside>
  `;
}

function renderWarnings(warnings) {
  return `
    <ul class="etf-warning-list">
      ${warnings.map((w) => `<li><code>${escapeHtml(w.code)}</code> ${escapeHtml(w.message)}</li>`).join("")}
    </ul>
  `;
}

function quoteForDefinition(item) {
  return quoteBySymbol().get(item.symbol) || null;
}

function renderEtfMiniCard(item, { featured = false } = {}) {
  const quote = quoteForDefinition(item);
  const saved = localPosition(item.symbol);
  const row = (latestPlan?.rows || []).find((entry) => entry.symbol === item.symbol);
  const price = currentPriceFor(item);
  const changePct = quote?.change_pct;
  const shares = Number(saved.shares || 0);
  const value = shares * price;
  const action = row?.action || "HOLD";
  return `
    <article class="etf-mini-card ${featured ? "is-featured" : ""}">
      <div class="etf-mini-head">
        <div>
          <p>${escapeHtml(item.code)} · ${escapeHtml(item.bucket)}</p>
          <h3>${escapeHtml(item.name)}</h3>
        </div>
        <span class="status-chip ${sideClass(action)}">${sideLabel(action)}</span>
      </div>
      <div class="etf-mini-price">
        <strong>${price ? money(price, 3) : "-"}</strong>
        <span class="${changePct == null ? "" : Number(changePct) >= 0 ? "etf-positive" : "etf-negative"}">
          ${changePct != null ? `${money(changePct)}%` : priceSourceLabel(item)}
        </span>
      </div>
      <div class="etf-mini-metrics">
        <span><small>目标</small><b>${pct(item.targetWeight)}</b></span>
        <span><small>持仓</small><b>${formatNumber(shares, 0)}</b></span>
        <span><small>市值</small><b>${money(value)}</b></span>
        <span><small>成交额</small><b>${amountText(quote?.amount)}</b></span>
      </div>
    </article>
  `;
}

function renderCashflowMiniCard(item, { featured = false } = {}) {
  const quote = quoteForDefinition(item);
  const price = currentPriceFor(item);
  const changePct = quote?.change_pct;
  return `
    <article class="etf-mini-card etf-mini-card--cashflow ${featured ? "is-featured" : ""}">
      <div class="etf-mini-head">
        <div>
          <p>${escapeHtml(item.code)} · CASHFLOW</p>
          <h3>${escapeHtml(item.name)}</h3>
        </div>
        <span class="status-chip etf-cashflow-fixed">固定月投</span>
      </div>
      <div class="etf-mini-price">
        <strong>${price ? money(price, 3) : "-"}</strong>
        <span class="${changePct == null ? "" : Number(changePct) >= 0 ? "etf-positive" : "etf-negative"}">
          ${changePct != null ? `${money(changePct)}%` : priceSourceLabel(item)}
        </span>
      </div>
      <div class="etf-mini-metrics">
        <span><small>成交额</small><b>${amountText(quote?.amount)}</b></span>
        <span><small>更新时间</small><b>${escapeHtml(formatDateTime(quote?.quote_time))}</b></span>
      </div>
    </article>
  `;
}

function renderQuoteDeck() {
  const haloItems = HALO_ETFS;
  return `
    <section class="etf-top-deck">
      <div class="etf-top-left">
        ${renderPlanSummary()}
        ${renderCashflowMiniCard(CASHFLOW_ETF, { featured: true })}
      </div>
      <div class="etf-mini-grid">
        ${haloItems.map((item) => renderEtfMiniCard(item)).join("")}
      </div>
    </section>
  `;
}

function renderWorkbench() {
  return `
    <section class="card etf-execution-table-card">
      <div class="section-head compact-head">
        <div>
          <p class="eyebrow">EXECUTION</p>
          <h2>持仓与执行</h2>
        </div>
      </div>
      <div class="table-wrap compact-table-wrap">
        <table class="etf-dense-table etf-combined-table">
          <thead>
            <tr>
              <th>ETF</th>
              <th>份额</th>
              <th>成本价</th>
              <th>现价</th>
              <th>操作</th>
              <th>指令份额</th>
              <th>预计金额</th>
              <th>当前权重</th>
              <th>目标权重</th>
              <th>执行后偏离</th>
            </tr>
          </thead>
          <tbody>${renderExecutionRows()}</tbody>
        </table>
      </div>
    </section>
  `;
}

function captureFocusedField() {
  const active = document.activeElement;
  if (!(active instanceof HTMLInputElement || active instanceof HTMLButtonElement)) return null;
  if (active.id === "etf-cash" || active.id === "etf-mode") {
    return { id: active.id, start: active.selectionStart, end: active.selectionEnd };
  }
  if (!active.dataset.symbol || !active.dataset.field) return null;
  return {
    symbol: active.dataset.symbol,
    field: active.dataset.field,
    start: active.selectionStart,
    end: active.selectionEnd,
  };
}

function restoreFocusedField(snapshot) {
  if (!snapshot) return;
  const selector = snapshot.id
    ? `#${snapshot.id}`
    : `[data-symbol="${CSS.escape(snapshot.symbol)}"][data-field="${CSS.escape(snapshot.field)}"]`;
  const next = document.querySelector(selector);
  if (!(next instanceof HTMLInputElement || next instanceof HTMLButtonElement)) return;
  next.focus({ preventScroll: true });
  try {
    if (snapshot.start != null && snapshot.end != null) next.setSelectionRange(snapshot.start, snapshot.end);
  } catch {
    // Numeric inputs do not always expose a text selection API.
  }
}

function renderAll(statusHtml = "") {
  const focused = captureFocusedField();
  document.getElementById("etf-overview").innerHTML = renderOverview();
  document.getElementById("etf-status").innerHTML = statusHtml;
  document.getElementById("etf-quote-deck").innerHTML = renderQuoteDeck();
  document.getElementById("etf-workbench").innerHTML = renderWorkbench();
  bindControls();
  restoreFocusedField(focused);
}

function updateStateFromInput(target) {
  if (!(target instanceof HTMLInputElement || target instanceof HTMLButtonElement)) return false;
  if (target.id === "etf-mode") {
    state.mode = target.value === "quarterly_rebalance" ? "quarterly_rebalance" : "monthly_dca";
    return true;
  }
  if (target.id === "etf-cash") {
    state.cashToInvest = Math.max(0, Number(target.value || 0));
    return true;
  }
  const symbol = target.dataset.symbol;
  const field = target.dataset.field;
  if (!symbol || !field) return false;
  const current = { ...localPosition(symbol) };
  if (field === "shares") current.shares = Math.max(0, Math.floor(Number(target.value || 0)));
  if (field === "costPrice") current.costPrice = Math.max(0, Number(target.value || 0));
  state.positions = { ...state.positions, [symbol]: current };
  return true;
}

function bindControls() {
  document.getElementById("etf-refresh-button")?.addEventListener("click", () => void loadQuotes({ force: true }));
  const modeRoot = document.querySelector('.dropdown[data-dropdown-id="etf-mode"]');
  if (modeRoot) {
    mountDropdown(modeRoot, {
      items: [
        { value: "monthly_dca", label: "月度定投" },
        { value: "quarterly_rebalance", label: "季度再平衡" },
      ],
      value: state.mode,
      placeholder: "选择模式",
      onChange: (v) => {
        state.mode = v === "quarterly_rebalance" ? "quarterly_rebalance" : "monthly_dca";
        handleStateChange();
      },
    });
  }
  document.getElementById("etf-cash")?.addEventListener("input", (event) => {
    if (updateStateFromInput(event.target)) handleStateChange();
  });
  document.querySelectorAll(".etf-cell-input").forEach((input) => {
    input.addEventListener("input", (event) => {
      if (updateStateFromInput(event.target)) handleStateChange();
    });
  });
}

function handleStateChange() {
  saveState();
  if (debounceTimer) window.clearTimeout(debounceTimer);
  debounceTimer = window.setTimeout(() => {
    void planRebalance();
  }, 650);
  const status = document.getElementById("etf-status");
  if (status) status.innerHTML = statusBanner("正在更新执行计划", "loading");
}

function buildPlanPayload() {
  return {
    mode: state.mode,
    cash_to_invest: Number(state.cashToInvest || 0),
    lot_size: 100,
    tolerance_pct: 0.02,
    hard_tolerance_pct: 0.05,
    positions: HALO_ETFS.map((item) => {
      const saved = localPosition(item.symbol);
      return {
        symbol: item.symbol,
        shares: Math.max(0, Math.floor(Number(saved.shares || 0))),
        cost_price: Math.max(0, Number(saved.costPrice || 0)),
        current_price: currentPriceFor(item) || undefined,
      };
    }),
  };
}

async function planRebalance() {
  planController?.abort();
  planController = new AbortController();
  try {
    latestPlan = await api.planEtfRebalance(buildPlanPayload(), { signal: planController.signal });
    renderAll(statusBanner("执行计划已生成", "success"));
  } catch (error) {
    if (error?.name === "AbortError") return;
    latestPlan = null;
    renderAll(statusBanner(`执行计划暂不可用：${String(error?.message || error).slice(0, 90)}`, "warning"));
  }
}

async function loadQuotes({ force = false } = {}) {
  activeController?.abort();
  activeController = new AbortController();
  renderAll(statusBanner(force ? "正在刷新行情" : "正在读取行情", "loading"));
  try {
    latestPayload = force
      ? await api.refreshEtfQuotes("all", { signal: activeController.signal })
      : await api.getEtfQuotes("all", { signal: activeController.signal });
    await planRebalance();
  } catch (error) {
    if (error?.name === "AbortError") return;
    renderAll(statusBanner("行情读取失败；将保留最新可用收盘价生成计划。", "warning"));
  }
}

export async function renderAshareEtf() {
  renderShell();
  renderAll(statusBanner("正在读取 A股ETF 行情", "loading"));
  const loadPromise = loadQuotes().catch((error) => {
    console.error("ashare-etf:initial-load:error", error);
  });
  return {
    async unmount() {
      activeController?.abort();
      planController?.abort();
      activeController = null;
      planController = null;
      if (debounceTimer) window.clearTimeout(debounceTimer);
      void loadPromise.catch(() => null);
    },
    async pause() {},
    async resume() {},
  };
}

export const renderPage = renderAshareEtf;
