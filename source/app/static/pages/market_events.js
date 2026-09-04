import { api, invalidateCache } from "../core/api.js";
import { appState, persistState } from "../core/state.js";
import {
  escapeHtml,
  formatDateOnly,
  revealStagger,
  setRoot,
  skeletonPhaseStyle,
} from "../core/dom.js";
import { mountDropdown } from "../ui/dropdown.js";
import { renderDisclosureToggle } from "../ui/disclosure.js";
import { createWorkbenchState } from "../core/workbenchState.js?v=operator-core-1";
import { mountWorkbenchUrlState } from "../core/workbenchUrlState.js";
import { mountContextRail } from "../ui/contextRail.js";
import { mountInspector } from "../ui/inspector.js?v=operator-core-1";
import { markWorkbenchRelations } from "../ui/semanticMotion.js?v=operator-core-1";

let autoSyncedEvents = false;
let translationPollTimer = null;

// 渲染去重:上一次渲染的指纹 + 缓存。无变化的刷新直接跳过 innerHTML 重建。
let lastFeedFingerprint = "";
let lastCalendarFingerprint = "";
let orderedItemsCache = [];
// 供给日历缓存(60s),避免每次 load 都重复请求同一批节点。
let calendarCachePayload = null;
let calendarCacheAt = 0;
const CALENDAR_TTL_MS = 60 * 1000;
// 当前供给日历筛选值(模块级,筛选切换时局部更新 list 容器)。
let currentCalendarFilter = "all";
let isSupplyCalendarCollapsed = true;
// 竞态防护:进行中的 load 请求统一走一个 AbortController。
let loadController = null;
let workbenchState = null;
let workbenchUrl = null;
let workbenchUnsubscribe = null;
let workbenchInteractionController = null;
let contextRail = null;
let inspector = null;
let workbenchFocusTimer = null;
const inspectionRegistry = new Map();

function restoreEventsWorkbenchFocus() {
  if (workbenchFocusTimer) window.clearTimeout(workbenchFocusTimer);
  workbenchFocusTimer = window.setTimeout(() => {
    workbenchFocusTimer = null;
    const target = document.getElementById("events-refresh");
    if (target?.isConnected && !target.disabled) target.focus({ preventScroll: true });
  }, 0);
}

function inspectionAttrs(item) {
  if (!item?.id) return "";
  inspectionRegistry.set(item.id, item);
  return `data-workbench-id="${escapeHtml(item.id)}" data-workbench-selectable tabindex="0" role="button" aria-label="查看 ${escapeHtml(item.title)} 的上下文"`;
}

function buildEventInspection(item, relatedIds = []) {
  if (!item?.event_id) return null;
  const id = `events:item:${item.event_id}`;
  return {
    id,
    type: "market-event",
    title: item.title || "未命名事件",
    current: item.sentiment_label || item.impact_label ? { label: "影响", value: item.sentiment_label || item.impact_label } : null,
    interpretation: item.summary || "",
    evidence: item.instrument_ids?.length ? [{
      id: `${id}:related`,
      label: "关联品种",
      value: item.instrument_ids.join(" · "),
      relatedIds,
    }] : [],
    sources: item.source ? [{
      name: item.source,
      status: ["live", "stale", "degraded", "unavailable"].includes(item.source_status) ? item.source_status : "unavailable",
      updatedAt: item.ts_event || null,
    }] : [],
    updatedAt: item.ts_event || null,
    relatedIds,
  };
}

function ensureEventsWorkbench(root) {
  if (!workbenchState) workbenchState = createWorkbenchState({ scopeId: "market-events" });
  contextRail?.destroy();
  inspector?.destroy();
  contextRail = mountContextRail(root.querySelector("#events-context-rail"));
  inspector = mountInspector(root.querySelector("#events-inspector"), {
    state: workbenchState,
    returnFocus: () => root.querySelector("#events-refresh"),
  });
  workbenchInteractionController?.abort();
  workbenchInteractionController = new AbortController();
  const signal = workbenchInteractionController.signal;
  const selectable = (target) => target instanceof Element ? target.closest("[data-workbench-selectable]") : null;
  root.addEventListener("pointerover", (event) => {
    const element = selectable(event.target);
    const item = element && inspectionRegistry.get(element.dataset.workbenchId);
    if (item) workbenchState.preview(item);
  }, { signal });
  root.addEventListener("pointerout", (event) => {
    const element = selectable(event.target);
    if (element && !element.contains(event.relatedTarget)) workbenchState.clearPreview();
  }, { signal });
  root.addEventListener("focusin", (event) => {
    const element = selectable(event.target);
    const item = element && inspectionRegistry.get(element.dataset.workbenchId);
    if (item) workbenchState.preview(item);
  }, { signal });
  root.addEventListener("focusout", (event) => {
    const element = selectable(event.target);
    if (element && !element.contains(event.relatedTarget)) workbenchState.clearPreview();
  }, { signal });
  root.addEventListener("click", (event) => {
    const element = selectable(event.target);
    if (!element) return;
    // Don't intercept event-freeze button — let its own handler run.
    if (event.target.closest("[data-event-freeze]")) return;
    const item = inspectionRegistry.get(element.dataset.workbenchId);
    if (item) workbenchState.select(item, { trigger: element });
  }, { signal });
  root.addEventListener("keydown", (event) => {
    if (event.key !== "Enter" && event.key !== " ") return;
    const element = selectable(event.target);
    if (!element) return;
    if (event.target.closest("[data-event-freeze]")) return;
    event.preventDefault();
    const item = inspectionRegistry.get(element.dataset.workbenchId);
    if (item) workbenchState.select(item, { trigger: element });
  }, { signal });
  workbenchUnsubscribe?.();
  workbenchUnsubscribe = workbenchState.subscribe((snapshot) => {
    markWorkbenchRelations(root, snapshot);
  });
}

