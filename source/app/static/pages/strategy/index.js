// app/static/pages/strategy/index.js
import { api } from "../../core/api.js";
import { appState } from "../../core/state.js";
import {
  escapeHtml, formatNumber, formatDateTime, setRoot,
  errorState, loadingState,
} from "../../core/dom.js";
import { normalizeUnifiedStrategy } from "./adapter.js?v=trade-4h-v1";
import { renderScanMatrix, bindScanMatrix } from "./renderScanMatrix.js?v=opportunity-matrix-v2";
import { renderScanRanked, bindScanRanked } from "./renderScanRanked.js";
import { openDetailPanel } from "./renderDetailPanel.js";
import { mountPageGuide } from "../../ui/pageGuideFab.js";

let mounted = false;
let activeController = null;
let detailLoadController = null; // 2026-08-11: abort previous detail panel requests
let activeDetailPanelClose = null;
let scanData = null; // cached ScanResult for resume
let prewarmed = false; // 2026-07-24: only fire prewarm once per page module load
// 2026-08-11: debounce matrix cell clicks to prevent rapid-fire panel opens
let strategyDebounceTimer = null;

function renderScanShell() {
  setRoot(`
    <section class="strategy-v2-page strategy-scan-page">
      <section class="strategy-v2-toolbar card">
        <div>
          <p class="eyebrow">OPPORTUNITY SCANNER</p>
          <h2 class="page-display-title">跨品种跨周期机会扫描</h2>
          <p>自动扫描全部品种 · 周线/日线/4H · 综合评分排序</p>
        </div>
        <div class="strategy-v2-actions">
          <button type="button" class="primary-button compact" id="strategy-scan-refresh">刷新扫描</button>
        </div>
      </section>
      <section class="grid cols-2 strategy-scan-grid">
        <section class="card" id="strategy-scan-matrix-section">
          <div class="section-head">
            <div>
              <p class="eyebrow">MATRIX</p>
              <h2>机会矩阵</h2>
              <p class="section-summary">仅显示通过严格门禁的高确定性机会</p>
            </div>
          </div>
          <div id="strategy-scan-matrix"></div>
        </section>
        <section class="card" id="strategy-scan-ranked-section">
          <div class="section-head">
            <div>
              <p class="eyebrow">RANKED</p>
              <h2>机会排序</h2>
              <p class="section-summary">候选信号按综合评分降序，保留置信度</p>
            </div>
          </div>
          <div id="strategy-scan-ranked"></div>
        </section>
      </section>
    </section>
  `);
}

function renderScanResults(data) {
  scanData = data;

  // Status bar removed — strategy page no longer shows a persistent status/banner.
  // Matrix is the canonical scan result. Deriving the ranked list and banner
  // from the same cells prevents stale cached `ranked` data from contradicting
  // the matrix shown beside it.
  const matrix = Array.isArray(data.matrix) ? data.matrix : [];
  const visibleInstrumentIds = new Set(appState.instruments.map((item) => item.id));
  const visibleMatrix = matrix.filter((item) => visibleInstrumentIds.has(item?.instrument_id));
  const ranked = visibleMatrix
    .filter((item) => (
      item?.cache_state === "fresh" && ["LONG", "SHORT"].includes(item?.direction)
    ))
    .sort((a, b) => Number(b.score || 0) - Number(a.score || 0));
  const qualified = visibleMatrix.filter((item) => item?.qualified === true);
  const oppCount = qualified.length;
  const candidateCount = ranked.length;
  const totalCells = appState.instruments.length * (data.timeframes?.length || 0);
  const sourceLabel = data.cache_meta?.source === "cache" ? "（缓存）" : "";
  // 2026-07-24 v3: per-cell readiness from backend.
  const meta = data.cache_meta || {};
  const cellsReady = visibleMatrix.filter((item) => item.cache_state === "fresh").length;
  const cellsPending = visibleMatrix.filter((item) =>
    ["missing", "warming", "error"].includes(item?.cache_state)
  ).length;

  const matrixEl = document.getElementById("strategy-scan-matrix");
  if (matrixEl) {
    matrixEl.innerHTML = renderScanMatrix(visibleMatrix, appState.instruments, onSelectOpportunity);
    bindScanMatrix(onSelectOpportunity);
  }

  const rankedEl = document.getElementById("strategy-scan-ranked");
  if (rankedEl) {
    // 2026-07-24 v3: pass hasPending to renderScanRanked so the
    // empty-state copy matches the banner.
    // 2026-09-23: pass the scan age through so a cached matrix built hours
    // ago is labelled as such — a ranked card must not read as a live
    // recommendation when the drawer behind it already moved on.
    rankedEl.innerHTML = renderScanRanked(ranked, cellsPending > 0, {
      scannedAt: data.scanned_at,
      servedAt: data.cache_meta?.served_at,
    });
    bindScanRanked(onSelectOpportunity);
  }
}

