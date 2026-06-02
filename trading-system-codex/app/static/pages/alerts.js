import { api } from "../core/api.js";
import { scheduleIdlePrecompute } from "../core/precompute.js";
import { appState } from "../core/state.js";
import {
  escapeHtml,
  formatDateOnly,
  formatIndicatorName,
  formatNumber,
  knowledgeTooltip,
  knowledgeTooltipWrap,
  metricCard,
  setRoot,
  statusBanner,
  statusChip,
} from "../core/dom.js";

const STATUS_HELP = {
  open: "待处理：告警仍需要人工查看或进一步决策。",
  acknowledged: "已查看：已确认看到该告警，但风险尚未解除。",
  resolved: "已解除：对应风险已处理，或该告警条件不再成立。",
  suppressed: "已抑制：该告警暂不纳入当前处理队列。",
};

function severityImpact(value) {
  if (value === "critical" || value === "high") return "bearish";
  if (value === "medium") return "event";
  return "neutral";
}

function severityLabel(value) {
  if (value === "critical") return "高";
  if (value === "high") return "中高";
  if (value === "medium") return "中";
  return "低";
}

function trendContextLabel(value) {
  const mapping = {
    uptrend: "上升趋势",
    downtrend: "下降趋势",
    sideways: "震荡整理",
    unknown: "未知",
  };
  return mapping[value] || value || "未知";
}

function severityChip(value) {
  const tone = severityImpact(value);
  const classMap = {
    bullish: "chip-bullish alert-pill",
    neutral: "chip-neutral alert-pill",
    bearish: "chip-bearish alert-pill",
    event: "chip-event alert-pill",
  };
  return statusChip(severityLabel(value), classMap[tone] || "chip-neutral alert-pill");
}

function chipWithTooltip(markup, text) {
  return knowledgeTooltipWrap(markup, "Alert Status / 告警状态", "tone-neutral", text, {
    extra: text,
  });
}

function stateChip(value) {
  const normalized = String(value || "").toLowerCase();
  const mapping = {
    open: ["待处理", "chip-bearish alert-pill"],
    acknowledged: ["已查看", "chip-event alert-pill"],
    resolved: ["已解除", "chip-bullish alert-pill"],
    suppressed: ["已抑制", "chip-neutral alert-pill"],
  };
  const [label, className] = mapping[normalized] || ["处理中", "chip-neutral alert-pill"];
  return chipWithTooltip(statusChip(label, className), STATUS_HELP[normalized] || "当前告警状态。");
}

function actionButtons(item) {
  const status = String(item.status || "open").toLowerCase();
  const buttons = [];
  if (status === "open") buttons.push(["acknowledged", "已查看"], ["resolved", "解除"], ["suppressed", "抑制"]);
  if (status === "acknowledged") buttons.push(["resolved", "解除"], ["suppressed", "抑制"], ["open", "重新打开"]);
  if (status === "resolved" || status === "suppressed") buttons.push(["open", "重新打开"]);
  return `
    <div class="alert-actions" data-alert-event-id="${escapeHtml(item.alert_event_id)}">
      ${buttons.map(([nextStatus, label]) => `
        <span class="alert-action-inline">
          <button type="button" class="alert-action-button" data-next-status="${nextStatus}">
            ${label}
          </button>
          ${knowledgeTooltip(
            "Foreground / Background Lane 与 Manual Refresh vs Auto Refresh",
            "tone-neutral",
            `将告警状态更新为：${label}`,
            { extra: `将告警状态更新为：${label}` },
          )}
        </span>
      `).join("")}
    </div>
  `;
}

function headerTooltip(label, term, fallback = "") {
  return `${label} ${knowledgeTooltip(term, "tone-neutral", fallback)}`;
}

function inlineHelp(term, fallback = "", options = {}) {
  return knowledgeTooltip(term, "tone-neutral", fallback, options);
}

function alertExplain(item) {
  return [
    item.indicator_key ? `由 ${formatIndicatorName(item.indicator_key)} 规则触发` : "",
    item.instrument_id || item.asset_code ? `关联标的：${item.instrument_id || item.asset_code}` : "",
    item.message ? `说明：${item.message}` : "",
  ].filter(Boolean).join(" ｜ ");
}

