import { api } from "../core/api.js";
import { escapeHtml, formatDateTime, formatNumber, setRoot, statusBanner } from "../core/dom.js";
import { destroyChartsForPage, lineDataset, renderChart } from "../ui/charts.js";
import { mountDropdown } from "../ui/dropdown.js";

// §Monet palette lock — read from CSS so the equity-curve chart and the
// 0-axis baseline stay aligned with the rest of the site even if the
// theme is later retuned in styles.css :root.
function _monetToken(name, fallback) {
  if (typeof window === "undefined" || !window.getComputedStyle) return fallback;
  const v = getComputedStyle(document.documentElement).getPropertyValue(name).trim();
  return v || fallback;
}

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
    mode: "weekly_dca_monthly_rebalance",
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
      mode: parsed.mode === "monthly_dca_quarterly_rebalance" ? "monthly_dca_quarterly_rebalance" : "weekly_dca_monthly_rebalance",
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

// Like ``money`` but always emits a sign on non-zero values, so a
// strategy-vs-lump-sum 权益差 of -5,000 reads as "-5,000" (策略跑输)
// rather than "5,000" which could be misread as a plain value.
function moneySigned(value) {
  const number = Number(value);
  if (!Number.isFinite(number)) return "-";
  const sign = number > 0 ? "+" : "";
  return `${sign}${formatNumber(number, 2)}`;
}

function pct(value) {
  const number = Number(value);
  if (!Number.isFinite(number)) return "-";
  return `${formatNumber(number * 100, 2)}%`;
}

