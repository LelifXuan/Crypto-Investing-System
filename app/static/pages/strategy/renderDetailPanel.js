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

// 2026-07-25: when the unified strategy payload is degraded (status
// 'degraded', degraded_components non-empty), the user used to see a
// stack of empty-state cards ("暂无周期证据 / 数据不足 / 状态待确认")
// and not realise anything was actually missing. This banner surfaces
// the situation explicitly: what's missing, why, and what they can do.
//
// `onForce` is the user-triggered "立即重建" handler. The panel attaches
// it to a button. We don't render the button if the caller didn't supply
// the hook (kept for testing/SSR safety).
function renderDegradedBanner(model) {
  const components = Array.isArray(model.degraded_components) && model.degraded_components.length
    ? model.degraded_components
    : ["strategy_unified_cache_missing"];
  const limitations = Array.isArray(model.refresh_limitations) ? model.refresh_limitations : [];
  const instruction = model.unified_state?.instruction || "策略数据正在重新计算中。";
  const reasonLabel = {
    strategy_unified_cache_missing: "统一策略缓存尚未生成",
    structure: "形态结构数据缺失",
    cross_horizon: "跨周期合成数据缺失",
    risk_gate: "风险门禁未启用",
    trade_plan: "执行计划合成失败",
    evidence: "证据链生成失败",
    narrative: "叙事生成失败",
    price_structure: "价格结构维度缺失",
  };
  const reasons = components.map((c) => reasonLabel[c] || c).join("；");
  const refreshState = model.refresh_state || "missing";
  const prewarmStatus = model.prewarm_status || "enqueued";
  const limitHtml = limitations.length
    ? `<p class="strategy-degraded-banner-meta">${escapeHtml(limitations.join(" · "))}</p>`
    : "";
  return `
    <aside class="strategy-degraded-banner card" data-tone="warn" role="status">
      <div class="strategy-degraded-banner-head">
        <span class="eyebrow">数据预热中</span>
        <strong>当前多周期推演链路尚未就绪</strong>
      </div>
      <p class="strategy-degraded-banner-body">${escapeHtml(instruction)}</p>
      <ul class="strategy-degraded-banner-reasons">
        <li><span>原因</span><strong>${escapeHtml(reasons)}</strong></li>
        <li><span>缓存状态</span><strong>${escapeHtml(refreshState)}</strong></li>
        <li><span>预热进度</span><strong>${escapeHtml(prewarmStatus)}</strong></li>
      </ul>
      ${limitHtml}
      <div class="strategy-degraded-banner-actions">
        <button type="button" class="primary-button" data-strategy-rebuild>立即重建本单元</button>
        <small>首次访问或后台异常时会触发；重建完成后数据自动刷新。</small>
      </div>
    </aside>
  `;
}

function hasPublishedDetail(model) {
  const snapshotId = String(model.market_decision_snapshot?.snapshot_id || "");
  const hasSnapshot = Boolean(snapshotId && snapshotId !== "-" && !snapshotId.startsWith("missing:"));
  const hasTimeframes = Array.isArray(model.timeframe_stack) && model.timeframe_stack.length > 0;
  const hasCoverage = Array.isArray(model.signal_coverage) && model.signal_coverage.length > 0;
  const hasCrossValidation = Array.isArray(model.cross_validation?.matrix)
    && model.cross_validation.matrix.length > 0;
  return hasSnapshot || hasTimeframes || hasCoverage || hasCrossValidation;
}

function renderPendingDetail(model) {
  const components = Array.isArray(model.degraded_components) && model.degraded_components.length
    ? model.degraded_components
    : ["strategy_unified_cache_missing"];
  const reasonLabel = {
    strategy_unified_cache_missing: "统一策略快照尚未发布",
    structure: "形态结构数据未就绪",
    cross_horizon: "跨周期合成未就绪",
    risk_gate: "风险门禁尚未生成",
    trade_plan: "执行计划尚未生成",
    evidence: "证据链尚未生成",
    narrative: "研究摘要尚未生成",
    price_structure: "价格结构尚未生成",
  };
  const reason = components.map((key) => reasonLabel[key] || key).join("、");
  const refreshState = String(model.refresh_state || "missing").toLowerCase();
  const prewarmStatus = String(model.prewarm_status || "enqueued").toLowerCase();
  const queued = ["enqueued", "queued", "running", "requested"].includes(prewarmStatus)
    || ["enqueued", "requested", "warming", "stale_revalidating"].includes(refreshState);
  const buildLabel = queued ? "后台任务已排队" : "等待后台任务";
  const buildTone = queued ? "is-active" : "";

  return `
    <section class="strategy-degraded-banner strategy-detail-pending card" role="status">
      <div class="strategy-detail-pending-copy">
        <p class="eyebrow">DETAIL NOT PUBLISHED</p>
        <h2>策略详情尚未形成</h2>
        <p>扫描层只负责发现候选。当前单元格还没有可审计的统一策略快照，因此暂不展示方向、风险门禁、执行计划和跨维度结论。</p>
      </div>
      <ol class="strategy-detail-build-flow" aria-label="策略详情生成进度">
        <li class="is-active"><span>01</span><div><strong>候选已选定</strong><small>标的与周期已确认</small></div></li>
        <li class="${buildTone}"><span>02</span><div><strong>${escapeHtml(buildLabel)}</strong><small>${escapeHtml(reason)}</small></div></li>
        <li><span>03</span><div><strong>发布可审计快照</strong><small>完成后才展示完整策略详情</small></div></li>
      </ol>
      <div class="strategy-detail-pending-actions">
        <button type="button" class="primary-button" data-strategy-rebuild>立即生成详情</button>
        <p>生成期间可返回扫描页继续浏览；后台任务不会阻塞页面切换。</p>
      </div>
    </section>
  `;
}

