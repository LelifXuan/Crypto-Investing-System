// app/static/pages/strategy/index.js
import { api } from "../../core/api.js";
import { appState } from "../../core/state.js";
import {
  escapeHtml, formatNumber, formatDateTime, setRoot,
  statusBanner, loadingState,
} from "../../core/dom.js";
import { normalizeUnifiedStrategy } from "./adapter.js?v=trade-4h-v1";
import { renderScanMatrix, bindScanMatrix } from "./renderScanMatrix.js";
import { renderScanRanked, bindScanRanked } from "./renderScanRanked.js";
import { openDetailPanel } from "./renderDetailPanel.js";
import { mountPageGuide } from "../../ui/pageGuideFab.js";

let mounted = false;
let activeController = null;
let detailLoadController = null; // 2026-08-11: abort previous detail panel requests
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
          <h1>跨品种跨周期机会扫描</h1>
          <p>自动扫描全部品种 · 周线/日线/4H · 综合评分排序</p>
        </div>
        <div class="strategy-v2-actions">
          <button type="button" class="primary-button compact" id="strategy-scan-refresh">刷新扫描</button>
        </div>
      </section>
      <div id="strategy-scan-status"></div>
      <section class="grid cols-2 strategy-scan-grid">
        <section class="card" id="strategy-scan-matrix-section">
          <div class="section-head">
            <div>
              <p class="eyebrow">MATRIX</p>
              <h2>机会矩阵</h2>
              <p class="section-summary">品种 × 级别 一览</p>
            </div>
          </div>
          <div id="strategy-scan-matrix"></div>
        </section>
        <section class="card" id="strategy-scan-ranked-section">
          <div class="section-head">
            <div>
              <p class="eyebrow">RANKED</p>
              <h2>机会排序</h2>
              <p class="section-summary">按综合评分降序，仅显示有方向的信号</p>
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

  const status = document.getElementById("strategy-scan-status");
  // Matrix is the canonical scan result. Deriving the ranked list and banner
  // from the same cells prevents stale cached `ranked` data from contradicting
  // the matrix shown beside it.
  const matrix = Array.isArray(data.matrix) ? data.matrix : [];
  const visibleInstrumentIds = new Set(appState.instruments.map((item) => item.id));
  const visibleMatrix = matrix.filter((item) => visibleInstrumentIds.has(item?.instrument_id));
  const ranked = visibleMatrix
    .filter((item) => ["LONG", "SHORT"].includes(item?.direction))
    .sort((a, b) => Number(b.score || 0) - Number(a.score || 0));
  const oppCount = ranked.length;
  const totalCells = appState.instruments.length * (data.timeframes?.length || 0);
  const sourceLabel = data.cache_meta?.source === "cache" ? "（缓存）" : "";
  // 2026-07-24 v3: per-cell readiness from backend.
  const meta = data.cache_meta || {};
  const cellsReady = visibleMatrix.filter((item) => item.cache_state === "fresh").length;
  const cellsPending = visibleMatrix.filter((item) =>
    ["missing", "warming", "error"].includes(item?.cache_state)
  ).length;

  // 2026-07-24 v3: three-way banner. The previous "当前无明确交易机会"
  // copy was misleading when data was still pending — users thought
  // the system was broken.
  let bannerText;
  let bannerTone;
  if (oppCount > 0) {
    bannerText = `发现 ${oppCount} 个方向信号 / 共扫描 ${totalCells} 个周期组合 ${sourceLabel}`;
    bannerTone = "success";
  } else if (cellsPending > 0) {
    bannerText = `数据补齐中（${cellsReady}/${totalCells} 已就绪），尚无明确交易机会 ${sourceLabel}`;
    bannerTone = "info";
  } else {
    // All cells ready, no opportunities — market is genuinely in transition.
    bannerText = `全部数据已就绪，当前无明确交易方向 ${sourceLabel}`;
    bannerTone = "neutral";
  }

  if (status) {
    status.innerHTML = statusBanner(bannerText, bannerTone);
  }

  const matrixEl = document.getElementById("strategy-scan-matrix");
  if (matrixEl) {
    matrixEl.innerHTML = renderScanMatrix(visibleMatrix, appState.instruments, onSelectOpportunity);
    bindScanMatrix(onSelectOpportunity);
  }

  const rankedEl = document.getElementById("strategy-scan-ranked");
  if (rankedEl) {
    // 2026-07-24 v3: pass hasPending to renderScanRanked so the
    // empty-state copy matches the banner.
    rankedEl.innerHTML = renderScanRanked(ranked, cellsPending > 0);
    bindScanRanked(onSelectOpportunity);
  }
}

