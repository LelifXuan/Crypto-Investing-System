import { api } from "../core/api.js";
import { escapeHtml, formatDateTime, formatNumber, setRoot, statusBanner } from "../core/dom.js";

let activeController = null;
let selectedGroup = "all";
let latestPayload = null;

function valueText(value, suffix = "") {
  if (value === null || value === undefined || value === "") return "暂不可用";
  return `${formatNumber(value, 2)}${suffix}`;
}

function changeClass(value) {
  const number = Number(value);
  if (Number.isNaN(number) || number === 0) return "etf-change-neutral";
  return number > 0 ? "etf-change-up" : "etf-change-down";
}

function amountText(value) {
  const number = Number(value);
  if (!Number.isFinite(number)) return "暂不可用";
  if (Math.abs(number) >= 100000000) return `${formatNumber(number / 100000000, 2)} 亿`;
  if (Math.abs(number) >= 10000) return `${formatNumber(number / 10000, 2)} 万`;
  return formatNumber(number, 2);
}

function allQuotes(payload) {
  return (payload.groups || []).flatMap((group) => group.items || []);
}

function groupLabel(group) {
  if (group === "all") return "全部";
  const found = (latestPayload?.groups || []).find((item) => item.group === group);
  return found?.group_label || group.toUpperCase();
}

function sourceStatusLabel(status, cacheStatus) {
  if (status === "ok" && cacheStatus === "live") return "实时行情";
  if (["stale", "cached"].includes(status) || cacheStatus === "stale") return "使用最近缓存";
  return {
    ok: "行情可用",
    partial: "部分可用",
    stale: "使用最近缓存",
    error: "行情源暂不可用",
  }[status] || "状态未知";
}

function renderGroupTabs(groups) {
  return `
    <div class="etf-group-tabs">
      <button type="button" class="${selectedGroup === "all" ? "is-active" : ""}" data-etf-group="all">全部</button>
      ${groups.map((group) => `
        <button type="button" class="${selectedGroup === group.group ? "is-active" : ""}" data-etf-group="${escapeHtml(group.group)}">
          ${escapeHtml(group.group_label || group.group)}
        </button>
      `).join("")}
    </div>`;
}

function renderOverview(payload, loadingMessage = "") {
  const quotes = allQuotes(payload || {});
  const okCount = quotes.filter((item) => item.status === "ok").length;
  const failedCount = Math.max(0, quotes.length - okCount);
  const statusLabel = sourceStatusLabel(payload?.source_status, payload?.cache_status);
  const generatedAt = payload?.generated_at ? formatDateTime(payload.generated_at) : "-";
  return `
    <section class="card etf-dashboard-card">
      <div class="etf-dashboard-head">
        <div>
          <p class="eyebrow">A-SHARE ETF</p>
          <h2>A股ETF</h2>
        </div>
        <button class="primary-action" id="etf-refresh-button">刷新行情</button>
      </div>
      <div class="etf-dashboard-meta">
        <span><small>更新时间</small><strong>${escapeHtml(generatedAt)}</strong></span>
        <span><small>来源状态</small><strong>${escapeHtml(statusLabel)}</strong></span>
        <span><small>成功 / 失败</small><strong>${okCount} / ${failedCount}</strong></span>
        <span><small>当前分组</small><strong>${escapeHtml(groupLabel(selectedGroup))}</strong></span>
      </div>
      <div class="etf-dashboard-bottom"><div id="etf-tabs">${renderGroupTabs(payload?.groups || [])}</div><div id="etf-status">${loadingMessage ? statusBanner(loadingMessage, "loading") : ""}</div></div>
    </section>`;
}

function priceText(item) {
  if (item.last_price !== null && item.last_price !== undefined && item.last_price !== "") {
    return { value: formatNumber(item.last_price, 2), label: "实时" };
  }
  if (item.prev_close !== null && item.prev_close !== undefined && item.prev_close !== "") {
    return { value: `${formatNumber(item.prev_close, 2)} (昨收)`, label: "昨收参考" };
  }
  return { value: "暂不可用", label: "暂无" };
}

