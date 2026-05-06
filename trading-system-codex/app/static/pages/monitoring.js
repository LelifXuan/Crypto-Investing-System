import { api } from "../core/api.js";
import { scheduleIdlePrecompute } from "../core/precompute.js";
import { appState } from "../core/state.js";
import {
  compactWindowLabel,
  escapeHtml,
  formatDateTime,
  formatIndicatorName,
  formatNumber,
  impactChip,
  knowledgeTooltip,
  metricCard,
  observationValue,
  setRoot,
  statusBanner,
} from "../core/dom.js";

const ACTIVE_ADDRESS_THRESHOLDS = {
  btc_active_addresses: { strongBull: 900000, mildBull: 780000, mildBear: 520000, strongBear: 400000 },
  eth_active_addresses: { strongBull: 650000, mildBull: 560000, mildBear: 420000, strongBear: 320000 },
};

const MVRV_THRESHOLDS = {
  btc_mvrv: { strongBull: 0.95, mildBull: 1.1, mildBear: 2.8, strongBear: 3.5 },
  eth_mvrv: { strongBull: 0.9, mildBull: 1.05, mildBear: 2.5, strongBear: 3.2 },
  btc_sth_mvrv: { strongBull: 1.0, mildBull: 1.15, mildBear: 2.4, strongBear: 3.0 },
  btc_lth_mvrv: { strongBull: 1.2, mildBull: 1.4, mildBear: 3.2, strongBear: 4.0 },
};

function decodePossiblyBrokenText(value) {
  if (typeof value !== "string" || !value) return value;
  if (!/[ÃÂâåéèêçø¤�]/.test(value)) return value;
  try {
    const bytes = Uint8Array.from([...value].map((char) => char.charCodeAt(0) & 0xff));
    const decoded = new TextDecoder("utf-8", { fatal: false }).decode(bytes);
    return decoded && decoded.includes("\uFFFD") ? value : decoded;
  } catch {
    return value;
  }
}

function text(value, fallback = "-") {
  if (value === null || value === undefined || value === "") return fallback;
  return decodePossiblyBrokenText(String(value));
}

function makeNeutral(bias, reason) {
  return { kind: "neutral", bias, reason };
}