function renderScanLoading() {
  const status = document.getElementById("strategy-scan-status");
  if (status) status.innerHTML = statusBanner("正在扫描全部品种×级别...", "info");
  const matrixEl = document.getElementById("strategy-scan-matrix");
  if (matrixEl) matrixEl.innerHTML = loadingState("正在计算各品种各周期策略...");
  const rankedEl = document.getElementById("strategy-scan-ranked");
  if (rankedEl) rankedEl.innerHTML = loadingState("等待扫描完成...");
}

// 2026-07-24: cold-load reliability. Shows a banner distinct from the
// regular loading dots so the user knows the system is warming caches
// (not stuck).
function renderWarmingStatus(message) {
  const text = message || "首次访问，正在后台预热数据缓存，预计 5-10 秒后出结果";
  const status = document.getElementById("strategy-scan-status");
  if (status) status.innerHTML = statusBanner(text, "info");
  const matrixEl = document.getElementById("strategy-scan-matrix");
  if (matrixEl) matrixEl.innerHTML = loadingState("正在预热数据缓存...");
  const rankedEl = document.getElementById("strategy-scan-ranked");
  if (rankedEl) rankedEl.innerHTML = loadingState("等待预热完成...");
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
    const unifiedTimeoutMs = loadOpts.timeoutMs ?? (force ? 60000 : 15000);
    const otherTimeoutMs = loadOpts.timeoutMs ?? 8000;
    const [unifiedResult, monitoringResult, derivativesResult, macroResult] =
      await Promise.allSettled([
        api.getUnifiedStrategy(iid, { force, timeoutMs: unifiedTimeoutMs, signal }),
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
  openDetailPanel(instrumentId, timeframe, loadStrategy, () => {
    // Panel closed — no action needed
  });
}

async function loadScan(force = false, opts = {}) {
  activeController?.abort();
  activeController = new AbortController();
  // 2026-07-24 v2: cold-load reliability. First cold scan can take 60+
  // seconds (rebuilds every cell's unified strategy from scratch).
  // Default 60s frontend timeout trips before the scan completes.
  // Use a 120s timeout on cold scans, drop back to 60s after a
  // successful first response, and retry once on transient failure.
  const timeoutMs = opts.timeoutMs ?? (force ? 60000 : 120000);
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
    // 2026-07-24 v2: one retry for transient failures (network blip /
    // 5xx) before showing the error banner. Bounded — single retry.
    if (!opts._retried && !opts._skipRetry) {
      console.warn("strategy:scan:retrying once after transient failure");
      await new Promise((r) => setTimeout(r, 2000));
      if (!mounted) return null;
      return loadScan(force, { _retried: true, timeoutMs: 120000 });
    }
    const status = document.getElementById("strategy-scan-status");
    if (status) {
      status.innerHTML = statusBanner(
        "扫描失败，请稍后重试",
        "error"
      );
    }
    return null;
  }
}

// 2026-07-24 v2: poll the backend while it returns 'warming'.
// Up to WARMING_RETRY_LIMIT attempts at WARMING_RETRY_DELAY_MS apart.
// Each attempt calls loadScan(); warming responses keep the banner up,
// data responses go through the normal render path, errors show
// the error banner (which loadScan handles internally).
const WARMING_RETRY_LIMIT = 6;
const WARMING_RETRY_DELAY_MS = 5000;

async function pollWhileWarming(attempt = 0) {
  if (!mounted) return;
  if (attempt >= WARMING_RETRY_LIMIT) {
    // Graceful give-up. Distinct from the error banner — this means
    // "the system is just slow, please manually retry", NOT a fault.
    renderWarmingStatus(
      "后台仍在预热数据，请点击「刷新扫描」按钮重试"
    );
    return;
  }
  await new Promise((r) => setTimeout(r, WARMING_RETRY_DELAY_MS));
  if (!mounted) return;
  const result = await loadScan(false, { timeoutMs: 90000 });
  if (!mounted) return;
  if (result && result.__state === "warming") {
    pollWhileWarming(attempt + 1);
    return;
  }
  // loadScan already rendered real data or the error banner.
}

export async function renderStrategy() {
  mounted = true;
  renderScanShell();
  renderWarmingStatus();

  // 2026-07-24: fire-and-forget prewarm so the cold-cache scan doesn't
  // block 60+ seconds before responding. Module-level guard ensures we
  // only fire this once per page module load (avoids precompute queue spam).
  await tryPrewarm();

  document.getElementById("strategy-scan-refresh")?.addEventListener("click", () => {
    renderScanLoading();
    loadScan(true);
  });

  const guideFab = mountPageGuide("ai-strategy");

  // Auto-scan on mount (force=false). If the first scan returns
  // 'warming', kick off the bounded poll loop instead of treating the
  // empty matrix as a real "no opportunities" result.
  const scanPromise = (async () => {
    const first = await loadScan(false);
    if (first && first.__state === "warming") {
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
      guideFab.unmount();
      mounted = false;
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
