let api;
let appState;
let getInstrumentMeta;
let persistState;
let emptyState;
let errorState;
let escapeHtml;
let formatDateTime;
let formatNumber;
let setRoot;
let statusBanner;
let statusChip;

const TIMEFRAMES = ["1h", "4h", "1d", "1w", "1M"];
let lastBundle = null;
let activeController = null;
let requestToken = 0;
let pollTimer = null;

const STATE_CONFIG = {
  NO_EDGE: { label: "多空不明", tone: "chip-neutral", hint: "多空分差不足，等待更清晰的结构与触发。" },
  OBSERVE: { label: "观察等待", tone: "chip-neutral", hint: "已有线索，但暂未形成可执行策略。" },
  CONFLICTED_NO_TRADE: { label: "多空冲突", tone: "chip-warning", hint: "多空证据互相抵消，暂不交易。" },
  LONG_BIAS: { label: "偏多观察", tone: "chip-bullish", hint: "多头占优，但触发条件未齐。" },
  SHORT_BIAS: { label: "偏空观察", tone: "chip-bearish", hint: "空头占优，但触发条件未齐。" },
  SETUP_DETECTED: { label: "策略结构已形成", tone: "chip-neutral", hint: "已有可跟踪 setup，等待触发或失效。" },
  WAIT_LONG_CONFIRMATION: { label: "等待多头确认", tone: "chip-bullish", hint: "偏多结构存在，等待入场触发。" },
  WAIT_SHORT_CONFIRMATION: { label: "等待空头确认", tone: "chip-bearish", hint: "偏空结构存在，等待入场触发。" },
  WAIT_LOWER_TF_CONFIRMATION: { label: "等待次级周期确认", tone: "chip-warning", hint: "当前周期有方向优势，但缺少低一级触发周期确认。" },
  WAIT_PULLBACK_CONFIRMATION: { label: "等待反抽/回踩", tone: "chip-warning", hint: "等待价格回到更合理的确认区。" },
  LONG_TRIGGERED: { label: "多头策略已触发", tone: "chip-bullish", hint: "多头入场条件已触发。" },
  SHORT_TRIGGERED: { label: "空头策略已触发", tone: "chip-bearish", hint: "空头入场条件已触发。" },
  TREND_FOLLOW_TRIGGERED: { label: "强趋势追随已触发", tone: "chip-bullish", hint: "趋势强度、动量与波动扩张共振。" },
  BREAKDOWN_TRIGGERED: { label: "破位跟随已触发", tone: "chip-bearish", hint: "价格已跌破关键确认位。" },
  BREAKOUT_TRIGGERED: { label: "突破跟随已触发", tone: "chip-bullish", hint: "价格已突破关键确认位。" },
  MOVE_MISSED: { label: "原计划入场已错过", tone: "chip-warning", hint: "价格已经离冻结入场位过远，不再按原计划等待。" },
  WAIT_RETEST_AFTER_MISSED_MOVE: { label: "等待反抽/回踩", tone: "chip-warning", hint: "行情已走出，等待新的反抽或回踩确认。" },
  TP1_HIT: { label: "第一目标已触发", tone: "chip-bullish", hint: "原 setup 已到达第一止盈目标，进入复盘或持有管理语境。" },
  TP2_HIT: { label: "第二目标已触发", tone: "chip-bullish", hint: "原 setup 已到达第二止盈目标。" },
  STOP_HIT: { label: "止损/失效已触发", tone: "chip-danger", hint: "原 setup 已触发止损或失效位。" },
  SETUP_EXPIRED: { label: "策略计划已过期", tone: "chip-neutral", hint: "原 setup 有效期已过。" },
  SETUP_INVALIDATED: { label: "策略结构已失效", tone: "chip-danger", hint: "结构条件已经破坏。" },
  INVALID_PLAN_LEVELS: { label: "策略价位无效", tone: "chip-danger", hint: "入场、止损、止盈顺序不满足方向约束。" },
  EVENT_WAIT: { label: "事件窗口等待", tone: "chip-warning", hint: "事件窗口影响较大，等待落地。" },
  RISK_OFF: { label: "风险关闭", tone: "chip-danger", hint: "风险门禁触发，暂停交易。" },
};

