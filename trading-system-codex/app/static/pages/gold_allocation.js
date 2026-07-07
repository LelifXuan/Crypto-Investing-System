import { api } from "../core/api.js";
import { escapeHtml, formatNumber, setRoot, statusBanner } from "../core/dom.js";

const STORAGE_KEY = "gold_execution_v3_settings";

let controller = null;
let latestPlan = null;
let latestMarket = null;
let debounceTimer = null;

const DEFAULT_STATE = {
  dailyDcaAmount: 100,
  dipMultiplier: 5,
  availableCash: 2000,
  cooldownDays: 7,
  executedToday: false,
  lastDipAddDate: "",
  lastDipCycleId: "",
};

const ACTION_LABELS = {
  daily_dca_only: "执行基础定投",
  daily_dca_plus_dip_add: "执行基础定投与固定加仓",
  manual_check: "等待报价复核",
  no_action: "今日不新增",
};

const DCA_STATUS_LABELS = {
  execute: "今日执行",
  already_executed: "今日已记录",
  stale_quote: "报价待刷新",
  invalid_amount: "金额未设置",
  insufficient_cash: "现金不足",
};

const DIP_STATUS_LABELS = {
  not_triggered: "未触发",
  candidate: "观察中",
  triggered: "触发固定加仓",
  cooldown: "冷却中",
  invalid_amount: "参数未设置",
  insufficient_data: "指标不足",
  stale_quote: "报价待刷新",
};

function readState() {
  try {
    const saved = JSON.parse(window.localStorage.getItem(STORAGE_KEY) || "{}");
    const migrated = { ...DEFAULT_STATE, ...saved };
    if (saved.dipAddAmount && !saved.dipMultiplier) {
      const base = Number(migrated.dailyDcaAmount) || DEFAULT_STATE.dailyDcaAmount;
      migrated.dipMultiplier = Math.max(0, Number(saved.dipAddAmount) / base);
    }
    return migrated;
  } catch {
    return { ...DEFAULT_STATE };
  }
}

function writeState(next) {
  window.localStorage.setItem(STORAGE_KEY, JSON.stringify(next));
}

function numberOr(value, fallback = 0) {
  const number = Number(value);
  return Number.isFinite(number) ? number : fallback;
}

function baseAmount(state) {
  return Math.max(0, numberOr(state.dailyDcaAmount));
}

function dipAmount(state) {
  return Math.max(0, baseAmount(state) * Math.max(0, numberOr(state.dipMultiplier)));
}

function money(value, digits = 0) {
  const number = Number(value);
  if (!Number.isFinite(number)) return "-";
  return `${formatNumber(number, digits)} 元`;
}

function qty(value) {
  const number = Number(value);
  if (!Number.isFinite(number)) return "-";
  return `${formatNumber(number, 6)} XAUT`;
}

function compactDate(value) {
  if (!value) return "待刷新";
  return String(value).replace("T", " ").replace(/\.\d+.*$/, "");
}

function todayIso() {
  return new Date().toISOString().slice(0, 10);
}

function statusLabel(map, key) {
  return map[key] || "待确认";
}

function quoteFromMarket() {
  const price = Number(latestMarket?.price ?? latestMarket?.xaut_price);
  if (!Number.isFinite(price) || price <= 0) return null;
  return {
    price,
    updated_at: latestMarket?.updated_at || new Date().toISOString(),
  };
}

function payloadFromState(state) {
  return {
    symbol: "XAUT_USDT",
    daily_dca_amount: baseAmount(state),
    dip_add_amount: dipAmount(state),
    available_cash: numberOr(state.availableCash),
    cooldown_days: Math.max(0, numberOr(state.cooldownDays, DEFAULT_STATE.cooldownDays)),
    executed_today: Boolean(state.executedToday),
    last_dip_add_date: state.lastDipAddDate || null,
    last_dip_cycle_id: state.lastDipCycleId || null,
    quote: quoteFromMarket(),
  };
}

function quoteStateLabel(value) {
  if (value === "stale") return "报价待刷新";
  if (value === "fresh") return "报价可用";
  return "待确认";
}