// Like ``pct`` but always emits a sign on non-zero values so the user
// can read -71.93% as "DCA underperformed buy-and-hold by 71.93%"
// rather than "DCA return is -71.93%".
function pctSigned(value) {
  const number = Number(value);
  if (!Number.isFinite(number)) return "-";
  const sign = number > 0 ? "+" : "";
  return `${sign}${formatNumber(number * 100, 2)}%`;
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
  return mode === "monthly_dca_quarterly_rebalance" ? "月度定投+季度调仓" : "周度定投+月度调仓";
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
    <section id="etf-equity-curve"></section>
    <section id="etf-quote-deck"></section>
    <section id="etf-workbench"></section>
  `);
}

// ---------------------------------------------------------------------------
// ETF equity curve module
//
// Two modes (toggled in the UI):
//   - simulation (default): replay the 资金投入 strategy (定稿 2026-08-06):
//     initial build at the confirmed target weights, then monthly DCA
//     (only-buys, under-allocated first) + quarter-end bandwidth review.
//   - holdings: faithful mark-to-market replay of the user's current
//     portfolio from a chosen start day to today (existing endpoint,
//     kept for users who want to see their actual PnL).
// ---------------------------------------------------------------------------

let equityCurveController = null;
let equityCurveCache = null;
let equityCurveMode = "simulation";
// 定投频率 (说明书§2.2: 周定投与月定投只是资金到账频率的区别;首次建档后固定)。
// 完整策略按周度定投执行(2026-08-07):HALO 六只周定投+季末带宽调仓,现金流
// ETF 周定投只买不卖。
let equityCurveFrequency = "week";

function _todayIso() {
  const d = new Date();
  return d.toISOString().slice(0, 10);
}

function _defaultEquityFromDate() {
  const today = new Date();
  const oneYear = new Date(today.getFullYear() - 1, today.getMonth(), today.getDate());
  return oneYear.toISOString().slice(0, 10);
}

function _buildSimulationPayload() {
  const monthRaw = document.getElementById("etf-equity-from-month")?.value;
  // On the very first discovery call (no user input yet, no cache), ask
  // for a wide window so the backend can return meta.halos_listing_start.
  // Subsequent calls use the actual input value.
  let fromMonth;
  if (monthRaw) {
    fromMonth = monthRaw;
  } else if (equityCurveCache?.meta?.halos_listing_start) {
    fromMonth = String(equityCurveCache.meta.halos_listing_start).slice(0, 7);
  } else {
    fromMonth = "2020-01";  // discovery: ask wide, backend narrows via meta
  }
  // Convert YYYY-MM → first day of month for the API
  const fromMonthIso = `${fromMonth}-01`;
  // 初始建仓资金 + 每期定投金额: read the inputs, fall back to the defaults
  // (10000 / 1000) when absent or non-finite.
  const capitalRaw = document.getElementById("etf-equity-initial-capital")?.value;
  let initialCapital = "10000";
  if (capitalRaw !== undefined && capitalRaw !== "") {
    const parsed = Number(capitalRaw);
    if (Number.isFinite(parsed) && parsed > 0) {
      initialCapital = String(Math.round(parsed));
    }
  }
  const monthlyRaw = document.getElementById("etf-equity-monthly-amount")?.value;
  let periodAmount = "1000";
  if (monthlyRaw !== undefined && monthlyRaw !== "") {
    const parsed = Number(monthlyRaw);
    if (Number.isFinite(parsed) && parsed >= 0) {
      periodAmount = String(Math.round(parsed));
    }
  }
  // 定投频率: 月定投(默认) 或 周定投 — 只是资金到账频率的区别(说明书§2.2/表0)。
  let frequency = "month";
  if (equityCurveFrequency === "week" || equityCurveFrequency === "month") {
    frequency = equityCurveFrequency;
  } else {
    const freqEl = document.getElementById("etf-equity-frequency");
    if (freqEl) {
      const v = freqEl.dataset.frequency || freqEl.dataset.value;
      if (v === "week" || v === "month") frequency = v;
    }
  }
  // Read the rebalance offset input (number of trading days between
  // month-end DCA and quarter-end bandwidth review). The spec says the
  // review happens on the funding day or the next 1–2 trading days, so
  // clamp to the backend range [0, 5]. Empty / NaN falls back to 0.
  const offsetInput = document.getElementById("etf-equity-offset-days")?.value;
  let rebalanceOffsetDays = 0;
  if (offsetInput !== undefined && offsetInput !== "") {
    const parsed = Number(offsetInput);
    if (Number.isFinite(parsed)) {
      rebalanceOffsetDays = Math.max(0, Math.min(5, Math.round(parsed)));
    }
  }
  return {
    from_month: fromMonthIso,
    to_date: _todayIso(),
    params: {
      initial_capital: initialCapital,
      period_amount: periodAmount,
      frequency,
      // 完整策略(2026-08-07):每周资金按 HALO:现金流 = cashflow_ratio:1
      // 拆分(默认 6:1)。6/7 投入 HALO 六只(周定投+季末带宽调仓),1/7
      // 投入现金流 ETF(159201,周定投只买不卖、永不调仓)。
      cashflow_ratio: 6,
      lot_size: 100,
      // Target weights / bandwidth / fees stay at the backend defaults
      // (研究确认的表1 权重;带宽 max(权重×20%, 2.5pp);佣金万2.5、最低
      // 佣金 5 元、滑点 0.1%) — the UI intentionally doesn't re-expose
      // the research knobs, per spec §7 (研究测算不进入正式执行文件).
      rebalance_offset_days: rebalanceOffsetDays,
    },
  };
}

function _buildEquityPayload() {
  const positions = [];
  for (const etf of HALO_ETFS) {
    const saved = state.positions[etf.symbol] || { shares: 0, costPrice: 0 };
    if (Number(saved.shares) > 0) {
      positions.push({
        symbol: etf.symbol,
        code: etf.code,
        shares: Number(saved.shares),
        cost_price: String(saved.costPrice ?? 0),
      });
    }
  }
  const cashflow = state.positions[CASHFLOW_ETF.symbol] || { shares: 0, costPrice: 0 };
  if (Number(cashflow.shares) > 0) {
    positions.push({
      symbol: CASHFLOW_ETF.symbol,
      code: CASHFLOW_ETF.code,
      shares: Number(cashflow.shares),
      cost_price: String(cashflow.costPrice ?? 0),
    });
  }
  const fromDateRaw = document.getElementById("etf-equity-from-date")?.value;
  return {
    from_date: fromDateRaw || _defaultEquityFromDate(),
    to_date: _todayIso(),
    cash: String(state.cashToInvest ?? 0),
    positions,
  };
}

function _renderEquitySummaryCards(summary, meta, mode) {
  if (mode === "simulation") {
    const rebalances = summary.rebalance_count ?? 0;
    const topups = summary.quarterly_topup_count ?? 0;
    const months = summary.months_simulated ?? 0;
    // Present-value comparison (2026-08-07): the three headline numbers are
    // all money, so the strategy-vs-buy-and-hold gap is readable at a glance
    // without normalising to a return percentage.
    const excess = Number(summary.final_total_value) - Number(summary.lump_sum_final_value);
    // 2026-08-07: 5 stats in one row. 累计投入 promotes from a sub-line
    // on the strategy card to its own headline stat — it is the
    // denominator for every return metric and deserves first-class
    // visibility. The strategy card drops the redundant 累计投入 figure
    // from its sub (keeps 现金 + 调仓次数) so the two cards don't echo.
    const cards = [
      {
        label: "策略权益",
        value: money(summary.final_total_value),
        sub: `现金 ${money(summary.final_cash_value)} · ${rebalances} 次调仓 · ${topups} 次季末加码`,
      },
      {
        label: "策略累计投入",
        value: money(summary.final_cost_value),
        // 月均投入 ≈ 累计投入 / 区间月数;周度策略下"月均"是有意义的概览数字。
        sub: months > 0
          ? `月均 ${money(Number(summary.final_cost_value) / months)} · ${months} 个月`
          : `${months} 个月`,
      },
      {
        label: "现金流ETF 权益",
        value: money(summary.final_cashflow_value),
        sub: `份额 ${summary.final_cashflow_shares ?? 0} · 池内现金 ${money(summary.final_cashflow_cash)}`,
      },
      {
        label: "一次性投入 权益",
        value: money(summary.lump_sum_final_value),
        sub: `区间 ${months} 个月`,
      },
      {
        // 旧 label "权益差(策略−一次性)" 的 em-dash 与汉字"一"同形,扫一眼分不清;
        // 改用 ASCII "vs" + 醒目色块避免歧义。
        label: "策略 vs 一次性",
        value: moneySigned(excess),
        sub: `DCA 相对 ${pctSigned(summary.lump_sum_vs_dca_pct)}`,
      },
    ];
    return cards
      .map(
        (c) => `
          <span class="etf-equity-stat">
            <small>${escapeHtml(c.label)}</small>
            <strong>${escapeHtml(c.value)}</strong>
            <em>${escapeHtml(c.sub)}</em>
          </span>
        `,
      )
      .join("");
  }
  // holdings (legacy equity curve)
  const cards = [
    {
      label: "当前总权益",
      value: money(summary.current_total_value),
      sub: `起 ${money(summary.starting_total_value)}`,
    },
    {
      label: "累计收益率",
      value: pct(summary.total_return_pct),
      sub: `区间 ${summary.days_observed} 个交易日`,
    },
    {
      label: "最大回撤",
      value: pct(summary.max_drawdown_pct),
      sub: `高 ${money(summary.peak_total_value)} · 低 ${money(summary.trough_total_value)}`,
    },
  ];
  return cards
    .map(
      (c) => `
        <span class="etf-equity-stat">
          <small>${escapeHtml(c.label)}</small>
          <strong>${escapeHtml(c.value)}</strong>
          <em>${escapeHtml(c.sub)}</em>
        </span>
      `,
    )
    .join("");
}

function _renderEquityCaption(meta, warnings, mode) {
  const source = escapeHtml(meta.data_source || "eastmoney_kline");
  const fetched = escapeHtml(formatDateTime(meta.fetched_at));
  const coverage = `${meta.coverage_start} → ${meta.coverage_end}`;
  const missing = meta.missing_dates?.length
    ? ` · 缺失 ${meta.missing_dates.length} 个交易日(沿用前日净值)`
    : "";
  const missingSymbols = meta.symbols_missing?.length
    ? ` · ${meta.symbols_missing.length} 个 ETF 无数据: ${escapeHtml(meta.symbols_missing.join(", "))}`
    : "";
  const warn = (warnings && warnings.length)
    ? ` · 警告 ${warnings.length} 条`
    : "";
  return `数据源 ${source} · 覆盖 ${coverage} · 抓取 ${fetched}${missing}${missingSymbols}${warn}`;
}

// Read the CURRENT equity-control input values before the section is rebuilt
// from innerHTML. Returns null for a control that doesn't exist yet (first
// render / mode not active), so callers fall back to their defaults. This
// preserves user edits across the post-fetch re-render instead of silently
// resetting them to the template literals.
function _captureEquityInputValues(root) {
  const get = (id) => {
    const el = root?.querySelector ? root.querySelector(`#${id}`) : null;
    return el ? el.value : null;
  };
  return {
    fromMonth: get("etf-equity-from-month"),
    fromDate: get("etf-equity-from-date"),
    initialCapital: get("etf-equity-initial-capital"),
    periodAmount: get("etf-equity-monthly-amount"),
    offsetDays: get("etf-equity-offset-days"),
  };
}