function renderScanLoading(message) {
  const matrixEl = document.getElementById("strategy-scan-matrix");
  if (matrixEl) matrixEl.innerHTML = loadingState(message || "正在计算各品种各周期策略...");
  const rankedEl = document.getElementById("strategy-scan-ranked");
  if (rankedEl) rankedEl.innerHTML = loadingState("等待扫描完成...");
}

// The scan panels are the only live surface on this page (the status rail was
// removed on purpose), so every terminal state has to be written into them.
// Writing the failure into `#strategy-scan-status` — an element that does not
// exist — left the loading dots up forever, which reads as "still working"
// after several minutes of nothing.
function renderScanError(message) {
  const matrixEl = document.getElementById("strategy-scan-matrix");
  if (matrixEl) matrixEl.innerHTML = errorState(message);
  const rankedEl = document.getElementById("strategy-scan-ranked");
  if (rankedEl) rankedEl.innerHTML = `<div class="data-state data-state-empty">点击「刷新扫描」可重试。</div>`;
}

// 2026-07-24: cold-load reliability. Shows a banner distinct from the
// regular loading dots so the user knows the system is warming caches
// (not stuck).
function renderWarmingStatus(message) {
  renderScanLoading("正在预热数据缓存...");
}

// 2026-07-24: fire-and-forget prewarm so cold cache isn't blocking the
// first scan for 60+ s. Module-level guard via `prewarmed` flag.
// 2026-08-11: prewarm ALL instruments (not just BTC) so the matrix
// doesn't show "无明确方向" for every cell on cold start.
async function tryPrewarm() {
  if (prewarmed) return;
  prewarmed = true;
  const instruments = appState.instruments || [];
  // Prewarm first 3 instruments in parallel (fire-and-forget)
  const prewarmTargets = instruments.slice(0, 3);
  if (prewarmTargets.length === 0) {
    prewarmTargets.push({ id: "btc-usdt-perp" });
  }
  for (const inst of prewarmTargets) {
    const instId = inst.id || inst.code || "btc-usdt-perp";
    api.prewarmStrategy(instId, { timeoutMs: 5000 }).catch((err) => {
      console.warn("strategy:prewarm:noop", instId, err?.message || err);
    });
  }
}

function onSelectOpportunity(instrumentId, timeframe) {
  // 2026-08-11: debounce rapid cell clicks — only open panel for the
  // final selection, not every intermediate click.
  if (strategyDebounceTimer) {
    clearTimeout(strategyDebounceTimer);
    strategyDebounceTimer = null;
  }
  strategyDebounceTimer = setTimeout(() => {
    strategyDebounceTimer = null;
    _openStrategyDetail(instrumentId, timeframe);
  }, 250);
}