function summarizeDipSignals(signals) {
  const items = Array.isArray(signals) ? signals : [];
  const priority = ["RSI14", "布林", "CCI20", "30 日", "60 日", "14 日", "7 日", "EMA20", "EMA50"];
  const picked = [];
  priority.forEach((keyword) => {
    const found = items.find((item) => String(item).includes(keyword));
    if (found && !picked.includes(found)) picked.push(found);
  });
  items.forEach((item) => {
    if (picked.length < 3 && !picked.includes(item)) picked.push(item);
  });
  return {
    primary: picked.slice(0, 3),
    extra: items.filter((item) => !picked.slice(0, 3).includes(item)),
  };
}

function persistTriggeredDipState(plan, currentState) {
  const dip = plan?.dip_add || {};
  if (dip.status !== "triggered" || !dip.cycle_id) return currentState;
  if (currentState.lastDipCycleId === dip.cycle_id) return currentState;
  const nextState = {
    ...currentState,
    lastDipAddDate: todayIso(),
    lastDipCycleId: dip.cycle_id,
  };
  writeState(nextState);
  return nextState;
}

function renderShell(state, banner = "") {
  return `
    <section class="hero-card gold-v3-hero">
      <div>
        <p class="eyebrow">GOLD EXECUTION</p>
        <h1>黄金配置</h1>
        <p>长期持有执行工作台：用 x 表示基础定投，用 n × x 表示黄金坑固定加仓。</p>
      </div>
      <button class="button compact" id="gold-reload-xaut" type="button">刷新 XAUT</button>
    </section>
    ${banner}
    <div class="gold-v3-layout">
      <section class="gold-top-grid">
        ${renderStrategyPanel(state)}
        ${renderMarketPanel()}
      </section>
      <section class="gold-formula-grid">
        ${renderFormulaCard("日常定投 x", "x", "每日纪律项", latestPlan?.daily_dca, money(baseAmount(state)))}
        ${renderFormulaCard("黄金坑 n × x", "n × x", "超跌事件固定项", latestPlan?.dip_add, `${formatNumber(numberOr(state.dipMultiplier), 2)} × x`)}
        ${renderTotalCard(state)}
      </section>
      <section class="gold-indicator-layout">
        ${renderIndicatorSection("核心指标", latestPlan?.diagnostics?.core_indicator_cards || [], "8 项核心指标用于复核日线样本和基础技术状态。")}
        ${renderIndicatorSection("派生指标", latestPlan?.diagnostics?.derived_indicator_cards || [], "6 项派生指标用于判断回撤、偏离和触发质量。")}
      </section>
      <section class="gold-bottom-grid">
        ${renderSettingsCard(state)}
        ${renderDiagnostics()}
      </section>
    </div>
  `;
}

function renderStrategyPanel(state) {
  const action = latestPlan?.execution?.action;
  const formula = latestPlan?.diagnostics?.strategy_formula || {
    base: "x",
    dip: "n × x",
    total_when_triggered: "x + n × x",
  };
  return `
    <section class="card gold-strategy-panel">
      <div class="section-head compact">
        <div>
          <p class="eyebrow">STRATEGY</p>
          <h2>代数化执行策略</h2>
        </div>
        <span class="chip">${escapeHtml(statusLabel(ACTION_LABELS, action))}</span>
      </div>
      <div class="gold-main-formula">
        <strong>${escapeHtml(formula.base)}</strong>
        <span>+</span>
        <strong>${escapeHtml(formula.dip)}</strong>
      </div>
      <p class="gold-strategy-copy">${escapeHtml(latestPlan?.execution?.summary || "正在读取 XAUT 报价与本地参数。")}</p>
      <div class="gold-strategy-metrics">
        <article><span>x 当前值</span><b>${money(baseAmount(state))}</b></article>
        <article><span>n 当前值</span><b>${formatNumber(numberOr(state.dipMultiplier), 2)}</b></article>
        <article><span>触发公式</span><b>${escapeHtml(formula.total_when_triggered)}</b></article>
      </div>
    </section>
  `;
}

