import { directionLabel } from "./adapter.js?v=trade-4h-v1";

function labelRole(value) {
  return {
    direction_input: "方向输入",
    confirmation: "确认信号",
    contrarian_crowding: "反向拥挤",
    risk_gate: "风险门控",
    execution_trigger: "执行触发",
    key_level: "关键价位",
    diagnostic: "仅诊断",
    trend: "方向输入",
    momentum: "确认信号",
    crowding: "反向拥挤",
    volatility: "风险门控",
  }[value] || value || "仅诊断";
}

function sourceLabel(value) {
  return {
    indicators: "技术指标",
    technical: "技术指标",
    structure: "形态结构",
    price_structure: "形态结构",
    btc_derivatives: "BTC 衍生品",
    derivatives: "BTC 衍生品",
    strategy_unified: "统一策略",
  }[value] || value || "策略输入";
}

function usageLabel(value) {
  return {
    used: "已参与",
    diagnostic: "仅诊断",
    excluded: "已排除",
    downgrade: "风险降级",
    block: "阻止执行",
  }[value] || value || "仅诊断";
}

export function renderDecisionAudit(model, helpers) {
  const { escapeHtml, formatDateTime } = helpers;
  const snapshot = model.market_decision_snapshot || {};
  const coverage = Array.isArray(model.signal_coverage) ? model.signal_coverage : [];
  const used = coverage
    .filter((item) => item.coverage_kind !== "input_indicator" && ["used", "downgrade", "block"].includes(item.usage_status))
    .slice(0, 12);
  const inputs = coverage.filter((item) => item.coverage_kind === "input_indicator");
  const diagnostics = inputs.filter((item) => item.usage_status !== "used");
  const matrix = Array.isArray(model.cross_validation?.matrix)
    ? model.cross_validation.matrix
    : [];
  const validation = model.shadow_evaluation?.validation || {};
  const snapshotInputs = Object.values(snapshot.input_snapshots || {})
    .flat()
    .filter((item) => item?.snapshot_id)
    .slice(0, 8);
  return `
    <section class="strategy-v2-section strategy-decision-audit card">
      <div class="section-heading strategy-compact-heading">
        <div>
          <p class="eyebrow">AUDITABLE DECISION</p>
          <h2>决策快照、交叉验证与指标覆盖</h2>
        </div>
        <span class="status-chip neutral">新模型仅影子记录，不影响当前主策略</span>
      </div>
      <div class="strategy-audit-summary">
        <article><span>主模型</span><strong>${escapeHtml(model.active_model_version)}</strong></article>
        <article><span>候选模型</span><strong>${escapeHtml(model.candidate_model_version)}</strong></article>
        <article><span>策略时间</span><strong>${escapeHtml(formatDateTime(model.strategy_as_of))}</strong></article>
        <article><span>价格时间</span><strong>${escapeHtml(formatDateTime(model.price_as_of))}</strong><small>${escapeHtml(model.price_source || "-")}</small></article>
        <article><span>重算状态</span><strong>${escapeHtml(model.recompute_status)}</strong></article>
      </div>
      <div class="strategy-audit-columns">
        <article>
          <h3>影子模型实际使用的证据</h3>
          <ul class="strategy-audit-list">
            ${used.map((item) => `<li><strong>${escapeHtml(item.indicator_key || item.signal_id)}</strong><span>${escapeHtml(`${sourceLabel(item.source_page)} · ${String(item.window || item.horizon || "-").toUpperCase()} · ${labelRole(item.semantic_role)}`)}</span><small>${escapeHtml(item.usage_reason || item.reason || "已参与影子计算")}</small></li>`).join("") || "<li>当前没有满足有效期和质量门槛的影子信号</li>"}
          </ul>
        </article>
        <article>
          <h3>跨模块复核</h3>
          <div class="table-shell">
            <table class="data-table">
              <thead><tr><th>模块</th><th>方向</th><th>多头贡献</th><th>空头贡献</th></tr></thead>
              <tbody>${matrix.map((item) => `<tr><td>${escapeHtml(sourceLabel(item.module))}</td><td>${escapeHtml(directionLabel(item.direction))}</td><td>${escapeHtml(Number(item.long || 0).toFixed(1))}</td><td>${escapeHtml(Number(item.short || 0).toFixed(1))}</td></tr>`).join("") || '<tr><td colspan="4">交叉验证数据不足</td></tr>'}</tbody>
            </table>
          </div>
          <p>${escapeHtml(model.cross_validation?.conflicts?.[0]?.resolution || "模块同向时提高确认度；冲突时降低影子模型权限并等待价格确认。")}</p>
        </article>
      </div>
      <details class="strategy-collapsible">
        <summary class="strategy-collapsible-summary"><div><strong>完整指标覆盖</strong><small>${inputs.length} 项输入；${diagnostics.length} 项仅诊断或未满足条件</small></div><span class="strategy-collapse-control" aria-hidden="true"></span></summary>
        <div class="strategy-collapsible-body table-shell">
          <table class="data-table strategy-coverage-table">
            <thead><tr><th>来源</th><th>周期</th><th>指标</th><th>角色</th><th>状态</th><th>变换 / 原因</th></tr></thead>
            <tbody>${inputs.map((item) => `<tr><td>${escapeHtml(sourceLabel(item.source_page))}</td><td>${escapeHtml(String(item.window || "-").toUpperCase())}</td><td>${escapeHtml(item.indicator_key)}</td><td>${escapeHtml(labelRole(item.semantic_role))}</td><td>${escapeHtml(usageLabel(item.usage_status))}</td><td><strong>${escapeHtml(item.transform || "identity")}</strong><small>${escapeHtml(item.usage_reason || "-")}</small></td></tr>`).join("") || '<tr><td colspan="6">暂无覆盖记录</td></tr>'}</tbody>
          </table>
        </div>
      </details>
      <details class="strategy-collapsible">
        <summary class="strategy-collapsible-summary"><div><strong>输入快照与切换门槛</strong><small>快照 ${escapeHtml(snapshot.snapshot_id || "-")} · 验证状态 ${escapeHtml(validation.status || "collecting")}</small></div><span class="strategy-collapse-control" aria-hidden="true"></span></summary>
        <div class="strategy-collapsible-body strategy-audit-snapshots">
          ${snapshotInputs.map((item) => `<article><strong>${escapeHtml(`${sourceLabel(item.source_page)} · ${String(item.timeframe || "-").toUpperCase()}`)}</strong><small>${escapeHtml(item.snapshot_id)}</small><span>${escapeHtml(`${formatDateTime(item.observed_at)} → ${formatDateTime(item.expires_at)}`)}</span></article>`).join("") || "<p>输入快照正在积累。</p>"}
          <p>候选模型只有在至少 90 天历史、30 天影子运行、120 个可评估决策及全部质量门槛通过后，才允许人工切换。</p>
        </div>
      </details>
    </section>
  `;
}