function _openStrategyDetail(instrumentId, timeframe) {
  // 2026-07-25: loadStrategy now accepts an options bag so the detail
  // panel's "立即重建" button can pass { force: true, timeoutMs: 60000 }.
  // We forward force to all four backend calls so the panel-level
  // rebuild avoids serving the cached stale-degraded payload that
  // triggered the rebuild in the first place.
  // 2026-08-11: AbortController cancels previous detail panel requests
  // when a new cell is clicked before the old one finishes.
  const loadStrategy = async (iid, tf, loadOpts = {}) => {
    // Abort any in-flight detail request from a previous cell click
    detailLoadController?.abort();
    detailLoadController = new AbortController();
    const signal = detailLoadController.signal;

    const force = loadOpts.force ?? false;
    // `bypassCache` re-reads the server snapshot without rebuilding it. A
    // plain unforced read is served from the 30 s client-side response cache
    // (see api.getUnifiedStrategy), so the detail panel's auto-refresh has to
    // ask for a real round trip — otherwise it re-reads its own stale copy and
    // can never observe the snapshot it is waiting for.
    const bypassCache = loadOpts.bypassCache ?? false;
    const unifiedTimeoutMs = loadOpts.timeoutMs ?? (force ? 60000 : 15000);
    const otherTimeoutMs = loadOpts.timeoutMs ?? 8000;
    const [unifiedResult, monitoringResult, derivativesResult, macroResult] =
      await Promise.allSettled([
        api.getUnifiedStrategy(iid, { force, bypassCache, timeoutMs: unifiedTimeoutMs, signal }),
        api.getMonitoringDashboard(iid, tf, { force, timeoutMs: otherTimeoutMs, signal }),
        api.getBtcDerivativesDashboard({}, { force, timeoutMs: otherTimeoutMs, signal }),
        api.getMacroOverview({ force, timeoutMs: otherTimeoutMs, signal }),
      ]);

    const code = appState.instruments.find((i) => i.id === iid)?.code || iid;
    const payload = unifiedResult.status === "fulfilled" ? unifiedResult.value : null;
    const model = normalizeUnifiedStrategy(payload || {}, {});
    model.instrument_code = code;

    model.data_access = {
      unified: payload,
      monitoring: monitoringResult.status === "fulfilled" ? monitoringResult.value : null,
      derivatives: derivativesResult.status === "fulfilled" ? derivativesResult.value : null,
      macro: macroResult.status === "fulfilled" ? macroResult.value : null,
    };
    model.data_access_failures = {
      unified: unifiedResult.status === "rejected" ? (unifiedResult.reason?.message || String(unifiedResult.reason)) : null,
      monitoring: monitoringResult.status === "rejected" ? (monitoringResult.reason?.message || String(monitoringResult.reason)) : null,
      derivatives: derivativesResult.status === "rejected" ? (derivativesResult.reason?.message || String(derivativesResult.reason)) : null,
      macro: macroResult.status === "rejected" ? (macroResult.reason?.message || String(macroResult.reason)) : null,
    };
    return model;
  };
  activeDetailPanelClose = openDetailPanel(instrumentId, timeframe, loadStrategy, () => {
    activeDetailPanelClose = null;
    detailLoadController?.abort();
    detailLoadController = null;
    // Panel closed — no action needed
  });
}

// A forced scan rebuilds every instrument's unified strategy serially
// (SQLite keeps one writer), measured at ~84 s for a 13-instrument
// universe. The old 60 s budget aborted the request mid-rebuild and the
// retry paid the whole cost again — a refresh could never succeed on the
// first attempt, and the matrix stayed on its loading dots throughout.
const FORCE_SCAN_TIMEOUT_MS = 240000;
const CACHED_SCAN_TIMEOUT_MS = 120000;

async function loadScan(force = false, opts = {}) {
  activeController?.abort();
  activeController = new AbortController();
  const timeoutMs = opts.timeoutMs ?? (force ? FORCE_SCAN_TIMEOUT_MS : CACHED_SCAN_TIMEOUT_MS);
  try {
    const data = await api.getStrategyScan({
      force,
      signal: activeController.signal,
      timeoutMs,
    });
    if (!mounted) return data;
    // 2026-07-24 v2: Backend signals "warming" via cache_meta.source
    // when cache is empty + force=false. The warming response has
    // empty matrix / empty ranked — we must NOT treat that as
    // "no opportunities found". Return a tagged object so
    // pollWhileWarming() can keep the warming banner up and retry.
    if (!force && data?.cache_meta?.source === "warming") {
      return { __state: "warming", payload: data };
    }
    renderScanResults(data);
    return data;
  } catch (err) {
    if (err?.name === "AbortError") return null;
    console.error("strategy:scan:error", err);
    const timedOut = err?.name === "TimeoutError";
    // 2026-07-24 v2: one retry for transient failures (network blip /
    // 5xx) before showing the error state. Bounded — single retry.
    if (!opts._retried && !opts._skipRetry) {
      console.warn("strategy:scan:retrying once after transient failure");
      renderScanLoading("扫描超时，正在重试...");
      await new Promise((r) => setTimeout(r, 2000));
      if (!mounted) return null;
      return loadScan(force, { _retried: true, timeoutMs: opts.timeoutMs });
    }
    renderScanError(
      timedOut
        ? `扫描超时（已等待 ${Math.round(timeoutMs / 1000)} 秒）。后台重算量较大时会超过这个时间。`
        : "扫描失败，请点击「刷新扫描」重试。"
    );
    return null;
  }
}

