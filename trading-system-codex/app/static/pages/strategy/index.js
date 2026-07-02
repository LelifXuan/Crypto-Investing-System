import { api } from "../../core/api.js";
import { appState, getInstrumentMeta, persistState } from "../../core/state.js";
import {
  emptyState,
  errorState,
  escapeHtml,
  formatDateTime,
  formatNumber,
  setRoot,
  statusBanner,
} from "../../core/dom.js";
import { normalizeUnifiedStrategy, buildDataDegradedCard } from "./adapter.js?v=narrative-layers";
import { renderEvidenceTrace } from "./renderEvidenceTrace.js?v=narrative-layers";
import { renderEventWatch } from "./renderEventWatch.js?v=narrative-layers";
import { renderHorizonGovernance } from "./renderHorizonGovernance.js?v=narrative-layers";
import { renderHorizonStack } from "./renderHorizonStack.js?v=narrative-layers";
import { renderMarketOperation } from "./renderMarketOperation.js?v=narrative-layers";
import { renderNarrative } from "./renderNarrative.js?v=narrative-layers";
import { renderOverview } from "./renderOverview.js?v=narrative-layers";
import { renderRiskPanel } from "./renderRiskPanel.js?v=narrative-layers";
import { renderTradePlans } from "./renderTradePlans.js?v=narrative-layers";

let activeController = null;
let requestToken = 0;
let mounted = false;

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

function renderDataAccessState(model) {
  const items = (model.timeframe_stack || []).map((node) => {
    const cacheState = node.raw_status?.cache_state || node.freshness || "unknown";
    const modules = (node.source_modules || []).join(" / ") || "-";
    return `
      <article class="strategy-data-state-item ${escapeHtml(cacheState)}">
        <strong>${escapeHtml(node.timeframe || "-")}</strong>
        <span>${escapeHtml(cacheState)}</span>
        <small>${escapeHtml(modules)}</small>
      </article>
    `;
  }).join("");
  return `
    <section class="strategy-data-state">
      <div>
        <p class="eyebrow">DATA ACCESS</p>
        <h2>六周期数据接入状态</h2>
      </div>
      <div class="strategy-data-state-grid">${items || emptyState("暂无周期数据状态")}</div>
    </section>
  `;
}

function renderModel(model) {
  const content = document.getElementById("strategy-content");
  if (!content) return;
  content.innerHTML = `
    ${renderOverview(model, helpers)}
    ${renderMarketOperation(model, helpers)}
    ${renderHorizonGovernance(model, helpers)}
    ${renderHorizonStack(model, helpers)}
    ${renderTradePlans(model, helpers)}
    ${renderRiskPanel(model, helpers)}
    ${renderEventWatch(model, helpers)}
    ${renderEvidenceTrace(model, helpers)}
    ${renderNarrative(model, helpers)}
    ${renderDataAccessState(model)}
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
      <span>${escapeHtml(item.note || item.summary || item.generated_at || "")}</span>
    </li>
  `).join("");
  el.innerHTML = `
    <section class="strategy-v2-section card">
      <div class="section-heading compact">
        <div>
          <p class="eyebrow">TACTICAL REVIEW</p>
          <h2>1d 战术快照与复盘辅助</h2>
        </div>
      </div>
      <ul class="strategy-monitor-list">${rows || "<li>暂无战术复盘记录</li>"}</ul>
    </section>
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

async function loadUnifiedStrategy({ force = false } = {}) {
  const token = ++requestToken;
  activeController?.abort();
  activeController = new AbortController();
  const status = document.getElementById("strategy-status");
  if (status) status.innerHTML = statusBanner(force ? "正在刷新统一策略推演" : "正在读取统一策略缓存", "info");
  const instrumentId = appState.selectedInstrumentId;
  const { signal } = activeController;
  const results = await Promise.allSettled([
    api.getUnifiedStrategy(instrumentId, { force, signal }),
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
    if (status) status.innerHTML = statusBanner("统一策略读取失败，请稍后重试", "error");
    const content = document.getElementById("strategy-content");
    if (content) content.innerHTML = errorState("统一策略读取失败，请稍后重试");
    return;
  }
  if (failed.length === 4) {
    if (status) status.innerHTML = statusBanner("四个数据源全部失败", "error");
    const content = document.getElementById("strategy-content");
    if (content) content.innerHTML = errorState("四个数据源全部不可用，请稍后重试");
    return;
  }
  const model = normalizeUnifiedStrategy(dataAccess.unified, dataAccess);
  model.data_access = dataAccess;
  model.data_access_failures = dataAccessFailures;
  renderModel(model);
  if (failed.length === 0) {
    if (status) status.innerHTML = statusBanner("统一策略推演已更新", "success");
  } else {
    if (status) status.innerHTML = statusBanner(`统一策略已更新；${failed.length}/4 数据源不可用`, "warning");
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
  return {
    mount: async () => {
      await loadUnifiedStrategy();
    },
    unmount: async () => {
      mounted = false;
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