const SUPPLY_FILTER_LABELS = {
  all: "全部解锁节点",
  scheduled_unlock: "计划解锁",
  committed_claim: "承诺领取",
  actual_claim: "实际领取",
  unstaking_maturity: "解质押到期",
  sellable_or_exchange_inflow: "可售 / 流入",
  restaked_or_absorbed: "重新质押 / 已吸收",
};

export function decodePossiblyBrokenText(value) {
  if (typeof value !== "string" || !value) return value;
  return value
    .replace(/\uFFFDs/g, "'s")
    .replace(/\u25A1s/g, "'s")
    .replace(/\uFFFD([^']{2,80}?)\uFFFD/g, '"$1"')
    .replace(/\uFFFD/g, "'")
    .replace(new RegExp("\\u95b3\\u30e6\\u7368", "g"), "'s")
    .replace(new RegExp("\\u95b3\\?", "g"), "'")
    .replace(/\s{2,}/g, " ")
    .trim();
}

function text(value, fallback = "-") {
  if (value === null || value === undefined || value === "") return fallback;
  return decodePossiblyBrokenText(String(value));
}

function groupEvents(items) {
  const groups = { macro: [], exchange: [], other: [] };
  items.forEach((item) => {
    if (item.category === "macro" || item.category === "regulatory") {
      groups.macro.push(item);
    } else if (item.category === "exchange") {
      groups.exchange.push(item);
    } else {
      groups.other.push(item);
    }
  });
  return groups;
}

function eventCategoryLabel(value) {
  if (value === "macro") return "宏观";
  if (value === "regulatory") return "监管";
  if (value === "exchange") return "交易所";
  return "其他";
}

function eventCategoryKey(value) {
  return ["macro", "regulatory", "exchange"].includes(value) ? value : "other";
}

function translationStatusLabel(value) {
  const mapping = {
    translated: "",
    pending: "翻译中",
    queued: "翻译中",
    skipped: "无需翻译",
    disabled: "",
    error: "中文翻译暂不可用，已显示原文",
    failed: "中文翻译暂不可用，已显示原文",
  };
  return mapping[value] ?? "";
}

function translationChipMarkup(payload, item) {
  if (!appState.translateEvents) return "";
  const status = payload.translation_status || item.translation_status || "";
  const label = translationStatusLabel(status);
  if (!label) return "";
  const isBusy = status === "pending" || status === "queued";
  const dot = isBusy ? `<span class="translation-dot" aria-hidden="true"></span>` : "";
  return `<span class="status-chip chip-translating">${dot}${escapeHtml(label)}</span>`;
}

function renderEventFeed(items) {
  const idsByCategory = new Map();
  items.forEach((item) => {
    if (!item?.event_id) return;
    const category = eventCategoryKey(item.category);
    const ids = idsByCategory.get(category) || [];
    ids.push(`events:item:${item.event_id}`);
    idsByCategory.set(category, ids);
  });
  const cards = items.length
    ? items
        .map((item) => {
          const payload = item.payload_json || {};
          const useTranslation = appState.translateEvents;
          const title =
            useTranslation && (payload.translated_title || item.translated_title)
              ? payload.translated_title || item.translated_title
              : item.title;
          const summary = text(
            useTranslation && (payload.translated_summary || item.translated_summary)
              ? payload.translated_summary || item.translated_summary
              : item.summary,
            "",
          );
          // 2026-08-11: 冻结状态标记 + 按钮
          const isFrozen = item.is_frozen === true;
          const frozenClass = isFrozen ? " is-frozen" : "";
          const freezeBtn = isFrozen
            ? `<button class="event-freeze-btn is-frozen" data-event-freeze="${item.event_id}" title="解冻事件">🔒</button>`
            : `<button class="event-freeze-btn" data-event-freeze="${item.event_id}" title="冻结事件（防止管道覆盖）">🔓</button>`;
          const categoryIds = idsByCategory.get(eventCategoryKey(item.category)) || [];
          const inspection = buildEventInspection(
            item,
            categoryIds.filter((id) => id !== `events:item:${item.event_id}`),
          );
          return `
            <article class="event-card event-feed-item${frozenClass}" data-event-id="${item.event_id}"${inspection ? ` ${inspectionAttrs(inspection)}` : ""}>
              <div class="event-feed-meta">
                <div class="event-feed-tags">
                  <span class="status-chip" data-event-category="${eventCategoryKey(item.category)}">${escapeHtml(eventCategoryLabel(item.category))}</span>
                  ${item.source ? `<span class="event-feed-source">${escapeHtml(text(item.source, ""))}</span>` : ""}
                  ${translationChipMarkup(payload, item)}
                  ${isFrozen ? `<span class="event-frozen-badge">已固化</span>` : ""}
                </div>
                <div class="event-feed-meta-right">
                  <small>${escapeHtml(formatDateOnly(item.ts_event))}</small>
                  ${freezeBtn}
                </div>
              </div>
              <strong>${escapeHtml(text(title, "-"))}</strong>
              ${summary ? `<p>${escapeHtml(summary)}</p>` : ""}
            </article>
          `;
        })
        .join("")
    : '<div class="compact-empty">当前信息流暂无内容。</div>';

  return `
    <article class="card events-feed-card">
      <div class="section-head">
        <div>
          <p class="eyebrow">EVENT FEED</p>
          <h2>最新信息流</h2>
        </div>
        <div class="events-feed-actions">
          <button id="events-translate-toggle" class="ghost-button compact" type="button">${appState.translateEvents ? "关闭中文翻译" : "开启中文翻译"}</button>
          <button id="events-refresh" class="primary-button compact" type="button">刷新信息流</button>
        </div>
      </div>
      <div class="event-feed">${cards}</div>
    </article>
  `;
}

function renderEventFeedLoading() {
  const rows = Array.from({ length: 6 }, (_, index) => `
    <div class="event-stream-skeleton-row" style="--event-row: ${index}" aria-hidden="true">
      <span class="event-stream-skeleton-dot"></span>
      <span class="event-stream-skeleton-copy">
        <i style="${skeletonPhaseStyle(index * 3)}"></i>
        <i style="${skeletonPhaseStyle(index * 3 + 1)}"></i>
        <i style="${skeletonPhaseStyle(index * 3 + 2)}"></i>
      </span>
    </div>
  `).join("");
  return `
    <article class="card events-feed-card events-feed-loading" role="status" aria-label="正在接入市场信息流">
      <div class="event-feed-loading-head">
        <div>
          <p class="eyebrow">EVENT FEED</p>
          <h2>正在接入信息流</h2>
        </div>
        <div class="events-feed-actions">
          <button id="events-translate-toggle" class="ghost-button compact" type="button">${appState.translateEvents ? "关闭中文翻译" : "开启中文翻译"}</button>
          <button id="events-refresh" class="primary-button compact" type="button">刷新信息流</button>
        </div>
      </div>
      <div class="event-stream-skeleton">${rows}</div>
    </article>
  `;
}

function setFeedBusy(isBusy) {
  const feed = document.getElementById("events-feed");
  if (!feed) return;
  feed.classList.toggle("is-syncing", isBusy);
  feed.setAttribute("aria-busy", String(isBusy));
}

function supplyNodeLabel(value) {
  const labels = {
    scheduled_unlock: "计划解锁",
    committed_claim: "承诺领取",
    actual_claim: "实际领取",
    unstaking_started: "发起解质押",
    unstaking_maturity: "解质押到期",
    sellable_or_exchange_inflow: "可售 / 交易所流入",
    restaked_or_absorbed: "重新质押 / 已吸收",
  };
  return labels[value] || value;
}

function supplyCalendarDateParts(value) {
  const date = new Date(value);
  if (Number.isNaN(date.getTime())) {
    return { year: "未知年份", monthDay: "--/--", weekday: "日期待确认" };
  }
  const year = String(date.getFullYear());
  const month = String(date.getMonth() + 1).padStart(2, "0");
  const day = String(date.getDate()).padStart(2, "0");
  const weekday = new Intl.DateTimeFormat("zh-CN", { weekday: "short" }).format(date);
  return { year, monthDay: `${month}/${day}`, weekday };
}

function supplyInstrumentLabel(value) {
  const raw = text(value, "-");
  return raw
    .replace(/-usdt-perp$/i, " 永续")
    .replace(/-/g, " ")
    .replace(/\bperp\b/i, "永续");
}

function supplyEvidenceLabel(snapshotId) {
  const value = text(snapshotId, "");
  if (!value) return "证据待补充";
  if (value.toLowerCase().includes("whitepaper")) return "白皮书快照";
  return "研究快照";
}

function compactNumber(value, maximumFractionDigits = 2) {
  const numeric = Number(value);
  if (!Number.isFinite(numeric)) return "-";
  return new Intl.NumberFormat("zh-CN", {
    notation: "compact",
    maximumFractionDigits,
  }).format(numeric);
}

function supplyQuantityLabel(item) {
  if (item.unlock_quantity === null || item.unlock_quantity === undefined) return "数量待确认";
  return `${compactNumber(item.unlock_quantity)} ${item.asset || ""}`.trim();
}

function usdValueLabel(value) {
  const numeric = Number(value);
  if (!Number.isFinite(numeric)) return "价值待确认";
  return `US$${compactNumber(numeric)}`;
}

function markPriceLabel(value) {
  const numeric = Number(value);
  if (!Number.isFinite(numeric)) return "现价待确认";
  return `按 US$${new Intl.NumberFormat("en-US", { maximumFractionDigits: 4 }).format(numeric)}`;
}

function supplyCalendarListHtml(items, filter = "all") {
  const visible = filter === "all"
    ? items
    : items.filter((item) => item.node_type === filter);
  if (!visible.length) {
    return '<div class="compact-empty">当前筛选范围内没有未来供给事件。</div>';
  }
  const groups = new Map();
  visible.forEach((item) => {
    const parts = supplyCalendarDateParts(item.event_at);
    if (!groups.has(parts.year)) groups.set(parts.year, []);
    groups.get(parts.year).push({ item, parts });
  });

  return [...groups.entries()].map(([year, entries], groupIndex) => `
    <section class="supply-calendar-year" aria-labelledby="supply-year-${escapeHtml(year)}">
      <header class="supply-calendar-year-head">
        <strong id="supply-year-${escapeHtml(year)}">${escapeHtml(year)}</strong>
        <span>${entries.length} 个节点</span>
      </header>
      <div class="supply-calendar-ledger">
        ${entries.map(({ item, parts }, index) => `
          <article class="supply-calendar-node ${groupIndex === 0 && index === 0 ? "is-next" : ""}"
                   data-node-type="${escapeHtml(item.node_type)}">
            <time datetime="${escapeHtml(item.event_at)}" class="supply-calendar-date">
              <strong>${escapeHtml(parts.monthDay)}</strong>
              <span>${escapeHtml(parts.weekday)}</span>
            </time>
            <span class="supply-calendar-track" aria-hidden="true">
              <span class="supply-node-dot is-${escapeHtml(item.node_type)}"></span>
            </span>
            <div class="supply-calendar-event">
              <span class="supply-calendar-kicker">${groupIndex === 0 && index === 0 ? "NEXT NODE" : "SUPPLY NODE"}</span>
              <strong>${escapeHtml(supplyNodeLabel(item.node_type))}</strong>
              <small>${escapeHtml(item.allocation || "分配对象待确认")}</small>
            </div>
            <div class="supply-calendar-asset">
              <span>${escapeHtml(item.asset || "-")}</span>
              <small>${escapeHtml(supplyInstrumentLabel(item.instrument_id))}</small>
            </div>
            <div class="supply-calendar-amount">
              <span>${escapeHtml(supplyQuantityLabel(item))}</span>
              <small>${item.release_pct === null || item.release_pct === undefined ? "占比待确认" : `释放进度 ${escapeHtml(String(item.release_pct))}%`}</small>
            </div>
            <div class="supply-calendar-value">
              <span>${escapeHtml(usdValueLabel(item.market_value))}</span>
              <small>${escapeHtml(markPriceLabel(item.mark_price))}</small>
            </div>
            <div class="supply-calendar-evidence" title="${escapeHtml(item.snapshot_id || "")}">
              <span>${escapeHtml(supplyEvidenceLabel(item.snapshot_id))}</span>
              <small>${escapeHtml(item.source || "事件证据")}</small>
            </div>
          </article>
        `).join("")}
      </div>
    </section>
  `).join("");
}

function supplyCoverageHtml(coverage) {
  if (!coverage.length) return "";
  return `
    <aside class="supply-calendar-coverage" aria-label="未排期资产">
      <div class="supply-coverage-intro">
        <span class="supply-calendar-kicker">UNSCHEDULED COVERAGE</span>
        <strong>无可核验日期</strong>
        <p>保留资产覆盖，但不把未公布日期的余额伪造成未来节点。</p>
      </div>
      ${coverage.map((item) => `
        <div class="supply-coverage-asset">
          <div><strong>${escapeHtml(item.asset)}</strong><small>${escapeHtml(supplyInstrumentLabel(item.instrument_id))}</small></div>
          <div><strong>${escapeHtml(compactNumber(item.remaining_quantity))} ${escapeHtml(item.asset)}</strong><small>未排期余额</small></div>
          <div><strong>${escapeHtml(usdValueLabel(item.market_value))}</strong><small>${escapeHtml(markPriceLabel(item.mark_price))}</small></div>
          <div><strong>暂无未来节点</strong><small>${escapeHtml(item.source || "来源待确认")}</small></div>
        </div>
      `).join("")}
    </aside>
  `;
}

function renderSupplyCalendarCard(items, coverage = [], filter = "all") {
  const filteredItems = filter === "all" ? items : items.filter((item) => item.node_type === filter);
  const assetCount = new Set([
    ...filteredItems.map((item) => item.asset),
    ...coverage.map((item) => item.asset),
  ].filter(Boolean)).size;
  const lastEvent = filteredItems.at(-1);
  const coverageEnd = lastEvent ? formatDateOnly(lastEvent.event_at) : "-";
  return `
    <article class="card supply-calendar-card ${isSupplyCalendarCollapsed ? "is-collapsed" : ""}">
      <div class="section-head">
        <div>
          <p class="eyebrow">STAKING UNLOCK CALENDAR</p>
          <h2>质押解锁日历</h2>
          <p class="section-summary">追踪可核验的计划解锁与解质押到期节点；数量按代币计量，价值使用最新本地标记价动态估算。</p>
        </div>
        <div class="supply-calendar-actions">
          <button class="dropdown supply-calendar-filter"
                  data-dropdown-id="supply-calendar-filter"
                  data-dropdown-size="compact"
                  type="button"
                  aria-label="解锁事件类型"
                  aria-haspopup="listbox"
                  aria-expanded="false">
            <span class="dropdown-icon" data-slot="icon" hidden></span>
            <span class="dropdown-label">${escapeHtml(SUPPLY_FILTER_LABELS[filter] || SUPPLY_FILTER_LABELS.all)}</span>
            <span class="dropdown-arrow" aria-hidden="true"><svg viewBox="0 0 10 10" width="11" height="11"><path d="M2 4l3 3 3-3" fill="none" stroke="currentColor" stroke-width="1.4" stroke-linecap="round" stroke-linejoin="round"/></svg></span>
          </button>
          ${renderDisclosureToggle({
            controls: "supply-calendar-body",
            expanded: !isSupplyCalendarCollapsed,
            expandLabel: "展开日历",
            collapseLabel: "收起日历",
            className: "supply-calendar-toggle",
          })}
        </div>
      </div>
      <div id="supply-calendar-body" class="supply-calendar-body" ${isSupplyCalendarCollapsed ? "hidden" : ""}>
        <div class="supply-calendar-summary" aria-label="日历摘要">
          <span><small>已排期节点</small><strong>${filteredItems.length}</strong><em>个节点</em></span>
          <span><small>覆盖资产</small><strong>${assetCount}</strong><em>个资产</em></span>
          <span><small>排期覆盖至</small><strong>${escapeHtml(coverageEnd)}</strong><em>UTC 日期</em></span>
        </div>
        ${supplyCoverageHtml(coverage)}
        <div class="supply-calendar-list">${supplyCalendarListHtml(items, filter)}</div>
      </div>
    </article>
  `;
}

function bindSupplyCalendarControls(root, items, coverage) {
  const filterRoot = root.querySelector('.dropdown[data-dropdown-id="supply-calendar-filter"]');
  if (filterRoot) {
    mountDropdown(filterRoot, {
      items: Object.entries(SUPPLY_FILTER_LABELS).map(([value, label]) => ({ value, label })),
      value: currentCalendarFilter,
      placeholder: "选择事件类型",
      density: "compact",
      maxVisibleItems: 7,
      onChange: (v) => {
        currentCalendarFilter = v;
        // 局部更新:只重建列表容器,保留 dropdown 实例与卡片外壳。
        const list = root.querySelector(".supply-calendar-list");
        if (list) list.innerHTML = supplyCalendarListHtml(items, v);
        const selected = v === "all" ? items : items.filter((item) => item.node_type === v);
        const summary = root.querySelector(".supply-calendar-summary");
        if (summary) {
          const assets = new Set([
            ...selected.map((item) => item.asset),
            ...coverage.map((item) => item.asset),
          ].filter(Boolean)).size;
          const end = selected.at(-1)?.event_at;
          summary.innerHTML = `
            <span><small>当前视图</small><strong>${selected.length}</strong><em>个节点</em></span>
            <span><small>涉及资产</small><strong>${assets}</strong><em>个资产</em></span>
            <span><small>覆盖至</small><strong>${escapeHtml(end ? formatDateOnly(end) : "-")}</strong><em>UTC 日期</em></span>
          `;
        }
      },
    });
  }
  root.querySelector(".supply-calendar-toggle")?.addEventListener("click", () => {
    isSupplyCalendarCollapsed = !isSupplyCalendarCollapsed;
    root.innerHTML = renderSupplyCalendarCard(items, coverage, currentCalendarFilter);
    bindSupplyCalendarControls(root, items, coverage);
    if (isSupplyCalendarCollapsed) {
      document.getElementById("events-feed")?.scrollIntoView({ block: "start", behavior: "smooth" });
    }
  });
}

function stopTranslationPolling() {
  if (translationPollTimer) {
    window.clearInterval(translationPollTimer);
    translationPollTimer = null;
  }
}

function abortInFlightLoad() {
  if (loadController) {
    loadController.abort();
    loadController = null;
  }
}

function fingerprintFeed(items) {
  // 渲染指纹:事件正文 + 翻译状态任一变化都会产生新指纹,否则跳过重建。
  return items
    .map((it) => {
      const p = it.payload_json || {};
      return [
        it.event_id || "",
        it.ts_event || "",
        it.title || "",
        it.summary || "",
        p.translated_title || "",
        p.translated_summary || "",
        p.translation_status || "",
      ].join("|");
    })
    .join("\n");
}

async function ensureCalendar(force = false, signal) {
  const now = Date.now();
  if (!force && calendarCachePayload && now - calendarCacheAt < CALENDAR_TTL_MS) {
    return calendarCachePayload;
  }
  try {
    calendarCachePayload = await api.getSupplyEventCalendar({ force, signal });
  } catch (error) {
    // 中止(页面切换/卸载)必须向上抛,不能让空日历覆盖真实渲染。
    if (error?.name === "AbortError") throw error;
    calendarCachePayload = { items: [] };
  }
  calendarCacheAt = Date.now();
  return calendarCachePayload;
}

export async function renderMarketEvents({ commands } = {}) {
  if (!workbenchState) workbenchState = createWorkbenchState({ scopeId: "market-events" });
  workbenchUrl = mountWorkbenchUrlState(workbenchState, inspectionRegistry, { fallbackId: "events-refresh" });
  const pageLifetime = new AbortController();
  let refreshInFlight = false;
  commands?.register({ id: "events:refresh", label: "刷新市场信息流", enabled: () => !refreshInFlight, run: refreshEvents });
  commands?.register({ id: "events:focus-feed", label: "聚焦事件列表", run: () => { const feed = document.getElementById("events-feed"); feed?.setAttribute("tabindex", "-1"); feed?.focus(); } });
  commands?.register({ id: "events:close-inspector", label: "关闭当前 Inspector", enabled: () => Boolean(workbenchState?.getSnapshot().selection), run: () => workbenchState.clearSelection() });
  stopTranslationPolling();
  abortInFlightLoad();
  // The page DOM is rebuilt on every SPA entry, while module-level fingerprints
  // survive. Reset them so an unchanged cached payload still repaints the new
  // page instead of leaving the feed shell blank.
  lastFeedFingerprint = "";
  lastCalendarFingerprint = "";
  setRoot(`
    <div id="events-context-rail"></div>
    <section id="events-supply-calendar"></section>
    <div class="events-actions-bar">
      <!-- The translate + refresh buttons live inside the feed-card header
           (rendered by renderEventFeed / renderEventFeedLoading). This bar
           is kept as an empty anchor so showContinueTranslationButton() can
           still insert the queue-join button when translation stalls. -->
    </div>
    <div class="workbench-page-layout events-workbench-layout">
      <section class="events-feed-shell" id="events-feed" aria-busy="true">${renderEventFeedLoading()}</section>
      <aside class="workbench-inspector" id="events-inspector" hidden></aside>
    </div>
  `);

  const renderStatus = (message, tone = "neutral") => {
    // Status bar removed — events page no longer shows a persistent status/banner.
    // Call sites are kept as no-ops so loading/error paths need no individual edits.
  };

  const clearStatus = () => {
    // No-op — status bar removed.
  };

  async function load(force = false) {
    const controller = new AbortController();
    abortInFlightLoad();
    loadController = controller;
    const signal = controller.signal;
    if (force) invalidateCache("/marketevents");

    // 2026-08-15: fade the feed + metrics + calendar sections before
    const [response, calendarPayload] = await Promise.all([
      api.getMarketEvents(50, appState.translateEvents, { force, signal }),
      ensureCalendar(force, signal),
    ]);
    if (signal.aborted || loadController !== controller) return orderedItemsCache;
    const items = response.items || response || [];

    // Feed:无变化跳过重建(避免 ttl 过期但数据相同时的重复 innerHTML)。
    const feedFingerprint = fingerprintFeed(items);
    if (feedFingerprint !== lastFeedFingerprint) {
      lastFeedFingerprint = feedFingerprint;
      orderedItemsCache = [...items].sort(
        (left, right) =>
          new Date(right.ts_event || 0).getTime() - new Date(left.ts_event || 0).getTime(),
      );
      const selectedId = workbenchState?.getSnapshot().selection?.id || null;
      inspectionRegistry.clear();
      document.getElementById("events-feed").innerHTML = renderEventFeed(orderedItemsCache);
      if (selectedId) {
        const updated = inspectionRegistry.get(selectedId);
        if (updated) workbenchState.select(updated, { trigger: document.querySelector(`[data-workbench-id="${CSS.escape(selectedId)}"]`) });
        else {
          workbenchState.clearSelection({ restoreFocus: false });
          restoreEventsWorkbenchFocus();
        }
      }
      revealStagger(document.getElementById("events-feed"), { selector: ".event-card" });
    }

    // 供给日历:单独指纹,变化时只重建日历卡。
    const calendarItems = calendarPayload?.items || [];
    const calendarCoverage = calendarPayload?.coverage || [];
    const calFingerprint = JSON.stringify({ items: calendarItems, coverage: calendarCoverage });
    if (calFingerprint !== lastCalendarFingerprint) {
      lastCalendarFingerprint = calFingerprint;
      const calendarRoot = document.getElementById("events-supply-calendar");
      calendarRoot.innerHTML = renderSupplyCalendarCard(calendarItems, calendarCoverage, currentCalendarFilter);
      bindSupplyCalendarControls(calendarRoot, calendarItems, calendarCoverage);
    }
    updateEventsContext(true);
    workbenchUrl?.dataReady();
    renderStatus("数据已就绪", "success");
    return orderedItemsCache;
  }

  // 只更新信息流容器(翻译开关切换时用,不重建 metrics/日历)。
  async function loadFeed(force = false) {
    const signal = loadController?.signal;
    if (force) invalidateCache("/marketevents");
    const response = await api.getMarketEvents(50, appState.translateEvents, { force, signal });
    if (signal?.aborted || !workbenchState) return;
    const items = response.items || response || [];
    lastFeedFingerprint = fingerprintFeed(items);
    orderedItemsCache = [...items].sort(
      (left, right) =>
        new Date(right.ts_event || 0).getTime() - new Date(left.ts_event || 0).getTime(),
    );
    const selectedId = workbenchState?.getSnapshot().selection?.id || null;
    inspectionRegistry.clear();
    document.getElementById("events-feed").innerHTML = renderEventFeed(orderedItemsCache);
    if (selectedId) {
      const updated = inspectionRegistry.get(selectedId);
      if (updated) workbenchState.select(updated, { trigger: document.querySelector(`[data-workbench-id="${CSS.escape(selectedId)}"]`) });
      else {
        workbenchState.clearSelection({ restoreFocus: false });
        restoreEventsWorkbenchFocus();
      }
    }
    revealStagger(document.getElementById("events-feed"), { selector: ".event-card" });
    updateEventsContext(true);
    workbenchUrl?.dataReady();
    renderStatus("数据已就绪", "success");
  }

  async function pollTranslations() {
    let pollCount = 0;
    const maxPolls = 40;
    const pollInterval = 3000;
    stopTranslationPolling();
    translationPollTimer = window.setInterval(async () => {
      pollCount += 1;
      try {
        const statusData = await api.getMarketEventTranslationStatus();
        if (statusData.disabled) {
          stopTranslationPolling();
          invalidateCache("/marketevents");
          await load(true);
          renderStatus("中文翻译未启用，已显示原文", "warning");
          return;
        }
        const pending = (statusData.pending || 0) + (statusData.queued || 0) + (statusData.queue_depth || 0);
        if (pending <= 0) {
          stopTranslationPolling();
          invalidateCache("/marketevents");
          await load(true);
          clearStatus();
          return;
        }
        renderStatus("翻译中", "loading");
        if (pollCount >= maxPolls) {
          stopTranslationPolling();
          invalidateCache("/marketevents");
          await load(true);
          renderStatus("翻译中", "loading");
          showContinueTranslationButton();
          return;
        }
      } catch (error) {
        stopTranslationPolling();
        renderStatus(`中文翻译状态读取失败：${String(error?.message || error).slice(0, 40)}`, "warning");
      }
    }, pollInterval);
  }

  function showContinueTranslationButton() {
    const statusbar = document.getElementById("events-actions-bar");
    if (!statusbar) return;
    const existing = document.getElementById("events-continue-translate");
    if (existing) return;
    const button = document.createElement("button");
    button.id = "events-continue-translate";
    button.type = "button";
    button.className = "primary-button compact";
    button.textContent = "继续等待翻译";
    button.addEventListener("click", async () => {
      button.disabled = true;
      button.textContent = "已加入队列";
      try {
        invalidateCache("/marketevents");
        await pollTranslations();
      } finally {
        button.remove();
      }
    });
    statusbar.insertAdjacentElement("afterend", button);
  }

  async function refreshEvents() {
    if (pageLifetime.signal.aborted || refreshInFlight) return;
    refreshInFlight = true;
    const button = document.getElementById("events-refresh");
    button.disabled = true;
    button.textContent = "同步中";
    setFeedBusy(true);
    try {
      renderStatus("正在同步市场信息流", "loading");
      await api.syncMarketEvents({ signal: pageLifetime.signal });
      if (pageLifetime.signal.aborted) return;
      await load(true);
      if (pageLifetime.signal.aborted) return;
      renderStatus("数据已就绪", "success");
    } finally {
      refreshInFlight = false;
      setFeedBusy(false);
      button.disabled = false;
      button.textContent = "刷新信息流";
    }
  }
  // 2026-09-04: 刷新/翻译按钮由 renderEventFeed 生成,feed 指纹重建会替换
  // 按钮 DOM。直接绑定会在第一次重建后失效(点击静默无响应),改为挂在
  // #events-feed 外层 shell 的一次性事件委托;委托监听器随 pageLifetime
  // signal 一并清理。
  document.getElementById("events-feed")?.addEventListener("click", (ev) => {
    if (ev.target.closest("#events-refresh")) {
      void refreshEvents().catch(() => { if (!pageLifetime.signal.aborted) renderStatus("刷新失败，已保留可用信息流", "warning"); });
      return;
    }
    if (ev.target.closest("#events-translate-toggle")) {
      void (async () => {
        appState.translateEvents = !appState.translateEvents;
        persistState();
        const toggleBtn = document.getElementById("events-translate-toggle");
        if (toggleBtn) toggleBtn.textContent = appState.translateEvents ? "关闭中文翻译" : "开启中文翻译";
        if (appState.translateEvents) {
          renderStatus("翻译中", "loading");
          api.refreshMarketEventTranslations({ limit: 50, maxBatches: 10 }).catch(() => {});
          await pollTranslations();
        } else {
          stopTranslationPolling();
          // 只重拉信息流并就地更新,不重建 metrics / 供给日历。
          invalidateCache("/marketevents");
          await loadFeed(true);
          renderStatus("已关闭中文翻译", "success");
        }
      })();
    }
  }, { signal: pageLifetime.signal });

  // 2026-08-11: 冻结/解冻按钮事件委托
  document.getElementById("events-feed")?.addEventListener("click", async (ev) => {
    const btn = ev.target.closest("[data-event-freeze]");
    if (!btn) return;
    const eventId = btn.dataset.eventFreeze;
    const wasFrozen = btn.classList.contains("is-frozen");
    btn.disabled = true;
    try {
      if (wasFrozen) {
        await api.request(`/market-events/${eventId}/unfreeze`, { method: "POST" });
      } else {
        await api.request(`/market-events/${eventId}/freeze`, { method: "POST" });
      }
      // 就地更新按钮状态，不重建整个列表
      btn.classList.toggle("is-frozen");
      btn.title = wasFrozen ? "冻结事件（防止管道覆盖）" : "解冻事件";
      btn.textContent = wasFrozen ? "🔓" : "🔒";
      // 更新卡片冻结视觉
      const card = btn.closest(".event-card");
      if (card) card.classList.toggle("is-frozen", !wasFrozen);
    } catch (err) {
      console.error("market-events:freeze:error", err);
    } finally {
      btn.disabled = false;
    }
  });

  const loadPromise = load().catch((error) => {
    if (error?.name === "AbortError") return; // 页面切换/卸载,静默。
    workbenchUrl?.dataReady();
    console.error("market-events:initial-load:error", error);
    const feed = document.getElementById("events-feed");
    if (feed) feed.innerHTML = '<div class="compact-empty">信息流暂时无法连接，请稍后刷新。</div>';
  }).finally(() => {
    setFeedBusy(false);
  });
  ensureEventsWorkbench(document);
  updateEventsContext();
  return {
    async unmount() {
      pageLifetime.abort();
      stopTranslationPolling();
      abortInFlightLoad();
      void loadPromise.catch(() => null);
      workbenchUnsubscribe?.();
      workbenchUnsubscribe = null;
      workbenchInteractionController?.abort();
      workbenchInteractionController = null;
      contextRail?.destroy();
      contextRail = null;
      inspector?.destroy();
      inspector = null;
      workbenchUrl?.destroy();
      workbenchUrl = null;
      workbenchState?.destroy();
      workbenchState = null;
      if (workbenchFocusTimer) window.clearTimeout(workbenchFocusTimer);
      workbenchFocusTimer = null;
      inspectionRegistry.clear();
    },
    async pause() {
      // 页面隐藏:停轮询并中止在途请求,避免后台空转。
      stopTranslationPolling();
      abortInFlightLoad();
    },
    async resume() {
      // 回到前台:重新拉一次最新数据(指纹 diff 会挡掉无变化的重建)。
      if (typeof load !== "function") return;
      try {
        await load();
      } catch (error) {
        if (error?.name === "AbortError") return;
        console.error("market-events:resume:load:error", error);
      }
    },
  };
}

function updateEventsContext(loaded = false) {
  const items = orderedItemsCache || [];
  const lastTs = items[0]?.ts_event || null;
  const sources = [...new Set(items.map((item) => item.source).filter(Boolean))];
  contextRail?.update({
    instrument: "市场信息流",
    primaryValue: loaded ? `${items.length} 条` : undefined,
    timeframe: appState.translateEvents ? "已开启中文翻译" : "原文",
    marketRisk: undefined,
    freshness: {
      label: "最新事件",
      value: loaded && lastTs ? formatDateOnly(lastTs) : (loaded ? "暂无事件" : "正在读取"),
      status: "unavailable",
    },
    sourceSummary: {
      value: sources.length ? sources.join(" · ") : "信源待确认",
      status: "unavailable",
    },
  });
}