function renderMarketPanel() {
  const quote = latestPlan?.quote || {};
  return `
    <section class="card gold-market-card">
      <div class="gold-card-head">
        <div>
          <p class="eyebrow">XAUT</p>
          <h2>XAUT 代理行情</h2>
        </div>
        <span>${quote.is_stale ? "报价待刷新" : "可用"}</span>
      </div>
      <div class="gold-market-price">${money(quote.price ?? latestMarket?.price, 2)}</div>
      <p class="section-summary">更新时间：${escapeHtml(compactDate(quote.updated_at || latestMarket?.updated_at))}</p>
      <div class="gold-card-metrics">
        <article><span>7 日变化</span><b>${formatPct(latestMarket?.ret_7d)}</b></article>
        <article><span>30 日变化</span><b>${formatPct(latestMarket?.ret_30d)}</b></article>
      </div>
    </section>
  `;
}

function renderFormulaCard(title, formula, subtitle, decision, valueText) {
  return `
    <article class="card gold-formula-card">
      <div class="gold-card-head">
        <div>
          <p class="eyebrow">${escapeHtml(subtitle)}</p>
          <h2>${escapeHtml(title)}</h2>
        </div>
        <span>${escapeHtml(statusLabel({ ...DCA_STATUS_LABELS, ...DIP_STATUS_LABELS }, decision?.status))}</span>
      </div>
      <div class="gold-formula-symbol">${escapeHtml(formula)}</div>
      <p>${escapeHtml(decision?.reason || "等待执行计划。")}</p>
      <small>当前参数：${escapeHtml(valueText)}</small>
    </article>
  `;
}

function renderTotalCard(state) {
  const execution = latestPlan?.execution || {};
  const totalWhenTriggered = baseAmount(state) + dipAmount(state);
  return `
    <article class="card gold-formula-card gold-formula-card--accent">
      <div class="gold-card-head">
        <div>
          <p class="eyebrow">TOTAL</p>
          <h2>今日合计</h2>
        </div>
        <span>${escapeHtml(statusLabel(ACTION_LABELS, execution.action))}</span>
      </div>
      <div class="gold-formula-symbol">x + n × x</div>
      <p>未触发黄金坑时只执行 x；触发时使用 x + n × x。</p>
      <div class="gold-card-metrics">
        <article><span>计划金额</span><b>${money(execution.total_amount)}</b></article>
        <article><span>理论上限</span><b>${money(totalWhenTriggered)}</b></article>
      </div>
    </article>
  `;
}

function renderIndicatorSection(title, cards, summary) {
  const items = Array.isArray(cards) ? cards : [];
  return `
    <section class="card gold-indicator-section">
      <div class="section-head compact">
        <div>
          <p class="eyebrow">INDICATORS</p>
          <h2>${escapeHtml(title)}</h2>
          <p class="section-summary">${escapeHtml(summary)}</p>
        </div>
      </div>
      <div class="gold-indicator-grid">
        ${items.map(renderIndicatorCard).join("") || `<article class="gold-indicator-card"><strong>待刷新</strong><span>指标正在读取</span></article>`}
      </div>
    </section>
  `;
}

function renderIndicatorCard(card) {
  return `
    <article class="gold-indicator-card" data-bias="${escapeHtml(card.bias || "neutral")}">
      <div>
        <strong>${escapeHtml(card.label || "指标")}</strong>
        <span class="gold-bias-chip gold-bias-${escapeHtml(card.bias || "neutral")}">${biasLabel(card.bias)}</span>
      </div>
      <b>${escapeHtml(card.display_value || "-")}</b>
      <small>${escapeHtml(card.note || "")}</small>
    </article>
  `;
}

function biasLabel(bias) {
  return {
    strong_bullish: "强势看多",
    bullish: "看多",
    neutral: "中性",
    bearish: "看空",
    strong_bearish: "强势看空",
    missing: "数据不足",
  }[bias] || "中性";
}

