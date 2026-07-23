function isRoutineEvent(item) {
  const status = String(item?.event_window_status || item?.status || "").trim().toLowerCase();
  return ["", "normal", "clear", "none", "ready", "no_event", "no-event", "清晰"].includes(status);
}

export function renderEventWatch(model, helpers) {
  const { escapeHtml, formatDateTime } = helpers;
  const items = (model.event_watch || []).filter((item) => !isRoutineEvent(item));
  const cards = items.map((item) => `
    <article class="strategy-v2-card">
      <p class="eyebrow">${escapeHtml(item.timeframe || "EVENT")}</p>
      <h3>${escapeHtml(item.event_window_status || "事件窗口")}</h3>
      <p>${escapeHtml(item.trading_rule || "事件窗口内降低交易权限。")}</p>
      <small>${escapeHtml(item.next_check_time ? (String(item.next_check_time).includes("T") ? formatDateTime(item.next_check_time) : item.next_check_time) : "")}</small>
    </article>
  `).join("");
  const isEmpty = items.length === 0;
  return `
    <details class="strategy-v2-section strategy-event-watch strategy-collapsible card" ${isEmpty ? "" : "open"}>
      <summary class="strategy-collapsible-summary">
        <div>
          <p class="eyebrow">EVENT WATCH</p>
          <h2>事件窗口与交易规则</h2>
          <small>${isEmpty ? "暂无高影响事件" : `${items.length} 个高影响事件窗口`}</small>
        </div>
        <span class="strategy-collapse-control" aria-hidden="true"></span>
      </summary>
      ${isEmpty ? "" : `<div class="strategy-collapsible-body"><div class="strategy-v2-grid">${cards}</div></div>`}
    </details>
  `;
}