function divergenceToneLabel(tone) {
  if (tone === "bullish") return "机会";
  if (tone === "bearish") return "风险";
  if (tone === "event") return "过滤";
  return "中性";
}

function chipStateMarkup(state) {
  const mapping = {
    ready: ["可用", "chip-bullish alert-pill"],
    low_confidence: ["置信度较低", "chip-event alert-pill"],
    missing: ["无法判断", "chip-bearish alert-pill"],
  };
  const [label, className] = mapping[state] || ["观察", "chip-neutral alert-pill"];
  return statusChip(label, className);
}

function chipStateLabelMarkup(payload) {
  const label = payload?.state_label || (payload?.state ? chipStateMarkup(payload.state) : statusChip("观察", "chip-neutral alert-pill"));
  if (typeof label !== "string" || label.includes("span")) {
    return label;
  }
  const className = {
    可用: "chip-bullish alert-pill",
    数据不完整: "chip-event alert-pill",
    信息缺失: "chip-event alert-pill",
    流动性不足: "chip-event alert-pill",
    风险受限: "chip-bearish alert-pill",
    无法判断: "chip-bearish alert-pill",
  }[label] || "chip-neutral alert-pill";
  const displayLabel = {
    可用: "状态可用",
    数据不完整: "状态降级",
    信息缺失: "信息缺失",
    流动性不足: "流动性不足",
    风险受限: "风险受限",
    无法判断: "无法判断",
  }[label] || label;
  return statusChip(displayLabel, className);
}

function chipRegimeLabel(value) {
  const mapping = {
    balanced_auction: "均衡状态",
    accumulation_proxy: "积累倾向",
    accumulation_candidate: "积累候选",
    distribution_proxy: "派发倾向",
    distribution_candidate: "派发候选",
    accumulation_confirmed: "积累确认",
    distribution_confirmed: "派发确认",
    leverage_compression: "杠杆压缩",
    liquidity_drought: "流动性枯竭",
    bullish_continuation_range: "偏多延续",
    bearish_continuation_range: "偏空延续",
    false_breakout: "假突破",
    false_breakdown: "假跌破",
  };
  return mapping[value] || "未知状态";
}

function chipActionLabel(value) {
  const mapping = {
    observe_only: "仅观察",
    observe: "仅观察",
    wait_confirmation: "等待确认",
    wait_for_confirmation: "等待确认",
    range_long_bias: "区间偏多",
    range_short_bias: "区间偏空",
    breakout_watch: "观察上破",
    breakdown_watch: "观察下破",
    probe: "试探参与",
    normal_trade: "正常参与",
    add_on_confirmation: "确认后加仓",
    reduce_or_exit: "减仓离场",
    no_trade: "不参与",
    reduce_size: "轻仓参与",
    risk_off: "风险关闭",
  };
  return mapping[value] || "未知状态";
}

function chipDirectionMarkup(score) {
  if (score >= 45) return statusChip("方向偏多", "chip-bullish alert-pill");
  if (score >= 15) return statusChip("方向偏多", "chip-bullish-soft alert-pill");
  if (score <= -45) return statusChip("方向偏空", "chip-bearish alert-pill");
  if (score <= -15) return statusChip("方向偏空", "chip-bearish-soft alert-pill");
  return statusChip("方向中性", "chip-neutral alert-pill");
}

function chipConfidenceMarkup(label) {
  const mapping = {
    invalid: ["状态置信无效", "chip-bearish alert-pill"],
    low: ["状态置信较低", "chip-bearish alert-pill"],
    watch_only: ["仅供观察", "chip-event alert-pill"],
    usable: ["状态置信可用", "chip-neutral alert-pill"],
    high: ["状态置信较高", "chip-bullish-soft alert-pill"],
    execution_ready: ["状态置信可执行", "chip-bullish alert-pill"],
  };
  const [text, className] = mapping[label] || ["仅供观察", "chip-event alert-pill"];
  return statusChip(text, className);
}

function chipExecutionMarkup(label) {
  const mapping = {
    blocked: ["盘口执行阻塞", "chip-bearish alert-pill"],
    poor: ["盘口执行较弱", "chip-bearish-soft alert-pill"],
    acceptable: ["盘口执行可接受", "chip-event alert-pill"],
    good: ["盘口执行良好", "chip-bullish-soft alert-pill"],
    strong: ["盘口执行很强", "chip-bullish alert-pill"],
  };
  const [text, className] = mapping[label] || ["盘口执行待定", "chip-neutral alert-pill"];
  return statusChip(text, className);
}