function observationImpact(item) {
  const key = String(item.indicator_key || "");
  const value = Number(item.value_num ?? 0);

  if (["funding_rate_zscore", "basis_rate_zscore"].includes(key)) {
    if (value >= 2) return { kind: "bearish", bias: "偏空", reason: "溢价或情绪显著过热，继续追多的性价比下降。" };
    if (value >= 1) return makeNeutral("中性偏空", "溢价开始抬升，短线继续追多需要更谨慎。");
    if (value <= -2) return { kind: "bullish", bias: "偏多", reason: "情绪显著降温，空头拥挤后的修复空间更大。" };
    if (value <= -1) return makeNeutral("中性偏多", "情绪偏冷，若结构企稳更容易出现反弹修复。");
    return makeNeutral("中性", "情绪仍在常态区间，对方向判断影响有限。");
  }

  if (key === "funding_rate") {
    if (value >= 0.015) return { kind: "bearish", bias: "偏空", reason: "资金费率明显偏高，多头拥挤度上升。" };
    if (value >= 0.006) return makeNeutral("中性偏空", "资金费率略偏高，继续追多的风险回报下降。");
    if (value <= -0.015) return { kind: "bullish", bias: "偏多", reason: "极端负费率往往对应过度悲观，利于反向修复。" };
    if (value <= -0.006) return makeNeutral("中性偏多", "负费率说明情绪偏冷，若价格止跌更有利于反弹。");
    return makeNeutral("中性", "资金费率平稳，尚未形成明确方向偏置。");
  }

  if (key === "basis_rate") {
    if (value >= 0.02) return { kind: "bearish", bias: "偏空", reason: "基差显著扩张，杠杆拥挤与回落风险同步上升。" };
    if (value >= 0.008) return makeNeutral("中性偏空", "基差偏高，继续加杠杆追涨并不划算。");
    if (value <= -0.02) return { kind: "bullish", bias: "偏多", reason: "深度贴水常见于情绪过冷，容易触发修复。" };
    if (value <= -0.008) return makeNeutral("中性偏多", "基差走弱说明预期偏冷，若现货稳住则有利于反弹。");
    return makeNeutral("中性", "基差仍在温和区间，未形成强方向驱动。");
  }

  if (["price_to_mark_deviation", "price_to_index_deviation"].includes(key)) {
    if (value >= 0.003) return { kind: "bearish", bias: "偏空", reason: "价格明显高于基准，短线回归压力抬升。" };
    if (value >= 0.0015) return makeNeutral("中性偏空", "价格略高于基准，继续上冲的阻力增加。");
    if (value <= -0.003) return { kind: "bullish", bias: "偏多", reason: "价格明显低于基准，偏离回补更有利于反弹。" };
    if (value <= -0.0015) return makeNeutral("中性偏多", "价格略低于基准，修复性回升空间更大。");
    return makeNeutral("中性", "价格与基准贴合，当前偏离不足以单独给出方向。");
  }

  if (["natr_14", "atr_14", "atr_expansion_warning"].includes(key)) {
    if (item.signal_state === "expanded" || value >= 3) {
      return { kind: "event", bias: "事件驱动", reason: "波动率扩张更适合作为风控与仓位管理信号，而非单边方向结论。" };
    }
    return makeNeutral("中性", "波动率仍在常态区间，更多是背景条件而不是方向信号。");
  }

  if (key.includes("mvrv")) {
    const thresholds = MVRV_THRESHOLDS[key] || { strongBull: 1, mildBull: 1.15, mildBear: 2.8, strongBear: 3.5 };
    if (value <= thresholds.strongBull) {
      return { kind: "bullish", bias: "偏多", reason: "估值处于相对低位，风险补偿更有利于多头。" };
    }
    if (value <= thresholds.mildBull) {
      return makeNeutral("中性偏多", "估值仍偏低，但还没到极端低估区。");
    }
    if (value >= thresholds.strongBear) {
      return { kind: "bearish", bias: "偏空", reason: "估值明显偏热，继续上行需要更强的新驱动。" };
    }
    if (value >= thresholds.mildBear) {
      return makeNeutral("中性偏空", "估值开始偏贵，做多的安全边际下降。");
    }
    return makeNeutral("中性", "估值仍在中性区间，对方向的约束不强。");
  }

  if (key.includes("exchange_net_position_change")) {
    if (value <= -2500) return { kind: "bullish", bias: "偏多", reason: "交易所净流出明显，潜在卖压边际减弱。" };
    if (value < -800) return makeNeutral("中性偏多", "净流出占优，对价格形成一定支撑。");
    if (value >= 2500) return { kind: "bearish", bias: "偏空", reason: "交易所净流入明显，潜在抛压有所抬升。" };
    if (value > 800) return makeNeutral("中性偏空", "净流入占优，短线供给压力略有上升。");
    return makeNeutral("中性", "链上净流向变化有限，暂时不改变方向判断。");
  }

  if (key.includes("active_addresses")) {
    const thresholds = ACTIVE_ADDRESS_THRESHOLDS[key] || { strongBull: 700000, mildBull: 560000, mildBear: 420000, strongBear: 320000 };
    if (value >= thresholds.strongBull) {
      return { kind: "bullish", bias: "偏多", reason: "活跃地址显著扩张，链上参与度对风险偏好有支撑。" };
    }
    if (value >= thresholds.mildBull) {
      return makeNeutral("中性偏多", "活跃度温和抬升，风险偏好有所改善。");
    }
    if (value <= thresholds.strongBear) {
      return { kind: "bearish", bias: "偏空", reason: "链上活跃度明显走弱，需求端承接减弱。" };
    }
    if (value <= thresholds.mildBear) {
      return makeNeutral("中性偏空", "活跃度偏弱，风险偏好尚未恢复。");
    }
    return makeNeutral("中性", "活跃度位于常态区间，对方向影响不强。");
  }

  return makeNeutral("中性", "当前信号更像背景信息，尚不足以单独定义方向。");
}

function observationImpactChip(impact) {
  if (impact.kind === "bullish") return impactChip("bullish", impact.reason, impact.bias);
  if (impact.kind === "bearish") return impactChip("bearish", impact.reason, impact.bias);
  if (impact.kind === "event") return impactChip("event", impact.reason, impact.bias);
  return impactChip("neutral", impact.reason, impact.bias || "中性");
}

