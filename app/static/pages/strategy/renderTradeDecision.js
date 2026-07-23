import { directionLabel, permissionLabel } from "./adapter.js";
import { formatNextCheck } from "./formatHelpers.js?v=iso-v1";

const STATUS_LABELS = {
  READY: "可以执行",
  WAIT_SETUP: "等待 4H 形态",
  WAIT_TRIGGER: "等待 1H 触发",
  BLOCKED: "当前不可执行",
  NO_DIRECTION: "方向未确认",
};

function formatPrice(value) {
  const number = Number(value);
  return Number.isFinite(number) ? number.toLocaleString("en-US", { maximumFractionDigits: 2 }) : "-";
}

function formatZone(values) {
  if (!Array.isArray(values) || !values.length) return "暂未生成";
  return values.map(formatPrice).join(" – ");
}

export function renderTradeDecision(model, helpers) {
  const { escapeHtml } = helpers;
  const decision = model.trade_decision || {};
  const primary = decision.primary_reason?.message || "等待统一交易判断。";
  const secondary = Array.isArray(decision.secondary_reasons) ? decision.secondary_reasons : [];
  const rr = decision.risk_reward || {};
  const tp1Ratio = Number(rr.tp1_ratio ?? rr.value);
  const tp2Ratio = Number(rr.tp2_ratio);
  const minimum = Number(rr.minimum_required ?? rr.threshold);
  const rrText = rr.valid === false
    ? `计划价位无效（${rr.invalid_reason || "价位不完整"}）`
    : Number.isFinite(tp1Ratio)
      ? `TP1 ${tp1Ratio.toFixed(2)}${Number.isFinite(tp2Ratio) ? ` / TP2 ${tp2Ratio.toFixed(2)}` : ""} / 门槛 ${Number.isFinite(minimum) ? minimum.toFixed(2) : "-"}`
      : "计划价位不完整";
  return `
    <section class="strategy-v2-section strategy-trade-decision card" data-status="${escapeHtml(decision.status || "NO_DIRECTION")}">
      <div class="section-heading">
        <div>
          <p class="eyebrow">CURRENT TRADE DECISION</p>
          <h2>${escapeHtml(STATUS_LABELS[decision.status] || "等待判断")}</h2>
        </div>
        <p>${escapeHtml(`${directionLabel(decision.side)} · ${permissionLabel(decision.permission)}`)}</p>
      </div>
      <div class="strategy-v2-grid">
        <article class="strategy-v2-card">
          <p class="eyebrow">主因</p>
          <h3>${escapeHtml(primary)}</h3>
          <p>${escapeHtml(decision.entry_condition || "等待价格行为形成可验证的入场条件。")}</p>
        </article>
        <article class="strategy-v2-card">
          <p class="eyebrow">执行链</p>
          <h3>${escapeHtml(`${decision.direction_source || "1d"} 定向 → ${decision.setup_timeframe || "4h"} 形态 → ${decision.trigger_timeframe || "1h"} 触发`)}</h3>
          <p>${escapeHtml(`${decision.filter_timeframe || "15m"} 仅负责执行过滤；${formatNextCheck(decision)}`)}</p>
        </article>
        <article class="strategy-v2-card">
          <p class="eyebrow">价格与盈亏比</p>
          <h3>${escapeHtml(formatZone(decision.entry_zone))}</h3>
          <p>${escapeHtml(`失效位 ${formatPrice(decision.invalidation)} · 盈亏比 ${rrText}`)}</p>
        </article>
      </div>
      ${secondary.length ? `
        <details class="strategy-decision-reasons">
          <summary>其他限制因素（${secondary.length}）</summary>
          <ul>${secondary.map((item) => `<li>${escapeHtml(item.message || item.code || "-")}</li>`).join("")}</ul>
        </details>
      ` : ""}
    </section>
  `;
}
