function asArray(value) {
  return Array.isArray(value) ? value : [];
}

function joinTimeframes(value) {
  const items = asArray(value).filter(Boolean);
  return items.length ? items.join(" / ") : "-";
}

function renderLayer(layer, escapeHtml) {
  return `
    <article class="strategy-narrative-layer">
      <div>
        <p class="eyebrow">${escapeHtml(layer.label || layer.key || "层级")}</p>
        <h3>${escapeHtml(layer.direction_label || layer.direction || "-")}</h3>
        <span>${escapeHtml(joinTimeframes(layer.timeframes))}</span>
      </div>
      <dl>
        <div>
          <dt>依据</dt>
          <dd>${escapeHtml(layer.basis || "缺少该层级的证据明细。")}</dd>
        </div>
        <div>
          <dt>等待信号</dt>
          <dd>${escapeHtml(layer.required_signal || "等待下级周期确认。")}</dd>
        </div>
      </dl>
    </article>
  `;
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
  const layers = asArray(narrative.layers).map((layer) => renderLayer(layer, escapeHtml)).join("");
  const watchlist = asArray(narrative.watchlist).map((item) => renderWatchItem(item, escapeHtml)).join("");
  return `
    <section class="strategy-v2-section strategy-narrative card">
      <div class="section-heading compact">
        <div>
          <p class="eyebrow">NARRATIVE</p>
          <h2>${escapeHtml(narrative.headline || "统一推演摘要")}</h2>
        </div>
      </div>
      <div class="strategy-narrative-layers">
        ${layers || helpers.emptyState("暂无分层结论")}
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
