// app/static/pages/strategy/renderScanMatrix.js
import { escapeHtml } from "../../core/dom.js";

const TIMEFRAME_LABELS = { "1w": "周线", "1d": "日线", "4h": "4H" };

// One label per meaning, for the whole matrix.
//
// A cell may only state a market conclusion when the payload behind it is
// usable. Missing / warming / error / stale payloads are system availability,
// not "no opportunity" (AGENTS.md §九.1) — they all share the single label
// below, so the matrix never reads as two different things at once. The
// per-state reason stays in the cell tooltip instead of adding a second
// visible word.
const DATA_PENDING_STATES = ["missing", "warming", "error", "stale", "unknown"];
// Only these three mean "there is no report to open". A stale snapshot serves
// last-known-good and an unknown state is worth inspecting, so both stay
// clickable — the drawer owns the per-state explanation.
const DATA_CLOSED_STATES = ["missing", "warming", "error"];
const DATA_PENDING_LABEL = "数据准备中";
const DATA_PENDING_HINT = {
  missing: "该周期快照尚未生成，后台正在补齐",
  warming: "首次生成中，完成后自动更新",
  error: "上次生成失败，后台将重试",
  stale: "快照已过期，正在重新推演",
  unknown: "数据状态未知，等待后台确认",
};
const DATA_PENDING_TOOLTIP = "数据未就绪时不代表没有机会，仅表示本单元还不可用";

// Gate reasons are internal codes; the cell tooltip shows them in the user's
// words so a rejected cell never reads as an unexplained dash.
const GATE_REASON_LABELS = {
  data_not_fresh: "数据未就绪",
  strategy_degraded: "推演链路降级",
  no_direction: "多周期无方向",
  confidence_below_gate: "置信度不足",
  score_below_gate: "综合评分不足",
  risk_reward_below_gate: "盈亏比不足",
  direction_gap_below_gate: "多空分歧不足",
  insufficient_alignment: "多周期未共振",
  direction_conflict: "周期方向冲突",
  position_cap_restricted: "仓位受限",
  explicit_conflict: "存在显式冲突",
};

/**
 * Describe one matrix cell in the single shared vocabulary.
 *
 * Kinds:
 *   "pending"   — payload is missing / warming / error / stale: not a market view
 *   "qualified" — payload is fresh and passed every execution gate
 *   "candidate" — payload is fresh with a direction, but the gate rejected it
 *   "idle"      — payload is fresh and there is no direction at all
 *
 * @param {object|undefined} item - ScanItem for this instrument + timeframe
 * @returns {{kind: string, label: string, direction: string, tone: string,
 *            clickable: boolean, tooltip: string}}
 */
export function cellState(item) {
  const cacheState = String(item?.cache_state || "").toLowerCase();
  const pendingHint = DATA_PENDING_HINT[cacheState] || DATA_PENDING_HINT.unknown;
  const gateReasons = Array.isArray(item?.qualification_reasons)
    ? item.qualification_reasons
    : [];
  const gateText = gateReasons
    .map((reason) => GATE_REASON_LABELS[reason] || String(reason || ""))
    .filter(Boolean)
    .join(" · ");

  if (!item || DATA_PENDING_STATES.includes(cacheState)) {
    return {
      kind: "pending",
      label: DATA_PENDING_LABEL,
      direction: "",
      directionKey: "",
      tone: "neutral",
      clickable: !DATA_CLOSED_STATES.includes(cacheState),
      tooltip: `${pendingHint}${gateText ? `（${gateText}）` : ""}。${DATA_PENDING_TOOLTIP}`,
    };
  }

  const direction = String(item.direction || "").toUpperCase();
  const directional = direction === "LONG" || direction === "SHORT";
  const directionLabel = item.direction_label
    || (direction === "LONG" ? "做多" : direction === "SHORT" ? "做空" : "等待确认");

  // The gate decides promotion only. The direction is reported either way,
  // because the detail drawer shows the same direction for the same cell —
  // hiding it here made the matrix say "等待确认" while the drawer said 做空.
  if (item.qualified !== true || !directional) {
    return {
      kind: directional ? "candidate" : "idle",
      label: "等待确认",
      direction: directional ? directionLabel : "",
      directionKey: directional ? direction : "",
      tone: "neutral",
      clickable: true,
      tooltip: gateText
        ? `未通过门禁：${gateText}`
        : directional
          ? "方向已出现，但执行条件尚未确认"
          : "数据已就绪，当前周期没有可执行方向",
    };
  }
  return {
    kind: "qualified",
    label: "",
    direction: directionLabel,
    directionKey: direction,
    tone: direction === "LONG" ? "bullish" : "bearish",
    clickable: true,
    tooltip: item.summary || "已通过严格门禁",
  };
}

const DIRECTION_ICON_PATH = {
  bullish: "M6 15V5m0 0-4 4m4-4 4 4",
  bearish: "M6 3v10m0 0-4-4m4 4 4-4",
};
const DIRECTION_ICON_BY_KEY = { LONG: DIRECTION_ICON_PATH.bullish, SHORT: DIRECTION_ICON_PATH.bearish };

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
  const state = cellState(item);
  const cls = ["scan-cell"];
  if (state.kind === "pending") cls.push("scan-cell-pending");
  if (state.kind === "idle") cls.push("scan-cell-wait");
  if (state.kind === "candidate") cls.push("scan-cell-wait", "scan-cell-unqualified");
  const attrs = state.clickable
    ? `data-instrument="${escapeHtml(instrumentId)}" data-timeframe="${escapeHtml(timeframe)}"`
    : 'disabled aria-disabled="true"';
  const iconPath = DIRECTION_ICON_BY_KEY[state.directionKey];
  const strong = state.direction
    ? `<strong>
        ${escapeHtml(state.direction)}
        <svg class="scan-cell-direction-icon" viewBox="0 0 12 18" aria-hidden="true">
          <path d="${iconPath || DIRECTION_ICON_PATH.bullish}" />
        </svg>
      </strong>`
    : '<strong aria-hidden="true">—</strong>';
  const small = state.label ? `<small>${escapeHtml(state.label)}</small>` : "";
  return `<td class="${cls.join(" ")}" data-tone="${escapeHtml(state.tone)}">
    <button class="scan-cell-btn" type="button" title="${escapeHtml(state.tooltip)}" ${attrs}>
      ${strong}
      ${small}
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
