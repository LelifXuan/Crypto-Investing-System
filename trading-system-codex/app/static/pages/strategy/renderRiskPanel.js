function riskIdentity(risk) {
  return risk.id || risk.key || [
    risk.category,
    risk.severity,
    risk.label,
    risk.source_module,
  ].filter(Boolean).join(":");
}

function dedupeRisks(items) {
  const seen = new Set();
  return (items || []).filter((risk) => {
    const key = riskIdentity(risk);
    if (seen.has(key)) return false;
    seen.add(key);
    return true;
  });
}

export function renderRiskPanel(model, helpers) {
  const { escapeHtml } = helpers;
  const groups = model.risk_groups || {};
  const groupKeys = ["strategic", "tactical", "execution", "data", "event"];
  const renderedGlobal = new Set();
  const renderGroup = (key) => {
    const grouped = Array.isArray(groups[key]) && groups[key].length
      ? groups[key]
      : model.risk_alerts.filter((risk) => risk.category === key);
    const items = dedupeRisks(grouped).filter((risk) => {
      const identity = riskIdentity(risk);
      if (renderedGlobal.has(identity)) return false;
      renderedGlobal.add(identity);
      return true;
    });
    if (!items.length) return "";
    return `
      <div class="strategy-risk-group">
        <h3>${escapeHtml(key)}</h3>
        ${items.map((risk) => `
          <article class="strategy-risk-item ${escapeHtml(risk.severity || "info")}">
            <span>${escapeHtml(risk.category || "risk")}</span>
            <strong>${escapeHtml(risk.label || "风险提示")}</strong>
            <p>${escapeHtml(risk.message || "")}</p>
            ${risk.action ? `<small>${escapeHtml(risk.action)}</small>` : ""}
          </article>
        `).join("")}
      </div>
    `;
  };
  const alerts = groupKeys.map(renderGroup).filter(Boolean).join("") || dedupeRisks(model.risk_alerts).map((risk) => `
    <article class="strategy-risk-item ${escapeHtml(risk.severity || "info")}">
      <span>${escapeHtml(risk.category || "risk")}</span>
      <strong>${escapeHtml(risk.label || "风险提示")}</strong>
      <p>${escapeHtml(risk.message || "")}</p>
    </article>
  `).join("");
  const focus = model.monitoring_focus.map((item) => `
    <li><strong>${escapeHtml(item.label || item.name || "-")}</strong><span>${escapeHtml(item.reason || item.message || "")}</span></li>
  `).join("");
  return `
    <section class="strategy-v2-section strategy-risk-layout card">
      <div>
        <div class="section-heading compact">
          <div>
            <p class="eyebrow">RISK GATES</p>
            <h2>风险门禁</h2>
          </div>
        </div>
        <div class="strategy-risk-list">${alerts || helpers.emptyState("暂无风险门禁")}</div>
      </div>
      <div>
        <div class="section-heading compact">
          <div>
            <p class="eyebrow">MONITORING</p>
            <h2>监控重点</h2>
          </div>
        </div>
        <ul class="strategy-monitor-list">${focus || "<li>暂无监控重点</li>"}</ul>
      </div>
    </section>
  `;
}