function chipRiskMarkup(label) {
  const mapping = {
    normal: ["风险正常", "chip-bullish alert-pill"],
    elevated: ["风险抬升", "chip-event alert-pill"],
    high: ["风险偏高", "chip-bearish-soft alert-pill"],
    extreme: ["风险极高", "chip-bearish alert-pill"],
  };
  const [text, className] = mapping[label] || ["风险待定", "chip-neutral alert-pill"];
  return statusChip(text, className);
}

function internalLabel(value) {
  const text = String(value ?? "").trim();
  const mapping = {
    proxy_only: "证据不足，仅供观察",
    partially_confirmed: "部分确认",
    confirmed: "已确认",
    pending: "待确认",
    missing: "缺失",
    blocked: "受阻",
    acceptable: "可接受",
    good: "良好",
    strong: "较强",
    low: "较低",
    high: "较高",
    invalid: "无效",
    watch_only: "仅供观察",
    normal: "正常",
    elevated: "风险抬升",
    extreme: "风险极高",
    MICROSTRUCTURE_MISSING: "缺少微观结构数据",
    NO_USABLE_CANDLES: "缺少可用 K 线",
    EXECUTION_SCORE_TOO_LOW: "盘口执行分过低",
    SLIPPAGE_HARD_LIMIT: "滑点超过限制",
    SPREAD_HARD_LIMIT: "买卖价差超过限制",
    PRICE_INDEX_DEVIATION_EXTREME: "价格相对指数价偏离过大",
    PRICE_MARK_DEVIATION_EXTREME: "价格相对标记价偏离过大",
  };
  return mapping[text] || text || "—";
}

function safeDisplay(value, fallback = "—") {
  if (value === null || value === undefined || value === "") return fallback;
  if (typeof value === "number" && !Number.isFinite(value)) return fallback;
  const text = String(value);
  if (["NaN", "nan", "None", "null", "undefined"].includes(text)) return fallback;
  return internalLabel(text);
}

function formatPctLabel(value, fallback = "0%") {
  const text = safeDisplay(value, fallback);
  return text === "—" ? fallback : text;
}

const EXPLAIN_TRANSLATIONS = [
  ["Direction bias is", "方向判断为"],
  ["Confidence cap is", "当前置信上限为"],
  ["Penalties applied:", "已扣分："],
  ["Risk gates triggered:", "已触发风控门禁："],
  ["Recommended action is", "建议动作："],
  ["No usable candles were available, so confidence is capped at zero.", "缺少可用 K 线，置信度被压制为 0，当前仅返回缺失状态。"],
];

function localizeExplainText(value) {
  let text = String(value || "");
  for (const [source, target] of EXPLAIN_TRANSLATIONS) {
    text = text.replaceAll(source, target);
  }
  return text
    .replaceAll("NO_USABLE_CANDLES", "缺少可用 K 线")
    .replaceAll("EXECUTION_SCORE_TOO_LOW", "盘口执行分过低")
    .replaceAll("SLIPPAGE_HARD_LIMIT", "滑点超过硬限制")
    .replaceAll("SPREAD_HARD_LIMIT", "买卖价差超过硬限制")
    .replaceAll("PRICE_INDEX_DEVIATION_EXTREME", "成交价相对指数价偏离过大")
    .replaceAll("PRICE_MARK_DEVIATION_EXTREME", "成交价相对标记价偏离过大")
    .replaceAll("MICROSTRUCTURE_MISSING", "缺少微观结构数据")
    .replaceAll("proxy_only", "证据不足，仅供观察")
    .replaceAll("partially_confirmed", "部分确认")
    .replaceAll("confirmed", "已确认")
    .replaceAll("pending", "待确认")
    .replaceAll("observe", "仅观察")
    .replaceAll("wait_for_confirmation", "等待确认")
    .replaceAll("probe", "小仓试探")
    .replaceAll("normal_trade", "正常参与")
    .replaceAll("add_on_confirmation", "确认后加仓")
    .replaceAll("no_trade", "不参与")
    .replaceAll("reduce_or_exit", "减仓或退出");
}

