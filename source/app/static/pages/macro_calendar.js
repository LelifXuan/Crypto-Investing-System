import { api, invalidateCache } from "../core/api.js";
import {
  escapeHtml,
  formatDateOnly,
  formatDateTime,
  formatNumber,
  impactChip,
  knowledgeTooltip,
  setRoot,
  tooltipWrap,
} from "../core/dom.js";
import { renderDisclosureToggle, setDisclosureState } from "../ui/disclosure.js";
import { createWorkbenchState } from "../core/workbenchState.js?v=operator-core-1";
import { mountWorkbenchUrlState } from "../core/workbenchUrlState.js";
import { mountInspector } from "../ui/inspector.js?v=operator-core-1";
import { markWorkbenchRelations } from "../ui/semanticMotion.js?v=operator-core-1";

const MONTH_NAMES = ["1月", "2月", "3月", "4月", "5月", "6月", "7月", "8月", "9月", "10月", "11月", "12月"];
const WEEKDAY_NAMES = ["一", "二", "三", "四", "五", "六", "日"];

function macroDayId(dateLike) {
  const date = new Date(dateLike);
  if (Number.isNaN(date.getTime())) return "macro:day:unknown";
  const month = String(date.getMonth() + 1).padStart(2, "0");
  const day = String(date.getDate()).padStart(2, "0");
  return `macro:day:${date.getFullYear()}-${month}-${day}`;
}

function macroEventId(item) {
  const key = item?.event_id || item?.event_key || item?.title || "event";
  const scheduledAt = item?.scheduled_at || "unscheduled";
  return `macro:event:${encodeURIComponent(String(key))}:${encodeURIComponent(String(scheduledAt))}`;
}

function addMonths(date, count) {
  return new Date(date.getFullYear(), date.getMonth() + count, 1);
}

function monthStart(date) {
  return new Date(date.getFullYear(), date.getMonth(), 1);
}

function dayOnly(dateLike) {
  const date = new Date(dateLike);
  return new Date(date.getFullYear(), date.getMonth(), date.getDate());
}

function filterCalendarItems(items) {
  const now = new Date();
  const start = addMonths(now, -3);
  const end = addMonths(now, 6);
  return items
    .filter((item) => {
      const scheduled = new Date(item.scheduled_at);
      return scheduled >= start && scheduled <= end;
    })
    .sort((a, b) => new Date(a.scheduled_at) - new Date(b.scheduled_at));
}

function diffDirection(item) {
  const isReleased = String(item.status || "").toLowerCase() === "released";
  const hasActual = item.actual_value_num !== null && item.actual_value_num !== undefined;
  if (!isReleased || !hasActual) {
    return { kind: "", label: "", reason: "", diff: null };
  }
  const actual = Number(item.actual_value_num ?? 0);
  const consensus = Number(item.consensus_value_num ?? 0);
  const diff = Number(item.surprise_num ?? (actual - consensus));
  const key = String(item.event_key || "").toLowerCase();

  if (["fomc", "treasury_refunding", "cn_mof_bond_issuance"].includes(key)) {
    return { kind: "event", label: "事件型", reason: "这类事件更适合结合正文与市场定价判断。", diff };
  }
  if (key.includes("cpi") || key.includes("ppi") || key.includes("pce")) {
    if (diff < 0) return { kind: "bullish", label: "利多", reason: "通胀低于预期通常有利于风险资产。", diff };
    if (diff > 0) return { kind: "bearish", label: "利空", reason: "通胀高于预期通常会压制风险资产。", diff };
    return { kind: "neutral", label: "影响有限", reason: "与预期一致，额外冲击有限。", diff };
  }
  if (key.includes("nfp")) {
    if (diff > 0 && diff <= 80) return { kind: "bullish", label: "利多", reason: "温和强于预期通常强化增长韧性。", diff };
    if (diff < -50 || diff > 120) return { kind: "bearish", label: "利空", reason: "明显偏离预期会加剧利率或增长担忧。", diff };
    return { kind: "neutral", label: "影响有限", reason: "偏离幅度有限。", diff };
  }
  if (key.includes("ism") || key.includes("pmi")) {
    if (diff > 0) return { kind: "bullish", label: "利多", reason: "景气高于预期通常有利于风险偏好。", diff };
    if (diff < 0) return { kind: "bearish", label: "利空", reason: "景气低于预期通常压制风险偏好。", diff };
    return { kind: "neutral", label: "影响有限", reason: "与预期一致。", diff };
  }
  return { kind: "neutral", label: "影响有限", reason: "需要结合上下文判断。", diff };
}

