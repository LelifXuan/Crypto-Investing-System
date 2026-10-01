// app/static/pages/strategy/renderScanRanked.js
import { escapeHtml, formatNumber } from "../../core/dom.js";
import { appState } from "../../core/state.js";

const TIMEFRAME_LABELS = { "1w": "周线", "1d": "日线", "4h": "4H" };

function riskRewardText(value, label = "交易级别盈亏比") {
  const ratio = Number(value);
  return Number.isFinite(ratio) && ratio > 0
    ? `${label} ${formatNumber(ratio, 2)}:1`
    : label === "交易级别盈亏比" ? "盈亏比待确认" : `${label}待确认`;
}

function formatLevelsPrice(value) {
  const number = Number(value);
  if (!Number.isFinite(number)) return "—";
  return number.toLocaleString("en-US", { maximumFractionDigits: 2 });
}

// The card's job is to answer "where do I enter, where am I wrong, where do
// I take profit" at a glance. The old summary quoted the bundle validator's
// verdict line ("CONTEXT_ALIGNED_SHORT：当前策略状态为…"), which spends the
// user's attention on process chatter instead of actionable numbers.
// Point levels come from the tactical plan matching the cell direction
// (backend _cell_execution_levels); missing levels hide the line.
function levelsLine(item) {
  // Only the selected period's validated execution plan may display levels.
  if (item?.qualified !== true) return "";
  const zone = Array.isArray(item?.entry_zone) ? item.entry_zone.map(Number).filter(Number.isFinite) : [];
  if (!zone.length) return "";
  if (item?.stop_loss == null) return "";
  const stop = Number(item.stop_loss);
  if (!Number.isFinite(stop)
    || (item.direction === "LONG" && stop >= Math.min(...zone))
    || (item.direction === "SHORT" && stop <= Math.max(...zone))) return "";
  const tp1 = Number(item?.take_profit_1);
  const horizonTarget = Number(item?.horizon_target);
  const zoneText = zone.map(formatLevelsPrice).join(" – ");
  const stopText = Number.isFinite(stop) ? formatLevelsPrice(stop) : "—";
  // A missing TP1 is not a zero target: hide it instead of printing 止盈 0.
  const tp1Text = Number.isFinite(tp1) && tp1 !== 0 ? formatLevelsPrice(tp1) : "—";
  const dirWord = item?.direction === "LONG" ? "做多" : item?.direction === "SHORT" ? "做空" : "";
  const prefix = dirWord ? `${dirWord} ` : "";
  const tradeTf = TIMEFRAME_LABELS[item.timeframe] || item.timeframe;
  const executionTf = { "1w": "日线", "1d": "4H", "4h": "1H" }[item.timeframe] || "入场周期";
  const horizonText = Number.isFinite(horizonTarget) && horizonTarget > 0 ? formatLevelsPrice(horizonTarget) : "—";
  return `${prefix}${zoneText}｜止损 ${stopText}｜${executionTf}首目标 ${tp1Text}｜${tradeTf}目标 ${horizonText}`;
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
      ? "部分数据仍在后台补齐；当前没有通过完整交易门禁的机会。"
      : "当前没有通过完整交易门禁的机会。";
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
      const levels = levelsLine(item);
      return `
        <article class="card scan-ranked-card" data-tone="${tone}" data-instrument="${escapeHtml(item.instrument_id)}" data-timeframe="${escapeHtml(item.timeframe)}" style="cursor:pointer">
          <div class="scan-ranked-head">
            <div>
              <span class="impact-chip impact-${tone}">${escapeHtml(code)} ${escapeHtml(item.direction_label)} ${arrow}</span>
              <span class="status-chip chip-neutral">${escapeHtml(timeframe)}</span>
              ${item.qualified === true ? "" : '<span class="status-chip chip-neutral">待确认</span>'}
            </div>
            <div class="scan-ranked-score">
              <strong>${escapeHtml(String(item.score))}</strong>
              <small>分</small>
            </div>
          </div>
          ${levels ? `<p class="scan-ranked-levels">${escapeHtml(levels)}</p>` : ""}
          <div class="scan-ranked-meta">
            <span title="证据质量：衡量数据新鲜度、证据覆盖与信号一致性，不代表预测胜率或盈利概率">证据质量 ${escapeHtml(String(Math.round(item.confidence)))}/100</span>
            <span>${escapeHtml(riskRewardText(item.risk_reward))}</span>
            ${item.qualified && item.first_risk_reward ? `<span>${escapeHtml(riskRewardText(item.first_risk_reward, "首目标盈亏比"))}</span>` : ""}
            ${item.qualified && item.expected_move_pct ? `<span>预期波动 ${escapeHtml(formatNumber(item.expected_move_pct, 2))}%</span>` : ""}
            <span title="模型杠杆参考，尚未计入个人账户资金、已有持仓和组合风险预算">模型杠杆 ${escapeHtml(item.leverage_hint === "spot" ? "现货" : item.leverage_hint)}</span>
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
