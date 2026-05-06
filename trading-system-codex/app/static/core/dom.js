import { findKnowledgeTerm } from "./knowledge.js";

const IMPACT_META = {
  bullish: { label: "偏多", className: "impact-bullish", tooltipTone: "tone-bullish" },
  neutral: { label: "中性", className: "impact-neutral", tooltipTone: "tone-neutral" },
  bearish: { label: "偏空", className: "impact-bearish", tooltipTone: "tone-bearish" },
  event: { label: "事件", className: "impact-event", tooltipTone: "tone-event" },
};

const INDICATOR_DISPLAY_NAMES = {
  funding_rate: "FUNDING RATE",
  funding_rate_zscore: "FUNDING RATE Z-SCORE",
  basis_rate: "BASIS RATE",
  basis_rate_zscore: "BASIS RATE Z-SCORE",
  price_to_mark_deviation: "PRICE TO MARK DEVIATION",
  price_to_index_deviation: "PRICE TO INDEX DEVIATION",
  natr_14: "NATR 14",
  atr_14: "ATR 14",
  atr_expansion_warning: "ATR EXPANSION WARNING",
  btc_mvrv: "BTC MVRV",
  eth_mvrv: "ETH MVRV",
  btc_sth_mvrv: "BTC STH MVRV",
  btc_lth_mvrv: "BTC LTH MVRV",
  btc_exchange_net_position_change: "BTC EXCHANGE NET POSITION CHANGE",
  eth_exchange_net_position_change: "ETH EXCHANGE NET POSITION CHANGE",
  btc_active_addresses: "BTC ACTIVE ADDRESSES",
  eth_active_addresses: "ETH ACTIVE ADDRESSES",
  us_cpi_yoy: "US CPI YOY",
  us_core_cpi_yoy: "US CORE CPI YOY",
  us_nfp: "US NFP",
  ism_mfg_pmi: "ISM MFG PMI",
  ism_srv_pmi: "ISM SRV PMI",
  us_10y_2y_spread: "US 10Y 2Y SPREAD",
  cn_cpi_yoy: "CN CPI YOY",
  cn_ppi_yoy: "CN PPI YOY",
  cn_omo_net: "CN OMO NET",
  cn_fr007: "CN FR007",
  cn_pmi_mfg: "CN PMI MFG",
  cn_retail_sales_yoy: "CN RETAIL SALES YOY",
  cn_shibor_3m: "CN SHIBOR 3M",
  cn_10y_cgb: "CN 10Y CGB",
  cn_usdcny: "USD CNY",
  cn_mof_bond_issuance: "CN MOF BOND ISSUANCE",
};

export function byId(id) {
  return document.getElementById(id);
}

export function escapeHtml(value) {
  return String(value ?? "")
    .replaceAll("&", "&amp;")
    .replaceAll("<", "&lt;")
    .replaceAll(">", "&gt;")
    .replaceAll('"', "&quot;")
    .replaceAll("'", "&#39;");
}

export function setRoot(content) {
  const root = byId("page-root");
  root.innerHTML = content;
  return root;
}

export function cardTitle(eyebrow, title, description = "") {
  return `
    <div class="section-head">
      <div>
        <p class="eyebrow">${escapeHtml(eyebrow)}</p>
        <h2>${escapeHtml(title)}</h2>
      </div>
      ${description ? `<p class="section-summary">${escapeHtml(description)}</p>` : ""}
    </div>
  `;
}

export function formatIndicatorName(raw) {
  if (!raw) return "-";
  return INDICATOR_DISPLAY_NAMES[raw] || String(raw).replaceAll("_", " ").toUpperCase();
}

export function formatNumber(value, digits = 2) {
  if (value === null || value === undefined || value === "") return "-";
  const num = Number(value);
  if (Number.isNaN(num)) return String(value);
  return num.toLocaleString("zh-CN", {
    minimumFractionDigits: 0,
    maximumFractionDigits: digits,
  });
}

export function formatSigned(value, digits = 2) {
  if (value === null || value === undefined || value === "") return "-";
  const num = Number(value);
  if (Number.isNaN(num)) return String(value);
  return `${num > 0 ? "+" : ""}${formatNumber(num, digits)}`;
}

export function formatPercent(value, digits = 2) {
  if (value === null || value === undefined || value === "") return "-";
  const num = Number(value);
  if (Number.isNaN(num)) return String(value);
  return `${num.toLocaleString("zh-CN", {
    minimumFractionDigits: 0,
    maximumFractionDigits: digits,
  })}%`;
}

export function formatDateTime(value) {
  if (!value) return "-";
  const date = value instanceof Date ? value : new Date(value);
  if (Number.isNaN(date.getTime())) return "-";
  return `${date.getFullYear()}/${date.getMonth() + 1}/${date.getDate()} ${String(date.getHours()).padStart(2, "0")}:${String(date.getMinutes()).padStart(2, "0")}`;
}

