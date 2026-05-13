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
let pollTimer = null;

const STATE_CONFIG = {
  NO_EDGE: { label: "多空不明", tone: "chip-neutral", hint: "多空分差不足，等待更清晰结构。" },
  OBSERVE: { label: "观察等待", tone: "chip-neutral", hint: "已有线索，但还没形成可执行策略。" },
  CONFLICTED_NO_TRADE: { label: "冲突观望", tone: "chip-warning", hint: "多空证据互相抵消，暂不交易。" },
  LONG_BIAS: { label: "偏多观察", tone: "chip-bullish", hint: "多头占优，但触发条件未齐。" },
  SHORT_BIAS: { label: "偏空观察", tone: "chip-bearish", hint: "空头占优，但触发条件未齐。" },
  WAIT_LONG_CONFIRMATION: { label: "等多头确认", tone: "chip-bullish", hint: "偏多结构存在，等待入场触发。" },
  WAIT_SHORT_CONFIRMATION: { label: "等空头确认", tone: "chip-bearish", hint: "偏空结构存在，等待入场触发。" },
  LONG_TRIGGERED: { label: "多头触发", tone: "chip-bullish", hint: "多头入场条件已触发。" },
  SHORT_TRIGGERED: { label: "空头触发", tone: "chip-bearish", hint: "空头入场条件已触发。" },
  EVENT_WAIT: { label: "事件等待", tone: "chip-warning", hint: "事件窗口影响较大，等待落地。" },
  RISK_OFF: { label: "风险关闭", tone: "chip-danger", hint: "风险门禁触发，暂停交易。" },
};

const BIAS_LABELS = {
  long: "偏多",
  short: "偏空",
  neutral: "中性",
  none: "多空不明",
};

const PERMISSION_LABELS = {
  allow: "允许",
  allowed: "允许",
  wait: "等待",
  observe: "观察",
  no_trade: "禁止交易",
  blocked: "禁止交易",
  risk_off: "风险关闭",
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
  return String(value)
    .replace(/_/g, " ")
    .replace(/\bWAIT SHORT CONFIRMATION\b/gi, "等待空头确认")
    .replace(/\bWAIT LONG CONFIRMATION\b/gi, "等待多头确认");
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
          <option value="${escapeHtml(item.value)}" ${item.selected ? "selected" : ""}>
            ${escapeHtml(item.label)}
          </option>
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
        <p class="muted">只读取已有快照与缓存，生成当前市场的多空策略、触发条件与风险约束。</p>
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
      <div class="strategy-control-note">当前页不录入持仓，只输出市场策略信号。</div>
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
            <span>${label}</span>
            <strong>${numberText(value)}</strong>
          </div>
          <i style="width:${Math.min(100, Math.abs(value) / max * 100)}%"></i>
        </div>
      `).join("")}
    </div>
  `;
}

function formatZone(zone) {
  if (Array.isArray(zone) && zone.length) {
    return zone.map((item) => numberText(item)).join(" - ");
  }
  return cleanText(zone, "-");
}

