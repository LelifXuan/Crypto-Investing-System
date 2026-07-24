import { escapeHtml, loadingState, errorState, formatNumber, formatDateTime, emptyState } from "../../core/dom.js";
import { renderOverview } from "./renderOverview.js?v=trade-4h-v1";
import { renderExecutionPlan } from "./renderExecutionPlan.js?v=trade-4h-v1";
import { renderDecisionAudit } from "./renderDecisionAudit.js?v=auditable-v1";
import { renderEvidenceStack } from "./renderEvidenceStack.js?v=compact-v3";
import { renderMarketOperation } from "./renderMarketOperation.js?v=decision-text-cleanup";
import { renderRiskPanel } from "./renderRiskPanel.js?v=compact-v3";
import { renderEventWatch } from "./renderEventWatch.js?v=compact-v3";
import { buildDataDegradedCard } from "./adapter.js?v=trade-4h-v1";

const helpers = {
  escapeHtml,
  formatNumber: (v, d) => { const n = Number(v); return Number.isNaN(n) ? "-" : n.toFixed(d ?? 2); },
  formatDateTime: (v) => v || "-",
  emptyState: (msg) => `<div class="data-state data-state-empty">${escapeHtml(msg)}</div>`,
  errorState: (msg) => `<div class="data-state data-state-error">${escapeHtml(msg)}</div>`,
};

/**
 * Open the slide-in detail panel for a specific instrument+timeframe.
 * @param {string} instrumentId
 * @param {string} timeframe
 * @param {Function} loadStrategy - async (instrumentId, timeframe) => normalized model
 * @param {Function} onClose - callback when panel is dismissed
 */
export function openDetailPanel(instrumentId, timeframe, loadStrategy, onClose) {
  // Remove existing panel if any
  const existingPanel = document.getElementById("strategy-detail-panel");
  const existingOverlay = document.getElementById("strategy-detail-overlay");
  if (existingPanel) existingPanel.remove();
  if (existingOverlay) existingOverlay.remove();

  // Create overlay
  const overlay = document.createElement("div");
  overlay.id = "strategy-detail-overlay";
  overlay.className = "strategy-detail-overlay";
  document.body.appendChild(overlay);

  // Create panel
  const panel = document.createElement("aside");
  panel.id = "strategy-detail-panel";
  panel.className = "strategy-detail-panel";
  panel.innerHTML = `
    <div class="strategy-detail-header">
      <button class="strategy-detail-back secondary-button" id="strategy-detail-close">← 返回扫描</button>
      <div class="strategy-detail-breadcrumb">
        <span class="eyebrow">STRATEGY DETAIL</span>
        <h2 id="strategy-detail-title">加载中...</h2>
      </div>
    </div>
    <div class="strategy-detail-body" id="strategy-detail-body">
      ${loadingState("正在加载完整策略推演...")}
    </div>
  `;
  document.body.appendChild(panel);

  // Animate in (next frame after DOM attach)
  requestAnimationFrame(() => {
    panel.classList.add("is-open");
    overlay.classList.add("is-visible");
  });

  // Close handler
  const close = () => {
    panel.classList.remove("is-open");
    overlay.classList.remove("is-visible");
    // Remove after transition (300ms)
    setTimeout(() => {
      panel.remove();
      overlay.remove();
      document.removeEventListener("keydown", escHandler);
      if (onClose) onClose();
    }, 300);
  };

  overlay.addEventListener("click", close);
  document.getElementById("strategy-detail-close")?.addEventListener("click", close);

  function escHandler(e) {
    if (e.key === "Escape") close();
  }
  document.addEventListener("keydown", escHandler);

  // Load and render strategy
  loadStrategy(instrumentId, timeframe)
    .then((model) => {
      const title = document.getElementById("strategy-detail-title");
      const body = document.getElementById("strategy-detail-body");
      if (!body) return;

      const instCode = model.instrument_code || instrumentId;
      const dirLabel = model.trade_decision?.side || model.trade_decision?.direction || "";
      if (title) title.textContent = `${instCode} · ${timeframe} · ${dirLabel}`;

      body.innerHTML = `
        ${renderOverview(model, helpers)}
        ${renderExecutionPlan(model, helpers)}
        ${renderDecisionAudit(model, helpers)}
        ${renderEvidenceStack(model, helpers)}
        ${renderMarketOperation(model, helpers)}
        ${renderRiskPanel(model, helpers)}
        ${renderEventWatch(model, helpers)}
        ${buildDataDegradedCard(model)}
      `;
    })
    .catch((err) => {
      const body = document.getElementById("strategy-detail-body");
      if (body) body.innerHTML = errorState(`策略加载失败：${escapeHtml(err.message || String(err))}`);
    });
}