export function formatDateOnly(value) {
  if (!value) return "-";
  const date = value instanceof Date ? value : new Date(value);
  if (Number.isNaN(date.getTime())) return "-";
  return `${date.getFullYear()}/${date.getMonth() + 1}/${date.getDate()}`;
}

export function compactWindowLabel(values) {
  const dates = values
    .map((item) => new Date(item))
    .filter((item) => !Number.isNaN(item.getTime()))
    .sort((a, b) => a.getTime() - b.getTime());
  if (!dates.length) return "暂无窗口";
  return `${formatDateOnly(dates[0])} - ${formatDateOnly(dates[dates.length - 1])}`;
}

export function tooltipIcon(text, tone = "", link = null) {
  const toneClass = {
    "tone-bullish": "tone-favorable",
    "tone-neutral": "tone-neutral",
    "tone-bearish": "tone-adverse",
    "tone-event": "tone-event",
  }[tone] || "tone-neutral";
  const linkMarkup = link?.href
    ? `<a class="tooltip-link" href="${escapeHtml(link.href)}">${escapeHtml(link.label || "查看百科")}</a>`
    : "";
  return `
    <span class="tooltip-anchor compact ${escapeHtml(toneClass)}" tabindex="0" aria-label="${escapeHtml(text)}">
      <span class="tooltip-icon">?</span>
      <span class="tooltip-bubble" role="tooltip">${escapeHtml(text)}${linkMarkup}</span>
    </span>
  `;
}

export function tooltipWrap(content, text, tone = "") {
  const toneClass = {
    "tone-bullish": "tone-favorable",
    "tone-neutral": "tone-neutral",
    "tone-bearish": "tone-adverse",
    "tone-event": "tone-event",
  }[tone] || "tone-neutral";
  return `
    <span class="tooltip-anchor inline ${escapeHtml(toneClass)}" tabindex="0" aria-label="${escapeHtml(text)}">
      ${content}
      <span class="tooltip-bubble" role="tooltip">${escapeHtml(text)}</span>
    </span>
  `;
}

function knowledgeTooltipSegments(term, options = {}) {
  const item = findKnowledgeTerm(term);
  if (!item) return [];
  const parts = [item.term, item.summary || item.definition].filter(Boolean);
  if (options.extra) parts.push(options.extra);
  return parts.slice(0, options.maxParts || 2);
}

export function knowledgeTooltipText(term, fallback = "", options = {}) {
  const parts = knowledgeTooltipSegments(term, options);
  if (!parts.length) return fallback;
  return parts.join(" | ");
}

export function knowledgeTooltip(term, tone = "", fallback = "", options = {}) {
  const item = findKnowledgeTerm(term);
  const text = knowledgeTooltipText(term, fallback, options);
  const link = item ? { href: `/knowledge-page#${item.id}`, label: "查看百科" } : null;
  return text ? tooltipIcon(text, tone, link) : "";
}

export function knowledgeTooltipWrap(content, term, tone = "", fallback = "", options = {}) {
  const text = knowledgeTooltipText(term, fallback, options);
  return text ? tooltipWrap(content, text, tone) : content;
}

export function impactChip(kind, tooltip = "", customLabel = "") {
  const meta = IMPACT_META[kind] || IMPACT_META.neutral;
  return `
    <span class="impact-chip ${meta.className}">
      ${escapeHtml(customLabel || meta.label)}
      ${tooltip ? tooltipIcon(tooltip, meta.tooltipTone) : ""}
    </span>
  `;
}

export function statusChip(text, className = "chip-neutral") {
  return `<span class="status-chip ${className}">${escapeHtml(text)}</span>`;
}

export function statusBanner(message, tone = "neutral") {
  if (!message) return "";
  return `<div class="status-banner status-${escapeHtml(tone)}">${escapeHtml(message)}</div>`;
}

export function loadingState(message = "正在读取缓存") {
  return `
    <div class="data-state data-state-loading">
      <span class="loading-dot" aria-hidden="true"></span>
      <strong>${escapeHtml(message)}</strong>
    </div>
  `;
}

export function emptyState(message = "暂无数据") {
  return `<div class="data-state data-state-empty">${escapeHtml(message)}</div>`;
}

export function errorState(message = "拉取失败，可手动重试") {
  return `<div class="data-state data-state-error">${escapeHtml(message)}</div>`;
}

export function metricCard(label, value, subLabel = "") {
  return `
    <article class="card metric">
      <span>${escapeHtml(label)}</span>
      <strong>${escapeHtml(String(value))}</strong>
      ${subLabel ? `<small class="metric-footnote">${escapeHtml(subLabel)}</small>` : ""}
    </article>
  `;
}

export function observationValue(value) {
  if (value === null || value === undefined) return "-";
  const num = Number(value);
  if (!Number.isNaN(num)) {
    return Math.abs(num) >= 1000 ? formatNumber(num, 0) : formatNumber(num, 2);
  }
  return String(value);
}

export function tableEmptyRow(colspan, text = "暂无数据") {
  return `<tr><td colspan="${colspan}" class="empty-row">${escapeHtml(text)}</td></tr>`;
}