function signalStateLabel(value) {
  const normalized = text(value, "normal");
  const mapping = {
    normal: "常态",
    neutral: "中性",
    elevated: "抬升",
    expanded: "扩张",
    overbought: "超买",
    oversold: "超卖",
    strong_trend: "强趋势",
    overheated: "过热",
    outflow_dominant: "净流出主导",
    inflow_dominant: "净流入主导",
    expanding: "扩张",
    live: "已更新",
    stale: "待更新",
    pending: "待接入",
    heating: "升温",
    loose: "偏松",
    tight: "偏紧",
    falling: "回落",
    steepening: "陡峭化",
    expansion: "扩张",
    released: "已发布",
    scheduled: "已排期",
  };
  return mapping[normalized] || normalized;
}

function formatWindowLabel(items) {
  const values = items.map((item) => item.observation_ts).filter(Boolean);
  return values.length ? compactWindowLabel(values) : "暂无样本";
}

function renderObservationCard(title, eyebrow, items) {
  return `
    <article class="card monitoring-pane">
      <div class="section-head">
        <div>
          <p class="eyebrow">${escapeHtml(eyebrow)}</p>
          <h2>${escapeHtml(title)}</h2>
        </div>
        ${items.length ? impactChip("neutral", formatWindowLabel(items), "观测窗口") : ""}
      </div>
      <div class="compact-observation-list">
        ${
          items.length
            ? items
                .map((item) => {
                  const impact = observationImpact(item);
                  return `
                    <div class="compact-observation-row">
                      <div>
                        <strong>${escapeHtml(formatIndicatorName(item.indicator_key))}</strong>
                        <small>${escapeHtml(signalStateLabel(item.signal_state))}</small>
                      </div>
                      <div class="compact-observation-meta">
                        <span>${escapeHtml(observationValue(item.value_num ?? item.value_text))}</span>
                        ${observationImpactChip(impact)}
                      </div>
                    </div>
                  `;
                })
                .join("")
            : '<div class="compact-empty">暂无最新观测数据。</div>'
        }
      </div>
    </article>
  `;
}

function macroBiasChip(value, reason) {
  const normalized = text(value, "中性");
  if (["偏多", "中性偏多", "做多"].includes(normalized)) {
    return impactChip("bullish", reason, normalized);
  }
  if (["偏空", "中性偏空", "减仓", "做空"].includes(normalized)) {
    return impactChip("bearish", reason, normalized);
  }
  if (normalized === "事件窗口") {
    return impactChip("event", reason, normalized);
  }
  return impactChip("neutral", reason, normalized || "中性");
}

function eventStatusChip(status, summary) {
  const normalized = text(status, "中性");
  if (["临近发布", "预警中", "待确认"].includes(normalized)) {
    return impactChip("event", summary, normalized);
  }
  return impactChip("neutral", summary, normalized || "中性");
}

function formatEventField(label, value) {
  return `<span class="status-chip chip-neutral">${escapeHtml(label)} · ${escapeHtml(text(value, "-"))}</span>`;
}

function renderMacroIndicator(item) {
  const isLive = item.status === "live";
  const statusText = isLive ? signalStateLabel(item.signal_state) : "待更新";
  const insight = text(item.insight, isLive ? "宏观观测已更新。" : "当前尚无最新宏观观测值。");

  return `
    <div class="macro-indicator-row">
      <div class="macro-indicator-main">
        <strong>${escapeHtml(text(item.region, "GLOBAL"))} · ${escapeHtml(formatIndicatorName(item.indicator_key))} ${item.tooltip ? knowledgeTooltip(formatIndicatorName(item.indicator_key), "tone-neutral", text(item.tooltip), { extra: text(item.tooltip) }) : ""}</strong>
        <small>${escapeHtml(statusText)} · ${escapeHtml(formatDateTime(item.observation_ts))}</small>
      </div>
      <div class="macro-indicator-meta">
        <span class="macro-indicator-value">${escapeHtml(observationValue(item.value_num ?? item.value_text))}</span>
        ${impactChip(isLive ? "neutral" : "event", insight, isLive ? "已更新" : "待更新")}
      </div>
    </div>
  `;
}

