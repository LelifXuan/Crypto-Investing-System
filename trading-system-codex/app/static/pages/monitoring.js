import { api } from "../core/api.js";
import {
  escapeHtml,
  formatDateTime,
  formatIndicatorName,
  formatNumber,
  impactChip,
  metricCard,
  observationValue,
  setRoot,
  statusBanner,
} from "../core/dom.js";
import { scheduleIdlePrecompute } from "../core/precompute.js";
import { appState } from "../core/state.js";

let activeController = null;
let macroRefreshPending = false;
const queuedKeys = new Set();

function text(value, fallback = "-") {
  if (value === null || value === undefined || value === "") return fallback;
  return String(value);
}

function signalStateLabel(value) {
  const mapping = {
    bullish: "偏多",
    bearish: "偏空",
    neutral: "中性",
    normal: "正常",
    strong: "偏强",
    weak: "偏弱",
    overbought: "超买",
    oversold: "超卖",
    positive_hist: "柱线转强",
    negative_hist: "柱线转弱",
    expanded: "波动扩张",
    compressed: "波动压缩",
    breakout_up: "向上突破",
    breakout_down: "向下跌破",
    strong_trend: "趋势较强",
    weak_trend: "趋势偏弱",
    developing_trend: "趋势形成中",
    cooling: "降温",
    falling: "回落",
    released: "已发布",
    scheduled: "待发布",
    inflow_dominant: "流入占优",
    outflow_dominant: "流出占优",
    undervalued: "低估",
    source_error: "来源异常",
  };
  return mapping[value] || text(value, "中性");
}

function observationTone(item) {
  const state = item.signal_state;
  if (["bullish", "strong", "positive_hist", "breakout_up", "outflow_dominant"].includes(state)) return "bullish";
  if (["bearish", "weak", "negative_hist", "breakout_down", "inflow_dominant"].includes(state)) return "bearish";
  if (["overbought", "oversold", "expanded", "scheduled", "released"].includes(state)) return "event";
  return "neutral";
}

function sourceStatusMeta(status) {
  const mapping = {
    online: { label: "在线", className: "chip-bullish" },
    ok: { label: "在线", className: "chip-bullish" },
    fresh: { label: "在线", className: "chip-bullish" },
    stale_cache: { label: "使用缓存", className: "chip-event" },
    stale: { label: "使用缓存", className: "chip-event" },
    cached: { label: "使用缓存", className: "chip-event" },
    no_data: { label: "无数据", className: "chip-event" },
    missing: { label: "无数据", className: "chip-event" },
    not_configured: { label: "未配置", className: "chip-neutral" },
    auth_missing: { label: "未配置", className: "chip-neutral" },
    updating: { label: "后台准备中", className: "chip-neutral" },
    pending: { label: "后台准备中", className: "chip-neutral" },
    offline: { label: "离线", className: "chip-bearish" },
    error: { label: "离线", className: "chip-bearish" },
    source_error: { label: "离线", className: "chip-bearish" },
    rate_limited: { label: "限流", className: "chip-event" },
  };
  return mapping[status] || { label: "未知", className: "chip-neutral" };
}

function normalizeSourceStatus(raw) {
  const labels = {
    gateio: "Gate.io",
    fred: "FRED",
    market_events: "市场事件",
    ashare_etf: "A股ETF",
  };
  const defaults = {
    online: "信源在线，缓存可用。",
    ok: "信源在线，缓存可用。",
    fresh: "信源在线，缓存可用。",
    stale_cache: "正在使用旧缓存。",
    stale: "正在使用旧缓存。",
    cached: "正在使用旧缓存。",
    no_data: "暂未读取到可用数据，等待后台补齐。",
    missing: "暂未读取到可用数据，等待后台补齐。",
    not_configured: "信源未配置，不视为系统故障。",
    auth_missing: "API Key 未配置，不视为系统故障。",
    updating: "后台正在准备数据。",
    pending: "后台正在准备数据。",
    offline: "信源读取失败。",
    error: "信源读取失败。",
    source_error: "信源读取失败。",
    rate_limited: "信源限流，稍后自动重试。",
  };
  const source = raw && typeof raw === "object" ? raw : {};
  return Object.entries(labels).map(([key, label]) => {
    const value = source[key];
    const item = value && typeof value === "object" ? value : { status: value || "updating" };
    const status = String(item.status || "updating");
    return {
      key,
      status,
      label: item.label || label,
      message: item.message || defaults[status] || "状态暂不可用。",
      lastError: item.last_error || item.lastError || "",
      updatedAt: item.updated_at || item.updatedAt || "",
      meta: sourceStatusMeta(status),
    };
  });
}

