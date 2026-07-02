function isRoutineEvent(item) {
  const status = String(item?.event_window_status || item?.status || "").trim().toLowerCase();
  return ["", "normal", "clear", "none", "ready", "no_event", "no-event", "清晰"].includes(status);
}

export function renderEventWatch(model, helpers) {
  const { escapeHtml } = helpers;
  const items = (model.event_watch || []).filter((item) => !isRoutineEvent(item));
  const cards = items.map((item) => `
    <article class="strategy-v2-card">
      <p class="eyebrow">${escapeHtml(item.timeframe || "EVENT")}</p>
      <h3>${escapeHtml(item.event_window_status || "事件窗口")}</h3>
      <p>${escapeHtml(item.trading_rule || "事件窗口内降低交易权限。")}</p>
      <small>${escapeHtml(item.next_check_time || "")}</small>
    </article>
  `).join("");
  return `
    <section class="strategy-v2-section strategy-event-watch card">
      <div class="section-heading">
        <div>
          <p class="eyebrow">EVENT WATCH</p>
          <h2>事件窗口与交易规则</h2>
        </div>
      </div>
      <div class="strategy-v2-grid">${cards || helpers.emptyState("暂无高影响事件窗口")}</div>
    </section>
  `;
}