function renderMacroEventList(overview) {
  const items = overview.event_items || [];
  return `
    <section class="macro-event-window">
      <div class="section-head">
        <div>
          <p class="eyebrow">EVENT WINDOW</p>
          <h3>宏观事件窗口</h3>
        </div>
        ${eventStatusChip(text(overview.event_window_status, "中性"), text(overview.event_window_summary, "宏观事件窗口状态"))}
      </div>
      <p class="section-summary">${escapeHtml(text(overview.event_window_summary, "暂无事件窗口摘要。"))}</p>
      <div class="macro-event-list">
        ${
          items.length
            ? items
                .map(
                  (item) => `
                    <article class="macro-layer-item">
                      <div class="card-head-inline">
                        <strong>${escapeHtml(text(item.title, "-"))}</strong>
                        <span class="status-chip chip-neutral">${escapeHtml(text(item.window_label, "-"))}</span>
                      </div>
                      <p>${escapeHtml(text(item.summary, "暂无事件摘要。"))}</p>
                      <div class="macro-layer-indicators">
                        ${formatEventField("地区", item.country_code)}
                        ${formatEventField("时间", formatDateTime(item.scheduled_at))}
                        ${formatEventField("状态", signalStateLabel(item.status))}
                        ${formatEventField("预期", item.consensus_value_num)}
                        ${formatEventField("实际", item.actual_value_num)}
                        ${formatEventField("前值", item.previous_value_num)}
                        ${formatEventField("Surprise", item.surprise_num)}
                      </div>
                    </article>
                  `,
                )
                .join("")
            : '<div class="compact-empty">当前还没有可展示的宏观事件。</div>'
        }
      </div>
    </section>
  `;
}

function operationTone(value, eventWindowStatus) {
  const bias = text(value, "观望");
  if (bias === "做多") return "bullish";
  if (bias === "减仓" || bias === "做空") return "bearish";
  if (["临近发布", "预警中", "待确认"].includes(text(eventWindowStatus, ""))) return "event";
  return "neutral";
}

function renderMacroOverviewCard(overview) {
  return `
    <article class="card macro-overview-card">
      <div class="macro-overview-top">
        <div>
          <p class="eyebrow">MACRO</p>
          <h2>宏观观察</h2>
          <p class="macro-regime-copy">${escapeHtml(text(overview.regime_label_cn, "观望整理"))} · ${escapeHtml(text(overview.operation_bias, "观望"))}</p>
          <p class="section-summary">${escapeHtml(text(overview.regime_summary || overview.event_window_summary, "等待更多宏观驱动确认。"))}</p>
        </div>
        <div class="macro-top-chips">
          ${impactChip(
            operationTone(overview.operation_bias, overview.event_window_status),
            text(overview.event_window_summary, "宏观窗口状态"),
            text(overview.operation_bias, "观望"),
          )}
        </div>
      </div>
      <div class="score-grid"></div>
      <div class="macro-layer-grid">
        ${(overview.layers || [])
          .map(
            (layer) => `
              <article class="macro-layer-item macro-layer-panel">
                <div class="card-head-inline">
                  <strong>${escapeHtml(text(layer.label_cn, "-"))}</strong>
                  ${macroBiasChip(text(layer.bias, "中性"), text(layer.summary, ""))}
                </div>
                <p>${escapeHtml(text(layer.summary, "暂无层级摘要。"))}</p>
                <div class="macro-indicator-list">
                  ${(layer.indicators || [])
                    .slice(0, 4)
                    .map((item) => renderMacroIndicator(item))
                    .join("")}
                </div>
              </article>
            `,
          )
          .join("")}
      </div>
      ${renderMacroEventList(overview)}
    </article>
  `;
}

const autoSyncKeys = new Set();

async function loadDashboardData(label, loader, fallback) {
  try {
    return await loader();
  } catch (error) {
    if (error?.name === "AbortError" || error?.name === "TimeoutError") {
      return fallback;
    }
    console.warn("monitoring:data-load:error", label, error);
    return fallback;
  }
}

