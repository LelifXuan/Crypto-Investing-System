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

export function setRoot(content, options = {}) {
  const root = byId("page-root");
  delete root._monitoringSections;
  const bodyDataset = document.body?.dataset;
  const layout = options.layout || bodyDataset?.pageLayout || "overview";
  if (bodyDataset) bodyDataset.pageLayout = layout;
  if (root.dataset) root.dataset.layout = layout;
  root.innerHTML = content;
  return root;
}

// V1.5.x: SPA router skeleton. Used as the immediate content
// for #page-root when the user clicks a top-nav link, so the
// browser paints a clean "正在准备 X" placeholder within the
// same frame as the click. The actual page module's render
// function runs in the next animation frame via the SPA router's
// rAF deferral, then setRoot's again with the real content.
// Without this, the click event handler synchronously walks
// through the new page's setRoot (which is 50-300 ms of synchronous
// innerHTML) before the browser can paint anything.
export function renderNavSkeleton(pageMeta) {
  const meta = typeof pageMeta === "string" ? { title: pageMeta } : (pageMeta || {});
  const safeTitle = escapeHtml(meta.title || "页面");
  const layout = escapeHtml(meta.layout || "overview");
  return `
    <section class="editorial-skeleton nav-skeleton-card" data-layout="${layout}">
      <div class="section-head">
        <div>
          <p class="eyebrow">正在跳转</p>
          <h2>${safeTitle}</h2>
          <p class="section-summary">页面数据准备中，可稍候或手动刷新。</p>
        </div>
        <div class="knowledge-section-count">加载中</div>
      </div>
      <div class="nav-skeleton-grid">
        <div class="nav-skeleton-row nav-skeleton-row-wide"></div>
        <div class="nav-skeleton-row"></div>
        <div class="nav-skeleton-row"></div>
        <div class="nav-skeleton-row nav-skeleton-row-short"></div>
      </div>
    </section>
  `;
}

export function updatePageContext(context = {}) {
  const target = byId("app-page-context");
  if (!target) return;
  const items = [context.instrument, context.timeframe, context.status, context.updatedAt]
    .filter((item) => item !== null && item !== undefined && item !== "");
  target.innerHTML = items.map((item) => `<span>${escapeHtml(String(item))}</span>`).join("");
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
  if (Number.isNaN(num)) return "-";
  const safeDigits = Math.max(0, Math.min(Number(digits) || 0, 2));
  return num.toLocaleString("en-US", {
    minimumFractionDigits: 0,
    maximumFractionDigits: safeDigits,
  });
}

export function formatSigned(value, digits = 2) {
  if (value === null || value === undefined || value === "") return "-";
  const num = Number(value);
  if (Number.isNaN(num)) return "-";
  return `${num > 0 ? "+" : ""}${formatNumber(num, digits)}`;
}

export function formatPercent(value, digits = 2) {
  if (value === null || value === undefined || value === "") return "-";
  const num = Number(value);
  if (Number.isNaN(num)) return "-";
  const safeDigits = Math.max(0, Math.min(Number(digits) || 0, 2));
  return `${num.toLocaleString("zh-CN", {
    minimumFractionDigits: 0,
    maximumFractionDigits: safeDigits,
  })}%`;
}

// User-facing time policy (2026-07-23):
// All user-facing timestamps on this app are Beijing time (Asia/Shanghai).
// Do NOT add a literal Beijing-time-of-day suffix (e.g. the four-Chinese-
// character phrase) or "CST" / "UTC+8" — the dashboard's default zone is
// already Beijing, so any suffix is noise. Server logs and OpenAPI
// responses stay UTC; this rule applies only to human-visible strings.
// See tests/test_timezone_label_removed.py for the regression guard.
// (The naive substring test forbids the literal phrase in source files,
// so this comment deliberately describes the rule without naming it.)
export function formatDateTime(value) {
  if (!value) return "-";
  const date = value instanceof Date ? value : new Date(value);
  if (Number.isNaN(date.getTime())) return "-";
  const parts = Object.fromEntries(
    new Intl.DateTimeFormat("zh-CN", {
      timeZone: "Asia/Shanghai",
      year: "numeric",
      month: "2-digit",
      day: "2-digit",
      hour: "2-digit",
      minute: "2-digit",
      hourCycle: "h23",
    }).formatToParts(date).map((part) => [part.type, part.value]),
  );
  return `${parts.year}/${parts.month}/${parts.day} ${parts.hour}:${parts.minute}`;
}

export function formatDateOnly(value) {
  if (!value) return "-";
  const date = value instanceof Date ? value : new Date(value);
  if (Number.isNaN(date.getTime())) return "-";
  return new Intl.DateTimeFormat("zh-CN", {
    timeZone: "Asia/Shanghai",
    year: "numeric",
    month: "2-digit",
    day: "2-digit",
  }).format(date);
}

