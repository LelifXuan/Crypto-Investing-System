// Shared helpers for formatting trigger/validity timestamps on the AI
// strategy page. The backend now emits absolute ISO timestamps
// (`valid_until_iso`, `next_check_at_iso`) on every decision / plan /
// operation card; we prefer those, and only fall back to the legacy
// relative phrasing when the schema field is absent.

export function formatIsoShort(iso) {
  if (!iso) return "";
  const date = iso instanceof Date ? iso : new Date(iso);
  if (Number.isNaN(date.getTime())) return "";
  const parts = Object.fromEntries(
    new Intl.DateTimeFormat("zh-CN", {
      timeZone: "Asia/Shanghai",
      year: "numeric",
      month: "2-digit",
      day: "2-digit",
      hour: "2-digit",
      minute: "2-digit",
      hourCycle: "h23",
    }).formatToParts(date).map((part) => [part.type, part.value]),
  );
  return `${parts.year}-${parts.month}-${parts.day} ${parts.hour}:${parts.minute} 北京时间`;
}

export function formatLegacyNextCheck(raw) {
  return String(raw || "")
    .replace("next_4h_close", "下一根 4H 收盘")
    .replace("next_1h_close", "下一根 1H 收盘")
    .replace("next_15m_close", "下一根 15M 收盘");
}

/**
 * Render a "下一检查" label from a decision or operation card.
 *
 * Prefers the absolute ISO timestamp emitted by the backend. Falls back to
 * the legacy Chinese string when the timestamp is unavailable.
 *
 * @param {object} source - Decision / operation / unified state object.
 * @param {string} [prefix="下一检查："] - Prefix to attach.
 */
export function formatNextCheck(source, prefix = "下一检查：") {
  if (!source) return "";
  const iso = source.next_check_at_iso || "";
  if (iso) return `${prefix}${formatIsoShort(iso)}`;
  const legacy = formatLegacyNextCheck(source.next_check || "");
  return legacy ? `${prefix}${legacy}` : "";
}

/**
 * Render a "有效期" label from a trade plan or decision.
 *
 * Prefers the absolute ISO timestamp. Falls back to the relative
 * "未来 N 根 TF K线" form when the timestamp is unavailable.
 */
export function formatValidUntil(plan, decision) {
  const iso = (plan && plan.valid_until_iso) || (decision && decision.valid_until_iso) || "";
  if (iso) return `有效期至 ${formatIsoShort(iso)}`;
  const relative = String(
    (plan && plan.valid_until) || (decision && decision.valid_until) || "",
  ).match(/^([^:]+):(\d+)_bars$/);
  if (!relative) return "";
  return `有效期：未来 ${relative[2]} 根 ${relative[1].toUpperCase()} K线`;
}

/**
 * Render a "distance from entry" warning.
 *
 * The backend emits `plan_distance_pct` (signed % from current price to
 * the *closer* edge of the planned entry zone). When the price has
 * drifted far enough away that the conditional limit order cannot
 * realistically trigger, the trigger row should warn the user instead
 * of pretending the plan is still actionable.
 *
 * Returns an empty string when the price is already inside the zone
 * (no warning needed) or when no plan is set.
 */
export function formatEntryDistance(source) {
  if (!source) return "";
  const pct = Number(source.plan_distance_pct);
  if (!Number.isFinite(pct) || pct <= 0) return "";
  const reason = source.plan_stale_reason ? `（${source.plan_stale_reason}）` : "";
  if (pct >= 3) {
    return `距离触发 +${pct.toFixed(2)}% — 主计划已远离入场区，建议等待主趋势重新对齐${reason}`;
  }
  // 1.5% ≤ pct < 3%
  return `距离触发 +${pct.toFixed(2)}%${reason ? `（${source.plan_stale_reason}）` : ""}`;
}

/**
 * Stale severity tag (0 / 50 / 100). Frontend renders this as a chip
 * tone so the table can show "1 warning" or "already stale" pills
 * next to the plan row.
 */
export function staleToneFor(source) {
  if (!source) return "neutral";
  const score = Number(source.plan_stale_score);
  if (score >= 100) return "stale";
  if (score >= 50) return "warning";
  return "neutral";
}
