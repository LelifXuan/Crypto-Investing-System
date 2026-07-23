import {
  decisionStatusLabel,
  directionLabel,
  permissionLabel,
  planLabel,
} from "./adapter.js?v=trade-4h-v1";
import {
  formatEntryDistance,
  formatNextCheck,
  formatValidUntil,
  staleToneFor,
} from "./formatHelpers.js?v=iso-v2-stale";

function formatPrice(value) {
  if (value === null || value === undefined || value === "") return "-";
  const number = Number(value);
  return Number.isFinite(number)
    ? number.toLocaleString("en-US", { minimumFractionDigits: 2, maximumFractionDigits: 2 })
    : "-";
}

function formatZone(values) {
  if (!Array.isArray(values) || !values.length) return "待生成";
  return values.map(formatPrice).join(" – ");
}

function formatTargets(items) {
  if (!Array.isArray(items) || !items.length) return "-";
  return items.map((item) => `${item.label || "目标"} ${formatPrice(item.price)}`).join(" / ");
}

function formatLeverage(plan, decision) {
  const recommended = Number(plan.recommended_leverage ?? decision.recommended_leverage ?? 0);
  const maximum = Number(plan.max_leverage ?? decision.max_leverage ?? 0);
  const planned = Number(plan.planned_leverage ?? decision.planned_leverage ?? 0);
  if (recommended <= 0 && planned > 0) return `条件满足后 ${planned.toFixed(0)}×`;
  if (recommended <= 0 || maximum <= 0) return "暂不使用";
  return `建议 ${recommended.toFixed(0)}× / 上限 ${maximum.toFixed(0)}×`;
}

function planRiskReward(plan, decision) {
  const payload = Object.keys(plan.risk_reward || {}).length
    ? plan.risk_reward
    : decision.risk_reward || {};
  if (payload.valid === false) return "计划价位无效";
  const raw = payload.tp1_ratio ?? payload.legacy_rr ?? payload.value;
  if (raw === null || raw === undefined || raw === "") return "计划价位不完整";
  const value = Number(raw);
  if (!Number.isFinite(value)) return "计划价位无效";
  const tp2 = Number(payload.tp2_ratio);
  return Number.isFinite(tp2)
    ? `TP1 ${value.toFixed(2)} / TP2 ${tp2.toFixed(2)}`
    : `TP1 ${value.toFixed(2)}`;
}

function orderTypeLabel(value) {
  return { MARKET: "市价执行计划", CONDITIONAL_LIMIT: "条件限价计划", NONE: "暂无订单计划" }[value] || "暂无订单计划";
}

function orderStatusLabel(value) {
  return {
    READY: "可执行",
    WAIT_PRICE: "等待价格进入区域",
    WAIT_CONFIRMATION: "等待小周期反转确认",
    BLOCKED: "暂不可执行",
    NO_DIRECTION: "方向未确认",
    INVALIDATED: "候选计划已失效，正在重新推演",
    STOP_HIT: "已入场计划触及止损",
    PRICE_STALE: "实时价格已过期，暂停执行",
  }[value] || "状态待确认";
}

function orderEntry(plan, decision) {
  if (plan.levels_active === false || decision.levels_active === false) {
    return "历史计划价位（当前不可执行）";
  }
  const type = plan.order_type || decision.order_type;
  if (type === "MARKET") return formatPrice(plan.execution_price ?? decision.execution_price);
  const zone = formatZone(plan.entry_zone?.length ? plan.entry_zone : decision.entry_zone);
  const limit = plan.limit_price ?? decision.limit_price;
  return limit === null || limit === undefined ? zone : `${zone}｜参考 ${formatPrice(limit)}`;
}

function triggerText(plan, decision) {
  if ((plan.order_type || decision.order_type) === "MARKET") {
    return plan.price_protection?.reason || decision.price_protection?.reason || "市价保护已通过";
  }
  const conditions = plan.activation_conditions?.length
    ? plan.activation_conditions
    : decision.activation_conditions || [];
  const validText = formatValidUntil(plan, decision);
  const nextText = formatNextCheck(decision);
  // V1.7.x: surface stale-plan distance between the user-facing
  // activation conditions and the validity window. The base source for
  // the stale fields is the decision (one per request), with per-plan
  // overrides if the trade_plan has its own (currently always mirrors
  // the decision).
  const staleSource = plan.plan_stale_score ? plan : decision;
  const distanceText = formatEntryDistance(staleSource);
  return [...conditions, validText, distanceText, nextText]
    .filter(Boolean)
    .join("；") || "无需额外触发";
}

function planRow(plan, decision, escapeHtml, isPrimary = false) {
  const status = isPrimary
    ? orderStatusLabel(decision.order_status)
    : permissionLabel(plan.permission);
  const title = isPrimary
    ? orderTypeLabel(plan.order_type || decision.order_type)
    : planLabel(plan);
  return `
    <tr class="${isPrimary ? "is-primary" : ""}">
      <td><strong>${escapeHtml(title)}</strong>${isPrimary ? "<small>当前主计划</small>" : ""}</td>
      <td>${escapeHtml(orderTypeLabel(plan.order_type || decision.order_type))}</td>
      <td>${escapeHtml(String(plan.trade_timeframe || decision.trade_timeframe || "4h").toUpperCase())}</td>
      <td>${escapeHtml(directionLabel(plan.direction))}</td>
      <td class="numeric">${escapeHtml(orderEntry(plan, decision))}</td>
      <td class="numeric">${escapeHtml(formatPrice(plan.stop_loss))}</td>
      <td class="numeric">${escapeHtml(formatTargets(plan.take_profit))}</td>
      <td class="numeric">${escapeHtml(planRiskReward(plan, decision))}</td>
      <td class="numeric">${escapeHtml(formatLeverage(plan, decision))}</td>
      <td>${escapeHtml(triggerText(plan, decision))}</td>
      <td>${escapeHtml(status)}</td>
    </tr>
  `;
}