function renderMacroValue(value) {
  if (value === null || value === undefined || value === "") {
    return "";
  }
  return formatNumber(value, 2);
}

function renderMonthGrid(items, activeMonth) {
  const start = monthStart(activeMonth);
  const end = addMonths(start, 1);
  const monthItems = items.filter((item) => {
    const ts = new Date(item.scheduled_at);
    return ts >= start && ts < end;
  });
  const offset = (new Date(start).getDay() + 6) % 7;
  const daysInMonth = new Date(start.getFullYear(), start.getMonth() + 1, 0).getDate();
  const cells = [];

  for (let i = 0; i < offset; i += 1) {
    cells.push('<div class="calendar-day is-empty"></div>');
  }

  for (let day = 1; day <= daysInMonth; day += 1) {
    const date = new Date(start.getFullYear(), start.getMonth(), day);
    const dayItems = monthItems.filter((item) => dayOnly(item.scheduled_at).getTime() === date.getTime());
    const dayId = macroDayId(date);
    const relatedIds = dayItems.map(macroEventId);
    if (dayItems.length) {
      inspectionRegistry.set(dayId, {
        id: dayId,
        type: "macro-day",
        title: `${date.getFullYear()} 年 ${date.getMonth() + 1} 月 ${day} 日`,
        current: { label: "事件数量", value: String(dayItems.length) },
        interpretation: "选择当天事件行可查看已发布数据、预期与影响解读。",
        evidence: dayItems.map((item) => ({
          id: `${dayId}:${macroEventId(item)}`,
          label: item.title || item.event_key || "宏观事件",
          value: String(item.status || "scheduled").toLowerCase() === "released" ? "已发布" : "待发布",
          relatedIds: [macroEventId(item)],
        })),
        sources: [{ name: "宏观日历", status: "unavailable", updatedAt: null }],
        updatedAt: dayItems[0]?.scheduled_at || null,
        relatedIds,
      });
    }
    cells.push(`
      <div class="calendar-day"${dayItems.length ? ` data-workbench-id="${escapeHtml(dayId)}" data-workbench-selectable tabindex="0" role="button" aria-label="查看 ${date.getMonth() + 1} 月 ${day} 日宏观事件"` : ""}>
        <strong>${day}</strong>
        <div class="calendar-dot-list">
          ${dayItems.slice(0, 3).map((item) =>
            tooltipWrap(
              '<span class="calendar-dot"></span>',
              `${item.title} · ${formatDateOnly(item.scheduled_at)}`,
              "tone-neutral",
            ),
          ).join("")}
          ${dayItems.length > 3 ? `<span class="calendar-more">+${dayItems.length - 3}</span>` : ""}
        </div>
      </div>
    `);
  }

  return `
    <div class="calendar-head">
      <button id="calendar-prev-month" class="calendar-month-button" type="button" aria-label="查看上个月" title="上个月">
        <svg viewBox="0 0 20 20" aria-hidden="true"><path d="m12.5 4.5-5 5.5 5 5.5"/></svg>
        <span>上个月</span>
      </button>
      <strong class="calendar-current-month" aria-live="polite">${activeMonth.getFullYear()} 年 ${MONTH_NAMES[activeMonth.getMonth()]}</strong>
      <button id="calendar-next-month" class="calendar-month-button" type="button" aria-label="查看下个月" title="下个月">
        <span>下个月</span>
        <svg viewBox="0 0 20 20" aria-hidden="true"><path d="m7.5 4.5 5 5.5-5 5.5"/></svg>
      </button>
    </div>
    <div class="calendar-weekdays">${WEEKDAY_NAMES.map((name) => `<span>${name}</span>`).join("")}</div>
    <div class="calendar-grid">${cells.join("")}</div>
  `;
}