function renderEquityCurve(data, mode) {
  const root = document.getElementById("etf-equity-curve");
  if (!root) return;
  mode = mode || equityCurveMode || "simulation";
  const summary = data?.summary || {};
  const meta = data?.meta || {};
  const sourceStatus = meta.source_status || "ok";
  const statusHint =
    sourceStatus === "ok"
      ? ""
      : sourceStatus === "partial"
        ? "数据不完整"
        : "等待历史数据";

  // Preserve the user's typed control values across re-renders. This section
  // is rebuilt from innerHTML on every response, so read the CURRENT inputs
  // first and reuse them as the new defaults — otherwise the hard-coded
  // template values (10000 / 1000 / 0) silently discard whatever the user
  // entered for 初始建仓 / 每期定投 / 调仓延后.
  const prevInputs = _captureEquityInputValues(root);

  // Default input values from cache or sensible default.
  // Simulation mode: the input defaults to the backend's
  // ``halos_listing_start`` (the first trading day EVERY HALO ETF has
  // data — the six-all-present day, e.g. 2023-07). On the very first
  // render there is no cache yet, so the input is left EMPTY and
  // ``_buildSimulationPayload`` issues a wide discovery call
  // (from_month 2020-01) to learn that date; once the meta arrives the
  // next render fills the input with it and a follow-up fetch replays
  // from there (see loadEquityCurve).
  const haloListing = equityCurveCache?.meta?.halos_listing_start
    ? String(equityCurveCache.meta.halos_listing_start).slice(0, 7)
    : null;
  const fromMonthDefault = (prevInputs.fromMonth || "")
    || haloListing
    || (equityCurveCache?.from_month
      ? equityCurveCache.from_month.slice(0, 7)
      : "");
  const fromDateDefault = prevInputs.fromDate
    || equityCurveCache?.from_date
    || _defaultEquityFromDate();
  // Money controls: keep the user's edits (captured above); fall back to the
  // spec defaults only when the input didn't exist yet (first render).
  const capitalDefault = prevInputs.initialCapital !== null
    ? prevInputs.initialCapital
    : "10000";
  const periodDefault = prevInputs.periodAmount !== null
    ? prevInputs.periodAmount
    : "1000";
  const offsetDefault = prevInputs.offsetDays !== null
    ? prevInputs.offsetDays
    : "0";

  root.innerHTML = `
    <div class="card etf-equity-curve">
      <header class="etf-equity-head">
        <div>
          <p class="eyebrow">组合权益曲线 · ${mode === "simulation" ? "策略模拟" : "持仓回放"}</p>
          <h2>${mode === "simulation" ? "HALO & 现金流 ETF" : "自选起始日 → 至今的权益轨迹"}</h2>
        </div>
        <div class="etf-equity-controls">
          <div class="etf-equity-mode">
            <button type="button" class="etf-equity-mode-btn ${mode === "simulation" ? "is-active" : ""}"
                    data-equity-mode="simulation" id="etf-equity-mode-simulation">策略模拟</button>
            <button type="button" class="etf-equity-mode-btn ${mode === "holdings" ? "is-active" : ""}"
                    data-equity-mode="holdings" id="etf-equity-mode-holdings">持仓回放</button>
          </div>
          ${
            mode === "simulation"
              ? `
          <label class="etf-equity-from">
            <span>起始月份</span>
            <input type="month" id="etf-equity-from-month"
                   min="2020-01" max="${escapeHtml(_todayIso().slice(0, 7))}"
                   step="any"
                   value="${escapeHtml(fromMonthDefault)}">
          </label>
          <label class="etf-equity-from">
            <span>初始建仓(元)</span>
            <input type="number" id="etf-equity-initial-capital"
                   min="1" step="100" value="${escapeHtml(capitalDefault)}"
                   title="首次批准投入的资金,按目标权重一次性建仓(说明书 §2.1)。">
          </label>
          <label class="etf-equity-from">
            <span>每期定投(元)</span>
            <input type="number" id="etf-equity-monthly-amount"
                   min="0" step="100" value="${escapeHtml(periodDefault)}"
                   title="每期定投金额(周/月);按 6:1 拆分:6/7 投入 HALO 六只(周定投+季末调仓),1/7 投入现金流 ETF(159201,只买不卖)。">
          </label>
          <label class="etf-equity-from">
            <span>定投频率</span>
            <button class="dropdown etf-equity-freq-btn"
                    id="etf-equity-frequency"
                    data-dropdown-id="etf-equity-frequency"
                    type="button"
                    aria-label="定投频率"
                    aria-haspopup="listbox"
                    aria-expanded="false">
              <span class="dropdown-icon" data-slot="icon" hidden></span>
              <span class="dropdown-label">${equityCurveFrequency === "week" ? "周定投" : "月定投"}</span>
              <span class="dropdown-arrow" aria-hidden="true"><svg viewBox="0 0 10 10" width="11" height="11"><path d="M2 4l3 3 3-3" fill="none" stroke="currentColor" stroke-width="1.4" stroke-linecap="round" stroke-linejoin="round"/></svg></span>
            </button>
          </label>
          <label class="etf-equity-offset">
            <span>调仓延后(交易日)</span>
            <input type="number" id="etf-equity-offset-days"
                   min="0" max="5" step="1"
                   value="${escapeHtml(offsetDefault)}"
                   title="季末定投计入后,带宽复核可延后 0–2 个交易日;不机械等 5/10 日(说明书 §5.6)。">
          </label>`
              : `
          <label class="etf-equity-from">
            <span>起始日</span>
            <input type="date" id="etf-equity-from-date"
                   min="2020-01-01" max="${escapeHtml(_todayIso())}"
                   step="any"
                   value="${escapeHtml(fromDateDefault)}">
          </label>`
          }
          <button type="button" class="primary-action" id="etf-equity-generate">
            生成曲线
          </button>
        </div>
        ${mode === "simulation" ? `<p class="etf-equity-strategy-note">资金按 6:1 分配至 HALO 六只与现金流 ETF（159201，仅买不卖）</p>` : ""}
      </header>
      <div class="etf-equity-stats">
        ${_renderEquitySummaryCards(summary, meta, mode)}
      </div>
      <div class="etf-equity-canvas-wrap">
        <canvas id="etf-equity-canvas" height="300"></canvas>
      </div>
      <p class="etf-equity-caption">${_renderEquityCaption(meta, data?.warnings || [], mode)}${statusHint ? ` · <strong>${escapeHtml(statusHint)}</strong>` : ""}</p>
      <div id="etf-equity-status"></div>
    </div>
  `;

  // Wire buttons
  const generateBtn = document.getElementById("etf-equity-generate");
  if (generateBtn) {
    generateBtn.addEventListener("click", () => void loadEquityCurve());
  }
  const modeButtons = document.querySelectorAll(".etf-equity-mode-btn");
  modeButtons.forEach((btn) => {
    btn.addEventListener("click", () => {
      const nextMode = btn.getAttribute("data-equity-mode");
      if (nextMode && nextMode !== equityCurveMode) {
        equityCurveMode = nextMode;
        // Re-render shell (with empty cache for the new mode) and fetch
        renderEquityCurve(equityCurveCache, equityCurveMode);
        void loadEquityCurve();
      }
    });
  });
  if (mode === "simulation") {
    const monthInput = document.getElementById("etf-equity-from-month");
    if (monthInput) {
      monthInput.addEventListener("change", () => void loadEquityCurve());
    }
    const capitalInput = document.getElementById("etf-equity-initial-capital");
    if (capitalInput) {
      capitalInput.addEventListener("change", () => void loadEquityCurve());
    }
    const monthlyInput = document.getElementById("etf-equity-monthly-amount");
    if (monthlyInput) {
      monthlyInput.addEventListener("change", () => void loadEquityCurve());
    }
    const freqInput = document.getElementById("etf-equity-frequency");
    if (freqInput) {
      mountDropdown(freqInput, {
        items: [
          { value: "month", label: "月定投" },
          { value: "week", label: "周定投" },
        ],
        value: equityCurveFrequency,
        placeholder: "选择频率",
        onChange: (v) => {
          equityCurveFrequency = v === "week" ? "week" : "month";
          void loadEquityCurve();
        },
      });
    }
    const offsetInput = document.getElementById("etf-equity-offset-days");
    if (offsetInput) {
      offsetInput.addEventListener("change", () => void loadEquityCurve());
    }
  } else {
    const dateInput = document.getElementById("etf-equity-from-date");
    if (dateInput) {
      dateInput.addEventListener("change", () => void loadEquityCurve());
    }
  }

  _renderEquityChart(data, mode);
}

