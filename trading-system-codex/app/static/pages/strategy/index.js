import { api } from "../../core/api.js";
import { appState, getInstrumentMeta, persistState } from "../../core/state.js";
import {
  emptyState,
  degradedState,
  errorState,
  escapeHtml,
  formatDateTime,
  formatNumber,
  setRoot,
  statusBanner,
} from "../../core/dom.js";
import { normalizeUnifiedStrategy, buildDataDegradedCard } from "./adapter.js?v=trade-4h-v1";
import { renderEventWatch } from "./renderEventWatch.js?v=compact-v3";
import { renderMarketOperation } from "./renderMarketOperation.js?v=decision-text-cleanup";
import { renderOverview } from "./renderOverview.js?v=trade-4h-v1";
import { renderRiskPanel } from "./renderRiskPanel.js?v=compact-v3";
import { renderExecutionPlan } from "./renderExecutionPlan.js?v=trade-4h-v1";
import { renderEvidenceStack } from "./renderEvidenceStack.js?v=compact-v3";
import { renderDecisionAudit } from "./renderDecisionAudit.js?v=auditable-v1";
import { mountPageGuide } from "../../ui/pageGuideFab.js";

let activeController = null;
let requestToken = 0;
let mounted = false;
let coldStartRetryTimer = null;
let coldStartRetryCount = 0;

const helpers = {
  emptyState,
  errorState,
  escapeHtml,
  formatDateTime,
  formatNumber,
};

function renderInstrumentOptions() {
  return appState.instruments.map((item) => `
    <option value="${escapeHtml(item.id)}" ${item.id === appState.selectedInstrumentId ? "selected" : ""}>
      ${escapeHtml(item.code)} · ${escapeHtml(item.name)}
    </option>
  `).join("");
}

function renderShell() {
  const instrument = getInstrumentMeta(appState.selectedInstrumentId);
  setRoot(`
    <section class="strategy-v2-page">
      <section class="strategy-v2-toolbar card">
        <div>
          <p class="eyebrow">AI STRATEGY V2</p>
          <h1>跨周期统一推演</h1>
          <p>${escapeHtml(instrument.code || appState.selectedInstrumentId)} · 六周期固定证据栈</p>
        </div>
        <label class="strategy-v2-select">
          <span>标的</span>
          <select id="strategy-instrument">${renderInstrumentOptions()}</select>
        </label>
        <div class="strategy-v2-actions">
          <button type="button" class="secondary-button" id="strategy-save-snapshot">保存战术快照</button>
          <button type="button" class="primary-button" id="strategy-refresh">刷新推演</button>
        </div>
      </section>
      <div id="strategy-status">${statusBanner("正在读取统一策略缓存", "info")}</div>
      <div id="strategy-content" class="strategy-v2-content">
        ${emptyState("统一策略推演加载中")}
      </div>
      <section id="strategy-review" class="strategy-v2-review"></section>
    </section>
  `);
}

function renderModel(model) {
  const content = document.getElementById("strategy-content");
  if (!content) return;
  content.innerHTML = `
    ${renderOverview(model, helpers)}
    ${renderExecutionPlan(model, helpers)}
    ${renderDecisionAudit(model, helpers)}
    ${renderEvidenceStack(model, helpers)}
    ${renderMarketOperation(model, helpers)}
    ${renderRiskPanel(model, helpers)}
    ${renderEventWatch(model, helpers)}
    ${buildDataDegradedCard(model)}
  `;
}

function renderReview(review) {
  const el = document.getElementById("strategy-review");
  if (!el) return;
  const items = Array.isArray(review?.recent_reviews) ? review.recent_reviews : [];
  const rows = items.slice(0, 5).map((item) => `
    <li>
      <strong>${escapeHtml(item.outcome || item.status || "复盘记录")}</strong>
      <span>${escapeHtml(item.note || item.summary || (item.generated_at ? formatDateTime(item.generated_at) : ""))}</span>
    </li>
  `).join("");
  const isEmpty = rows.length === 0;
  el.innerHTML = `
    <details class="strategy-v2-section strategy-collapsible strategy-review-panel card" ${isEmpty ? "" : "open"}>
      <summary class="strategy-collapsible-summary">
        <div>
          <p class="eyebrow">TACTICAL REVIEW</p>
          <h2>1d 战术快照与复盘辅助</h2>
          <small>${isEmpty ? "暂无战术复盘记录" : `${rows.length} 条近期记录`}</small>
        </div>
        <span class="strategy-collapse-control" aria-hidden="true"></span>
      </summary>
      ${isEmpty ? "" : `<div class="strategy-collapsible-body"><ul class="strategy-monitor-list">${rows}</ul></div>`}
    </details>
  `;
}

async function loadReview() {
  try {
    const review = await api.getStrategyReview(appState.selectedInstrumentId, "1d");
    renderReview(review);
  } catch (error) {
    console.debug("strategy:review:skipped", error);
  }
}

