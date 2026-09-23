// app/static/pages/strategy/renderScanRanked.js
import { escapeHtml, formatNumber } from "../../core/dom.js";
import { appState } from "../../core/state.js";

const TIMEFRAME_LABELS = { "1w": "周线", "1d": "日线", "4h": "4H" };

function riskRewardText(value) {
  const ratio = Number(value);
  return Number.isFinite(ratio) && ratio > 0
    ? `盈亏比 ${formatNumber(ratio, 2)}:1`
    : "盈亏比待确认";
}

/**
 * Render the ranked opportunity list (only items with direction, sorted by score).
 * @param {Array} ranked - ScanItem[] already sorted by score desc
 * @param {boolean} hasPending - whether any visible matrix cell is still warming
 * @param {object} meta - { scannedAt, servedAt } ISO strings for the scan age label
 */
export function renderScanRanked(ranked, hasPending = false, meta = {}) {
  if (!ranked.length) {
    const emptyMsg = hasPending
      ? "数据补齐中，稍后将有方向出现。"
      : "当前无交易机会，市场处于震荡行情或等待确认阶段。";
    return `<div class="data-state data-state-empty">${escapeHtml(emptyMsg)}</div>`;
  }

  // A cached scan row can be hours old (scan TTL is 2h; the client also
  // caches 60 s). The drawer behind a card always shows the *current*
  // unified snapshot, so a card built long ago must say so — otherwise a
  // 94.6 分 made at 04:47 reads as a live recommendation against a drawer
  // that moved to "方向未确认" by 05:14.
  const ageLabel = scanAgeLabel(meta.scannedAt);
  const cards = ranked
    .map((item) => {
      const tone = item.direction === "LONG" ? "bullish" : "bearish";
      const arrow = item.direction === "LONG" ? "↑" : "↓";
      const timeframe = TIMEFRAME_LABELS[item.timeframe] || item.timeframe;
      const code = item.instrument_code || appState.instruments.find((i) => i.id === item.instrument_id)?.code || item.instrument_id;
      return `
        <article class="card scan-ranked-card" data-tone="${tone}" data-instrument="${escapeHtml(item.instrument_id)}" data-timeframe="${escapeHtml(item.timeframe)}" style="cursor:pointer">
          <div class="scan-ranked-head">
            <div>
              <span class="impact-chip impact-${tone}">${escapeHtml(code)} ${escapeHtml(item.direction_label)} ${arrow}</span>
              <span class="status-chip chip-neutral">${escapeHtml(timeframe)}</span>
            </div>
            <div class="scan-ranked-score">
              <strong>${escapeHtml(String(item.score))}</strong>
              <small>分</small>
            </div>
          </div>
          <p class="scan-ranked-summary">${escapeHtml(item.summary || "暂无摘要")}</p>
          <div class="scan-ranked-meta">
            <span>置信度 ${escapeHtml(String(Math.round(item.confidence)))}%</span>
            <span>${escapeHtml(riskRewardText(item.risk_reward))}</span>
            <span>${escapeHtml(item.leverage_hint === "spot" ? "现货" : item.leverage_hint)}</span>
            ${ageLabel ? `<span title="该评分生成时间，抽屉显示当前快照，两者可能不同代">${escapeHtml(ageLabel)}</span>` : ""}
          </div>
        </article>
      `;
    })
    .join("");

  return `<div class="scan-ranked-list">${cards}</div>`;
}

function scanAgeLabel(scannedAt) {
  if (!scannedAt) return "";
  const scanned = Date.parse(scannedAt);
  if (!Number.isFinite(scanned)) return "";
  const minutes = Math.max(0, Math.round((Date.now() - scanned) / 60000));
  if (minutes < 1) return "刚刚扫描";
  if (minutes < 60) return `${minutes} 分钟前扫描`;
  const hours = Math.floor(minutes / 60);
  const rest = minutes % 60;
  return rest ? `${hours} 小时 ${rest} 分钟前扫描` : `${hours} 小时前扫描`;
}

/**
 * Attach click handlers to ranked cards after rendering.
 */
export function bindScanRanked(onSelect) {
  document.querySelectorAll(".scan-ranked-card").forEach((card) => {
    card.addEventListener("click", () => {
      const instrumentId = card.dataset.instrument;
      const timeframe = card.dataset.timeframe;
      if (instrumentId && timeframe) onSelect(instrumentId, timeframe);
    });
  });
}