// Color cue for the rebalance vertical-line annotation:
// - dominatedBy === "sell": more symbols sold than bought this month →
//   bearish red. The strategy was trimming overweight positions.
// - dominatedBy === "buy": more bought than sold → bullish green.
//   Strategy was topping up underweight positions.
// - dominatedBy === "neutral": equal counts or single-side → muted grey.
const REBALANCE_LINE_COLORS = {
  // §Monet palette lock: sell → --bearish (#b07558), buy → --accent (#5b8a83),
  // neutral → --neutral (#7d8893). Aligns with monitoring/analysis/btc charts.
  sell: "rgba(176, 117, 88, 0.7)",
  buy: "rgba(91, 138, 131, 0.7)",
  neutral: "rgba(125, 136, 147, 0.55)",
};

// Monet-palette tokens resolved at render time so any future theme
// retune in styles.css propagates here. Fallbacks match :root in
// styles.css (Monet-aligned palette block) so a stale computed style
// still produces a sensible colour.
const EQUITY_COLORS = {
  primary:        _monetToken("--accent", "#5b8a83"),           // --bullish / --accent
  primarySoft:    _monetToken("--bullish-soft", "rgba(91, 138, 131, 0.18)"),
  bearish:        _monetToken("--bearish", "#b07558"),          // --bearish
  bearishSoft:    _monetToken("--bearish-soft", "rgba(176, 117, 88, 0.18)"),
  neutral:        _monetToken("--neutral", "#7d8893"),          // --neutral
  neutralSoft:    _monetToken("--neutral-soft", "rgba(125, 136, 147, 0.14)"),
  // Fill colour for the strategy-market-value area UNDER the curve
  // (changed 2026-08-07 from --bullish-soft to a neutral tone so the
  // weekly contrast bars sit on a non-tinted canvas; with a teal fill,
  // "up" bars disappeared into the fill and the strategy-vs-lump-sum
  // signal was unreadable).
  fillArea:       _monetToken("--neutral-soft", "rgba(125, 136, 147, 0.14)"),
  // Weekly contrast-bar fills use SOLID palette anchors at higher
  // alpha (0.55) so the strategy-vs-lump-sum signal is visible at
  // chart-thumbnail size. The legacy --*-soft tokens at alpha 0.18
  // were visually indistinguishable from the neutral fill area.
  weeklyUpFill:   "rgba(91, 138, 131, 0.55)",                   // 策略赢 → 青绿
  weeklyDownFill: "rgba(176, 117, 88, 0.55)",                   // 策略输 → 暖棕
  weeklyEvenFill: "rgba(125, 136, 147, 0.45)",                  // 持平 → 中性
  referenceLine:  _monetToken("--warning", "#b8924a"),          // --warning / --warm
  zeroBaseline:   _monetToken("--chart-reference-line", "rgba(83, 99, 108, 0.72)"),
};