function monitoringStatusMessage(bundle, isStale) {
  if (!bundle) return "正在读取监控快照";
  if (bundle.cache_state === "missing") return "暂无监控快照，已加入后台预计算队列。";
  if (bundle.cache_state === "updating") return "监控快照正在后台准备中，当前先展示可用缓存。";
  if (bundle.cache_state === "error") return "监控快照读取异常，页面已保留可用缓存和降级信息。";
  if (isStale) return "监控快照可用但可能滞后，后台会继续补齐。";
  return "监控快照已就绪。";
}

function renderObservationCard(title, eyebrow, items, emptyText) {
  return `
    <article class="card monitoring-pane">
      <div class="section-head">
        <div>
          <p class="eyebrow">${escapeHtml(eyebrow)}</p>
          <h2>${escapeHtml(title)}</h2>
        </div>
        <span class="status-chip chip-neutral">${items.length} 项</span>
      </div>
      <div class="compact-observation-list">
        ${
          items.length
            ? items
                .map(
                  (item) => `
                    <div class="compact-observation-row">
                      <div>
                        <strong>${escapeHtml(formatIndicatorName(item.indicator_key))}</strong>
                        <small>${escapeHtml(formatDateTime(item.observation_ts))}</small>
                      </div>
                      <div class="compact-observation-meta">
                        <span>${escapeHtml(observationValue(item.value_num ?? item.value_text))}</span>
                        ${impactChip(observationTone(item), signalStateLabel(item.signal_state), signalStateLabel(item.signal_state))}
                      </div>
                    </div>
                  `,
                )
                .join("")
            : `<div class="compact-empty">${escapeHtml(emptyText)}</div>`
        }
      </div>
    </article>
  `;
}

function renderSourceStatus(sourceStatus) {
  const rows = normalizeSourceStatus(sourceStatus);
  return `
    <article class="card monitoring-source-card">
      <div class="section-head">
        <div>
          <p class="eyebrow">SOURCE HEALTH</p>
          <h2>信源状态</h2>
          <p class="section-summary">信源异常只影响对应数据块，页面会优先展示已缓存快照。</p>
        </div>
      </div>
      <div class="source-status-grid">
        ${rows
          .map(
            (item) => `
              <div class="source-status-item">
                <div class="card-head-inline">
                  <strong>${escapeHtml(item.label)}</strong>
                  <span class="status-chip ${escapeHtml(item.meta.className)}">${escapeHtml(item.meta.label)}</span>
                </div>
                <p>${escapeHtml(item.message)}</p>
                ${item.updatedAt ? `<small>最近更新：${escapeHtml(formatDateTime(item.updatedAt))}</small>` : ""}
                ${item.lastError ? `<small class="source-error">错误：${escapeHtml(item.lastError)}</small>` : ""}
              </div>
            `,
          )
          .join("")}
      </div>
    </article>
  `;
}

function confidenceLabel(value) {
  const mapping = {
    high: "高",
    medium: "中",
    low: "低",
    insufficient: "不足",
  };
  return mapping[value] || text(value, "不足");
}

