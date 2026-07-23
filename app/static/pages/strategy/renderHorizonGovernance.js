import { directionLabel, verdictLabel } from "./adapter.js";

function formatPrice(value) {
  if (value === null || value === undefined || value === "") return "-";
  const n = Number(value);
  if (!Number.isFinite(n)) return "-";
  return n.toLocaleString("en-US", { minimumFractionDigits: 2, maximumFractionDigits: 2 });
}

function scoreText(nodes) {
  const longScore = Math.round(nodes.reduce((sum, node) => sum + Number(node.long_score || 0), 0) / Math.max(nodes.length, 1));
  const shortScore = Math.round(nodes.reduce((sum, node) => sum + Number(node.short_score || 0), 0) / Math.max(nodes.length, 1));
  return `${longScore} / ${shortScore}`;
}

function nodeByTimeframe(nodes, timeframe) {
  return nodes.find((node) => node.timeframe === timeframe) || {};
}

function firstPrice(nodes, key) {
  const node = nodes.find((item) => item[key] !== null && item[key] !== undefined);
  return node ? node[key] : null;
}

function higherDecisionText(model, higher) {
  const nodes = (model.timeframe_stack || []).filter((node) => ["1M", "1w"].includes(node.timeframe));
  const resistance = firstPrice(nodes, "key_resistance");
  const support = firstPrice(nodes, "key_support");
  const invalidation = firstPrice(nodes, "invalidation") ?? support;
  const direction = higher.direction || model.horizon_views?.strategic?.direction || "NEUTRAL";
  if (direction === "LONG") {
    return `高周期偏多。1M/1w 多/空分 ${scoreText(nodes)}；只要周线不跌破关键失效位 ${formatPrice(invalidation)}，回踩支撑 ${formatPrice(support)} 后仍按多头背景处理。`;
  }
  if (direction === "SHORT") {
    return `高周期偏空。1M/1w 多/空分 ${scoreText(nodes)}；只要周线不能站回关键结构位 ${formatPrice(resistance)}，反弹更适合按减仓或空头背景处理。`;
  }
  return `高周期没有方向优势。1M/1w 多/空分 ${scoreText(nodes)}；周线站上 ${formatPrice(resistance)} 才转为偏多，跌破 ${formatPrice(support)} 才转为偏空，当前不支持单边押注。`;
}

function lowerDecisionText(model, lower) {
  const nodes = model.timeframe_stack || [];
  const h4 = nodeByTimeframe(nodes, "4h");
  const h1 = nodeByTimeframe(nodes, "1h");
  const m15 = nodeByTimeframe(nodes, "15m");
  const resistance = h1.key_resistance ?? h4.key_resistance ?? m15.key_resistance;
  const support = h1.key_support ?? h4.key_support ?? m15.key_support;
  const invalidation = h1.invalidation ?? h4.invalidation ?? (String(lower.direction || "").includes("SHORT") ? resistance : support);
  const direction = lower.direction || model.horizon_views?.execution?.direction || "WAIT";
  if (direction === "WAIT_LONG_TRIGGER") {
    return `低周期只等多头触发：1H 收盘站上 ${formatPrice(resistance)} 且 15M 回踩不跌回 ${formatPrice(invalidation)}，才允许执行多头计划；跌破 ${formatPrice(support)} 则触发失败。`;
  }
  if (direction === "WAIT_SHORT_TRIGGER") {
    return `低周期只等空头触发：1H 收盘跌破 ${formatPrice(support)} 且 15M 反抽不站回 ${formatPrice(invalidation)}，才允许执行空头计划；站回 ${formatPrice(resistance)} 则触发失败。`;
  }
  return `低周期没有执行信号。4H/1H/15M 多/空分 ${scoreText([h4, h1, m15])}；向上站上 ${formatPrice(resistance)} 才观察多头触发，向下跌破 ${formatPrice(support)} 才观察空头触发。`;
}

function renderResolutionGovernanceCard(card, helpers) {
  const { escapeHtml } = helpers;
  const safe = card || {};
  const sources = Array.isArray(safe.source_timeframes) ? safe.source_timeframes.join(" / ") : "";
  const allowed = Array.isArray(safe.allowed_actions) && safe.allowed_actions.length
    ? safe.allowed_actions.slice(0, 2).join(" / ")
    : "等待确认";
  const blocked = Array.isArray(safe.blocked_actions) && safe.blocked_actions.length
    ? safe.blocked_actions.slice(0, 2).join(" / ")
    : "暂无";
  return `
    <article class="strategy-v2-card">
      <p class="eyebrow">${escapeHtml(sources || safe.key || "-")}</p>
      <h3>${escapeHtml(safe.title || "-")}</h3>
      <p>${escapeHtml(safe.instruction || "等待关键价位补齐后再确认。")}</p>
      <small>${escapeHtml(`允许：${allowed} · 禁止：${blocked} · 仓位：${safe.position_cap || "-"}`)}</small>
    </article>
  `;
}

export function renderHorizonGovernance(model, helpers) {
  const { escapeHtml } = helpers;
  const governance = model.horizon_governance || {};
  const resolutionCards = Array.isArray(model.governance_cards) && model.governance_cards.length
    ? model.governance_cards
    : Array.isArray(governance.governance_cards) ? governance.governance_cards : [];
  const higher = governance.higher_timeframe_constraint || {};
  const lower = governance.lower_timeframe_driver || {};
  const unifiedState = model.unified_state || {};
  const verdict = verdictLabel(unifiedState.code || "RANGE_NO_EDGE");
  const upgradePath = resolutionCards.find((card) => Array.isArray(card.upgrade_path))?.upgrade_path || governance.upgrade_path;
  const invalidationPath = resolutionCards.find((card) => Array.isArray(card.invalidation_path))?.invalidation_path || governance.invalidation_path;
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
        ${resolutionCards.map((card) => renderResolutionGovernanceCard(card, helpers)).join("")}
        <article class="strategy-v2-card">
          <p class="eyebrow">HIGHER TF</p>
          <h3>${escapeHtml(directionLabel(higher.direction))}</h3>
          <p>${escapeHtml(higherDecisionText(model, higher))}</p>
          <small>${escapeHtml((higher.source_timeframes || []).join(" / "))}</small>
        </article>
        <article class="strategy-v2-card">
          <p class="eyebrow">LOWER TF</p>
          <h3>${escapeHtml(directionLabel(lower.direction))}</h3>
          <p>${escapeHtml(lowerDecisionText(model, lower))}</p>
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
          <ul>${list(upgradePath)}</ul>
        </article>
        <article>
          <h3>失效路径</h3>
          <ul>${list(invalidationPath)}</ul>
        </article>
      </div>
    </section>
  `;
}