function _buildRebalanceByDate(events) {
  // Map date-string -> { sells: [[code, notional], ...], buys: [...],
  //   dominatedBy, sellTotal, buyTotal, rationale } so the chart can
  // both colour the dashed line and surface a tooltip breakdown on hover.
  // Sells and buys are sorted by the engine's execution order:
  // sells ascending by notional (most-overweight first), buys descending
  // by notional (most-underweight first).
  const out = new Map();
  (events || [])
    .filter((e) => e && e.kind === "quarterly_rebalance")
    .forEach((e) => {
      const trades = e.rebalance_trades || {};
      const sells = Object.entries(trades)
        .filter(([, v]) => Number(v) < 0)
        .map(([code, v]) => [code, Math.abs(Number(v))])
        .sort((a, b) => b[1] - a[1]); // largest |sell| first for display
      const buys = Object.entries(trades)
        .filter(([, v]) => Number(v) > 0)
        .map(([code, v]) => [code, Number(v)])
        .sort((a, b) => b[1] - a[1]); // largest buy first for display
      let dominatedBy = "neutral";
      if (sells.length > buys.length) dominatedBy = "sell";
      else if (buys.length > sells.length) dominatedBy = "buy";
      const sellTotal = sells.reduce((acc, [, v]) => acc + v, 0);
      const buyTotal = buys.reduce((acc, [, v]) => acc + v, 0);
      out.set(String(e.date), {
        sells,
        buys,
        dominatedBy,
        sellTotal,
        buyTotal,
        rationale: e.trade_rationale || {},
      });
    });
  return out;
}