async function loadUnifiedStrategy({ force = false, bypassCache = false } = {}) {
  const token = ++requestToken;
  if (coldStartRetryTimer) {
    clearTimeout(coldStartRetryTimer);
    coldStartRetryTimer = null;
  }
  activeController?.abort();
  activeController = new AbortController();
  const status = document.getElementById("strategy-status");
  if (status) status.innerHTML = statusBanner(force ? "正在刷新统一策略推演" : "正在读取统一策略缓存", "info");
  const instrumentId = appState.selectedInstrumentId;
  const { signal } = activeController;
  const results = await Promise.allSettled([
    api.getUnifiedStrategy(instrumentId, {
      force,
      bypassCache: bypassCache || coldStartRetryCount > 0,
      signal,
    }),
    api.getMonitoringDashboard(instrumentId, "1d", { signal }),
    api.getBtcDerivativesDashboard({ signal }),
    api.getMacroOverview({ signal }),
  ]);
  if (!mounted || token !== requestToken) return;
  const failed = results.filter((r) => r.status === "rejected");
  const dataAccess = {
    unified: results[0].status === "fulfilled" ? results[0].value : null,
    monitoring: results[1].status === "fulfilled" ? results[1].value : null,
    derivatives: results[2].status === "fulfilled" ? results[2].value : null,
    macro: results[3].status === "fulfilled" ? results[3].value : null,
  };
  const dataAccessFailures = {
    unified: results[0].status === "rejected" ? results[0].reason?.message || "读取失败" : null,
    monitoring: results[1].status === "rejected" ? results[1].reason?.message || "读取失败" : null,
    derivatives: results[2].status === "rejected" ? results[2].reason?.message || "读取失败" : null,
    macro: results[3].status === "rejected" ? results[3].reason?.message || "读取失败" : null,
  };
  if (!dataAccess.unified) {
    if (status) status.innerHTML = statusBanner("策略推演暂时不可用，已自动触发后台预热", "warning");
    const content = document.getElementById("strategy-content");
    if (content) content.innerHTML = degradedState(
      "策略推演暂时不可用",
      "统一策略服务正在恢复，已自动触发后台预热。"
    );
    // Re-trigger prewarm in case the mount-time fire failed
    api.prewarmStrategy(instrumentId).catch(() => {});
    return;
  }
  if (failed.length === 4) {
    if (status) status.innerHTML = statusBanner("所有数据源不可用，已自动触发后台预热", "warning");
    const content = document.getElementById("strategy-content");
    if (content) content.innerHTML = degradedState(
      "所有数据源不可用",
      "监控、衍生品、宏观、统一策略全部失败。"
    );
    api.prewarmStrategy(instrumentId).catch(() => {});
    return;
  }
  const model = normalizeUnifiedStrategy(dataAccess.unified, dataAccess);
  model.data_access = dataAccess;
  model.data_access_failures = dataAccessFailures;
  renderModel(model);
  const shouldAutoRetryColdStart = !force
    && model.degraded_components?.includes("strategy_unified_cache_missing");
  if (failed.length === 0 && !model.degraded) {
    if (status) status.innerHTML = statusBanner("统一策略推演已更新", "success");
  } else if (model.degraded) {
    const components = (model.degraded_components || []).join("、") || "部分组件";
    if (status) status.innerHTML = statusBanner(`策略已渲染；${components} 降级，后台预热中`, "warning");
  } else {
    if (status) status.innerHTML = statusBanner(`统一策略已更新；${failed.length}/4 数据源不可用`, "warning");
  }
  if (shouldAutoRetryColdStart) {
    api.prewarmStrategy(instrumentId).catch(() => {});
    coldStartRetryCount += 1;
    if (status) {
      status.innerHTML = statusBanner(
        `统一策略快照尚未就绪，后台预热中 (${coldStartRetryCount})`,
        "warning"
      );
    }
    coldStartRetryTimer = setTimeout(() => {
      if (mounted) void loadUnifiedStrategy({ force: false, bypassCache: true });
    }, Math.min(8000, 1500 + coldStartRetryCount * 1000));
  } else {
    coldStartRetryCount = 0;
  }
  await loadReview();
}

function attachEvents() {
  document.getElementById("strategy-instrument")?.addEventListener("change", async (event) => {
    appState.selectedInstrumentId = event.target.value;
    persistState();
    renderShell();
    attachEvents();
    await loadUnifiedStrategy();
  });
  document.getElementById("strategy-refresh")?.addEventListener("click", async (event) => {
    const button = event.currentTarget;
    button.disabled = true;
    try {
      await loadUnifiedStrategy({ force: true });
    } finally {
      button.disabled = false;
    }
  });
  document.getElementById("strategy-save-snapshot")?.addEventListener("click", async (event) => {
    const button = event.currentTarget;
    const status = document.getElementById("strategy-status");
    button.disabled = true;
    try {
      await api.saveStrategySnapshot(appState.selectedInstrumentId, "1d");
      if (status) status.innerHTML = statusBanner("1d 战术快照已保存", "success");
      await loadReview();
    } catch (error) {
      if (status) status.innerHTML = statusBanner("战术快照保存失败", "error");
    } finally {
      button.disabled = false;
    }
  });
}

export async function renderStrategy() {
  mounted = true;
  renderShell();
  attachEvents();
  const guideFab = mountPageGuide("ai-strategy");
  return {
    mount: async () => {
      // Fire-and-forget background prewarm (don't await)
      api.prewarmStrategy(appState.selectedInstrumentId).catch(() => {});
      coldStartRetryCount = 0;
      await loadUnifiedStrategy();
    },
    unmount: async () => {
      guideFab.unmount();
      mounted = false;
      if (coldStartRetryTimer) {
        clearTimeout(coldStartRetryTimer);
        coldStartRetryTimer = null;
      }
      coldStartRetryCount = 0;
      activeController?.abort();
      activeController = null;
    },
    pause: async () => {},
    resume: async () => {
      if (mounted) await loadUnifiedStrategy();
    },
  };
}

export default renderStrategy;