function legacyPlanTable(plans, decision, escapeHtml) {
  return `
    <div class="table-shell strategy-plan-table-shell">
      <table class="data-table strategy-plan-table">
        <thead>
          <tr><th>计划</th><th>订单类型</th><th>交易级别</th><th>方向</th><th>执行价 / 限价区间</th><th>止损</th><th>止盈</th><th>盈亏比</th><th>杠杆</th><th>触发条件</th><th>状态</th></tr>
        </thead>
        <tbody>${plans.map((plan) => planRow(plan, decision, escapeHtml, false)).join("")}</tbody>
      </table>
    </div>
  `;
}

function primaryPlanCard(plan, decision, escapeHtml) {
  // Compact "card" form for the primary plan: the same 6 detail fields as
  // the table but laid out as labelled rows so the primary plan pops out
  // without requiring the legacy 11-column table. The order_type / direction
  // / trade_timeframe / leverage live in the top strip / leverage_reason.
  return `
    <div class="strategy-primary-plan-card">
      <div class="strategy-primary-plan-card-head">
        <strong>${escapeHtml(orderTypeLabel(plan.order_type || decision.order_type))}</strong>
        <small>当前主计划 · ${escapeHtml(String(plan.trade_timeframe || decision.trade_timeframe || "4h").toUpperCase())}</small>
      </div>
      <dl class="strategy-primary-plan-grid">
        <div><dt>执行价 / 限价区间</dt><dd class="numeric">${escapeHtml(orderEntry(plan, decision))}</dd></div>
        <div><dt>止损</dt><dd class="numeric">${escapeHtml(formatPrice(plan.stop_loss))}</dd></div>
        <div><dt>止盈</dt><dd class="numeric">${escapeHtml(formatTargets(plan.take_profit))}</dd></div>
        <div><dt>盈亏比</dt><dd class="numeric">${escapeHtml(planRiskReward(plan, decision))}</dd></div>
        <div><dt>触发条件</dt><dd>${escapeHtml(triggerText(plan, decision))}</dd></div>
        <div><dt>状态</dt><dd>${escapeHtml(orderStatusLabel(decision.order_status))}</dd></div>
      </dl>
    </div>
  `;
}

export function renderExecutionPlan(model, helpers) {
  const { escapeHtml } = helpers;
  const decision = model.trade_decision || {};
  const plans = Array.isArray(model.trade_plans) ? model.trade_plans : [];
  const levelsActive = decision.levels_active !== false;
  const hasOrder = levelsActive && decision.order_type && decision.order_type !== "NONE";
  const primary = hasOrder
    ? plans.find((plan) => plan.order_type && plan.order_type !== "NONE" && plan.direction === decision.side)
      || plans.find((plan) => String(plan.type || "").startsWith("TACTICAL_") && plan.direction === decision.side)
      || plans.find((plan) => plan.direction === decision.side && plan.type !== "EXECUTION_TRIGGER")
      || plans[0]
    : null;
  const secondary = primary ? plans.filter((plan) => plan.id !== primary.id) : plans;
  const recommended = Number(decision.recommended_leverage || 0);
  const maximum = Number(decision.max_leverage || 0);
  const leverageText = recommended > 0
    ? `建议 ${recommended.toFixed(0)}×｜上限 ${maximum.toFixed(0)}×`
    : "暂不使用杠杆";
  const planned = Number(decision.planned_leverage || 0);
  const displayedLeverage = recommended > 0
    ? leverageText
    : planned > 0
      ? `条件满足后计划 ${planned.toFixed(0)}×`
      : leverageText;
  return `
    <section class="strategy-v2-section strategy-execution-plan card" data-status="${escapeHtml(decision.status || "NO_DIRECTION")}">
      <div class="section-heading strategy-compact-heading">
        <div>
          <p class="eyebrow">TRADE EXECUTION</p>
          <h2>交易决策与执行计划</h2>
        </div>
      </div>
      <div class="strategy-decision-strip">
        <div><span>方向</span><strong>${escapeHtml(directionLabel(decision.side))}</strong></div>
        <div><span>执行状态</span><strong>${escapeHtml(orderStatusLabel(decision.order_status))}</strong></div>
        <div class="wide"><span>主要原因</span><strong>${escapeHtml(decision.primary_reason?.message || "等待交易条件确认。")}</strong></div>
      </div>
      <p class="strategy-leverage-reason">${escapeHtml(decision.leverage_reason || `杠杆：${displayedLeverage}。`)}</p>
      ${levelsActive ? "" : `<div class="strategy-invalidated-banner" role="status">${escapeHtml(decision.invalidation_reason || decision.primary_reason?.message || "旧计划已失效，正在重新推演。")}</div>`}
      ${primary ? primaryPlanCard(primary, decision, escapeHtml) : helpers.emptyState("暂无交易计划")}
      ${secondary.length ? `
        <details class="strategy-collapsible strategy-secondary-plans">
          <summary class="strategy-collapsible-summary">
            <div><strong>${levelsActive ? "其他计划" : "失效计划审计"}</strong><small>${levelsActive ? `${secondary.length} 项长期、备用或触发计划` : `${secondary.length} 项旧计划，仅供复核`}</small></div>
            <span class="strategy-collapse-control" aria-hidden="true"></span>
          </summary>
          <div class="strategy-collapsible-body">${legacyPlanTable(secondary, decision, escapeHtml)}</div>
        </details>
      ` : ""}
    </section>
  `;
}