function _renderEquityChart(data, mode) {
  const canvas = document.getElementById("etf-equity-canvas");
  if (!canvas) return;
  if (typeof window.Chart === "undefined") {
    return;
  }
  destroyChartsForPage("ashare-etf-equity-");
  if (!data) return;

  // Weekly x-axis granularity: when the backend emits a weekly
  // mark-to-market trail, prefer it over the legacy monthly labels so
  // the equity curve and the weekly bars line up tick-for-tick.
  const weeklySeries = Array.isArray(data.weekly_series) && data.weekly_series.length
    ? data.weekly_series
    : null;
  const weeks = Array.isArray(data.weeks) && data.weeks.length
    ? data.weeks
    : null;

  let labels;
  let datasets;
  let annotations = [];
  let rebalanceByDate = new Map();

  if (mode === "simulation") {
    // Prefer weekly granularity when the backend provides it (2026-08-07):
    // the equity curve, the rebalance annotations, and the weekly bars
    // all line up at weekly x-axis ticks so the user sees one bar per
    // ISO week. Falls back to monthly labels if no weekly trail is
    // present (legacy clients / cached responses).
    if (weeklySeries && weeks) {
      labels = weeks.map((d) => String(d));
    } else {
      labels = (data.months || []).map((d) => String(d));
    }
    const srcSeries = weeklySeries || data.series || [];
    const costValue = srcSeries.map((p) => Number(p.cost_value));
    // Present-value curves (2026-08-07): the strategy's total market value
    // vs the same-cash lump-sum benchmark vs the cumulative invested capital.
    // All three are money on one yuan axis, so the DCA-vs-buy-and-hold gap is
    // directly comparable (the old return-percentage pair was dominated by
    // the early lump-sum deployment and looked near-identical to the
    // benchmark). The strategy series is the FULL strategy — initial build +
    // 周/月定投 + 季末带宽调仓 — not a plain DCA line.
    const strategyValue = srcSeries.map((p) => Number(p.total_value || 0));
    const lumpSumValue = srcSeries.map((p) => Number(p.lump_sum_value || 0));
    if (!labels.length) return;
    datasets = [
      // Full-strategy present value — --accent (Monet teal), matching the
      // headline curve colour of the monitoring/analysis/btc charts.
      lineDataset("策略权益", strategyValue, EQUITY_COLORS.primary, {
        fill: "origin",
        // 2026-08-07: switched from --bullish-soft to a neutral fill
        // (see EQUITY_COLORS.fillArea comment) so the weekly contrast
        // bars on top of the strategy curve are readable.
        backgroundColor: EQUITY_COLORS.fillArea,
        borderWidth: 2.6,
        tension: 0.18,
      }),
      // 累计投入 reference line — how much capital was actually deployed
      // (initial + every 定投), so the gap to the strategy value reads as
      // the unrealised gain. --warning (warm amber) keeps it distinct.
      lineDataset("累计投入", costValue, EQUITY_COLORS.referenceLine, {
        borderDash: [6, 4],
        borderWidth: 1.8,
        tension: 0.1,
      }),
      // Buy-and-hold benchmark — same-cash lump sum opened on from_month,
      // never rebalanced.
      // 2026-08-07: bumped to a denser stroke (--info blue, larger dash
      // gap, 2.4px width) so the curve survives the weekly-x-axis
      // view. In the legacy monthly view a 1.6px [2,3] amber dash was
      // readable; under the weekly view the lump-sum curve sits in the
      // bottom ~5% of the chart range (the cashflow-pool value starts
      // at -658, the y-axis therefore extends to ≈ -12895, and the
      // cashflow-only portion of the lump-sum value hovers within a
      // 17px band at the chart bottom) so the old thin amber dashed
      // line was invisible. The blue dash is also visually distinct
      // from the cumulative-cost line (which stays amber) so the two
      // reference lines are easy to tell apart.
      lineDataset(
        "一次性投入 权益",
        lumpSumValue,
        _monetToken("--info", "#6b86a8"),
        {
          borderDash: [8, 5],
          borderWidth: 2.4,
          tension: 0.0,
        },
      ),
    ];
    // Annotate rebalance events with vertical dashed lines. The referenceLines
    // plugin finds the x position by label match (string compare); we pass
    // the date string verbatim so the dashed line lands on the exact
    // funding date (matches either the weekly tick or the monthly tick
    // according to the chart's x-axis granularity).
    rebalanceByDate = _buildRebalanceByDate(data.events);
    annotations = Array.from(rebalanceByDate.entries())
      .filter(([d]) => labels.includes(d))
      .map(([d, info]) => ({
        type: "verticalLine",
        axis_id: "x",
        x: d,
        color: REBALANCE_LINE_COLORS[info.dominatedBy]
          || REBALANCE_LINE_COLORS.neutral,
        width: 1.6,
        label: "调仓",
      }));
  } else {
    // Holdings (legacy equity-curve endpoint payload)
    labels = (data.labels || []).map((d) => String(d));
const totalValue = (data.total_value || []).map((v) => Number(v));
    if (!labels.length) return;
    datasets = [
      // Holdings-mode legacy curve — same Monet teal as the DCA mode
      // so switching between simulation / holdings doesn't recolour
      // the headline curve.
      lineDataset("总权益", totalValue, EQUITY_COLORS.primary, {
        fill: "origin",
        // Same neutral fill as the simulation curve (2026-08-07) so
        // weekly contrast bars / legend swatches stay consistent
        // across modes.
        backgroundColor: EQUITY_COLORS.fillArea,
        borderWidth: 2.6,
        tension: 0.18,
      }),
    ];
  }

  // Build weekly bars overlay items: one bar per ISO-week x-position,
  // coloured by strategy-vs-lump-sum return-pct delta. The plugin reads
  // strategyValue from datasets[0].data[index] (the 策略权益 curve) so
  // each bar is automatically clamped to live INSIDE the strategy
  // market-value fill area (top edge = curve, bottom edge = y=0).
  let weeklyBarsItems = [];
  let weeklyByDate = new Map();
  if (mode === "simulation" && weeklySeries && weeks) {
    weeklyBarsItems = weeklySeries.map((p, i) => {
      const dateStr = String(weeks[i]);
      const diffPct = Number(p.return_pct || 0) - Number(p.lump_sum_return_pct || 0);
      return { x: dateStr, diffPct };
    });
    weeklySeries.forEach((p, i) => {
      const dateStr = String(weeks[i]);
      weeklyByDate.set(dateStr, {
        strategy_pct: Number(p.return_pct || 0),
        lump_pct: Number(p.lump_sum_return_pct || 0),
        diff_pct: Number(p.return_pct || 0) - Number(p.lump_sum_return_pct || 0),
      });
    });
  }

  renderChart("ashare-etf-equity-canvas", canvas, {
    type: "line",
    // 2026-08-07: present-value view. All three datasets are money on a
    // single yuan axis — no more percent axis (the old dual-axis view paired
    // a percent axis with a yuan ``y1``; every curve now shares the yuan
    // scale so the strategy-vs-benchmark gap is directly readable).
    axes: {
      y: {
        // 元 label via ``value_format: "integer"`` — keeps the axis compact
        // using the standard ``formatChartValue`` pipeline (renders
        // ``12,482``). The prefix ¥ is added by the static guard; the
        // runtime formatter stays locale-neutral.
        profile: "raw",
        position: "left",
        value_format: "integer",
        padding_ratio: 0.06,
      },
    },
    annotations,
    weeklyBars: weeklyBarsItems,
    weeklyBarsOptions: {
      upFill: EQUITY_COLORS.weeklyUpFill,    // 策略赢 → 青绿 (alpha 0.55)
      downFill: EQUITY_COLORS.weeklyDownFill, // 策略输 → 暖棕 (alpha 0.55)
      evenFill: EQUITY_COLORS.weeklyEvenFill, // 持平 → 中性灰 (alpha 0.45)
      threshold: 0.005,                      // ±0.5% 死区
      barWidth: 0.7,                         // 占类别宽度 70%
    },
    data: { labels, datasets },
    options: {
      // Forward the rebalance annotations to the custom ``referenceLines``
      // chart.js plugin (see charts.js:363) so the vertical dashed lines
      // actually render on the canvas. Without this explicit merge the
      // top-level ``annotations`` config only reaches the plugin when
      // the caller also passes ``axes``, which the equity curve does not.
      plugins: {
        referenceLines: { annotations },
        weeklyBars: {
          items: weeklyBarsItems,
          upFill: EQUITY_COLORS.weeklyUpFill,
          downFill: EQUITY_COLORS.weeklyDownFill,
          evenFill: EQUITY_COLORS.weeklyEvenFill,
          threshold: 0.005,
          barWidth: 0.7,
        },
        legend: { display: true, position: "bottom" },
        tooltip: {
          callbacks: {
            label: (ctx) => {
              const label = ctx.dataset.label || "";
              // Every dataset is money (元) in the present-value view.
              return `${label} ${formatNumber(ctx.parsed.y, { maximumFractionDigits: 0 })}`;
            },
            // When the hovered x lands on a rebalance month, append a
            // buy/sell breakdown to the tooltip so users see which ETFs
            // were trimmed and which were topped up. When weekly x-axis
            // granularity is active, also append the per-week
            // strategy-vs-lump-sum return pcts that drive the bar colour.
            afterBody: (items) => {
              if (mode !== "simulation" || !items?.length) return "";
              const xLabel = String(items[0].label || "");
              const lines = [];
              const weekInfo = weeklyByDate.get(xLabel);
              if (weekInfo) {
                lines.push(
                  "",
                  `本周策略 ${pctSigned(weekInfo.strategy_pct)} / 一次性 ${pctSigned(weekInfo.lump_pct)} / 差 ${pctSigned(weekInfo.diff_pct)}`,
                );
              }
              const info = rebalanceByDate.get(xLabel);
              if (info) {
                lines.push("", `本次调仓 ${info.sells.length} 卖 / ${info.buys.length} 买`);
                // Show top 3 of each side; remaining count is summarised.
                info.sells.slice(0, 3).forEach(([code, v]) => {
                  lines.push(`  卖 ${code} ${formatNumber(v, { maximumFractionDigits: 0 })}`);
                });
                if (info.sells.length > 3) {
                  lines.push(`  …还有 ${info.sells.length - 3} 笔卖出`);
                }
                info.buys.slice(0, 3).forEach(([code, v]) => {
                  lines.push(`  买 ${code} ${formatNumber(v, { maximumFractionDigits: 0 })}`);
                });
                if (info.buys.length > 3) {
                  lines.push(`  …还有 ${info.buys.length - 3} 笔买入`);
                }
              }
              return lines;
            },
          },
        },
      },
    },
  });
}