// 2026-07-24 v2: poll the backend while it returns 'warming'.
// Up to WARMING_RETRY_LIMIT attempts at WARMING_RETRY_DELAY_MS apart.
// Each attempt calls loadScan(); warming responses keep the warming state
// up, data responses go through the normal render path, errors render the
// error state (which loadScan handles internally).
const WARMING_RETRY_LIMIT = 6;
const WARMING_RETRY_DELAY_MS = 5000;

async function pollWhileWarming(attempt = 0) {
  if (!mounted) return;
  if (attempt >= WARMING_RETRY_LIMIT) {
    // Graceful give-up. Distinct from the error state — this means
    // "the system is just slow, please manually retry", NOT a fault.
    renderScanError(
      "后台仍在预热数据（已等待约 30 秒仍未完成）。请点击「刷新扫描」重试。"
    );
    return;
  }
  await new Promise((r) => setTimeout(r, WARMING_RETRY_DELAY_MS));
  if (!mounted) return;
  const result = await loadScan(false, { timeoutMs: 90000, _skipRetry: true });
  if (!mounted) return;
  if (result && result.__state === "warming") {
    pollWhileWarming(attempt + 1);
    return;
  }
  // loadScan already rendered real data or the error state.
}

export async function renderStrategy({ commands } = {}) {
  mounted = true;
  renderScanShell();
  const commandDisposers = [];
  const commandLifetime = new AbortController();
  let refreshBusy = false;

  // 2026-08-17: delayed warming placeholder. When the scan cache is
  // fresh the backend responds in <500ms and we should render results
  // immediately — flashing a warming banner for 200ms then replacing it
  // looks like a glitch. We show warming only if data hasn't arrived
  // after WARMING_DELAY_MS. This keeps the warming signal for genuine
  // cold loads without the flicker on cache hits.
  const WARMING_DELAY_MS = 500;
  let warmingVisible = false;
  let warmingTimer = null;

  function showWarmingDelayed() {
    warmingTimer = setTimeout(() => {
      if (!mounted) return;
      warmingVisible = true;
      renderWarmingStatus();
    }, WARMING_DELAY_MS);
  }

  showWarmingDelayed();

  // 2026-07-24: fire-and-forget prewarm so the cold-cache scan doesn't
  // block 60+ seconds before responding. Module-level guard ensures we
  // only fire this once per page module load (avoids precompute queue spam).
  await tryPrewarm();

  async function refreshScan() {
    if (!mounted || commandLifetime.signal.aborted || refreshBusy) return;
    refreshBusy = true;
    const button = document.getElementById("strategy-scan-refresh");
    if (button) button.disabled = true;
    // Manual refresh always shows loading state — user expects feedback.
    // A forced scan rebuilds every cell serially (~1-2 min for the full
    // universe), so say so instead of showing an unbounded spinner.
    if (warmingTimer) { clearTimeout(warmingTimer); warmingTimer = null; }
    warmingVisible = true;
    if (button) button.textContent = "正在重算...";
    renderScanLoading("正在重新推演全部品种×周期，约需 1-2 分钟...");
    try { await loadScan(true); }
    finally {
      refreshBusy = false;
      if (!commandLifetime.signal.aborted && button?.isConnected) {
        button.disabled = false;
        button.textContent = "刷新扫描";
      }
    }
  }
  document.getElementById("strategy-scan-refresh")?.addEventListener("click", refreshScan, { signal: commandLifetime.signal });
  const focusSection = (id) => () => {
    const element = document.getElementById(id);
    if (element) { element.tabIndex = -1; element.focus({ preventScroll: false }); }
  };
  for (const command of [
    { id: "strategy:refresh-scan", label: "刷新策略扫描", enabled: () => !refreshBusy, run: refreshScan },
    { id: "strategy:focus-matrix", label: "聚焦策略矩阵", run: focusSection("strategy-scan-matrix-section") },
    { id: "strategy:focus-ranked", label: "聚焦策略排名", run: focusSection("strategy-scan-ranked-section") },
    { id: "strategy:close-detail", label: "关闭策略详情", enabled: () => Boolean(activeDetailPanelClose), run: () => activeDetailPanelClose?.() },
  ]) if (commands) commandDisposers.push(commands.register(command));

  const guideFab = mountPageGuide("ai-strategy");

  // Auto-scan on mount (force=false). If the first scan returns
  // 'warming', kick off the bounded poll loop instead of treating the
  // empty matrix as a real "no opportunities" result.
  //
  // Live refresh (2026-09-23): the backend rebuilds the scan row inline
  // whenever its unified inputs moved (source=live), so a plain re-read
  // converges without a 50 s force. Re-read every 60 s while mounted:
  // silent when nothing changed (same scanned_at), seamless re-render
  // when the backend rebuilt. visibilitychange pauses the timer; unmount
  // clears it (AbortController cancels the in-flight read).
  const LIVE_REFRESH_MS = 60000;
  let liveRefreshTimer = null;
  function scheduleLiveRefresh() {
    if (liveRefreshTimer) clearTimeout(liveRefreshTimer);
    liveRefreshTimer = setTimeout(async () => {
      liveRefreshTimer = null;
      if (!mounted || document.hidden) { scheduleLiveRefresh(); return; }
      try {
        const data = await api.getStrategyScan({ signal: commandLifetime.signal, timeoutMs: 30000 });
        if (!mounted || !data || data?.cache_meta?.source === "warming") { scheduleLiveRefresh(); return; }
        if (data.scanned_at && data.scanned_at !== scanData?.scanned_at) {
          renderScanResults(data);
        }
      } catch (err) {
        if (err?.name !== "AbortError") console.warn("strategy:scan:live-refresh", err?.message || err);
      }
      scheduleLiveRefresh();
    }, LIVE_REFRESH_MS);
  }
  document.addEventListener("visibilitychange", () => {
    if (!document.hidden && mounted && !liveRefreshTimer) scheduleLiveRefresh();
  }, { signal: commandLifetime.signal });
  scheduleLiveRefresh();
  const scanPromise = (async () => {
    const first = await loadScan(false);
    // Data arrived — cancel the delayed-warming timer so the banner
    // never flashes if it hasn't appeared yet.
    if (warmingTimer) { clearTimeout(warmingTimer); warmingTimer = null; }
    if (first && first.__state === "warming") {
      // Genuine cold load — show warming now (data path will replace it
      // once the poll loop gets a real result).
      warmingVisible = true;
      renderWarmingStatus(first.cache_meta?.message);
      pollWhileWarming(0);
    }
    return first;
  })();

  return {
    mount: async () => {
      if (scanData) renderScanResults(scanData);
      else {
        // The SPA considers mount() part of the navigation critical path.
        // Waiting for a cold strategy scan here keeps main.js in its
        // `spaNavigationInFlight` state for up to 120 seconds, so every nav
        // click is merely queued and the user appears trapped on this page.
        // The stable warming shell is already mounted above; let the scan
        // continue in the background and let unmount() abort it immediately
        // when the user leaves.
        void scanPromise;
      }
    },
    unmount: async () => {
      commandLifetime.abort();
      commandDisposers.forEach((dispose) => dispose());
      guideFab.unmount();
      mounted = false;
      if (warmingTimer) { clearTimeout(warmingTimer); warmingTimer = null; }
      if (liveRefreshTimer) { clearTimeout(liveRefreshTimer); liveRefreshTimer = null; }
      activeDetailPanelClose?.();
      activeDetailPanelClose = null;
      if (strategyDebounceTimer) { clearTimeout(strategyDebounceTimer); strategyDebounceTimer = null; }
      activeController?.abort();
      activeController = null;
      detailLoadController?.abort();
      detailLoadController = null;
    },
    pause: async () => {},
    resume: async () => {
      if (mounted && !scanData) await loadScan(false);
    },
  };
}

export default renderStrategy;
