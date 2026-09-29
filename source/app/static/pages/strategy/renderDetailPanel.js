import { escapeHtml, loadingState, errorState, formatNumber, formatDateTime, emptyState } from "../../core/dom.js";
import { renderEventWatch } from "./renderEventWatch.js?v=compact-v3";
import { renderTimeframeFocus } from "./renderTimeframeFocus.js?v=period-v1";
import { renderPeriodOpportunity } from "./renderPeriodOpportunity.js?v=period-v1";
import { buildDataDegradedCard } from "./adapter.js?v=trade-4h-v1";
import { registerOverlay, LAYER, isTopOverlay } from "../../ui/overlayCoordinator.js";

const helpers = {
  escapeHtml,
  formatNumber: (v, d) => { const n = Number(v); return Number.isNaN(n) ? "-" : n.toFixed(d ?? 2); },
  // The drawer used to re-stub this as a pass-through, so the overview printed
  // raw ISO strings ("2026-09-22T09:20:45.583117+00:00") for 生成时间 /
  // 策略时间 / 价格时间. core/dom.js owns the user-facing time policy
  // (Beijing, minute precision, no zone suffix) — use it.
  formatDateTime,
  emptyState: (msg) => `<div class="data-state data-state-empty">${escapeHtml(msg)}</div>`,
  errorState: (msg) => `<div class="data-state data-state-error">${escapeHtml(msg)}</div>`,
};

let dismissActiveDetailPanel = null;

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
  if (model?.selected_timeframe) return Boolean(model.opportunity_decisions?.[model.selected_timeframe]);
  const snapshotId = String(model.market_decision_snapshot?.snapshot_id || "");
  const hasSnapshot = Boolean(snapshotId && snapshotId !== "-" && !snapshotId.startsWith("missing:"));
  const hasTimeframes = Array.isArray(model.timeframe_stack) && model.timeframe_stack.length > 0;
  const hasCoverage = Array.isArray(model.signal_coverage) && model.signal_coverage.length > 0;
  const hasCrossValidation = Array.isArray(model.cross_validation?.matrix)
    && model.cross_validation.matrix.length > 0;
  return hasSnapshot || hasTimeframes || hasCoverage || hasCrossValidation;
}