function renderMacroStrip(snapshot) {
  if (!snapshot) return "";
  const items = [
    { key: "real_yield_10y", label: "实际利率 (TIPS yield)", value: snapshot.real_yield_10y },
    { key: "dxy", label: "DXY 美元指数", value: snapshot.dxy },
    { key: "cpi_yoy", label: "CPI 同比", value: snapshot.cpi_yoy },
    { key: "vix", label: "VIX 波动率", value: snapshot.vix },
  ];
  const liquidityShock = snapshot._diagnostics?.liquidity_shock_detected;
  return `
    <section class="gold-bottom-group" data-section="macro-strip">
      <div class="section-head compact">
        <div>
          <p class="eyebrow">MACRO INPUTS</p>
          <h2>宏观输入</h2>
          <p class="section-summary">直接影响黄金价格的 4 个宏观信号 (real_yield_10y / DXY / CPI YoY / VIX)。</p>
        </div>
      </div>
      ${liquidityShock ? '<div class="gold-liquidity-shock-banner">⚠ 流动性冲击模式：VIX 急升 + DXY 走强 + 实际利率上行，短期黄金先被卖补保证金。</div>' : ""}
      <div class="gold-macro-strip">
        ${items.map((item) => renderMacroCard(item.label, item.value)).join("")}
      </div>
    </section>
  `;
}

function renderMacroCard(label, macro) {
  if (!macro || macro.status === "missing") {
    return `
      <article class="gold-macro-card" data-status="missing" data-bias="missing">
        <div>
          <strong>${escapeHtml(label)}</strong>
          <span class="gold-bias-chip gold-bias-missing">数据不足</span>
        </div>
        <b>—</b>
        <small>${escapeHtml(macro?.display_label || "")}</small>
      </article>
    `;
  }
  return `
    <article class="gold-macro-card" data-bias="${escapeHtml(macro.bias || "neutral")}">
      <div>
        <strong>${escapeHtml(label)}</strong>
        <span class="gold-bias-chip gold-bias-${escapeHtml(macro.bias || "neutral")}">${biasLabel(macro.bias)}</span>
      </div>
      <b>${formatNumber(macro.value, 2)}${escapeHtml(macro.unit || "")}</b>
      <small>${escapeHtml(macro.display_label)} · 来源 ${escapeHtml(macro.source)}</small>
      <p class="gold-macro-reason">${escapeHtml(macro.bias_reason || "")}</p>
    </article>
  `;
}

function renderSettingsCard(state) {
  return `
    <section class="card gold-settings-card">
      <div class="gold-card-head">
        <div>
          <p class="eyebrow">PARAMETERS</p>
          <h2>执行设置</h2>
        </div>
        <span>本地保存</span>
      </div>
      <div class="gold-settings-grid">
        ${renderNumberInput("dailyDcaAmount", "基础定投 x", state.dailyDcaAmount, "1")}
        ${renderNumberInput("dipMultiplier", "黄金坑系数 n", state.dipMultiplier, "0.1")}
        ${renderNumberInput("availableCash", "可用现金", state.availableCash, "1")}
        ${renderNumberInput("cooldownDays", "冷却天数", state.cooldownDays, "1")}
        ${renderDateInput("lastDipAddDate", "上次加仓日期", state.lastDipAddDate)}
        ${renderTextInput("lastDipCycleId", "上次事件编号", state.lastDipCycleId)}
      </div>
      <label class="gold-checkbox">
        <input id="gold-executedToday" data-gold-field="executedToday" type="checkbox" ${state.executedToday ? "checked" : ""}>
        <span>今日基础定投已记录</span>
      </label>
    </section>
  `;
}

function renderNumberInput(field, label, value, step) {
  return `
    <label>
      <span>${escapeHtml(label)}</span>
      <input data-gold-field="${field}" type="number" min="0" step="${escapeHtml(step)}" value="${escapeHtml(String(value ?? ""))}">
    </label>
  `;
}

function renderDateInput(field, label, value) {
  return `
    <label>
      <span>${escapeHtml(label)}</span>
      <input data-gold-field="${field}" type="date" value="${escapeHtml(String(value ?? ""))}">
    </label>
  `;
}

function renderTextInput(field, label, value) {
  return `
    <label>
      <span>${escapeHtml(label)}</span>
      <input data-gold-field="${field}" type="text" value="${escapeHtml(String(value ?? ""))}">
    </label>
  `;
}