function fallbackChipStructureCard(errorMessage = "") {
  const message = errorMessage || "当前无法读取筹码结构结果，暂时仅显示告警与背离信息。";
  return `
    <section class="card alert-chip-hero">
      <div class="section-head">
        <div>
          <p class="eyebrow">筹码结构</p>
          <h2>筹码结构</h2>
        </div>
        <div class="alert-chip-hero-tags">
          ${statusChip("缺失", "chip-bearish alert-pill")}
          ${statusChip("中性", "chip-neutral alert-pill")}
        </div>
      </div>
      <div class="alert-chip-headline">
        <article class="alert-chip-block">
          <div class="list-card-head"><strong>主结论</strong></div>
          <h3>暂时无法输出筹码结构</h3>
          <p class="section-summary">${escapeHtml(appState.selectedInstrumentId)} · ${escapeHtml(appState.selectedTimeframe)}</p>
        </article>
        <article class="alert-chip-block">
          <div class="list-card-head"><strong>状态说明</strong></div>
          <p><strong>无法判断</strong></p>
          <p>${escapeHtml(message)}</p>
        </article>
        <article class="alert-chip-block">
          <div class="list-card-head"><strong>现货建议占比</strong></div>
          <p><strong>0%</strong></p>
          <p>当前不建议配置新的现货方向仓位。</p>
        </article>
        <article class="alert-chip-block">
          <div class="list-card-head"><strong>合约建议占比</strong></div>
          <p><strong>0%</strong></p>
          <p>当前不建议增加合约风险敞口。</p>
        </article>
        <article class="alert-chip-block">
          <div class="list-card-head"><strong>单次试探仓上限</strong></div>
          <p><strong>0%</strong></p>
          <p>等待关键输入恢复后再考虑试探仓。</p>
        </article>
        <article class="alert-chip-block">
          <div class="list-card-head"><strong>建议动作</strong></div>
          <p>${statusChip("仅观察", "chip-event alert-pill")}</p>
          <p>当前仅使用告警列表与背离提醒辅助观察。</p>
        </article>
      </div>
      <div class="alert-chip-bottom-grid">
        <article class="alert-chip-block">
          <div class="list-card-head"><strong>建议</strong></div>
          <ul class="structure-bullet-list">
            <li>若后端数据恢复，可重新点击“刷新告警”读取筹码结构。</li>
            <li>在关键输入恢复前，维持总资本防守状态。</li>
          </ul>
        </article>
      </div>
    </section>
  `;
}

