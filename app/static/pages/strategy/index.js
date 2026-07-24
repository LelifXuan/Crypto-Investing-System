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
let scanData = null; // cached ScanResult for resume

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
          <button type="button" class="primary-button" id="strategy-scan-refresh">刷新扫描</button>
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
  const oppCount = data.ranked?.length || 0;
  const totalCells = (data.instruments?.length || 0) * (data.timeframes?.length || 0);
  const sourceLabel = data.cache_meta?.source === "cache" ? "（缓存）" : "";

  if (status) {
    status.innerHTML = statusBanner(
      oppCount > 0
        ? `发现 ${oppCount} 个交易机会 / 共扫描 ${totalCells} 个级别组合 ${sourceLabel}`
        : `当前无明确交易机会 ${sourceLabel}`,
      oppCount > 0 ? "success" : "neutral"
    );
  }

  const matrixEl = document.getElementById("strategy-scan-matrix");
  if (matrixEl) {
    matrixEl.innerHTML = renderScanMatrix(data.matrix || [], appState.instruments, onSelectOpportunity);
    bindScanMatrix(onSelectOpportunity);
  }

  const rankedEl = document.getElementById("strategy-scan-ranked");
  if (rankedEl) {
    rankedEl.innerHTML = renderScanRanked(data.ranked || [], onSelectOpportunity);
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

function onSelectOpportunity(instrumentId, timeframe) {
  const loadStrategy = async (iid, tf) => {
    const payload = await api.getUnifiedStrategy(iid, { force: false, timeoutMs: 20000 });
    const code = appState.instruments.find((i) => i.id === iid)?.code || iid;
    const model = normalizeUnifiedStrategy(payload, {});
    model.instrument_code = code;
    model.data_access = { unified: payload, monitoring: null, derivatives: null, macro: null };
    model.data_access_failures = { unified: null, monitoring: null, derivatives: null, macro: null };
    return model;
  };
  openDetailPanel(instrumentId, timeframe, loadStrategy, () => {
    // Panel closed — no action needed
  });
}

async function loadScan(force = false) {
  activeController?.abort();
  activeController = new AbortController();
  try {
    const data = await api.getStrategyScan({ force, signal: activeController.signal, timeoutMs: 60000 });
    if (!mounted) return;
    renderScanResults(data);
  } catch (err) {
    if (err?.name === "AbortError") return;
    console.error("strategy:scan:error", err);
    const status = document.getElementById("strategy-scan-status");
    if (status) status.innerHTML = statusBanner("扫描失败，请稍后重试", "error");
  }
}

export async function renderStrategy() {
  mounted = true;
  renderScanShell();
  renderScanLoading();

  document.getElementById("strategy-scan-refresh")?.addEventListener("click", () => {
    renderScanLoading();
    loadScan(true);
  });

  const guideFab = mountPageGuide("ai-strategy");

  // Auto-scan on mount
  const scanPromise = loadScan(false);

  return {
    mount: async () => {
      if (scanData) renderScanResults(scanData);
      else await scanPromise;
    },
    unmount: async () => {
      guideFab.unmount();
      mounted = false;
      activeController?.abort();
      activeController = null;
    },
    pause: async () => {},
    resume: async () => {
      if (mounted && !scanData) await loadScan(false);
    },
  };
}

export default renderStrategy;