const BIAS_LABELS = {
  long: "偏多",
  short: "偏空",
  neutral: "中性",
  none: "多空不明",
  conflicted: "冲突",
  risk_off: "风险关闭",
};

const PERMISSION_LABELS = {
  allow: "允许执行",
  allowed: "允许执行",
  conditional: "条件允许",
  wait: "等待",
  observe: "仅观察",
  observe_only: "仅观察",
  no_trade: "禁止交易",
  blocked: "禁止交易",
  risk_off: "风险关闭",
};

const GATE_STATUS_LABELS = {
  pass: "通过",
  fail: "失败",
  warn: "警告",
  missing: "缺失",
};

async function ensureDeps() {
  if (api && appState) return;
  const assetVersion = window.__ASSET_VERSION__
    ? `?v=${encodeURIComponent(window.__ASSET_VERSION__)}`
    : "";
  const [apiModule, stateModule, domModule] = await Promise.all([
    import(`../core/api.js${assetVersion}`),
    import(`../core/state.js${assetVersion}`),
    import(`../core/dom.js${assetVersion}`),
  ]);
  ({ api } = apiModule);
  ({ appState, getInstrumentMeta, persistState } = stateModule);
  ({
    emptyState,
    errorState,
    escapeHtml,
    formatDateTime,
    formatNumber,
    setRoot,
    statusBanner,
    statusChip,
  } = domModule);
}

function cleanText(value, fallback = "-") {
  if (value === null || value === undefined || value === "") return fallback;
  return String(value).replace(/_/g, " ");
}

function numberText(value, fallback = "0") {
  if (value === null || value === undefined || value === "") return fallback;
  return formatNumber(value, 2);
}

function stateInfo(state) {
  return STATE_CONFIG[state] || {
    label: cleanText(state, "观察等待"),
    tone: "chip-neutral",
    hint: "等待下一轮策略信号。",
  };
}

function labelFromMap(map, value, fallback = "-") {
  if (!value) return fallback;
  return map[String(value).toLowerCase()] || cleanText(value, fallback);
}

function cacheTone(state) {
  if (["fresh", "ready"].includes(state)) return "success";
  if (["stale", "updating", "missing"].includes(state)) return "warning";
  if (["degraded", "error"].includes(state)) return "danger";
  return "info";
}

function selectField(label, id, options) {
  return `
    <label class="strategy-control-field">
      <span>${escapeHtml(label)}</span>
      <select id="${escapeHtml(id)}">
        ${options.map((item) => `
          <option value="${escapeHtml(item.value)}" ${item.selected ? "selected" : ""}>${escapeHtml(item.label)}</option>
        `).join("")}
      </select>
    </label>
  `;
}

function miniMetric(label, value, tone = "") {
  return `
    <div class="strategy-mini-metric ${tone}">
      <span>${escapeHtml(label)}</span>
      <strong>${escapeHtml(cleanText(value))}</strong>
    </div>
  `;
}

function list(items, fallback, limit = 5) {
  const filtered = (items || []).filter(Boolean).slice(0, limit);
  if (!filtered.length) return `<p class="muted">${escapeHtml(fallback)}</p>`;
  return `<ul>${filtered.map((item) => `<li>${escapeHtml(cleanText(item))}</li>`).join("")}</ul>`;
}

function renderShell() {
  const instrument = getInstrumentMeta(appState.selectedInstrumentId);
  setRoot(`
    <section class="strategy-toolbar card strategy-compact-toolbar">
      <div>
        <p class="eyebrow">AI STRATEGY</p>
        <h2>市场多空策略信号</h2>
        <p class="muted">读取已有快照与缓存，跟踪当前市场 setup 的生命周期、触发条件和风险约束。</p>
      </div>
      <div class="strategy-actions">
        <button class="button-link" id="strategy-save-snapshot">保存信号</button>
        <button class="primary-action" id="strategy-refresh">刷新信号</button>
      </div>
    </section>

    <section class="strategy-control-panel card">
      ${selectField("交易标的", "strategy-instrument", appState.instruments.map((item) => ({
        value: item.id,
        label: `${item.code} · ${item.name}`,
        selected: item.id === appState.selectedInstrumentId,
      })))}
      ${selectField("观察周期", "strategy-timeframe", TIMEFRAMES.map((item) => ({
        value: item,
        label: item,
        selected: item === appState.selectedTimeframe,
      })))}
      <div class="strategy-control-note">当前页只输出市场策略信号，不记录真实持仓，也不自动下单。</div>
    </section>

    <div id="strategy-status">
      ${statusBanner(`${instrument.code} · ${appState.selectedTimeframe} 正在读取策略缓存`, "info")}
    </div>
    <section id="strategy-content" class="strategy-content">
      ${emptyState("正在读取最近一次可用策略信号。")}
    </section>
  `);
}