function renderChipStructureCard(payload) {
  if (!payload || typeof payload !== "object") {
    return fallbackChipStructureCard();
  }
  const explain = Array.isArray(payload.explain) ? payload.explain : [];
  const riskGates = Array.isArray(payload.risk_gates) ? payload.risk_gates : [];
  const confidenceLabel = payload.confidence_label || "watch_only";
  const executionLabel = payload.execution_label || "blocked";
  const riskLabel = payload.risk_label || "normal";
  const recommendedAction = payload.recommended_action_v2 || payload.recommended_action;
  const allowFuturesLong = payload.allow_futures_long === true;
  const stateConfidenceLabel = payload.state_confidence_label || internalLabel(payload.confidence_label) || "状态置信待定";
  const executionQualityLabel = payload.execution_quality_label || "盘口执行质量待定";
  const entryTriggerLabel = payload.entry_trigger_label || "交易触发待定";
  const positionReason = payload.allocation_reason || payload.position_sizing_reason || "当前暂无明确仓位建议。";
  const components = payload.components || {};
  const componentRows = Object.entries(components).slice(0, 4);
  const scoreItems = [
    ["方向分", formatNumber(payload.direction_score, 0)],
    ["状态置信", formatNumber(payload.confidence_score, 0)],
    ["执行分", formatNumber(payload.execution_score, 0)],
    ["风险分", formatNumber(payload.risk_score, 0)],
    ["总资本", payload.capital_allocation_label || "0%"],
  ];

  return `
    <section class="card alert-chip-hero">
      <div class="section-head">
        <div>
          <p class="eyebrow">筹码结构</p>
          <h2>筹码结构</h2>
        </div>
        <div class="alert-chip-hero-tags">
          ${chipStateLabelMarkup(payload)}
          ${chipDirectionMarkup(payload.direction_score)}
          ${chipConfidenceMarkup(confidenceLabel)}
          ${chipExecutionMarkup(executionLabel)}
          ${chipRiskMarkup(riskLabel)}
        </div>
      </div>
      <div class="alert-chip-headline">
        <article class="alert-chip-primary-card">
          <div class="list-card-head"><strong>主结论</strong>${chipStateLabelMarkup(payload)}</div>
          <h3>${escapeHtml(chipRegimeLabel(payload.primary_regime))}</h3>
          <p class="section-summary">${escapeHtml(safeDisplay(payload.instrument_id))} · ${escapeHtml(safeDisplay(payload.timeframe))} · 次级情景：${escapeHtml(chipRegimeLabel(payload.secondary_regime))}</p>
          <div class="alert-chip-primary-actions">
            ${statusChip(chipActionLabel(recommendedAction), "chip-event alert-pill")}
            ${statusChip(allowFuturesLong ? "允许评估合约" : "合约门控未通过", allowFuturesLong ? "chip-bullish alert-pill" : "chip-bearish alert-pill")}
          </div>
          <p>${escapeHtml(positionReason)}</p>
        </article>
        <div class="alert-chip-status-grid">
          <article class="alert-chip-block">
            <div class="list-card-head"><strong>状态说明</strong></div>
            <p><strong>${escapeHtml(payload.state_label || "观察")}</strong></p>
            <p>${escapeHtml(payload.state_reason || "当前状态说明暂不可用。")}</p>
          </article>
          <article class="alert-chip-block">
            <div class="list-card-head"><strong>状态置信</strong></div>
            <p>${chipConfidenceMarkup(confidenceLabel)}</p>
            <p>${escapeHtml(stateConfidenceLabel)} · 上限 ${formatNumber(payload.confidence_cap, 0)} · ${escapeHtml(internalLabel(payload.evidence_quality))}</p>
          </article>
          <article class="alert-chip-block">
            <div class="list-card-head"><strong>盘口执行质量</strong></div>
            <p>${chipExecutionMarkup(executionLabel)}</p>
            <p>${escapeHtml(executionQualityLabel)}</p>
          </article>
          <article class="alert-chip-block">
            <div class="list-card-head"><strong>风险等级</strong></div>
            <p>${chipRiskMarkup(riskLabel)}</p>
            <p>${riskGates.length ? `主要限制：${escapeHtml(riskGates.map(internalLabel).join(" / "))}` : "当前未触发额外风控限制。"}</p>
          </article>
        </div>
      </div>
      <div class="alert-chip-score-strip">
        ${scoreItems.map(([label, value]) => `<span><em>${escapeHtml(label)}</em><strong>${escapeHtml(String(value))}</strong></span>`).join("")}
      </div>
      <div class="alert-chip-position-grid">
        <article class="alert-chip-block">
          <div class="list-card-head"><strong>交易触发状态</strong></div>
          <p>${statusChip(entryTriggerLabel, entryTriggerLabel.includes("可用") ? "chip-bullish alert-pill" : "chip-event alert-pill")}</p>
          <p>执行准备度：${escapeHtml(internalLabel(payload.execution_readiness))}</p>
        </article>
        <article class="alert-chip-block">
          <div class="list-card-head"><strong>仓位解释</strong></div>
          <div class="alert-chip-allocation-row">
            <span>现货 <strong>${escapeHtml(formatPctLabel(payload.spot_allocation_label))}</strong></span>
            <span>合约 <strong>${escapeHtml(formatPctLabel(payload.futures_allocation_label))}</strong></span>
            <span>试探 <strong>${escapeHtml(formatPctLabel(payload.probe_position_label))}</strong></span>
          </div>
          <p>${allowFuturesLong ? "合约开多门槛已通过。" : "合约开多门槛未通过，合约仓位保持 0%。"}</p>
        </article>
      </div>
      <div class="alert-chip-support-grid alert-chip-support-grid-compact">
        <article class="alert-chip-block">
          <div class="list-card-head"><strong>引擎解释</strong></div>
          ${explain.length ? `<ul class="structure-bullet-list">${explain.slice(0, 4).map((item) => `<li>${escapeHtml(localizeExplainText(item))}</li>`).join("")}</ul>` : `<p>当前暂无引擎解释。</p>`}
        </article>
        <article class="alert-chip-block">
          <div class="list-card-head"><strong>证据组件</strong></div>
          ${componentRows.length ? `<div class="alert-chip-components">${componentRows.map(([key, value]) => `<div class="alert-chip-component-row"><span>${escapeHtml(internalLabel(key))}</span><strong>${formatNumber(value?.weighted ?? value?.raw ?? 0, 2)}</strong></div>`).join("")}</div>` : `<p>当前暂无组件评分。</p>`}
        </article>
      </div>
    </section>
  `;
}