function renderPlanSummary(title, plan, fallback) {
  if (!plan || (!plan.pattern_type && !plan.pattern_label && !plan.strategy_logic)) {
    return `
      <article class="strategy-plan-compact muted-card">
        <strong>${escapeHtml(title)}</strong>
        <p>${escapeHtml(fallback)}</p>
      </article>
    `;
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
          <div>
            <strong>确认条件</strong>
            ${list(plan.entry_conditions || plan.confirmation_criteria, "暂无确认条件")}
          </div>
          <div>
            <strong>失效条件</strong>
            ${list(plan.invalidation_rules || plan.invalidation_criteria, "暂无失效条件")}
          </div>
        </div>
      </details>
    </article>
  `;
}

function normalizeCheck(item) {
  const raw = cleanText(item.status || (item.met ? "满足" : "未满足"));
  const met = item.met === true || ["满足", "通过", "satisfied", "met"].includes(raw.toLowerCase());
  const partial = ["部分满足", "partial"].includes(raw.toLowerCase()) || raw.includes("部分");
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
  const gates = (decision.gates || [])
    .map((item) => item.message || item.reason || item.name)
    .filter(Boolean);
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
  const permission = labelFromMap(
    PERMISSION_LABELS,
    decision.strategy_permission_label || decision.strategy_permission,
  );
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
      <article class="card strategy-compact-card">
        <h3>入场条件检查</h3>
        ${renderChecklist(decision.entry_checklist || [])}
      </article>
      <article class="card strategy-compact-card">
        <h3>风险门禁</h3>
        ${renderReasons(decision)}
      </article>
    </section>

    <section class="strategy-main-grid compact">
      <article class="card strategy-compact-card">
        <div class="card-head-inline">
          <div>
            <p class="eyebrow">EVIDENCE MATRIX</p>
            <h3>证据矩阵</h3>
          </div>
          ${statusChip(`质量 ${numberText(decision.data_quality_score)}`, "chip-neutral")}
        </div>
        ${renderEvidence(decision.evidence_matrix || [])}
      </article>
      <article class="card strategy-compact-card">
        <h3>复盘与迭代</h3>
        <div class="strategy-review-columns">
          <div>
            <strong>复盘标签</strong>
            ${list(decision.review_tags || [], "暂无复盘标签。", 5)}
          </div>
          <div>
            <strong>迭代建议</strong>
            ${list((bundle.iteration_proposals || []).map((item) => (
              item.proposal || item.message || String(item)
            )), "暂无迭代建议。", 5)}
          </div>
        </div>
      </article>
    </section>
  `;
}

async function loadStrategy(options = {}) {
  activeController?.abort();
  activeController = new AbortController();
  document.getElementById("strategy-status").innerHTML = statusBanner("正在读取策略缓存", "info");
  try {
    const bundle = await api.getStrategyBundle(
      appState.selectedInstrumentId,
      appState.selectedTimeframe,
      { ...options, signal: activeController.signal },
    );
    renderBundle(bundle);
  } catch (error) {
    if (error?.name === "AbortError") return;
    const msg = `策略信号读取失败：${error?.message || "未知错误"}`;
    document.getElementById("strategy-status").innerHTML = statusBanner(msg, "danger");
    if (!lastBundle) {
      document.getElementById("strategy-content").innerHTML = errorState(msg);
    }
  }
}

async function enqueueRefresh() {
  const button = document.getElementById("strategy-refresh");
  button.disabled = true;
  try {
    const response = await api.refreshStrategyBundle(
      appState.selectedInstrumentId,
      appState.selectedTimeframe,
    );
    const text = response.status === "deduped"
      ? "策略刷新已在队列中，继续显示最近一次结果。"
      : "策略刷新已加入后台队列，继续显示最近一次结果。";
    document.getElementById("strategy-status").innerHTML = statusBanner(text, "info");
    schedulePoll();
  } catch (error) {
    document.getElementById("strategy-status").innerHTML = statusBanner(
      `刷新入队失败：${error?.message || "未知错误"}`,
      "danger",
    );
  } finally {
    button.disabled = false;
  }
}

function schedulePoll() {
  if (pollTimer) window.clearTimeout(pollTimer);
  pollTimer = window.setTimeout(() => loadStrategy({ force: true }), 3500);
}

export async function renderStrategy() {
  await ensureDeps();
  renderShell();

  document.getElementById("strategy-instrument").addEventListener("change", async (event) => {
    appState.selectedInstrumentId = event.target.value;
    persistState();
    lastBundle = null;
    await loadStrategy({ force: true });
  });
  document.getElementById("strategy-timeframe").addEventListener("change", async (event) => {
    appState.selectedTimeframe = event.target.value;
    persistState();
    lastBundle = null;
    await loadStrategy({ force: true });
  });
  document.getElementById("strategy-refresh").addEventListener("click", enqueueRefresh);
  document.getElementById("strategy-save-snapshot").addEventListener("click", async () => {
    const button = document.getElementById("strategy-save-snapshot");
    button.disabled = true;
    try {
      await api.saveStrategySnapshot(appState.selectedInstrumentId, appState.selectedTimeframe);
      document.getElementById("strategy-status").innerHTML = statusBanner("策略信号已保存", "success");
    } catch (error) {
      document.getElementById("strategy-status").innerHTML = statusBanner(
        `保存失败：${error?.message || "暂无可保存策略"}`,
        "danger",
      );
    } finally {
      button.disabled = false;
    }
  });

  await loadStrategy();
}

export default renderStrategy;