async function loadEquityCurve() {
  const statusRoot = document.getElementById("etf-equity-status");
  equityCurveController?.abort();
  equityCurveController = new AbortController();
  const isSim = equityCurveMode === "simulation";
  // First-ever render has an EMPTY from-month input → this call is the
  // wide discovery window; record it BEFORE fetching, because the response
  // handler re-renders the shell which immediately fills the input with
  // meta.halos_listing_start (making a post-hoc emptiness check useless).
  const monthInput = document.getElementById("etf-equity-from-month");
  const discoveryCall = Boolean(isSim && monthInput && !monthInput.value);
  if (statusRoot) {
    statusRoot.innerHTML = statusBanner(
      isSim ? "正在模拟 ETF 资金投入策略..." : "正在拉取 ETF 历史净值...",
      "loading",
    );
  }
  try {
    let payload;
    let result;
    if (isSim) {
      payload = _buildSimulationPayload();
      result = await api.getEtfSimulation(payload, {
        signal: equityCurveController.signal,
      });
    } else {
      payload = _buildEquityPayload();
      result = await api.getEtfEquityCurve(payload, {
        signal: equityCurveController.signal,
      });
    }
    equityCurveCache = result;
    if (statusRoot) statusRoot.innerHTML = "";
    renderEquityCurve(result, equityCurveMode);
    // Discovery resolved: replay once from the six-all-present day (e.g.
    // 2023-07) so the chart starts at the first complete basket month.
    // The input is now non-empty, so the follow-up call is NOT a discovery
    // and this never loops.
    const halo = result?.meta?.halos_listing_start;
    if (discoveryCall && halo) {
      const nextInput = document.getElementById("etf-equity-from-month");
      if (nextInput) nextInput.value = String(halo).slice(0, 7);
      void loadEquityCurve();
    }
  } catch (error) {
    if (error?.name === "AbortError") return;
    console.error("ashare-etf:equity-curve:error", error);
    if (statusRoot) {
      statusRoot.innerHTML = statusBanner(
        `曲线拉取失败:${error?.message || "unknown"}`,
        "warning",
      );
    }
  }
}

