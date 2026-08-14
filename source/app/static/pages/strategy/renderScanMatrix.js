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
    <p class="scan-matrix-hint">点击任意单元格查看完整策略推演</p>
  `;
}

function renderCell(item, instrumentId, timeframe) {
  // 2026-07-24 v3: distinguish three cell states.
  // 1. cache_state in {missing, warming, error} → "数据待补" (data still pending)
  // 2. cache_state == "fresh" + direction in {WAIT, NO_TRADE} → "无明确方向"
  //    (data ready, market genuinely in transition)
  // 3. cache_state == "fresh" + direction in {LONG, SHORT} → arrow + confidence
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
  if (!item || item.direction === "WAIT" || item.direction === "NO_TRADE") {
    return `<td class="scan-cell scan-cell-wait">
      <button class="scan-cell-btn" data-instrument="${escapeHtml(instrumentId)}" data-timeframe="${escapeHtml(timeframe)}">
        <small>无明确方向</small>
      </button>
    </td>`;
  }
  const tone = item.direction === "LONG" ? "bullish" : "bearish";
  const arrow = item.direction === "LONG" ? "↑" : "↓";
  return `<td class="scan-cell" data-tone="${tone}">
    <button class="scan-cell-btn" data-instrument="${escapeHtml(instrumentId)}" data-timeframe="${escapeHtml(timeframe)}">
      <strong>${escapeHtml(item.direction_label)} ${arrow}</strong>
      <small>${escapeHtml(String(Math.round(item.confidence)))}%</small>
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
