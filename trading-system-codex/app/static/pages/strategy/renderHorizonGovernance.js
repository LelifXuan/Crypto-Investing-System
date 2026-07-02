import { directionLabel, verdictLabel } from "./adapter.js";

export function renderHorizonGovernance(model, helpers) {
  const { escapeHtml } = helpers;
  const governance = model.horizon_governance || {};
  const higher = governance.higher_timeframe_constraint || {};
  const lower = governance.lower_timeframe_driver || {};
  const unifiedState = model.unified_state || {};
  const verdict = verdictLabel(unifiedState.code || "RANGE_NO_EDGE");
  const list = (items) => (Array.isArray(items) && items.length
    ? items.map((item) => `<li>${escapeHtml(item)}</li>`).join("")
    : "<li>暂无</li>");
  return `
    <section class="strategy-v2-section strategy-horizon-governance card">
      <div class="section-heading">
        <div>
          <p class="eyebrow">HORIZON GOVERNANCE</p>
          <h2>大周期约束与小周期推动</h2>
        </div>
        <p>${escapeHtml(`统一结论：${verdict}；仓位上限：${governance.position_cap || "-"}；允许方向：${(governance.allowed_sides || []).map(directionLabel).join(" / ") || "-"}`)}</p>
      </div>
      <div class="strategy-v2-grid">
        <article class="strategy-v2-card">
          <p class="eyebrow">HIGHER TF</p>
          <h3>${escapeHtml(directionLabel(higher.direction))}</h3>
          <p>${escapeHtml(higher.rule || "高周期负责战略边界。")}</p>
          <small>${escapeHtml((higher.source_timeframes || []).join(" / "))}</small>
        </article>
        <article class="strategy-v2-card">
          <p class="eyebrow">LOWER TF</p>
          <h3>${escapeHtml(directionLabel(lower.direction))}</h3>
          <p>${escapeHtml(lower.rule || "低周期负责执行触发。")}</p>
          <small>${escapeHtml((lower.source_timeframes || []).join(" / "))}</small>
        </article>
        <article class="strategy-v2-card">
          <p class="eyebrow">POSITION CAP</p>
          <h3>${escapeHtml(governance.position_cap || "-")}</h3>
          <p>${escapeHtml(`允许方向：${(governance.allowed_sides || []).map(directionLabel).join(" / ") || "-"}`)}</p>
        </article>
      </div>
      <div class="strategy-governance-paths">
        <article>
          <h3>升级路径</h3>
          <ul>${list(governance.upgrade_path)}</ul>
        </article>
        <article>
          <h3>失效路径</h3>
          <ul>${list(governance.invalidation_path)}</ul>
        </article>
      </div>
    </section>
  `;
}