function renderOverview() {
  // P5: Top bar removed — mode selector and summary are now in 持仓与执行
  // Keep etf-cash input here for state binding
  return `
    <input id="etf-cash" type="number" min="0" step="100" value="${escapeHtml(state.cashToInvest)}" hidden />
    <div id="etf-status"></div>
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
        <span><small>权益</small><b>${money(value)}</b></span>
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
  const summary = latestPlan?.deviation_summary || {};
  const cash = latestPlan?.cash || {};
  const portfolio = latestPlan?.portfolio || {};
  const warnings = latestPlan?.warnings || [];
  return `
    <section class="card etf-execution-table-card">
      <div class="section-head compact-head">
        <div>
          <p class="eyebrow">EXECUTION</p>
          <h2>持仓与执行</h2>
        </div>
        <div class="etf-mode-inline">
          <button type="button" class="primary-button compact" id="etf-refresh-button">刷新行情</button>
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
        </div>
      </div>
      <div class="etf-plan-inline">
        <div class="etf-summary-grid">
          <span><small>执行前总偏离</small><strong>${pct(summary.before_total_abs_deviation)}</strong></span>
          <span><small>执行后总偏离</small><strong>${pct(summary.after_total_abs_deviation)}</strong></span>
          <span><small>改善幅度</small><strong>${pct(summary.improvement_total_abs_deviation)}</strong></span>
          <span><small>现金占比</small><strong>${pct(cash.cash_weight_after)}</strong></span>
          <span><small>换手金额</small><strong>${money(portfolio.turnover_amount)}</strong></span>
          <span><small>交易笔数</small><strong>${formatNumber(portfolio.trade_count || 0, 0)}</strong></span>
        </div>
        ${warnings.length > 0 ? renderWarnings(warnings) : ""}
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
  renderEquityCurve(equityCurveCache);
  bindControls();
  restoreFocusedField(focused);
}

function updateStateFromInput(target) {
  if (!(target instanceof HTMLInputElement || target instanceof HTMLButtonElement)) return false;
  if (target.id === "etf-mode") {
    state.mode = target.value === "monthly_dca_quarterly_rebalance" ? "monthly_dca_quarterly_rebalance" : "weekly_dca_monthly_rebalance";
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
        { value: "weekly_dca_monthly_rebalance", label: "周度定投+月度调仓" },
        { value: "monthly_dca_quarterly_rebalance", label: "月度定投+季度调仓" },
      ],
      value: state.mode,
      placeholder: "选择模式",
      onChange: (v) => {
        state.mode = v === "monthly_dca_quarterly_rebalance" ? "monthly_dca_quarterly_rebalance" : "weekly_dca_monthly_rebalance";
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
  // 执行区两种策略形态(周度定投+月度调仓 / 月度定投+季度调仓)都是
  // "定投+调仓"组合;后端 PlanMode 只区分是否允许卖出超配资产,调仓形态
  // 统一映射 quarterly_rebalance(先卖超配→再买欠配)。定投频率是前端
  // 现金流概念,与优化器 mode 无关(2026-08-07: 修正 mode 字面量不匹配
  // 导致的 422)。
  const backendMode = "quarterly_rebalance";
  return {
    mode: backendMode,
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
  // Equity curve loads in parallel — never blocks initial paint of the
  // overview / quote deck / workbench.
  void loadEquityCurve();
  return {
    async mount() { await loadPromise; },
    async unmount() {
      activeController?.abort();
      planController?.abort();
      equityCurveController?.abort();
      activeController = null;
      planController = null;
      equityCurveController = null;
      if (debounceTimer) window.clearTimeout(debounceTimer);
      destroyChartsForPage("ashare-etf-equity-");
      void loadPromise.catch(() => null);
    },
    async pause() {},
    async resume() {},
  };
}

export const renderPage = renderAshareEtf;
