// app/static/pages/strategy/renderScanRanked.js
import { escapeHtml, formatNumber } from "../../core/dom.js";

const LEVEL_LABELS = { "1w": "战略级", "1d": "战术级", "4h": "执行级" };

/**
 * Render the ranked opportunity list (only items with direction, sorted by score).
 * @param {Array} ranked - ScanItem[] already sorted by score desc
 * @param {Function} onSelect - callback(instrumentId, timeframe)
 */
export function renderScanRanked(ranked, onSelect) {
  if (!ranked.length) {
    return `<div class="data-state data-state-empty">当前无明确交易机会。所有品种×级别均处于等待状态。</div>`;
  }

  const cards = ranked
    .map((item) => {
      const tone = item.direction === "LONG" ? "bullish" : "bearish";
      const arrow = item.direction === "LONG" ? "↑" : "↓";
      const level = LEVEL_LABELS[item.timeframe] || item.timeframe;
      return `
        <article class="card scan-ranked-card" data-tone="${tone}" data-instrument="${escapeHtml(item.instrument_id)}" data-timeframe="${escapeHtml(item.timeframe)}" style="cursor:pointer">
          <div class="scan-ranked-head">
            <div>
              <span class="impact-chip impact-${tone}">${escapeHtml(item.direction_label)} ${arrow}</span>
              <span class="status-chip chip-neutral">${escapeHtml(level)}</span>
            </div>
            <div class="scan-ranked-score">
              <strong>${escapeHtml(String(item.score))}</strong>
              <small>分</small>
            </div>
          </div>
          <p class="scan-ranked-summary">${escapeHtml(item.summary || "暂无摘要")}</p>
          <div class="scan-ranked-meta">
            <span>置信度 ${escapeHtml(String(Math.round(item.confidence)))}%</span>
            <span>盈亏比 ${escapeHtml(formatNumber(item.risk_reward, 2))}:1</span>
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