export async function renderMonitoring() {
  let activeController = null;
  setRoot(`
    <section id="monitoring-statusbar"></section>
    <section class="grid cols-4" id="monitoring-summary-cards"></section>
    <section id="macro-overview-root"></section>
    <section class="monitoring-observation-grid" id="monitoring-observations-grid"></section>
  `);

  const renderStatus = (message, tone = "neutral") => {
    const el = document.getElementById("monitoring-statusbar");
    if (el) el.innerHTML = statusBanner(message, tone);
  };

  activeController?.abort();
  activeController = new AbortController();
  const dashboardBundle = await loadDashboardData(
    "monitoring-dashboard",
    () => api.getMonitoringDashboard(appState.selectedInstrumentId, appState.selectedTimeframe, {
      signal: activeController.signal,
    }),
    {
      status: "missing",
      status_message: "暂无快照，已加入预计算队列",
      macro_overview: { layers: [], event_items: [] },
      technical_observations: [],
      onchain_observations: [],
      alert_events: [],
    },
  );
  let macroOverview = dashboardBundle.macro_overview || { layers: [], event_items: [] };
  let technicalItems = dashboardBundle.technical_observations || [];
  let onchainItems = dashboardBundle.onchain_observations || [];
  const alerts = dashboardBundle.alert_events || [];

  const technicalKey = `technical:${appState.selectedInstrumentId}:${appState.selectedTimeframe}`;
  if ((dashboardBundle.status === "missing" || dashboardBundle.status === "stale" || !technicalItems.length) && !autoSyncKeys.has(technicalKey)) {
    autoSyncKeys.add(technicalKey);
    renderStatus("本地暂无数据，正在从 Gate.io 拉取 K 线并计算指标", "loading");
    await scheduleIdlePrecompute({
      page: "monitoring-overview",
      instrumentId: appState.selectedInstrumentId,
      timeframe: appState.selectedTimeframe === "1M" ? "30d" : appState.selectedTimeframe,
      reason: "monitoring_dashboard_read",
      priority: 3,
    });
    renderStatus(technicalItems.length ? "数据已就绪" : "同步完成，但暂无技术观测", technicalItems.length ? "success" : "warning");
  }

  const macroHasData = (macroOverview.layers || []).length || (macroOverview.event_items || []).length;
  if (!macroHasData && dashboardBundle.status === "missing" && !autoSyncKeys.has("macro")) {
    autoSyncKeys.add("macro");
    renderStatus("正在同步宏观日历与宏观观测", "loading");
    await scheduleIdlePrecompute({
      page: "monitoring-overview",
      instrumentId: appState.selectedInstrumentId,
      timeframe: appState.selectedTimeframe === "1M" ? "30d" : appState.selectedTimeframe,
      reason: "monitoring_macro_missing",
      priority: 4,
    });
    macroOverview = await loadDashboardData("macro-overview-reload", () => api.getMacroOverview(), {
      layers: [],
      event_items: [],
    });
    const refreshedMacroHasData = (macroOverview.layers || []).length || (macroOverview.event_items || []).length;
    renderStatus(refreshedMacroHasData ? "数据已就绪" : "同步完成，但暂无宏观观测", refreshedMacroHasData ? "success" : "warning");
  }

  const macroLayers = Object.fromEntries((macroOverview.layers || []).map((layer) => [layer.layer_key, layer]));

  document.getElementById("monitoring-summary-cards").innerHTML = [
    metricCard("技术观测数", technicalItems.length, "最近样本"),
    metricCard("宏观状态", text(macroOverview.regime_label_cn, "观望整理"), text(macroOverview.operation_bias, "观望")),
    metricCard("链上观测数", onchainItems.length, "最近样本"),
    metricCard("当前 Open 告警", alerts.filter((item) => item.status === "open").length, "站内告警"),
  ].join("");

  document.getElementById("macro-overview-root").innerHTML = renderMacroOverviewCard(macroOverview);
  document.querySelector("#macro-overview-root .score-grid").innerHTML = [
    metricCard("POLICY SCORE", formatNumber(macroOverview.policy_score, 0), text(macroLayers.rates_policy?.bias, "中性")),
    metricCard("INFLATION SCORE", formatNumber(macroOverview.inflation_score, 0), text(macroLayers.inflation?.bias, "中性")),
    metricCard("GROWTH SCORE", formatNumber(macroOverview.growth_score, 0), text(macroLayers.growth_labor?.bias, "中性")),
    metricCard("LIQUIDITY SCORE", formatNumber(macroOverview.liquidity_score, 0), text(macroLayers.liquidity_credit?.bias, "中性")),
  ].join("");

  document.getElementById("monitoring-observations-grid").innerHTML = [
    renderObservationCard("技术观测", "TECHNICAL", technicalItems),
    renderObservationCard("链上观测", "ON-CHAIN", onchainItems),
  ].join("");
}