function renderDiagnostics() {
  const diagnostics = latestPlan?.diagnostics || {};
  const signals = Array.isArray(latestPlan?.dip_add?.triggered_signals)
    ? latestPlan.dip_add.triggered_signals
    : [];
  const signalSummary = summarizeDipSignals(signals);
  const coreCount = Array.isArray(diagnostics.core_indicator_cards) ? diagnostics.core_indicator_cards.length : 0;
  const derivedCount = Array.isArray(diagnostics.derived_indicator_cards) ? diagnostics.derived_indicator_cards.length : 0;
  return `
    <section class="card gold-system-card">
      <div class="section-head compact">
        <div>
          <p class="eyebrow">SYSTEM</p>
          <h2>系统诊断</h2>
          <p class="section-summary">用于复核报价、K 线样本和指标状态，不改变日常定投纪律。</p>
        </div>
      </div>
      <div class="gold-diagnostics-grid">
        <article><span>报价状态</span><b>${quoteStateLabel(diagnostics.quote_state)}</b></article>
        <article><span>K 线数量</span><b>${escapeHtml(String(diagnostics.candle_count ?? "-"))}</b></article>
        <article><span>核心指标</span><b>${coreCount ? `${coreCount} 项` : "待刷新"}</b></article>
        <article><span>派生指标</span><b>${derivedCount ? `${derivedCount} 项` : "待刷新"}</b></article>
      </div>
      <div class="gold-diagnostics-lists">
        <p>额外信号：${signalSummary.extra.length ? signalSummary.extra.map((item) => escapeHtml(item)).join(" / ") : "无更多信号。"}</p>
      </div>
    </section>
  `;
}

function formatPct(value) {
  const number = Number(value);
  if (!Number.isFinite(number)) return "-";
  return `${formatNumber(number * 100, 1)}%`;
}

function readFormState() {
  const state = readState();
  document.querySelectorAll("[data-gold-field]").forEach((input) => {
    const field = input.dataset.goldField;
    state[field] = input.type === "checkbox" ? input.checked : input.value;
  });
  writeState(state);
  return state;
}

function schedulePlanReload() {
  window.clearTimeout(debounceTimer);
  debounceTimer = window.setTimeout(() => {
    loadExecutionPlan({ preserveShell: true }).catch((error) => {
      console.error("gold execution reload failed", error);
    });
  }, 450);
}

async function loadExecutionPlan({ forceMarket = false, preserveShell = false } = {}) {
  if (controller) controller.abort();
  controller = new AbortController();
  let state = preserveShell ? readFormState() : readState();
  if (!preserveShell) {
    setRoot(renderShell(state, statusBanner("正在读取黄金执行计划", "loading")));
  }
  try {
    latestMarket = await api.getGoldMarketState({ force: forceMarket, signal: controller.signal });
  } catch (error) {
    if (error?.name !== "AbortError") {
      console.warn("XAUT market state unavailable", error);
    }
  }
  latestPlan = await api.planGoldExecution(payloadFromState(state), { signal: controller.signal });
  state = persistTriggeredDipState(latestPlan, state);
  setRoot(renderShell(state, statusBanner("黄金执行计划已生成", "neutral")));
  bindEvents();
}

function bindEvents() {
  document.querySelectorAll("[data-gold-field]").forEach((input) => {
    input.addEventListener(input.type === "checkbox" ? "change" : "input", schedulePlanReload);
  });
  document.getElementById("gold-reload-xaut")?.addEventListener("click", () => {
    loadExecutionPlan({ forceMarket: true }).catch((error) => {
      console.error("gold reload failed", error);
      setRoot(renderShell(readState(), statusBanner("XAUT 刷新失败，可稍后重试", "error")));
      bindEvents();
    });
  });
}

export async function renderGoldAllocation() {
  const loadPromise = loadExecutionPlan().catch((error) => {
    if (error?.name !== "AbortError") console.error("gold execution initial load failed", error);
  });
  return {
    unmount() {
      if (controller) controller.abort();
      window.clearTimeout(debounceTimer);
    },
    ready: loadPromise,
  };
}