/**
 * Open the slide-in detail panel for a specific instrument+timeframe.
 * @param {string} instrumentId
 * @param {string} timeframe
 * @param {Function} loadStrategy - async (instrumentId, timeframe, options?) => normalized model
 *        When the user clicks "立即重建", the panel calls
 *        `loadStrategy(iid, tf, { force: true, timeoutMs: 60000 })`.
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
      <button class="strategy-detail-back secondary-button" id="strategy-detail-close">返回扫描</button>
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

  // 2026-07-25: Track panel mounted + latest model so async rebuild
  // responses don't fight with a stale close timer.
  let mountedAt = Date.now();
  let lastModel = null;
  let forcePending = false;

  function renderBody(model) {
    const title = document.getElementById("strategy-detail-title");
    const body = document.getElementById("strategy-detail-body");
    if (!body) return;

    const instCode = model.instrument_code || instrumentId;
    const td = model.trade_decision || {};
    const pending = !hasPublishedDetail(model);
    const dirLabel = pending
      ? "数据构建中"
      : td.side === "LONG" ? "做多" : td.side === "SHORT" ? "做空" : "等待确认";
    if (title) title.textContent = `${instCode} · ${timeframe} · ${dirLabel}`;

    // A cold-cache response is system availability, not a market conclusion.
    // Do not manufacture a 0.00 price, "high risk", empty evidence tables and
    // six placeholder market cards from an unpublished snapshot.
    if (pending) {
      body.innerHTML = renderPendingDetail(model);
      const rebuildBtn = body.querySelector("[data-strategy-rebuild]");
      if (rebuildBtn) {
        rebuildBtn.disabled = forcePending;
        rebuildBtn.addEventListener("click", () => triggerRebuild(), { once: true });
      }
      return;
    }

    // 2026-07-25: bring back the full multi-horizon reasoning chain.
    // Previously the panel short-circuited on side === NONE and
    // showed only a single stub card, which hid the execution plan
    // / decision audit / evidence stack / market operation / risk
    // panel / event watch from the user. The engine still produces
    // horizon views + evidence_trace + market_operation + risk_alerts
    // even when there is no direction, so we must surface those so
    // the user can see why the engine concluded there is no edge.
    const sections = [
      renderOverview(model, helpers),
      renderExecutionPlan(model, helpers),
      renderDecisionAudit(model, helpers),
      renderEvidenceStack(model, helpers),
      renderMarketOperation(model, helpers),
      renderRiskPanel(model, helpers),
      renderEventWatch(model, helpers),
      buildDataDegradedCard(model),
    ];

    // 2026-07-25: when the payload is degraded (cold cache / prewarm
    // pending / cross-horizon synthesis failed), prepend a high-contrast
    // "数据预热中" banner that surfaces what's missing and offers a
    // manual rebuild button. Without this, the 7 renderers below all
    // render their empty-state copy and the user reads them as
    // "system says nothing" instead of "system is still working".
    if (model.degraded) {
      sections.unshift(renderDegradedBanner(model));
    }

    body.innerHTML = sections.filter(Boolean).join("");

    // Wire the rebuild button (only present when degraded banner was rendered).
    const rebuildBtn = body.querySelector("[data-strategy-rebuild]");
    if (rebuildBtn) {
      rebuildBtn.disabled = forcePending;
      rebuildBtn.addEventListener("click", () => triggerRebuild(), { once: true });
    }
  }

  async function triggerRebuild() {
    if (forcePending) return;
    forcePending = true;
    const body = document.getElementById("strategy-detail-body");
    const btn = body?.querySelector("[data-strategy-rebuild]");
    if (btn) {
      btn.disabled = true;
      btn.textContent = "正在重建...";
    }
    try {
      const next = await loadStrategy(instrumentId, timeframe, {
        force: true,
        timeoutMs: 60000,
      });
      if (!body?.isConnected) return; // panel was closed during the wait
      lastModel = next;
      renderBody(next);
      forcePending = false;
    } catch (err) {
      forcePending = false;
      if (btn) {
        btn.disabled = false;
        btn.textContent = "立即重建本单元";
      }
      console.error("strategy:rebuild:error", err);
    }
  }

  // Close handler
  const close = () => {
    if (!panel.isConnected && !overlay.isConnected) return;
    panel.classList.remove("is-open");
    overlay.classList.remove("is-visible");
    // Detach immediately after the close intent. The visual exit is brief,
    // but leaving a full-screen invisible overlay mounted blocks the next
    // matrix click during rapid research workflows.
    panel.remove();
    overlay.remove();
    document.removeEventListener("keydown", escHandler);
    if (onClose) onClose();
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
      if (!document.getElementById("strategy-detail-body")?.isConnected) return;
      lastModel = model;
      renderBody(model);
    })
    .catch((err) => {
      // 2026-08-11: AbortError means a new panel was opened before this
      // one finished — silently ignore, the new panel handles its own render.
      if (err?.name === "AbortError") return;
      const body = document.getElementById("strategy-detail-body");
      if (body) body.innerHTML = errorState(`策略加载失败：${escapeHtml(err.message || String(err))}`);
    });

  // (mountedAt currently used for diagnostics; reserved for future deprecation)
  void mountedAt;
  void lastModel;
}