function renderCalendarTable(items) {
  return `
    <div class="section-head">
      <div>
        <p class="eyebrow">RELEASE BOARD</p>
        <h2>宏观事件明细</h2>
      </div>
    </div>
    <div class="table-wrap">
        <table>
          <thead>
            <tr>
              <th>事件</th>
              <th>时间</th>
              <th>实际</th>
              <th>预期</th>
              <th>前值</th>
              <th>差值</th>
              <th>状态</th>
            </tr>
          </thead>
          ${items.length ? `<tbody>
            ${items.map((item) => {
              const direction = diffDirection(item);
              const isReleased = String(item.status || "").toLowerCase() === "released";
              const actualDisplay = isReleased ? renderMacroValue(item.actual_value_num) : "";
              const consensusDisplay = isReleased ? renderMacroValue(item.consensus_value_num) : "";
              const previousDisplay = isReleased ? renderMacroValue(item.previous_value_num) : "";
              const diffDisplay = direction.diff === null ? "" : `${direction.diff > 0 ? "+" : ""}${formatNumber(direction.diff, 2)}`;
              const statusDisplay = direction.kind ? impactChip(direction.kind, direction.reason) : "";
              const id = macroEventId(item);
              const dayId = macroDayId(item.scheduled_at);
              const inspection = {
                id,
                type: "macro-event",
                title: item.title || item.event_key || "宏观事件",
                current: direction.kind
                  ? { label: "影响", value: direction.label, marketTone: direction.kind }
                  : { label: "状态", value: isReleased ? "已发布" : "等待发布" },
                interpretation: direction.reason || "等待事件发布后解读。",
                evidence: isReleased ? [
                  { id: `${id}:actual`, label: "实际值", value: actualDisplay || "—" },
                  { id: `${id}:consensus`, label: "预期值", value: consensusDisplay || "—" },
                ] : [],
                sources: [{ name: "宏观日历", status: ["live", "stale", "degraded", "unavailable"].includes(item.source_status) ? item.source_status : "unavailable", updatedAt: item.updated_at || null }],
                updatedAt: item.scheduled_at || null,
                relatedIds: [dayId],
              };
              inspectionRegistry.set(id, inspection);
              return `
                <tr data-workbench-id="${id}" data-workbench-selectable tabindex="0" role="button"
                    data-workbench-title="${(item.title || "").replace(/"/g, "&quot;")}"
                    data-workbench-value="${(direction.label || (isReleased ? "已发布" : "等待发布")).replace(/"/g, "&quot;")}"
                    data-workbench-tone="${direction.kind || ""}"
                    data-workbench-interpretation="${(direction.reason || "").replace(/"/g, "&quot;")}"
                    data-workbench-actual="${actualDisplay.replace(/"/g, "&quot;")}"
                    data-workbench-consensus="${consensusDisplay.replace(/"/g, "&quot;")}"
                    data-workbench-updated-at="${item.scheduled_at || ""}"
                    aria-label="查看 ${item.title} 上下文">
                  <td>
                    <strong>${item.title}</strong>
                    <small>${String(item.event_key || "").toUpperCase().replaceAll("_", " ")}</small>
                  </td>
                  <td>${formatDateOnly(item.scheduled_at)}</td>
                  <td>${actualDisplay}</td>
                  <td>${consensusDisplay}</td>
                  <td>${previousDisplay}</td>
                  <td>${diffDisplay ? `<span class="macro-diff macro-diff-${direction.kind}">${diffDisplay}</span>` : ""}</td>
                  <td>${statusDisplay}</td>
                </tr>
              `;
            }).join("")}
          </tbody>` : `<tbody class="macro-table-empty">
            <tr>
              <td colspan="7">
                <div class="macro-empty-state">
                  <strong>当前没有可展示的宏观事件</strong>
                  <span>可能是日历尚未同步或当前月份没有计划内事件。点击「更新日历」重新拉取；同步成功且确无事件时属正常状态。</span>
                  <span class="macro-empty-updated">最近同步：${macroLastSyncedAt ? escapeHtml(formatDateTime(macroLastSyncedAt)) : "尚未同步"}</span>
                </div>
              </td>
            </tr>
          </tbody>`}
        </table>
      </div>
  `;
}

