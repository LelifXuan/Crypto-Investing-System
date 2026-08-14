function asArray(value) {
  return Array.isArray(value) ? value : [];
}

function renderWatchItem(item, escapeHtml) {
  return `
    <li>
      <strong>${escapeHtml(item.timeframe || "-")}</strong>
      <span>${escapeHtml(item.indicator || "检查项")}</span>
      <p>${escapeHtml(item.condition || "-")}</p>
    </li>
  `;
}

export function renderNarrative(model, helpers) {
  const { escapeHtml } = helpers;
  const narrative = model.narrative || {};
  const watchlist = asArray(narrative.watchlist).map((item) => renderWatchItem(item, escapeHtml)).join("");
  return `
    <section class="strategy-v2-section strategy-narrative card">
      <div class="section-heading compact">
        <div>
          <p class="eyebrow">NARRATIVE</p>
          <h2>${escapeHtml(narrative.headline || "统一推演摘要")}</h2>
        </div>
      </div>
      <div class="strategy-narrative-watch">
        <div>
          <p class="eyebrow">NEXT CHECK</p>
          <h3>下一检查项</h3>
        </div>
        <ul>${watchlist || "<li>暂无下一检查项</li>"}</ul>
      </div>
      ${narrative.action ? `<p class="strategy-narrative-action">${escapeHtml(narrative.action)}</p>` : ""}
    </section>
  `;
}
