// app/static/pages/strategy/renderScanMatrix.js
import { escapeHtml } from "../../core/dom.js";

const TIMEFRAME_LABELS = { "1w": "周线", "1d": "日线", "4h": "4H" };

/**
 * Render the instrument × timeframe opportunity matrix.
 * @param {Array} matrix - ScanItem[] from /strategy/scan
 * @param {Array} instruments - appState.instruments array
 * @param {Function} onSelect - callback(instrumentId, timeframe) when a cell is clicked
 */
export function renderScanMatrix(matrix, instruments, onSelect) {
  const rows = instruments
    .map((inst) => {
      const cells = ["1w", "1d", "4h"]
        .map((tf) => {
          const item = matrix.find(
            (m) => (
              m.instrument_id === inst.id || m.instrument_code === inst.code
            ) && m.timeframe === tf
          );
          return renderCell(item, inst.id, tf);
        })
        .join("");
      return `<tr>
        <td class="scan-matrix-code">${escapeHtml(inst.code)}</td>
        ${cells}
      </tr>`;
    })
    .join("");

  return `
    <div class="table-wrap">
      <table class="scan-matrix-table">
        <thead>
          <tr>
            <th>品种</th>
            <th>${TIMEFRAME_LABELS["1w"]}</th>
            <th>${TIMEFRAME_LABELS["1d"]}</th>
            <th>${TIMEFRAME_LABELS["4h"]}</th>
          </tr>
        </thead>
        <tbody>${rows}</tbody>
      </table>
    </div>
    <p class="scan-matrix-hint">矩阵仅标记通过严格门禁的机会；点击其他单元格可查看候选推演</p>
  `;
}

function renderCell(item, instrumentId, timeframe) {
  // The matrix is a promotion surface, not a confidence report.  Directional
  // candidates that did not pass the backend's strict gate remain available
  // for drill-down, but are not painted as opportunities here.
  if (
    item &&
    typeof item.cache_state === "string" &&
    ["missing", "warming", "error"].includes(item.cache_state)
  ) {
    return `<td class="scan-cell scan-cell-pending">
      <button class="scan-cell-btn" type="button" disabled aria-disabled="true">
        <small>数据构建中</small>
      </button>
    </td>`;
  }
  if (!item || item.qualified !== true) {
    return `<td class="scan-cell scan-cell-wait scan-cell-unqualified">
      <button class="scan-cell-btn" data-instrument="${escapeHtml(instrumentId)}" data-timeframe="${escapeHtml(timeframe)}">
        <strong aria-hidden="true">—</strong>
        <small>等待确认</small>
      </button>
    </td>`;
  }
  const tone = item.direction === "LONG" ? "bullish" : "bearish";
  const iconPath = item.direction === "LONG"
    ? "M6 15V5m0 0-4 4m4-4 4 4"
    : "M6 3v10m0 0-4-4m4 4 4-4";
  return `<td class="scan-cell" data-tone="${tone}">
    <button class="scan-cell-btn" data-instrument="${escapeHtml(instrumentId)}" data-timeframe="${escapeHtml(timeframe)}">
      <strong>
        ${escapeHtml(item.direction_label)}
        <svg class="scan-cell-direction-icon" viewBox="0 0 12 18" aria-hidden="true">
          <path d="${iconPath}" />
        </svg>
      </strong>
    </button>
  </td>`;
}

/**
 * Attach click handlers to matrix cells after rendering.
 */
export function bindScanMatrix(onSelect) {
  document.querySelectorAll(".scan-cell-btn").forEach((btn) => {
    btn.addEventListener("click", () => {
      const instrumentId = btn.dataset.instrument;
      const timeframe = btn.dataset.timeframe;
      if (instrumentId && timeframe) onSelect(instrumentId, timeframe);
    });
  });
}
