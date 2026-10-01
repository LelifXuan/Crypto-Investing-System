// app/static/pages/strategy/renderScanMatrix.js
import { escapeHtml } from "../../core/dom.js";

const TIMEFRAME_LABELS = { "1w": "周线", "1d": "日线", "4h": "4H" };

// The scan is a trade surface. A research bias enters it only after the
// complete execution and risk gate passes. Unpublished data stays pending;
// stale last-known-good remains in storage but is not a current opportunity.
const DATA_PENDING_STATES = ["missing", "warming", "error", "unknown"];
const DATA_STALE_STATE = "stale";
const DATA_PENDING_LABEL = "数据准备中";
const DATA_STALE_LABEL = "数据更新中";
const DATA_PENDING_HINT = {
  missing: "该周期快照尚未生成，后台正在补齐",
  warming: "首次生成中，完成后自动更新",
  error: "上次生成失败，后台将重试",
  stale: "快照已过期，后台正在刷新",
  unknown: "数据状态未知，等待后台确认",
};
const DATA_PENDING_TOOLTIP = "数据未就绪时不代表没有机会，仅表示本单元还不可用";

// Gate reasons are internal codes; the cell tooltip shows them in the user's
// words so a rejected cell never reads as an unexplained dash.
const GATE_REASON_LABELS = {
  data_not_fresh: "数据未就绪",
  strategy_degraded: "推演链路降级",
  no_direction: "多周期无方向",
  unified_direction_not_aligned: "跨周期执行方向尚未确认",
  timeframe_not_executable: "该周期仅供结构研判",
  trade_permission_not_granted: "当前没有开仓许可",
  confidence_below_gate: "证据质量未达门槛",
  score_below_gate: "综合评分不足",
  risk_reward_below_gate: "盈亏比不足",
  direction_gap_below_gate: "多空分歧不足",
  insufficient_alignment: "多周期未共振",
  direction_conflict: "周期方向冲突",
  position_cap_restricted: "仓位受限",
  explicit_conflict: "存在显式冲突",
  WAIT_DATA: "执行数据准备中",
  WAIT_LEVELS: "进出场价位待确认",
  WAIT_TRIGGER: "等待入场触发",
  WAIT_RISK: "风险预算不足",
  NO_DIRECTION: "该周期暂无方向",
  BLOCKED: "该周期暂停开仓",
  PRICE_UNAVAILABLE: "市场价格尚未就绪",
  period_decision_missing: "该周期决策正在生成",
  invalid_execution_levels: "执行价位几何关系无效",
};

/**
 * Describe one matrix cell in the single shared vocabulary.
 *
 * Kinds:
 *   "pending"   — payload is missing / warming / error: not a market view
 *   "stale"     — payload is stale: no current trading permission
 *   "qualified" — payload is fresh and passed every execution gate
 *   "idle"      — payload is fresh but has no executable opportunity
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
      clickable: false,
      tooltip: `${pendingHint}${gateText ? `（${gateText}）` : ""}。${DATA_PENDING_TOOLTIP}`,
    };
  }

  const direction = String(item.direction || "").toUpperCase();
  const directional = direction === "LONG" || direction === "SHORT";
  const directionLabel = item.direction_label
    || (direction === "LONG" ? "做多" : direction === "SHORT" ? "做空" : "无机会");

  // An old direction stays in the published snapshot for audit, but the
  // trade matrix does not show it as a current opportunity.
  if (cacheState === DATA_STALE_STATE) {
    return {
      kind: "stale",
      label: DATA_STALE_LABEL,
      direction: "",
      directionKey: "",
      tone: "neutral",
      clickable: false,
      tooltip: `${pendingHint}${gateText ? `（${gateText}）` : ""}。更新完成后重新评估交易许可`,
    };
  }

  // A rejected scan cell remains neutral and absent from the ranked trade
  // list, but its published decision can still be inspected in the drawer.
  if (item.qualified !== true || !directional) {
    return {
      kind: "idle",
      label: "无机会",
      direction: "",
      directionKey: "",
      tone: "neutral",
      clickable: true,
      tooltip: gateText
        ? `本周期未形成完整交易计划：${gateText}。点击查看判断依据`
        : "数据已就绪，本周期没有通过完整交易门禁的机会；点击查看判断依据",
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
    <p class="scan-matrix-hint">每格是一个独立交易级别；已计算的“无机会”也可点开查看判定依据，但不进入交易机会排序。周线用日线、日线用 4H、4H 用 1H 确定执行。</p>
  `;
}

function renderCell(item, instrumentId, timeframe) {
  const state = cellState(item);
  const cls = ["scan-cell"];
  if (state.kind === "pending") cls.push("scan-cell-pending");
  if (state.kind === "stale") cls.push("scan-cell-stale");
  if (state.kind === "idle") cls.push("scan-cell-wait");
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