function renderScoreBars(decision) {
  const values = [
    ["多头", Number(decision.long_score || 0), "bull"],
    ["空头", Number(decision.short_score || 0), "bear"],
    ["中性", Number(decision.neutral_score || 0), "neutral"],
  ];
  const max = Math.max(...values.map((item) => Math.abs(item[1])), 1);
  return `
    <div class="strategy-score-bars">
      ${values.map(([label, value, tone]) => `
        <div class="strategy-score-bar ${tone}">
          <div class="strategy-score-bar-head">
            <span>${escapeHtml(label)}</span>
            <strong>${numberText(value)}</strong>
          </div>
          <i style="width:${Math.min(100, Math.abs(value) / max * 100)}%"></i>
        </div>
      `).join("")}
    </div>
  `;
}

function formatZone(zone) {
  if (Array.isArray(zone) && zone.length) return zone.map((item) => numberText(item)).join(" - ");
  return cleanText(zone, "-");
}

function renderSetupContinuity(decision) {
  const setup = decision.active_setup || {};
  const lifecycle = decision.setup_lifecycle || {};
  const lowerTf = decision.lower_tf_confirmation || {};
  if (!setup.setup_id && !lifecycle.state && !lowerTf.required_timeframe) {
    return `<article class="card strategy-compact-card"><h3>Setup 连续性</h3><p class="muted">当前没有冻结 setup，等待下一次有效策略结构形成。</p></article>`;
  }
  return `
    <article class="card strategy-compact-card">
      <div class="card-head-inline">
        <div>
          <p class="eyebrow">SETUP LIFECYCLE</p>
          <h3>Setup 连续性</h3>
        </div>
        ${statusChip(stateInfo(lifecycle.state || decision.strategy_state).label, stateInfo(lifecycle.state || decision.strategy_state).tone)}
      </div>
      <div class="strategy-inline-metrics">
        ${miniMetric("Setup ID", setup.setup_id || "-")}
        ${miniMetric("创建时间", formatDateTime(setup.created_at) || "-")}
        ${miniMetric("入场模式", setup.entry_mode || decision.entry_mode || "-")}
        ${miniMetric("冻结入场价", numberText(setup.entry_price, "-"))}
        ${miniMetric("冻结止损", numberText(setup.stop_price, "-"))}
        ${miniMetric("TP1 / TP2", `${numberText(setup.take_profit_1, "-")} / ${numberText(setup.take_profit_2, "-")}`)}
        ${miniMetric("当前生命周期", lifecycle.state_label || stateInfo(lifecycle.state).label || "-")}
        ${miniMetric("次级确认周期", lowerTf.required_timeframe || "-")}
      </div>
      <p class="muted">${escapeHtml(cleanText(lifecycle.reason || (lowerTf.missing ? "缺少次级周期触发数据。" : "setup 状态随刷新持续评估。")))}</p>
    </article>
  `;
}