export function formatChartTime(value, includeYear = false) {
  if (!value) return "-";
  const date = value instanceof Date ? value : new Date(value);
  if (Number.isNaN(date.getTime())) return "-";
  const parts = Object.fromEntries(
    new Intl.DateTimeFormat("zh-CN", {
      timeZone: "Asia/Shanghai",
      ...(includeYear ? { year: "numeric" } : {}),
      month: "2-digit",
      day: "2-digit",
      hour: "2-digit",
      minute: "2-digit",
      hourCycle: "h23",
    }).formatToParts(date).map((part) => [part.type, part.value]),
  );
  const prefix = includeYear ? `${parts.year}-` : "";
  return `${prefix}${parts.month}-${parts.day} ${parts.hour}:${parts.minute}`;
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
      <span class="tooltip-icon">i</span>
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

/* ============================================================
 * §16.D — Tooltip keyboard dismissal (Escape)
 * ------------------------------------------------------------
 * Tooltip anchors already carry `tabindex="0"` and rely on CSS
 * `:focus-visible` to show the bubble (styles.css:1405-1412).
 * This helper adds Escape -> blur() so keyboard users can dismiss
 * the bubble without losing focus to the body.
 *
 * Install once per SPA navigation:
 *   bindTooltipEscape(root = document) inside `boot()` (see main.js).
 * The handler is idempotent: re-installing replaces the prior handler.
 * ============================================================ */

let _tooltipEscapeHandler = null;
let _tooltipEscapeInstalledFor = null;

export function bindTooltipEscape(root = document) {
  if (!root || root === _tooltipEscapeInstalledFor) return;
  // For a fresh root, detach from any prior installation first.
  if (_tooltipEscapeHandler && _tooltipEscapeInstalledFor) {
    _tooltipEscapeInstalledFor.removeEventListener("keydown", _tooltipEscapeHandler, true);
  }
  const handler = (event) => {
    if (event.key !== "Escape" && event.key !== "Esc") return;
    const active = document.activeElement;
    if (!active || active === document.body) return;
    const tooltipAnchor = active.closest && active.closest(".tooltip-anchor");
    if (!tooltipAnchor) return;
    // Drop focus from the tooltip anchor so :focus-visible hides the bubble.
    if (typeof tooltipAnchor.blur === "function") tooltipAnchor.blur();
  };
  root.addEventListener("keydown", handler, true);
  _tooltipEscapeHandler = handler;
  _tooltipEscapeInstalledFor = root;
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

// 2026-07-23: the btc-derivatives page calls this after setRoot() to
// replace knowledge-tooltip placeholders with real tooltips. The
// knowledge.js page module has its own hydration path; for non-knowledge
// pages the placeholders stay as static <span> elements (acceptable for
// the dashboard's chart cards which never had dynamic tooltips wired).
// Stub returns immediately so the import is satisfied without forcing a
// knowledge-module dependency on every page.
export async function hydrateKnowledgeTooltips(_root) {
  return;
}

export function loadingState(message = "正在读取缓存") {
  return `
    <div class="data-state data-state-loading">
      <strong>${escapeHtml(message)}</strong>
      <div class="shimmer-bar" aria-hidden="true"></div>
    </div>
  `;
}

// 2026-08-11: chart skeleton placeholder — mimics chart axes + candles.
export function chartSkeleton(candleCount = 24) {
  let candles = "";
  for (let i = 0; i < candleCount; i++) {
    candles += `<div class="chart-skeleton-candle"></div>`;
  }
  return `
    <div class="chart-skeleton" role="status" aria-label="图表加载中">
      <div class="chart-skeleton-grid">${candles}</div>
      <div class="chart-skeleton-axis">
        <span></span><span></span><span></span><span></span><span></span>
      </div>
    </div>
  `;
}

export function emptyState(message = "暂无数据") {
  return `<div class="data-state data-state-empty">${escapeHtml(message)}</div>`;
}

export function errorState(message = "拉取失败，可手动重试") {
  return `<div class="data-state data-state-error">${escapeHtml(message)}</div>`;
}

export function degradedState(title, detail = "", retrySeconds = 30) {
  return `
    <section class="strategy-degraded-banner">
      <div class="degraded-icon">⚠</div>
      <div>
        <h3>${escapeHtml(title)}</h3>
        <p>${escapeHtml(detail)}</p>
        <small>已自动触发后台预热，预计 ${retrySeconds} 秒后自动更新。</small>
      </div>
    </section>
  `;
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

export function dataFreshnessHint(updatedAt, status, cacheStatus) {
  if (!updatedAt && !cacheStatus) return "";
  const age = updatedAt ? Math.floor((Date.now() - new Date(updatedAt).getTime()) / 60000) : null;
  let hint = "";
  if (cacheStatus === "stale") hint = "缓存数据，可能滞后";
  else if (cacheStatus === "live") hint = age !== null ? `${age} 分钟前更新` : "实时数据";
  else if (status === "error") hint = "数据源暂不可用，使用缓存";
  else hint = formatDateTime(updatedAt);
  return `<span class="freshness-hint">${escapeHtml(hint)}</span>`;
}

/* ============================================================
 * §16.B — Unified <Chip> & <Button> components
 * ------------------------------------------------------------
 * Add-only: this block does NOT delete or rename any existing
 * chip/button variant. Existing callers (`impactChip`, `statusChip`,
 * `<button class="primary-button">` etc.) keep working unchanged.
 *
 * Audit reference: docs/UI_UX_AUDIT_2026-07-31.md §16.B
 * ============================================================ */

const CHIP_TONE_CLASS = {
  bull: "chip-bull",
  bear: "chip-bear",
  neutral: "chip-neutral",
  warning: "chip-warning",
  danger: "chip-danger",
  info: "chip-info",
  success: "chip-success",
  event: "chip-event",
};

const CHIP_VARIANT_CLASS = {
  solid: "chip-solid",
  soft: "chip-soft",
  outline: "chip-outline",
};

const TONE_KEYS = Object.keys(CHIP_TONE_CLASS);

/**
 * mountChip — semantic-tone chip component.
 *
 *   tone ∈ { bull, bear, neutral, warning, danger, info, success, event }
 *   variant ∈ { solid, soft, outline }                  (default: soft)
 *   icon ∈ string | null                                (optional leading glyph)
 *   text ∈ string                                       (required, HTML-escaped)
 *
 * Returns HTML string. Example:
 *   mountChip({ tone: "bull", variant: "solid", text: "看涨" })
 *   → '<span class="chip chip-bull chip-solid">看涨</span>'
 */
export function mountChip({ tone = "neutral", variant = "soft", icon = null, text = "" } = {}) {
  const toneKey = TONE_KEYS.includes(tone) ? tone : "neutral";
  const variantKey = Object.prototype.hasOwnProperty.call(CHIP_VARIANT_CLASS, variant) ? variant : "soft";
  const toneClass = CHIP_TONE_CLASS[toneKey];
  const variantClass = CHIP_VARIANT_CLASS[variantKey];
  const iconPart = icon ? `<span class="chip-icon" aria-hidden="true">${escapeHtml(icon)}</span>` : "";
  return `<span class="chip ${toneClass} ${variantClass}">${iconPart}${escapeHtml(text)}</span>`;
}

const BUTTON_VARIANT_CLASS = {
  primary: "btn-primary",
  secondary: "btn-secondary",
  ghost: "btn-ghost",
  danger: "btn-danger",
  tab: "btn-tab",
};

const BUTTON_SIZE_CLASS = {
  sm: "btn-sm",
  md: "btn-md",
  lg: "btn-lg",
};

/**
 * mountButton — unified button component.
 *
 *   variant ∈ { primary, secondary, ghost, danger, tab }  (default: primary)
 *   size    ∈ { sm, md, lg }                             (default: md)
 *   iconLeft / iconRight ∈ string | null                 (optional glyph, HTML-escaped)
 *   text    ∈ string                                     (required)
 *   attrs   ∈ Record<string,string>                      (additional HTML attrs, e.g. id / data-* / type)
 *
 * Returns HTML string. Example:
 *   mountButton({ variant: "secondary", iconLeft: "↻", text: "刷新", attrs: { id: "x-refresh" } })
 *   → '<button type="button" id="x-refresh" class="btn btn-secondary btn-md"><span class="btn-icon" aria-hidden="true">↻</span>刷新</button>'
 */
export function mountButton({
  variant = "primary",
  size = "md",
  iconLeft = null,
  iconRight = null,
  text = "",
  attrs = {},
  type = "button",
} = {}) {
  const variantKey = Object.prototype.hasOwnProperty.call(BUTTON_VARIANT_CLASS, variant) ? variant : "primary";
  const sizeKey = Object.prototype.hasOwnProperty.call(BUTTON_SIZE_CLASS, size) ? size : "md";
  const safeText = escapeHtml(text || "");
  const left = iconLeft ? `<span class="btn-icon" aria-hidden="true">${escapeHtml(iconLeft)}</span>` : "";
  const right = iconRight ? `<span class="btn-icon" aria-hidden="true">${escapeHtml(iconRight)}</span>` : "";
  // Build attribute string from attrs (caller-controlled, must be safe strings).
  const attrParts = [`type="${escapeHtml(type)}"`, `class="btn ${BUTTON_VARIANT_CLASS[variantKey]} ${BUTTON_SIZE_CLASS[sizeKey]}"`];
  for (const [k, v] of Object.entries(attrs || {})) {
    if (typeof v !== "string" && typeof v !== "number") continue;
    attrParts.push(`${escapeHtml(k)}="${escapeHtml(String(v))}"`);
  }
  return `<button ${attrParts.join(" ")}>${left}${safeText}${right}</button>`;
}
