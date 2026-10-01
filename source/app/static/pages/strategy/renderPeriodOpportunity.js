const PERIOD = { "1w": "周线", "1d": "日线", "4h": "4H", "1h": "1H" };
const SIDE = { LONG: "做多", SHORT: "做空", NONE: "等待方向" };
const STATUS = {
  READY: "可按计划执行",
  WAIT_TRIGGER: "等待入场触发",
  WAIT_LEVELS: "等待有效进出场价位",
  WAIT_DATA: "执行数据准备中",
  WAIT_RISK: "风险预算不足",
  NO_DIRECTION: "暂无交易方向",
  BLOCKED: "暂停开仓",
  invalid_execution_levels: "执行价位几何关系无效",
};
const PERMISSION = { allow: "允许按计划执行", conditional: "满足触发条件后执行", observe: "仅观察" };
const TARGET_SOURCE = { trade_plan: "交易周期结构", observed_structure: "已观测结构位", atr_projection: "基于交易周期 ATR 的模型投影" };

export function renderPeriodOpportunity(decision, model, helpers) {
  const { escapeHtml, formatNumber, formatDateTime } = helpers;
  const trade = PERIOD[decision.trade_timeframe] || decision.trade_timeframe;
  const execution = PERIOD[decision.execution_timeframe] || decision.execution_timeframe;
  const side = SIDE[decision.side] || SIDE.NONE;
  const scan = model.scan_item;
  const rejected = scan?.qualified === false || decision.status !== "READY" || decision.permission !== "allow";
  const status = scan?.qualified === false && decision.status === "READY"
    ? "交易门槛未通过" : STATUS[decision.status] || decision.status;
  const levels = !rejected && decision.levels_active && decision.entry_zone?.length;
  const zone = levels ? decision.entry_zone.map((value) => formatNumber(value, 2)).join(" – ") : "未形成有效计划";
  const stop = levels && decision.invalidation_price ? formatNumber(decision.invalidation_price, 2) : "—";
  const target = levels && decision.take_profit_1 ? formatNumber(decision.take_profit_1, 2) : "—";
  const horizonTarget = levels && decision.horizon_target ? formatNumber(decision.horizon_target, 2) : "—";
  const firstRr = levels && decision.first_risk_reward ? decision.first_risk_reward : "—";
  const rr = levels && decision.risk_reward?.value ? decision.risk_reward.value : "—";
  const firstRrText = firstRr === "—" ? "—" : `${firstRr}:1`;
  const rrText = rr === "—" ? "—" : `${rr}:1`;
  const expectedMove = levels && decision.expected_move_pct ? `${decision.expected_move_pct}%` : "—";
  const stopDistance = levels && decision.stop_distance_pct ? `${decision.stop_distance_pct}%` : "—";
  const leverage = !rejected && decision.recommended_leverage > 0
    ? `建议 ${decision.recommended_leverage}×`
    : !rejected && decision.planned_leverage > 0
      ? `触发后计划 ${decision.planned_leverage}×`
      : "暂不使用";
  const evidence = [...(decision.setup_evidence || []), ...(decision.execution_evidence || [])].slice(0, 12);
  const gateReasons = (scan?.qualification_reasons || [])
    .map((reason) => STATUS[reason] || reason)
    .filter(Boolean);
  const gateExplanation = gateReasons.length ? gateReasons.join("；") : status;
  return `<section class="strategy-period-opportunity card" data-opportunity-id="${escapeHtml(decision.opportunity_id || "")}" data-trade-timeframe="${escapeHtml(decision.trade_timeframe || "")}" data-execution-timeframe="${escapeHtml(decision.execution_timeframe || "")}">
    <p class="eyebrow">PERIOD TRADE · ${escapeHtml(trade)}交易</p>
    <h2>${escapeHtml(trade)} ${escapeHtml(side)} · ${escapeHtml(status)}</h2>
    <p>${escapeHtml(decision.primary_reason?.message || "等待该周期独立判断。")}</p>
    <div class="strategy-period-gate" data-trade-eligible="${rejected ? "false" : "true"}">
      <strong>${rejected ? "本周期未通过交易门槛" : "本周期已通过交易门槛"}</strong>
      <span>${escapeHtml(gateExplanation)}</span>
      ${rejected ? "<small>以下方向和结构仅用于复核，当前没有开仓许可；未形成有效计划时不提供入场、止损、目标与杠杆。</small>" : ""}
    </div>
    <small>入场与出场参考：${escapeHtml(execution)} K 线 · 快照 ${escapeHtml(formatDateTime(model.generated_at))}</small>
    <div class="strategy-timeframe-focus-metrics">
      <div><span>交易级别</span><strong>${escapeHtml(trade)}</strong></div>
      <div><span>执行级别</span><strong>${escapeHtml(execution)}</strong></div>
      <div><span>本机会许可</span><strong>${escapeHtml(rejected ? "仅观察" : PERMISSION[decision.permission] || "仅观察")}</strong></div>
      <div><span>入场区间</span><strong>${escapeHtml(zone)}</strong></div>
      <div><span>结构止损</span><strong>${escapeHtml(stop)}</strong></div>
      <div><span>${escapeHtml(execution)} 第一目标</span><strong>${escapeHtml(target)}</strong></div>
      <div><span>${escapeHtml(trade)} 交易目标</span><strong>${escapeHtml(horizonTarget)}</strong></div>
      <div><span>预期波动幅度</span><strong>${escapeHtml(expectedMove)}</strong></div>
      <div><span>止损距离</span><strong>${escapeHtml(stopDistance)}</strong></div>
      <div><span>执行目标盈亏比</span><strong>${escapeHtml(firstRrText)}</strong></div>
      <div><span>交易级别盈亏比</span><strong>${escapeHtml(rrText)}</strong></div>
      <div><span>模型杠杆参考</span><strong>${escapeHtml(leverage)}</strong></div>
    </div>
    <p class="strategy-leverage-reason">杠杆仅按本机会的止损距离、波动与模型上限估算；尚未计入个人账户资金、已有持仓和组合风险预算，不能作为账户级下单额度。</p>
    ${levels ? `<p class="strategy-leverage-reason">交易目标口径：${escapeHtml(TARGET_SOURCE[decision.target_source] || "交易周期结构")}；止损由 ${escapeHtml(PERIOD[decision.stop_source] || decision.stop_source || execution)} 结构约束。${escapeHtml(decision.leverage_reason || "")}</p>` : ""}
    ${evidence.length ? `<details class="strategy-collapsible" ${rejected ? "open" : ""}><summary>本周期与执行周期证据</summary><ul>${evidence.map((line) => `<li>${escapeHtml(line)}</li>`).join("")}</ul></details>` : ""}
  </section>`;
}