// Two different situations both render as "the plan is not actionable", and the
// drawer has to tell them apart:
//
//   1. The snapshot itself is missing / warming / expired. The read path
//      enqueues precompute work, so re-reading a few seconds later returns the
//      new snapshot. Waiting is the right move.
//   2. The snapshot is fresh, but the live mark price has left the plan's
//      levels behind (recompute_status=enqueued from the price guard). The
//      plan's levels are structural, so a rebuild reproduces the same
//      geometry: the answer will not change by waiting. Polling here is what
//      kept "正在重新推演" on screen for minutes with nothing behind it.
function detailRebuildPending(model) {
  if (!model) return true;
  const cacheState = String(model.cache_state || "").toLowerCase();
  if (["missing", "warming", "error", "stale"].includes(cacheState)) return true;
  return !cacheState && !hasPublishedDetail(model);
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
  const focusOrigin = document.activeElement;
  let layer = null;
  // Close through the registered lifecycle so listeners from the previous
  // drawer cannot survive a rapid switch between matrix cells.
  dismissActiveDetailPanel?.();
  const existingPanel = document.getElementById("strategy-detail-panel");
  const existingOverlay = document.getElementById("strategy-detail-overlay");
  existingPanel?.remove();
  existingOverlay?.remove();

  // Create overlay
  const overlay = document.createElement("div");
  overlay.id = "strategy-detail-overlay";
  overlay.className = "strategy-detail-overlay";
  document.body.appendChild(overlay);

  // Create panel
  const panel = document.createElement("aside");
  panel.id = "strategy-detail-panel";
  panel.className = "strategy-detail-panel";
  panel.setAttribute("role", "dialog");
  panel.setAttribute("aria-modal", "true");
  panel.setAttribute("aria-labelledby", "strategy-detail-title");
  panel.innerHTML = `
    <div class="strategy-detail-header">
      <button class="strategy-detail-back secondary-button" id="strategy-detail-close">返回扫描</button>
      <div class="strategy-detail-breadcrumb">
        <span class="eyebrow">STRATEGY DETAIL</span>
        <h2 id="strategy-detail-title">加载中...</h2>
      </div>
      <div class="strategy-detail-header-actions">
        <span class="strategy-detail-refresh" id="strategy-detail-refresh" role="status" hidden></span>
        <button type="button" class="secondary-button" id="strategy-detail-rebuild">重新推演</button>
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

  // 2026-09-04 (ui-audit P1#2): aria-modal 的对话框必须实现焦点生命周期
  // (§10) — 打开后焦点进入面板,Tab/Shift+Tab 循环约束在面板内,关闭时
  // 由 close() 恢复 focusOrigin。
  const backBtn = panel.querySelector("#strategy-detail-close");
  (backBtn || panel).focus({ preventScroll: true });

  function tabHandler(e) {
    if (!isTopOverlay(panel)) return;
    if (e.key !== "Tab") return;
    const focusables = panel.querySelectorAll(
      'button, [href], input, select, textarea, [tabindex]:not([tabindex="-1"])'
    );
    const visible = [...focusables].filter((el) => !el.disabled && el.offsetParent !== null);
    if (!visible.length) return;
    const first = visible[0];
    const last = visible[visible.length - 1];
    const active = document.activeElement;
    if (e.shiftKey && (active === first || !panel.contains(active))) {
      e.preventDefault();
      last.focus();
    } else if (!e.shiftKey && (active === last || !panel.contains(active))) {
      e.preventDefault();
      first.focus();
    }
  }
  document.addEventListener("keydown", tabHandler);

  // 2026-07-25: Track panel mounted + latest model so async rebuild
  // responses don't fight with a stale close timer.
  let mountedAt = Date.now();
  let lastModel = null;
  let forcePending = false;
  let refreshTimer = null;
  let refreshAttempts = 0;

  // A stale/unpublished snapshot resolves on its own once the queued precompute
  // finishes, so the panel re-reads instead of leaving the user to guess
  // whether anything is happening. Bounded: after the attempts are spent the
  // panel stops polling and points at the manual rebuild.
  const REFRESH_INTERVAL_MS = 5000;
  const REFRESH_MAX_ATTEMPTS = 9;

  function setRefreshNote(text) {
    const note = document.getElementById("strategy-detail-refresh");
    if (!note) return;
    note.textContent = text || "";
    note.hidden = !text;
  }

  function stopRefreshPoll() {
    if (refreshTimer) {
      clearTimeout(refreshTimer);
      refreshTimer = null;
    }
  }

  function modelKey(model) {
    return [
      model?.snapshot_key || model?.generated_at || "",
      model?.cache_state || "",
      model?.recompute_status || "",
    ].join("|");
  }

  function scheduleRefreshPoll() {
    stopRefreshPoll();
    if (forcePending || !detailRebuildPending(lastModel)) return;
    if (!document.getElementById("strategy-detail-body")?.isConnected) return;
    if (refreshAttempts >= REFRESH_MAX_ATTEMPTS) {
      setRefreshNote("后台仍在重算，可点击「重新推演」");
      return;
    }
    if (refreshAttempts === 0) {
      // Say it before the first tick: a panel that shows a stale plan with no
      // hint of activity is what made the user wait minutes on nothing.
      setRefreshNote("数据尚未就绪，本面板会自动刷新");
    }
    refreshTimer = setTimeout(() => {
      refreshTimer = null;
      void refreshDetail();
    }, REFRESH_INTERVAL_MS);
  }

  async function refreshDetail() {
    const previousKey = modelKey(lastModel);
    refreshAttempts += 1;
    setRefreshNote(`数据更新中，本面板会自动刷新（${refreshAttempts}/${REFRESH_MAX_ATTEMPTS}）`);
    let next = null;
    try {
      // bypassCache: the client keeps a 30 s copy of /strategy/unified. Without
      // it this poll would re-read that copy, see no change, and give up while
      // the fresh snapshot was already published server-side.
      next = await loadStrategy(instrumentId, timeframe, { bypassCache: true });
    } catch (err) {
      if (err?.name === "AbortError") return;
      console.warn("strategy:detail:refresh:error", err);
    }
    const body = document.getElementById("strategy-detail-body");
    if (!body?.isConnected) return;
    if (!next) {
      scheduleRefreshPoll();
      return;
    }
    if (modelKey(next) !== previousKey) {
      applyModel(next);
    } else {
      lastModel = next;
    }
    if (!detailRebuildPending(lastModel)) {
      // The snapshot arrived — say so once, then get out of the way. Scoped to
      // this panel: a reload during the 4 s must not clear the new drawer's note.
      setRefreshNote("已更新为最新快照");
      setTimeout(() => {
        if (panel.isConnected) setRefreshNote("");
      }, 4000);
      return;
    }
    scheduleRefreshPoll();
  }

  function applyModel(model) {
    lastModel = model;
    renderBody(model);
    if (!detailRebuildPending(model)) {
      refreshAttempts = 0;
      if (!forcePending) setRefreshNote("");
    }
    scheduleRefreshPoll();
  }

  function renderBody(model) {
    const title = document.getElementById("strategy-detail-title");
    const body = document.getElementById("strategy-detail-body");
    if (!body) return;

    const instCode = model.instrument_code || instrumentId;
    const opportunity = model.opportunity_decisions?.[timeframe];
    const pending = !hasPublishedDetail(model) || !opportunity;
    // The matrix and the selected-period section both use this node. The
    // unified trade decision below it answers a different question: whether
    // the complete cross-period gate permits an order.
    const cellNode = (model.timeframe_stack || []).find(
      (node) => String(node?.timeframe || "") === String(timeframe || "")
    );
    const cellDir = String(opportunity?.side || cellNode?.direction || "").toUpperCase();
    const cellDirLabel = cellDir === "LONG" ? "做多" : cellDir === "SHORT" ? "做空" : "";
    const dirLabel = pending
      ? "数据准备中"
      : cellDirLabel || "等待确认";
    if (title) {
      title.textContent = `${instCode} · ${timeframe} · ${dirLabel}`;
      title.removeAttribute("title");
    }

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
      renderPeriodOpportunity(opportunity, model, helpers),
      renderTimeframeFocus(model, timeframe, helpers),
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
    stopRefreshPoll();
    refreshAttempts = 0;
    const body = document.getElementById("strategy-detail-body");
    const btn = body?.querySelector("[data-strategy-rebuild]");
    const headerBtn = document.getElementById("strategy-detail-rebuild");
    if (btn) {
      btn.disabled = true;
      btn.textContent = "正在推演...";
    }
    if (headerBtn) {
      headerBtn.disabled = true;
      headerBtn.textContent = "正在推演...";
    }
    setRefreshNote("正在基于最新数据重新推演...");
    try {
      const next = await loadStrategy(instrumentId, timeframe, {
        force: true,
        timeoutMs: 60000,
      });
      if (!body?.isConnected) return; // panel was closed during the wait
      forcePending = false;
      applyModel(next);
    } catch (err) {
      forcePending = false;
      if (btn) {
        btn.disabled = false;
        btn.textContent = "立即重建本单元";
      }
      setRefreshNote("重新推演失败，请稍后重试");
      console.error("strategy:rebuild:error", err);
    } finally {
      if (headerBtn?.isConnected) {
        headerBtn.disabled = false;
        headerBtn.textContent = "重新推演";
      }
    }
  }

  // The drawer needs a way out of every state, including the terminal one:
  // a fresh snapshot whose plan levels the live price has already left behind
  // has no queued work and no automatic recovery, so the user must be able to
  // ask for a re-derivation on demand.
  document.getElementById("strategy-detail-rebuild")?.addEventListener("click", () => {
    void triggerRebuild();
  });

  // Close handler
  const close = () => {
    if (!panel.isConnected && !overlay.isConnected) return;
    stopRefreshPoll();
    panel.classList.remove("is-open");
    overlay.classList.remove("is-visible");
    // Detach immediately after the close intent. The visual exit is brief,
    // but leaving a full-screen invisible overlay mounted blocks the next
    // matrix click during rapid research workflows.
    panel.remove();
    overlay.remove();
    layer?.destroy(); layer = null;
    document.removeEventListener("keydown", escHandler);
    document.removeEventListener("keydown", tabHandler);
    document.removeEventListener("pointerdown", outsidePointerHandler, true);
    if (dismissActiveDetailPanel === close) dismissActiveDetailPanel = null;
    if (onClose) onClose();
    if (focusOrigin?.isConnected) focusOrigin.focus({ preventScroll: true });
  };

  overlay.addEventListener("click", close);
  document.getElementById("strategy-detail-close")?.addEventListener("click", close);

  // The sidebar and topbar intentionally sit above the scrim. Capture the
  // pointer before their handlers run so every click outside the drawer
  // dismisses it without swallowing the user's intended navigation click.
  function outsidePointerHandler(event) {
    if (!isTopOverlay(panel)) return;
    if (!panel.contains(event.target)) close();
  }
  document.addEventListener("pointerdown", outsidePointerHandler, true);

  function escHandler(e) {
    if (!isTopOverlay(panel)) return;
    if (e.key === "Escape") close();
  }
  document.addEventListener("keydown", escHandler);
  dismissActiveDetailPanel = close;
  layer = registerOverlay({ element: panel, priority: LAYER.dialog, modal: true, close });

  // Load and render strategy
  loadStrategy(instrumentId, timeframe)
    .then((model) => {
      if (!document.getElementById("strategy-detail-body")?.isConnected) return;
      applyModel(model);
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
  return close;
}