function renderMacroOverview(overview) {
  if (!overview) {
    return `
      <article class="card">
        <div class="section-head">
          <div>
            <p class="eyebrow">MACRO</p>
            <h2>宏观观察</h2>
          </div>
          <button class="ghost-button macro-refresh-button" id="macro-refresh-btn" onclick="event.preventDefault();refreshMacroData()">刷新宏观</button>
        </div>
        <div class="empty-state">宏观快照暂不可用，点击刷新获取数据。</div>
      </article>
    `;
  }
  const contributions = overview.layer_contributions || {};
  const contributionRows = [
    ["rates_policy", "利率与政策", overview.policy_score],
    ["inflation", "通胀与价格", overview.inflation_score],
    ["growth_labor", "增长与就业", overview.growth_score],
    ["liquidity_credit", "流动性与信用", overview.liquidity_score],
    ["cross_asset_confirmation", "跨资产确认", null],
    ["event_window", "事件窗口", null],
  ];
  const layers = overview.layers || [];
  return `
    <article class="card macro-overview-card">
      <div class="section-head">
        <div>
          <p class="eyebrow">MACRO</p>
          <h2>宏观观察</h2>
          <p class="section-summary">${escapeHtml(overview.regime_summary || "宏观状态暂不可用。")}</p>
        </div>
        <button class="ghost-button macro-refresh-button" id="macro-refresh-btn" onclick="event.preventDefault();refreshMacroData()">刷新宏观</button>
      </div>
      <div class="macro-overview-top">
        <div class="macro-score-block">
          <span>宏观总分</span>
          <strong>${escapeHtml(formatNumber(overview.total_score ?? 0, 0))}</strong>
          <small>${escapeHtml(overview.score_band || overview.regime_label_cn || "-")} · 置信度 ${escapeHtml(confidenceLabel(overview.confidence))}</small>
        </div>
        <div class="macro-score-bar" aria-hidden="true">
          <span style="width:${Math.max(0, Math.min(100, Number(overview.total_score || 0)))}%"></span>
        </div>
      </div>
      <p class="section-summary">${escapeHtml(overview.score_explanation || "")}</p>
      <div class="macro-contribution-grid">
        ${contributionRows
          .map(([key, label, score]) => {
            const contribution = Number(contributions[key] || 0);
            return `
              <div class="macro-contribution-row">
                <span>${escapeHtml(label)}</span>
                <strong>${score === null ? escapeHtml(formatNumber(contribution, 2)) : escapeHtml(formatNumber(score, 0))}</strong>
                <small>贡献 ${contribution >= 0 ? "+" : ""}${escapeHtml(formatNumber(contribution, 2))}</small>
              </div>
            `;
          })
          .join("")}
      </div>
      ${overview.warnings?.length ? `<div class="status-banner status-warning">${overview.warnings.map(escapeHtml).join("；")}</div>` : ""}
      <div class="macro-layer-list">
        ${layers
          .map(
            (layer) => `
              <section class="macro-layer-item">
                <div class="card-head-inline">
                  <strong>${escapeHtml(layer.label_cn)}</strong>
                  <span class="status-chip chip-neutral">${escapeHtml(layer.bias)} · ${escapeHtml(formatNumber(layer.score, 0))}</span>
                </div>
                <p>${escapeHtml(layer.summary || "")}</p>
                <small>有效指标 ${escapeHtml(formatNumber(layer.effective_count || 0, 0))}/${escapeHtml(formatNumber(layer.total_count || 0, 0))}</small>
              </section>
            `,
          )
          .join("")}
      </div>
    </article>
  `;
}

function renderShellFallback() {
  document.getElementById("monitoring-summary-cards").innerHTML = [
    metricCard("技术观测数", "-", "技术快照暂不可用"),
    metricCard("宏观状态", "暂不可用", "中性"),
    metricCard("信源状态", "-", "后台准备中"),
    metricCard("Open 告警", "-", "暂不可用"),
  ].join("");
  document.getElementById("source-status-root").innerHTML = renderSourceStatus({});
  document.getElementById("macro-overview-root").innerHTML = renderMacroOverview(null);
  document.getElementById("monitoring-observations-grid").innerHTML = renderObservationCard(
    "技术观测",
    "TECHNICAL",
    [],
    "技术快照暂不可用，后台准备中。",
  );
}

