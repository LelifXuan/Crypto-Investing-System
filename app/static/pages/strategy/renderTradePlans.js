function formatPrice(value) {
  if (value === null || value === undefined || value === "") return "-";
  const n = Number(value);
  if (!Number.isFinite(n)) return "-";
  return n.toLocaleString("en-US", { minimumFractionDigits: 2, maximumFractionDigits: 2 });
}

function formatZone(zone) {
  if (!Array.isArray(zone) || zone.length === 0) return "-";
  if (zone.length === 1) return formatPrice(zone[0]);
  return `${formatPrice(zone[0])} – ${formatPrice(zone[1])}`;
}

function formatTakeProfit(items) {
  if (!Array.isArray(items) || items.length === 0) return "-";
  return items
    .map((item) => `${item.label || "TP"} ${formatPrice(item.price)}`)
    .join(" / ");
}

function stopLossText(value) {
  if (value === null || value === undefined) return "-";
  return formatPrice(value);
}

export function renderTradePlans(model, helpers) {
  const { escapeHtml } = helpers;
  const cards = model.trade_plans.map((plan) => {
    const planType = String(plan.type || plan.plan_type || "PLAN");
    const title = String(plan.label || plan.title || "策略计划");
    const entryZone = formatZone(plan.entry_zone);
    const takeProfit = formatTakeProfit(plan.take_profit);
    const stopLoss = stopLossText(plan.stop_loss);
    return `
      <article class="strategy-v2-card strategy-plan-card">
        <p class="eyebrow">${escapeHtml(planType)}</p>
        <h3>${escapeHtml(title)}</h3>
        <dl>
          <div><dt>入场逻辑</dt><dd>${escapeHtml(plan.entry_logic || "-")}</dd></div>
          <div><dt>入场区间</dt><dd>${escapeHtml(entryZone)}</dd></div>
          <div><dt>止损</dt><dd>${escapeHtml(stopLoss)}</dd></div>
          <div><dt>止盈</dt><dd>${escapeHtml(takeProfit)}</dd></div>
          <div><dt>失效条件</dt><dd>${escapeHtml(plan.invalidation || "-")}</dd></div>
          <div><dt>仓位规则</dt><dd>${escapeHtml(plan.position_rule || "-")}</dd></div>
        </dl>
      </article>
    `;
  }).join("");
  return `
    <section class="strategy-v2-section strategy-trade-plans card">
      <div class="section-heading">
        <div>
          <p class="eyebrow">TRADE PLANS</p>
          <h2>长期配置、战术交易与执行触发</h2>
        </div>
      </div>
      <div class="strategy-v2-grid">${cards || helpers.emptyState("暂无可执行计划")}</div>
    </section>
  `;
}