function renderQuoteCard(item) {
  const unavailable = item.status !== "ok";
  const change = item.change_pct;
  const price = priceText(item);
  return `
    <article class="etf-quote-card ${unavailable ? "is-unavailable" : ""}">
      <div class="etf-quote-head">
        <div><p class="eyebrow">${escapeHtml(item.code)} · ${escapeHtml(item.market || "-")}</p><h3>${escapeHtml(item.name || item.source_name || item.code)}</h3></div>
        <span class="status-chip ${unavailable ? "chip-warning" : (item.last_price != null ? "chip-success" : "chip-neutral")}">${unavailable ? "暂不可用" : price.label}</span>
      </div>
      <div class="etf-price-row"><strong>${escapeHtml(price.value)}</strong><span class="${changeClass(change)}">${valueText(item.change_pct, "%")} / ${valueText(item.change_amount)}</span></div>
      <div class="etf-metric-grid">
        <span><small>今开</small><b>${valueText(item.open)}</b></span>
        <span><small>最高</small><b>${valueText(item.high)}</b></span>
        <span><small>最低</small><b>${valueText(item.low)}</b></span>
        <span><small>昨收</small><b>${valueText(item.prev_close)}</b></span>
        <span><small>成交额</small><b>${amountText(item.amount)}</b></span>
        <span><small>成交量</small><b>${amountText(item.volume)}</b></span>
        <span><small>报价时间</small><b>${item.quote_time ? escapeHtml(formatDateTime(item.quote_time)) : "暂不可用"}</b></span>
        <span><small>来源</small><b>${escapeHtml(item.source || "Eastmoney")}</b></span>
      </div>
      ${item.error_message ? `<p class="etf-error">${escapeHtml(item.error_message)}</p>` : ""}
    </article>`;
}

function renderGroup(group) {
  const items = group.items || [];
  return `
    <section class="card etf-section" id="etf-group-${escapeHtml(group.group || "all")}">
      <div class="section-head"><div><p class="eyebrow">${escapeHtml(group.group || "ETF")}</p><h2>${escapeHtml(group.group_label || group.group || "ETF")}</h2></div><span class="status-chip chip-neutral">${items.length} 项</span></div>
      <div class="etf-grid">${items.length ? items.map(renderQuoteCard).join("") : '<div class="empty-state">暂无 ETF 行情。</div>'}</div>
    </section>`;
}

function filteredGroups(payload) {
  const groups = payload.groups || [];
  return selectedGroup === "all" ? groups : groups.filter((group) => group.group === selectedGroup);
}

function bindControls() {
  document.getElementById("etf-refresh-button")?.addEventListener("click", () => void loadQuotes({ force: true }));
  document.querySelectorAll("[data-etf-group]").forEach((button) => {
    button.addEventListener("click", () => {
      selectedGroup = button.dataset.etfGroup || "all";
      renderEtfPayload(latestPayload);
    });
  });
}

function renderEtfPayload(payload, loadingMessage = "") {
  latestPayload = payload || latestPayload || { groups: [] };
  document.getElementById("etf-overview").innerHTML = renderOverview(latestPayload, loadingMessage);
  document.getElementById("etf-groups").innerHTML = filteredGroups(latestPayload).map(renderGroup).join("");
  bindControls();
}

async function loadQuotes({ force = false } = {}) {
  activeController?.abort();
  activeController = new AbortController();
  renderEtfPayload(latestPayload || { groups: [] }, force ? "正在刷新 A股ETF 行情" : "正在读取 A股ETF 行情");
  try {
    const payload = force ? await api.refreshEtfQuotes("all", { signal: activeController.signal }) : await api.getEtfQuotes("all", { signal: activeController.signal });
    renderEtfPayload(payload);
    const tone = payload.source_status === "error" ? "warning" : "success";
    const message = payload.cache_status === "stale"
      ? "行情源暂不可用，已展示最近缓存。"
      : payload.source_status === "error"
        ? "行情源暂不可用，已保留 ETF 列表。"
        : `行情已更新：${formatDateTime(payload.generated_at)}`;
    document.getElementById("etf-status").innerHTML = statusBanner(message, tone);
  } catch (error) {
    if (error?.name === "AbortError") return;
    renderEtfPayload(latestPayload || { groups: [] });
    document.getElementById("etf-status").innerHTML = statusBanner("A股ETF 行情读取失败，可稍后重试。", "warning");
    if (!latestPayload) document.getElementById("etf-groups").innerHTML = '<div class="empty-state">行情源暂不可用。</div>';
  }
}

export async function renderAshareEtf() {
  setRoot(`<section id="etf-overview"></section><section class="etf-page-grid" id="etf-groups"></section>`);
  renderEtfPayload({ groups: [] }, "正在读取 A股ETF 行情");
  await loadQuotes();
  return { unmount: async () => activeController?.abort() };
}

export const renderPage = renderAshareEtf;