function renderPlanSummary(title, plan, fallback) {
  if (!plan || (!plan.pattern_type && !plan.pattern_label && !plan.strategy_logic)) {
    return `<article class="strategy-plan-compact muted-card"><strong>${escapeHtml(title)}</strong><p>${escapeHtml(fallback)}</p></article>`;
  }
  return `
    <article class="strategy-plan-compact">
      <div class="card-head-inline">
        <div>
          <p class="eyebrow">${escapeHtml(title)}</p>
          <h3>${escapeHtml(cleanText(plan.pattern_label || plan.pattern_type || "策略路径"))}</h3>
        </div>
        ${plan.risk_reward_ratio ? statusChip(`RR ${numberText(plan.risk_reward_ratio)}`, "chip-neutral") : ""}
      </div>
      <p>${escapeHtml(cleanText(plan.strategy_logic || "等待更多确认。"))}</p>
      <div class="strategy-inline-metrics">
        ${miniMetric("入场区", formatZone(plan.entry_zone || plan.entry_price_range))}
        ${miniMetric("止损", plan.stop_loss_rule || "-")}
        ${miniMetric("止盈", plan.take_profit_rule || "-")}
      </div>
      <details>
        <summary>查看条件</summary>
        <div class="strategy-list-pair">
          <div><strong>确认条件</strong>${list(plan.entry_conditions || plan.confirmation_criteria, "暂无确认条件")}</div>
          <div><strong>失效条件</strong>${list(plan.invalidation_rules || plan.invalidation_criteria, "暂无失效条件")}</div>
        </div>
      </details>
    </article>
  `;
}

function normalizeCheck(item) {
  const raw = cleanText(item.status || (item.met ? "满足" : "未满足"));
  const lower = raw.toLowerCase();
  const met = item.met === true || ["满足", "通过", "satisfied", "met", "pass"].includes(lower);
  const partial = raw.includes("部分") || lower === "partial";
  return {
    label: cleanText(item.condition || item.name || "-"),
    value: cleanText(item.current_value ?? item.value ?? ""),
    status: partial ? "部分满足" : met ? "满足" : raw || "未满足",
    tone: met ? "chip-bullish" : partial ? "chip-warning" : "chip-neutral",
  };
}

function renderChecklist(items) {
  const normalized = (items || []).map(normalizeCheck).filter((item) => item.label !== "-");
  if (!normalized.length) return `<p class="muted">暂无入场条件检查。</p>`;
  return `
    <div class="strategy-checklist compact">
      ${normalized.map((item) => `
        <div class="strategy-check-row">
          <strong>${escapeHtml(item.label)}</strong>
          <span>${escapeHtml(item.value)}</span>
          ${statusChip(item.status, item.tone)}
        </div>
      `).join("")}
    </div>
  `;
}

function diagnosticTone(status) {
  if (status === "pass") return "chip-bullish";
  if (status === "missing" || status === "warn") return "chip-warning";
  if (status === "fail") return "chip-danger";
  return "chip-neutral";
}

function renderGateDiagnostics(decision) {
  const gates = decision.trigger_diagnostics || decision.gates || [];
  if (!gates.length) return `<p class="muted">暂无额外门禁诊断。</p>`;
  return `
    <div class="strategy-checklist compact">
      ${gates.slice(0, 10).map((gate) => `
        <div class="strategy-check-row">
          <strong>${escapeHtml(cleanText(gate.code || gate.name || "gate"))}</strong>
          <span>${escapeHtml(cleanText(gate.message || gate.reason || ""))}</span>
          <span>${escapeHtml(cleanText(gate.current ?? ""))}${gate.required !== undefined ? ` / ${escapeHtml(cleanText(gate.required))}` : ""}</span>
          ${statusChip(GATE_STATUS_LABELS[gate.status] || cleanText(gate.status || gate.severity || "提示"), diagnosticTone(gate.status))}
        </div>
      `).join("")}
    </div>
  `;
}

function renderEvidence(items) {
  const evidence = (items || []).filter(Boolean);
  if (!evidence.length) return `<p class="muted">暂无证据矩阵。</p>`;
  return `
    <div class="strategy-evidence-compact">
      ${evidence.slice(0, 6).map((item) => `
        <article>
          <strong>${escapeHtml(cleanText(item.name || item.label || "-"))}</strong>
          <span>多 ${numberText(item.long_score ?? item.score)} / 空 ${numberText(item.short_score ?? 0)}</span>
          <p>${escapeHtml(cleanText(item.detail || item.message || ""))}</p>
        </article>
      `).join("")}
    </div>
  `;
}

function renderReasons(decision) {
  const reasons = [
    ...(decision.no_trade_reasons || []),
    ...(decision.conflict_reasons || []),
    ...(decision.risk_reasons || []),
  ].filter(Boolean);
  const gates = (decision.gates || []).map((item) => item.message || item.reason || item.name).filter(Boolean);
  return list(reasons.length ? reasons : gates, "暂无阻断门禁。", 6);
}