let autoSyncedMacro = false;
// 2026-09-04 (ui-audit P2#13): 空表明细需要真实同步时间,区分
// 「尚未同步」与「同步成功但无事件」。
let macroLastSyncedAt = null;
let workbenchState = null;
let workbenchUrl = null;
let workbenchUnsubscribe = null;
let workbenchInteractionController = null;
let inspector = null;
const inspectionRegistry = new Map();

function ensureMacroWorkbench(root) {
  if (!workbenchState) workbenchState = createWorkbenchState({ scopeId: "macro-calendar" });
  inspector?.destroy();
  inspector = mountInspector(root.querySelector("#macro-inspector"), {
    state: workbenchState,
    returnFocus: () => root.querySelector("#macro-sync-button"),
  });
  workbenchInteractionController?.abort();
  workbenchInteractionController = new AbortController();
  const signal = workbenchInteractionController.signal;
  const selectable = (target) => target instanceof Element ? target.closest("[data-workbench-selectable]") : null;
  root.addEventListener("pointerover", (event) => {
    const element = selectable(event.target);
    const id = element?.dataset.workbenchId;
    const item = id && inspectionRegistry.get(id);
    if (item) workbenchState.preview(item);
  }, { signal });
  root.addEventListener("pointerout", (event) => {
    const element = selectable(event.target);
    if (element && !element.contains(event.relatedTarget)) workbenchState.clearPreview();
  }, { signal });
  root.addEventListener("focusin", (event) => {
    const element = selectable(event.target);
    const id = element?.dataset.workbenchId;
    const item = id && inspectionRegistry.get(id);
    if (item) workbenchState.preview(item);
  }, { signal });
  root.addEventListener("focusout", (event) => {
    const element = selectable(event.target);
    if (element && !element.contains(event.relatedTarget)) workbenchState.clearPreview();
  }, { signal });
  root.addEventListener("click", (event) => {
    const element = selectable(event.target);
    if (!element) return;
    const id = element.dataset.workbenchId;
    const item = id && inspectionRegistry.get(id);
    if (item) workbenchState.select(item, { trigger: element });
  }, { signal });
  root.addEventListener("keydown", (event) => {
    if (event.key !== "Enter" && event.key !== " ") return;
    const element = selectable(event.target);
    if (!element) return;
    event.preventDefault();
    const id = element.dataset.workbenchId;
    const item = id && inspectionRegistry.get(id);
    if (item) workbenchState.select(item, { trigger: element });
  }, { signal });
  workbenchUnsubscribe?.();
  workbenchUnsubscribe = workbenchState.subscribe((snapshot) => {
    markWorkbenchRelations(root, snapshot);
  });
}


