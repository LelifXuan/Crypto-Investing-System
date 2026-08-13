// app/static/pages/strategy/renderScanRanked.js
import { escapeHtml, formatNumber } from "../../core/dom.js";

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
 */
export function renderScanRanked(ranked, hasPending = false) {
  if (!ranked.length) {
    const emptyMsg = hasPending
      ? "数据补齐中，稍后将有方向出现。"
      : "当前无交易机会，市场处于震荡行情或等待确认阶段。";
    return `<div class="data-state data-state-empty">${escapeHtml(emptyMsg)}</div>`;
  }

  const cards = ranked
    .map((item) => {
      const tone = item.direction === "LONG" ? "bullish" : "bearish";
      const arrow = item.direction === "LONG" ? "↑" : "↓";
      const timeframe = TIMEFRAME_LABELS[item.timeframe] || item.timeframe;
      return `
        <article class="card scan-ranked-card" data-tone="${tone}" data-instrument="${escapeHtml(item.instrument_id)}" data-timeframe="${escapeHtml(item.timeframe)}" style="cursor:pointer">
          <div class="scan-ranked-head">
            <div>
              <span class="impact-chip impact-${tone}">${escapeHtml(item.direction_label)} ${arrow}</span>
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
          </div>
        </article>
      `;
    })
    .join("");

  return `<div class="scan-ranked-list">${cards}</div>`;
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