function renderBundle(bundle) {
  const decision = bundle.decision || {};
  const state = decision.strategy_state || "NO_EDGE";
  const info = stateInfo(state);
  const primary = decision.primary_strategy || {};
  const alternative = decision.alternative_strategy || decision.backup_strategy || {};
  const instrument = getInstrumentMeta(bundle.instrument_id || appState.selectedInstrumentId);
  const generatedAt = formatDateTime(bundle.generated_at || bundle.snapshot_at);
  const permission = labelFromMap(PERMISSION_LABELS, decision.strategy_permission_label || decision.strategy_permission);
  const bias = decision.strategy_bias_label || labelFromMap(BIAS_LABELS, decision.strategy_bias, "中性");
  lastBundle = bundle;

  document.getElementById("strategy-status").innerHTML = statusBanner(
    bundle.status_message || `策略缓存状态：${cleanText(bundle.cache_state || bundle.status || "ready")}`,
    cacheTone(bundle.cache_state || bundle.status),
  );

  document.getElementById("strategy-content").innerHTML = `
    <section class="strategy-dashboard">
      <article class="card strategy-primary-card">
        <div class="strategy-decision-head">
          <div>
            <p class="eyebrow">MARKET STRATEGY SIGNAL</p>
            <h2>${escapeHtml(info.label)}</h2>
            <p>${escapeHtml(instrument.code || bundle.instrument_id)} · ${escapeHtml(bundle.timeframe || appState.selectedTimeframe)} · ${escapeHtml(info.hint)}</p>
          </div>
          ${statusChip(bias, info.tone)}
        </div>
        <div class="strategy-primary-grid">
          ${miniMetric("交易许可", permission, "accent")}
          ${miniMetric("数据质量", numberText(decision.data_quality_score ?? decision.confidence_score), "accent")}
          ${miniMetric("风险分", numberText(decision.risk_score), "warn")}
          ${miniMetric("更新时间", generatedAt || "-", "")}
        </div>
        ${decision.explain?.length ? `<ul class="strategy-explain-list">${decision.explain.slice(0, 3).map((item) => `<li>${escapeHtml(cleanText(item))}</li>`).join("")}</ul>` : ""}
      </article>

      <article class="card strategy-score-card">
        <div class="card-head-inline">
          <div>
            <p class="eyebrow">SCORES</p>
            <h3>多空评分</h3>
          </div>
          ${statusChip(cleanText(bundle.cache_state || bundle.status || "ready"), "chip-neutral")}
        </div>
        ${renderScoreBars(decision)}
      </article>
    </section>

    <section class="strategy-main-grid">
      ${renderPlanSummary("主策略", primary, "当前多空不明，暂不形成主策略。")}
      ${renderPlanSummary("备用策略", alternative, "主策略失效后再等待备用路径。")}
    </section>

    <section class="strategy-main-grid compact">
      ${renderSetupContinuity(decision)}
      <article class="card strategy-compact-card"><h3>入场条件检查</h3>${renderChecklist(decision.entry_checklist || [])}</article>
    </section>

    <section class="strategy-main-grid compact is-hidden">
      <article class="card strategy-compact-card"><h3>触发门禁诊断</h3>${renderGateDiagnostics(decision)}</article>
      <article class="card strategy-compact-card"><h3>风险门禁</h3>${renderReasons(decision)}</article>
    </section>

    <section class="strategy-main-grid compact strategy-single-column">
      <article class="card strategy-compact-card">
        <div class="card-head-inline">
          <div><p class="eyebrow">EVIDENCE MATRIX</p><h3>证据矩阵</h3></div>
          ${statusChip(`质量 ${numberText(decision.data_quality_score)}`, "chip-neutral")}
        </div>
        ${renderEvidence(decision.evidence_matrix || [])}
      </article>
      <article class="card strategy-compact-card is-hidden">
        <h3>复盘与迭代</h3>
        <div class="strategy-review-columns">
          <div><strong>复盘标签</strong>${list(decision.review_tags || [], "暂无复盘标签。", 5)}</div>
          <div><strong>迭代建议</strong>${list((bundle.iteration_proposals || []).map((item) => item.proposal || item.message || String(item)), "暂无迭代建议。", 5)}</div>
        </div>
      </article>
    </section>
  `;
}