// 2026-08-19: market-events-style context bar — unified 3-column card with
// title + inline metrics + actions, replacing the separate summary cards
// and table toolbar. Mirrors the events-context-bar design language.
function renderContextBar(items, isCalendarCollapsed) {
  const released = items.filter((item) => item.status === "released").length;
  const scheduled = items.filter((item) => item.status !== "released").length;
  const fomc = items.filter((item) => String(item.event_key || "").includes("fomc")).length;
  const core = items.filter((item) => ["us_cpi", "us_nfp", "ism_mfg", "ism_srv"].includes(item.event_key)).length;
  return `
    <div class="macro-calendar-head">
      <div class="macro-context-copy">
        <p class="eyebrow">CALENDAR</p>
        <h2 class="page-display-title">宏观日历</h2>
      </div>
      <dl class="macro-metrics-grid">
        <div class="macro-inline-metric">
          <dt>已发布</dt>
          <dd>${released}</dd>
        </div>
        <div class="macro-inline-metric">
          <dt>待发布</dt>
          <dd>${scheduled}</dd>
        </div>
        <div class="macro-inline-metric">
          <dt>FOMC</dt>
          <dd>${fomc}</dd>
        </div>
        <div class="macro-inline-metric">
          <dt>核心发布</dt>
          <dd>${core}</dd>
        </div>
      </dl>
      <div class="macro-context-actions">
        ${renderDisclosureToggle({
          id: "macro-calendar-toggle",
          controls: "macro-calendar-body",
          expanded: !isCalendarCollapsed,
          expandLabel: "展开日历",
          collapseLabel: "收起日历",
          className: "macro-calendar-toggle",
        })}
        <button id="macro-sync-button" class="primary-button compact" type="button">更新日历</button>
      </div>
    </div>
  `;
}

// 骨架占位：与真实结构一致，避免"空白 → 加载中 → 内容"三段跳
function renderCalendarSkeleton() {
  return `
    <section id="macro-calendar-container">
      <article class="card macro-calendar-card is-collapsed">
        <header class="macro-calendar-card-head">
          <div class="macro-calendar-head">
            <div class="macro-context-copy"><p class="eyebrow">CALENDAR</p><h2 class="page-display-title">宏观日历</h2></div>
            <dl class="macro-metrics-grid">
              <div class="skeleton-cell" style="width:64px;height:32px"></div>
              <div class="skeleton-cell" style="width:64px;height:32px"></div>
              <div class="skeleton-cell" style="width:64px;height:32px"></div>
              <div class="skeleton-cell" style="width:64px;height:32px"></div>
            </dl>
            <div class="macro-context-actions">
              ${renderDisclosureToggle({
                controls: "macro-calendar-body",
                expanded: false,
                expandLabel: "展开日历",
                collapseLabel: "收起日历",
                className: "macro-calendar-toggle",
                disabled: true,
              })}
              <button class="primary-button compact" type="button" disabled>更新日历</button>
            </div>
          </div>
        </header>
        <div id="macro-calendar-body" class="macro-calendar-body" hidden></div>
      </article>
      <div class="workbench-page-layout macro-workbench-layout">
        <article id="macro-calendar-detail" class="card macro-calendar-detail-card">
          <div class="skeleton-cell" style="height:200px"></div>
        </article>
        <aside class="workbench-inspector" id="macro-inspector" hidden></aside>
      </div>
    </section>
  `;
}

// 宏观日历卡片：标题行 + 日历网格（标题行在卡片顶部，始终可见）
function renderMacroCalendarCard(items, currentMonth, isCalendarCollapsed) {
  return `
    <article class="card macro-calendar-card${isCalendarCollapsed ? " is-collapsed" : ""}">
      <header class="macro-calendar-card-head">
        ${renderContextBar(items, isCalendarCollapsed)}
      </header>
      <div id="macro-calendar-body" class="macro-calendar-body" ${isCalendarCollapsed ? "hidden" : ""}>
        ${renderMonthGrid(items, currentMonth)}
      </div>
    </article>
  `;
}

// 底栏：context bar 移至页面底部（状态栏上方）
function renderMacroBottomBar(items, isCalendarCollapsed) {
  return `
    <footer class="macro-bottom-bar">
      ${renderContextBar(items, isCalendarCollapsed)}
    </footer>
  `;
}

// 宏观事件明细卡片
function renderMacroDetailCard(items) {
  return `
    <article id="macro-calendar-detail" class="card macro-calendar-detail-card">
      ${renderCalendarTable(items)}
    </article>
  `;
}