const autoRefreshKeys = new Set();
let isMounted = false;

export async function renderAlerts() {
  let activeController = null;
  if (!isMounted) {
    setRoot(`
    <section id="alerts-statusbar"></section>
    <section id="alerts-chip-structure"></section>
    <section id="alerts-chip-appendix"></section>
    <section class="card divergence-alert-card alert-block">
      <div class="section-head">
        <div>
          <p class="eyebrow">背离检测</p>
          <h2>背离风险提醒</h2>
        </div>
      </div>
      <div id="alerts-divergence"></div>
    </section>
    <section class="card alert-list-card alert-block">
        <div class="section-head">
          <div>
            <p class="eyebrow">活跃及历史告警</p>
            <h2>告警列表</h2>
          </div>
          <div class="toolbar compact-toolbar"><button id="alerts-refresh" type="button">刷新告警</button></div>
        </div>
        <section class="grid cols-3 alert-summary-grid" id="alerts-summary"></section>
        <div class="table-wrap">
          <table>
            <colgroup>
              <col class="alert-col-time" />
              <col class="alert-col-severity" />
              <col class="alert-col-indicator" />
              <col class="alert-col-asset" />
              <col class="alert-col-message" />
              <col class="alert-col-state" />
              <col class="alert-col-actions" />
            </colgroup>
            <thead>
              <tr>
                <th>${headerTooltip("时间", "Event Feed / 信息流 与 Reliability / 可信度", "告警首次触发时间。")}</th>
                <th>${headerTooltip("级别", "Alert Severity / 告警级别")}</th>
                <th>${headerTooltip("指标", "Observation / 观测值 与 Signal State / 信号状态", "触发告警规则的监控指标。")}</th>
                <th>${headerTooltip("标的", "Instrument / 交易标的")}</th>
                <th>${headerTooltip("消息", "Alert Message / 告警消息")}</th>
                <th>${headerTooltip("状态", "Alert Status / 告警状态")}</th>
                <th>${headerTooltip("操作", "Foreground / Background Lane 与 Manual Refresh vs Auto Refresh", "处理状态会持久化写入数据库。")}</th>
              </tr>
            </thead>
            <tbody id="alerts-body"></tbody>
          </table>
        </div>
    </section>
  `);
    isMounted = true;
  }

  const renderStatus = (message, tone = "neutral") => {
    const el = document.getElementById("alerts-statusbar");
    if (el) el.innerHTML = statusBanner(message, tone);
  };

  async function load({ allowAutoRefresh = true } = {}) {
    activeController?.abort();
    activeController = new AbortController();
    let bundle;
    try {
      bundle = await api.getAlertsBundle(
        appState.selectedInstrumentId,
        appState.selectedTimeframe,
        { signal: activeController.signal },
      );
    } catch (error) {
      if (error?.name === "AbortError" || error?.name === "TimeoutError") {
        return;
      }
      throw error;
    }
    const items = bundle.alert_events || [];
    const seen = new Set();
    const dedupedItems = items.filter(item => {
      const key = `${item.rule_key || item.indicator_key}|${item.instrument_id || ""}|${String(item.triggered_at || "").slice(0, 16)}`;
      if (seen.has(key)) return false;
      seen.add(key);
      return true;
    });
    const divergence = bundle.divergence_summary || {
      instrument_id: appState.selectedInstrumentId,
      timeframe: appState.selectedTimeframe,
      overall: {
        tone: "neutral",
        title: "背离结果暂不可用",
        score: 0,
        confidence: 0,
        leaders: [],
        message: "当前无法读取背离摘要，请稍后重试。",
      },
      signals: [],
      filters: [],
    };
    const chipStructure = bundle.chip_structure || null;
    const chipMissing = !chipStructure || chipStructure.state === "missing" || chipStructure.state_label === "无法判断";
    const divergenceMissing = !divergence.signals?.length;
    const autoKey = `${appState.selectedInstrumentId}:${appState.selectedTimeframe}`;
    if (allowAutoRefresh && (bundle.status === "missing" || bundle.status === "stale" || chipMissing || divergenceMissing) && !autoRefreshKeys.has(autoKey)) {
      autoRefreshKeys.add(autoKey);
      renderStatus(bundle.status_message || "后台正在准备最新数据", "loading");
      await scheduleIdlePrecompute({
        page: "alert-center",
        instrumentId: appState.selectedInstrumentId,
        timeframe: appState.selectedTimeframe === "1M" ? "30d" : appState.selectedTimeframe,
        reason: "alerts_bundle_read",
        priority: 3,
      });
      await load({ allowAutoRefresh: false });
      return;
    }

    document.getElementById("alerts-chip-structure").innerHTML = chipStructure
      ? renderChipStructureCard(chipStructure)
      : fallbackChipStructureCard(bundle.status_message || "筹码结构接口暂不可用。");

    document.getElementById("alerts-body").innerHTML = dedupedItems.length
      ? dedupedItems.map((item) => `
        <tr>
          <td class="alert-col-time">${formatDateOnly(item.triggered_at)}</td>
          <td class="alert-col-severity">${severityChip(item.severity)}</td>
          <td class="alert-col-indicator">
            <div class="alert-cell-stack">
              <strong>${escapeHtml(formatIndicatorName(item.indicator_key))}</strong>
              <span class="alert-inline-help">${inlineHelp(
                formatIndicatorName(item.indicator_key),
                `该告警由 ${formatIndicatorName(item.indicator_key)} 规则触发。`,
                { extra: item.message ? `当前触发消息：${item.message}` : "" },
              )}</span>
            </div>
          </td>
          <td class="alert-col-asset">
            <div class="alert-cell-stack">
              <span>${escapeHtml(item.instrument_id || item.asset_code || "-")}</span>
              <span class="alert-inline-help">${inlineHelp(
                "Instrument / 交易标的",
                `当前关联标的：${item.instrument_id || item.asset_code || "-"}`,
                { extra: `当前关联标的：${item.instrument_id || item.asset_code || "-"}` },
              )}</span>
            </div>
          </td>
          <td class="alert-col-message">
            <div class="alert-cell-stack">
              <span>${escapeHtml(item.message)}</span>
              <span class="alert-inline-help">${inlineHelp(
                "Alert Message / 告警消息",
                item.message || "暂无额外说明。",
                { extra: item.message || "当前没有额外消息文本。" },
              )}</span>
            </div>
          </td>
          <td class="alert-col-state">${stateChip(item.status)}</td>
          <td class="alert-col-actions">${actionButtons(item)}</td>
        </tr>
      `).join("")
      : '<tr><td colspan="7" class="empty-row">当前没有告警。</td></tr>';

    const openItems = dedupedItems.filter((item) => item.status === "open");
    document.getElementById("alerts-summary").innerHTML = [
      metricCard("当前待处理", openItems.length, "仍处于待处理状态的站内告警。"),
      metricCard("最高优先级", openItems.find((item) => item.severity === "critical") ? "严重" : "普通", "当前最高告警等级。"),
      metricCard("最新触发", dedupedItems[0] ? formatIndicatorName(dedupedItems[0].indicator_key) : "-", dedupedItems[0]?.message || "暂无告警说明。"),
    ].join("");

    const divergenceItems = [...divergence.signals, ...divergence.filters].slice(0, 7);
    document.getElementById("alerts-divergence").innerHTML = `
      <p class="section-summary divergence-context">
        ${escapeHtml(appState.selectedInstrumentId)} · ${escapeHtml(appState.selectedTimeframe)}，背离仅作为预警参考，不直接作为入场信号。
      </p>
      <article class="divergence-overall divergence-${divergence.overall.tone}">
        <div class="list-card-head">
          <strong>${escapeHtml(divergence.overall.title)}</strong>
          ${statusChip(divergenceToneLabel(divergence.overall.tone), `chip-${divergence.overall.tone === "event" ? "event" : divergence.overall.tone} alert-pill`)}
        </div>
        <div class="divergence-score-row">
          <span>综合分 <strong>${formatNumber(divergence.overall.score, 2)}</strong></span>
          <span>置信度 <strong>${formatNumber(divergence.overall.confidence, 2)}</strong></span>
          <span>主导指标 <strong>${escapeHtml(divergence.overall.leaders.join(" / ") || "-")}</strong></span>
        </div>
        <p>${escapeHtml(divergence.overall.message)}</p>
        ${divergence.overall.trend_context ? `<p class="divergence-subcopy">趋势环境：${escapeHtml(trendContextLabel(divergence.overall.trend_context))}</p>` : ""}
      </article>
      <div class="divergence-alert-list">
        ${divergenceItems.length ? divergenceItems.map((item) => `
          <article class="divergence-alert-item divergence-${item.tone || item.direction}">
            <div class="list-card-head">
              <strong>${escapeHtml(item.title)}</strong>
              ${statusChip(
                item.tone === "event" ? "过滤" : item.direction === "bullish" ? "机会" : item.direction === "bearish" ? "风险" : "中性",
                `chip-${item.tone === "event" ? "event" : item.direction || item.tone || "neutral"} alert-pill`,
              )}
            </div>
            ${item.weight !== undefined ? `<div class="divergence-score-row"><span>权重 ${formatNumber(item.weight, 2)}</span><span>强度 ${formatNumber(item.strength, 2)}</span><span>贡献 ${formatNumber(item.score, 2)}</span></div>` : ""}
            <p>${escapeHtml(item.message)}</p>
            ${
              item.confirmation || item.invalidation
                ? `<div class="divergence-subcopy">${item.confirmation ? `<span>${escapeHtml(item.confirmation)}</span>` : ""}${item.invalidation ? `<span>${escapeHtml(item.invalidation)}</span>` : ""}</div>`
                : ""
            }
          </article>
        `).join("") : `<article class="divergence-alert-item divergence-neutral"><p>暂无单项背离贡献。</p></article>`}
      </div>
    `;
  }

  document.getElementById("alerts-refresh").addEventListener("click", async () => {
    const button = document.getElementById("alerts-refresh");
    if (button) {
      button.disabled = true;
      button.textContent = "刷新中";
    }
      try {
        renderStatus("正在刷新告警摘要", "loading");
        await api.refreshAlertsBundle(appState.selectedInstrumentId, appState.selectedTimeframe);
        await load({ allowAutoRefresh: false });
        renderStatus("数据已就绪", "success");
      } finally {
      if (button) {
        button.disabled = false;
        button.textContent = "刷新告警";
      }
    }
  });
  document.getElementById("alerts-body").addEventListener("click", async (event) => {
    const button = event.target.closest("[data-next-status]");
    if (!button) return;
    const container = button.closest("[data-alert-event-id]");
    const alertEventId = container?.dataset.alertEventId;
    const nextStatus = button.dataset.nextStatus;
    if (!alertEventId || !nextStatus) return;
    button.disabled = true;
    button.textContent = "处理中";
    try {
      await api.updateAlertEventStatus(alertEventId, nextStatus);
      await load();
    } catch (error) {
      console.error("alerts:update-status:error", error);
      button.disabled = false;
      button.textContent = "失败";
    }
  });

  try {
    await load();
  } catch (error) {
    console.error("alerts:initial-load:error", error);
    renderStatus("告警摘要暂不可用，已保留页面骨架，可稍后重试或手动刷新。", "danger");
    document.getElementById("alerts-chip-structure").innerHTML = fallbackChipStructureCard(
      String(error?.message || error || "告警摘要暂不可用。"),
    );
    document.getElementById("alerts-divergence").innerHTML =
      '<div class="empty-state">背离摘要暂不可用。</div>';
    document.getElementById("alerts-summary").innerHTML = [
      metricCard("当前待处理", "-", "告警快照暂不可用。"),
      metricCard("最高优先级", "-", "告警快照暂不可用。"),
      metricCard("最新触发", "-", "告警快照暂不可用。"),
    ].join("");
    document.getElementById("alerts-body").innerHTML =
      '<tr><td colspan="7" class="empty-row">告警列表暂不可用。</td></tr>';
  }
}