async function loadStrategy(options = {}) {
  activeController?.abort();
  activeController = new AbortController();
  const token = ++requestToken;
  document.getElementById("strategy-status").innerHTML = statusBanner("正在读取策略缓存", "info");
  try {
    const bundle = await api.getStrategyBundle(appState.selectedInstrumentId, appState.selectedTimeframe, {
      ...options,
      signal: activeController.signal,
    });
    if (token !== requestToken) return null;
    renderBundle(bundle);
    return bundle;
  } catch (error) {
    if (error?.name === "AbortError" || token !== requestToken) return null;
    const msg = `策略信号读取失败：${error?.message || "未知错误"}`;
    document.getElementById("strategy-status").innerHTML = statusBanner(msg, "danger");
    if (!lastBundle) document.getElementById("strategy-content").innerHTML = errorState(msg);
    return null;
  }
}

function isReady(bundle) {
  return bundle && ["fresh", "ready"].includes(bundle.cache_state || bundle.status);
}

async function boundedStrategyPoll(token, maxAttempts = 5) {
  for (let pollAttempts = 0; pollAttempts < maxAttempts; pollAttempts += 1) {
    if (token !== requestToken) return;
    await new Promise((resolve) => {
      pollTimer = window.setTimeout(resolve, 2500 + pollAttempts * 500);
    });
    if (token !== requestToken) return;
    const bundle = await loadStrategy({ force: true });
    if (isReady(bundle)) return;
  }
}

async function enqueueRefresh({ auto = false } = {}) {
  const token = requestToken;
  const button = document.getElementById("strategy-refresh");
  if (button) button.disabled = true;
  try {
    document.getElementById("strategy-status").innerHTML = statusBanner(
      auto ? "正在刷新当前标的/周期策略信号" : "策略刷新已提交，继续显示最近一次结果。",
      "info",
    );
    await api.refreshStrategyBundle(appState.selectedInstrumentId, appState.selectedTimeframe);
    await boundedStrategyPoll(token);
  } catch (error) {
    if (token !== requestToken) return;
    document.getElementById("strategy-status").innerHTML = statusBanner(
      `刷新入队失败：${error?.message || "未知错误"}`,
      "danger",
    );
  } finally {
    if (button) button.disabled = false;
  }
}

async function refreshAfterSelection({ instrumentId, timeframe }) {
  if (pollTimer) window.clearTimeout(pollTimer);
  requestToken += 1;
  if (instrumentId) appState.selectedInstrumentId = instrumentId;
  if (timeframe) appState.selectedTimeframe = timeframe;
  persistState();
  renderShell();
  attachEvents();
  await loadStrategy({ force: true });
  await enqueueRefresh({ auto: true });
}

function attachEvents() {
  document.getElementById("strategy-instrument")?.addEventListener("change", async (event) => {
    await refreshAfterSelection({ instrumentId: event.target.value });
  });
  document.getElementById("strategy-timeframe")?.addEventListener("change", async (event) => {
    await refreshAfterSelection({ timeframe: event.target.value });
  });
  document.getElementById("strategy-refresh")?.addEventListener("click", () => enqueueRefresh());
  document.getElementById("strategy-save-snapshot")?.addEventListener("click", async () => {
    const button = document.getElementById("strategy-save-snapshot");
    button.disabled = true;
    try {
      await api.saveStrategySnapshot(appState.selectedInstrumentId, appState.selectedTimeframe);
      document.getElementById("strategy-status").innerHTML = statusBanner("策略信号已保存。", "success");
    } catch (error) {
      document.getElementById("strategy-status").innerHTML = statusBanner(
        `保存失败：${error?.message || "暂无可保存策略"}`,
        "danger",
      );
    } finally {
      button.disabled = false;
    }
  });
}

export async function renderStrategy() {
  await ensureDeps();
  renderShell();
  attachEvents();
  await loadStrategy();
}

export default renderStrategy;