export async function renderMacroCalendar({ commands } = {}) {
  if (!workbenchState) workbenchState = createWorkbenchState({ scopeId: "macro-calendar" });
  workbenchUrl = mountWorkbenchUrlState(workbenchState, inspectionRegistry, { fallbackId: "macro-sync-button" });
  let currentMonth = monthStart(new Date());
  let isCalendarCollapsed = true;
  let disposed = false;
  const pageController = new AbortController();
  let loadRevision = 0;
  let refreshInFlight = false;
  let refreshCalendar = async () => {};
  let expandCalendar = () => {};
  commands?.register({ id: "macro:refresh", label: "更新宏观日历", enabled: () => !disposed && !refreshInFlight && Boolean(document.getElementById("macro-sync-button")), run: () => refreshCalendar() });
  commands?.register({ id: "macro:expand", label: "展开宏观日历", run: () => expandCalendar(true) });
  commands?.register({ id: "macro:close-inspector", label: "关闭当前 Inspector", enabled: () => Boolean(workbenchState?.getSnapshot().selection), run: () => workbenchState.clearSelection() });
  let weekdaysScrollHandler = null;
  let fadeRaf = null;
  let workbenchFocusTimer = null;

  const restoreMacroWorkbenchFocus = () => {
    if (workbenchFocusTimer) window.clearTimeout(workbenchFocusTimer);
    workbenchFocusTimer = window.setTimeout(() => {
      workbenchFocusTimer = null;
      const target = document.getElementById("macro-sync-button");
      if (target?.isConnected && !target.disabled) target.focus({ preventScroll: true });
    }, 0);
  };
  setRoot(renderCalendarSkeleton());

  const renderStatus = (message, tone = "neutral") => {
    // Status bar removed — macro calendar page no longer shows a persistent status/banner.
    // Call sites are kept as no-ops so loading/error paths need no individual edits.
  };

  async function load(force = false) {
    const revision = ++loadRevision;
    if (force) invalidateCache("/macro/calendar");
    if (force) renderStatus("正在同步宏观日历", "loading");
    let payload = await api.getMacroCalendar(300, { signal: pageController.signal });
    let items = filterCalendarItems(payload || []);
    macroLastSyncedAt = new Date().toISOString();
    if (false && !items.length && !force && !autoSyncedMacro) {
      autoSyncedMacro = true;
      renderStatus("正在同步宏观日历", "loading");
      await api.refreshMacro();
      invalidateCache("/macro/calendar");
      payload = await api.getMacroCalendar(300);
      items = filterCalendarItems(payload || []);
      renderStatus(items.length ? "数据已就绪" : "同步完成，但暂无宏观事件", items.length ? "success" : "warning");
    }
    if (disposed || revision !== loadRevision) return;

    const container = document.getElementById("macro-calendar-container");
    const selectedId = workbenchState?.getSnapshot().selection?.id || null;
    inspectionRegistry.clear();
    // Replace calendar + detail (inside workbench-layout); inspector stays
    // mounted by ensureMacroWorkbench below.
    container.innerHTML = `
      ${renderMacroCalendarCard(items, currentMonth, isCalendarCollapsed)}
      <div class="workbench-page-layout macro-workbench-layout">
        ${renderMacroDetailCard(items)}
        <aside class="workbench-inspector" id="macro-inspector" hidden></aside>
      </div>
    `;
    ensureMacroWorkbench(document);
    renderStatus(items.length ? "数据已就绪" : "当前范围暂无宏观事件", items.length ? "success" : "info");
    if (selectedId) {
      const updated = inspectionRegistry.get(selectedId);
      if (updated) workbenchState.select(updated, { trigger: document.querySelector(`[data-workbench-id="${CSS.escape(selectedId)}"]`) });
      else {
        workbenchState.clearSelection({ restoreFocus: false });
        restoreMacroWorkbenchFocus();
      }
    }

    workbenchUrl?.dataReady();
    if (weekdaysScrollHandler) {
      window.removeEventListener("scroll", weekdaysScrollHandler);
      weekdaysScrollHandler = null;
    }

    // Bind the weekday fade only while the calendar is visible. Measuring a
    // hidden row yields a zero rect and would otherwise leave it transparent
    // on the first expansion.
    const bindWeekdaysFade = () => {
      const weekdaysRow = document.querySelector(".macro-calendar-card .calendar-weekdays");
      if (!weekdaysRow || weekdaysScrollHandler) return;
      const FADE_DISTANCE = 40;
      const updateFade = () => {
        if (fadeRaf) return;
        fadeRaf = requestAnimationFrame(() => {
          fadeRaf = null;
          const card = weekdaysRow.closest(".macro-calendar-card");
          if (!card || disposed || !weekdaysRow.isConnected) return;
          const cardRect = card.getBoundingClientRect();
          const rowRect = weekdaysRow.getBoundingClientRect();
          // 当星期横栏上沿距卡片顶边（即表头边缘）< FADE_DISTANCE 时渐隐
          const distFromTop = rowRect.top - cardRect.top;
          const opacity = Math.max(0, Math.min(1, distFromTop / FADE_DISTANCE));
          weekdaysRow.style.opacity = String(opacity);
        });
      };
      weekdaysScrollHandler = updateFade;
      window.addEventListener("scroll", weekdaysScrollHandler, { passive: true });
      updateFade();
    };

    if (!isCalendarCollapsed) bindWeekdaysFade();

    expandCalendar = (expanded) => {
      isCalendarCollapsed = !expanded;
      const card = document.querySelector(".macro-calendar-card");
      const body = document.getElementById("macro-calendar-body");
      const button = document.getElementById("macro-calendar-toggle");
      card?.classList.toggle("is-collapsed", isCalendarCollapsed);
      if (body) body.hidden = isCalendarCollapsed;
      setDisclosureState(button, !isCalendarCollapsed);
      if (isCalendarCollapsed && weekdaysScrollHandler) {
        window.removeEventListener("scroll", weekdaysScrollHandler);
        weekdaysScrollHandler = null;
      } else if (!isCalendarCollapsed) {
        bindWeekdaysFade();
      }
    };
    document.getElementById("macro-calendar-toggle")?.addEventListener("click", () => expandCalendar(isCalendarCollapsed));

    document.getElementById("calendar-prev-month").addEventListener("click", async () => {
      workbenchUrl?.clearContext();
      currentMonth = addMonths(currentMonth, -1);
      await load();
    });
    document.getElementById("calendar-next-month").addEventListener("click", async () => {
      workbenchUrl?.clearContext();
      currentMonth = addMonths(currentMonth, 1);
      await load();
    });
    refreshCalendar = async () => {
      if (disposed || refreshInFlight) return;
      refreshInFlight = true;
      const button = document.getElementById("macro-sync-button");
      if (button) {
        button.disabled = true;
        button.textContent = "更新中";
      }
      try {
        renderStatus("正在更新宏观日历", "loading");
        await api.refreshMacro({ signal: pageController.signal });
        if (disposed) return;
        await load(true);
        renderStatus("数据已就绪", "success");
      } finally {
        refreshInFlight = false;
        if (button) {
          button.disabled = false;
          button.textContent = "更新日历";
        }
      }
    };
    document.getElementById("macro-sync-button").addEventListener("click", () => { void refreshCalendar().catch(() => { if (!disposed) renderStatus("更新失败，已保留日历", "warning"); }); }, { signal: pageController.signal });
  }

  const loadPromise = load().catch((error) => {
    if (!disposed) workbenchUrl?.dataReady();
    if (!disposed) console.error("macro-calendar:initial-load:error", error);
  });
  return {
    async unmount() {
      disposed = true;
      pageController.abort();
      if (fadeRaf) cancelAnimationFrame(fadeRaf);
      if (weekdaysScrollHandler) {
        window.removeEventListener("scroll", weekdaysScrollHandler);
        weekdaysScrollHandler = null;
      }
      void loadPromise.catch(() => null);
      workbenchUnsubscribe?.();
      workbenchUnsubscribe = null;
      workbenchInteractionController?.abort();
      workbenchInteractionController = null;
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
    async pause() {},
    async resume() {},
  };
}