function renderDashboard(bundle) {
  const technicalItems = bundle.technical_observations || [];
  const sourceItems = normalizeSourceStatus(bundle.source_status || {});
  document.getElementById("monitoring-summary-cards").innerHTML = [
    metricCard("技术观测数", formatNumber(bundle.technical_indicator_count ?? technicalItems.length, 0), bundle.technical_source || "等待快照"),
    metricCard("宏观状态", bundle.macro_overview?.score_band || "暂不可用", `总分 ${formatNumber(bundle.macro_overview?.total_score, 0)}`),
    metricCard("信源状态", `${sourceItems.filter((item) => ["online", "ok", "fresh", "stale_cache", "cached"].includes(item.status)).length}/${sourceItems.length}`, "在线或可用缓存"),
    metricCard("Open 告警", formatNumber((bundle.alert_events || []).length, 0), "当前监控摘要"),
  ].join("");
  document.getElementById("source-status-root").innerHTML = renderSourceStatus(bundle.source_status || {});
  document.getElementById("macro-overview-root").innerHTML = renderMacroOverview(bundle.macro_overview);
  document.getElementById("monitoring-observations-grid").innerHTML = renderObservationCard(
    "技术观测",
    "TECHNICAL",
    technicalItems,
    "技术快照暂不可用，后台准备中。",
  );
}

async function loadDashboard() {
  activeController?.abort();
  activeController = new AbortController();
  const statusRoot = document.getElementById("monitoring-statusbar");
  statusRoot.innerHTML = statusBanner("正在读取监控快照", "loading");
  try {
    const bundle = await api.getMonitoringDashboard(appState.selectedInstrumentId, appState.selectedTimeframe, {
      signal: activeController.signal,
      force: true,
      timeoutMs: 30000,
    });
    const stale = ["stale", "missing", "updating"].includes(bundle.cache_state);
    statusRoot.innerHTML = statusBanner(monitoringStatusMessage(bundle, stale), stale ? "info" : "success");
    renderDashboard(bundle);
    const key = `monitoring:${appState.selectedInstrumentId}:${appState.selectedTimeframe}`;
    if (stale && !queuedKeys.has(key)) {
      queuedKeys.add(key);
      scheduleIdlePrecompute({
        currentPage: "monitoring-overview",
        instrumentId: appState.selectedInstrumentId,
        timeframe: appState.selectedTimeframe,
        reason: "monitoring-dashboard-stale",
        priority: 2,
      });
    }
  } catch (error) {
    if (error?.name === "AbortError") return;
    console.warn("monitoring:data-load:error", error);
    statusRoot.innerHTML = statusBanner("监控快照读取失败，已保留页面骨架，可稍后重试。", "warning");
    renderShellFallback();
  }
}

export async function renderMonitoring() {
  setRoot(`
    <section id="monitoring-statusbar"></section>
    <section class="grid cols-4" id="monitoring-summary-cards"></section>
    <section id="source-status-root"></section>
    <section id="macro-overview-root"></section>
    <section class="monitoring-observation-grid" id="monitoring-observations-grid"></section>
  `);
  renderShellFallback();
  await loadDashboard();
  return {
    unmount: async () => activeController?.abort(),
    pause: async () => activeController?.abort(),
    resume: async () => loadDashboard(),
  };
}

async function refreshMacroData() {
  if (macroRefreshPending) return;
  macroRefreshPending = true;
  const statusRoot = document.getElementById("monitoring-statusbar");
  const btn = document.getElementById("macro-refresh-btn");
  if (btn) btn.textContent = "同步中...";
  try {
    statusRoot.innerHTML = statusBanner("正在同步宏观数据", "loading");
    await api.refreshMacro();
    await loadDashboard();
  } catch (error) {
    console.warn("macro-refresh:error", error);
    statusRoot.innerHTML = statusBanner("宏观数据同步失败，已保留当前缓存。", "warning");
  } finally {
    macroRefreshPending = false;
    if (btn) btn.textContent = "刷新宏观";
  }
}

window.refreshMacroData = refreshMacroData;
