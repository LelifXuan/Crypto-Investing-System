import { api, invalidateCache } from "../core/api.js";
import {
  formatDateOnly,
  formatNumber,
  impactChip,
  knowledgeTooltip,
  setRoot,
  statusBanner,
  tooltipWrap,
} from "../core/dom.js";
import { renderDisclosureToggle, setDisclosureState } from "../ui/disclosure.js";

const MONTH_NAMES = ["1月", "2月", "3月", "4月", "5月", "6月", "7月", "8月", "9月", "10月", "11月", "12月"];
const WEEKDAY_NAMES = ["一", "二", "三", "四", "五", "六", "日"];

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
    cells.push(`
      <div class="calendar-day">
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
          <tbody>
            ${items.map((item) => {
              const direction = diffDirection(item);
              const isReleased = String(item.status || "").toLowerCase() === "released";
              const actualDisplay = isReleased ? renderMacroValue(item.actual_value_num) : "";
              const consensusDisplay = isReleased ? renderMacroValue(item.consensus_value_num) : "";
              const previousDisplay = isReleased ? renderMacroValue(item.previous_value_num) : "";
              const diffDisplay = direction.diff === null ? "" : `${direction.diff > 0 ? "+" : ""}${formatNumber(direction.diff, 2)}`;
              const statusDisplay = direction.kind ? impactChip(direction.kind, direction.reason) : "";
              return `
                <tr>
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
          </tbody>
        </table>
      </div>
  `;
}

let autoSyncedMacro = false;

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
        <h2>宏观日历</h2>
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
        <div class="macro-calendar-head">
          <div class="macro-context-copy"><p class="eyebrow">CALENDAR</p><h2>宏观日历</h2></div>
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
      </article>
      <article id="macro-calendar-detail" class="card macro-calendar-detail-card">
        <div class="skeleton-cell" style="height:200px"></div>
      </article>
    </section>
    <footer id="macro-statusbar" class="macro-statusbar">${statusBanner("正在读取日历数据", "loading")}</footer>
  `;
}

// 宏观日历卡片：context bar + 日历网格
function renderMacroCalendarCard(items, currentMonth, isCalendarCollapsed) {
  return `
    <article class="card macro-calendar-card${isCalendarCollapsed ? " is-collapsed" : ""}">
      ${renderContextBar(items, isCalendarCollapsed)}
      <div id="macro-calendar-body" class="macro-calendar-body" ${isCalendarCollapsed ? "hidden" : ""}>
        ${renderMonthGrid(items, currentMonth)}
      </div>
    </article>
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

export async function renderMacroCalendar() {
  let currentMonth = monthStart(new Date());
  let isCalendarCollapsed = true;
  let disposed = false;
  let weekdaysScrollHandler = null;
  setRoot(renderCalendarSkeleton());

  const renderStatus = (message, tone = "neutral") => {
    const el = document.getElementById("macro-statusbar");
    if (el) el.innerHTML = statusBanner(message, tone);
  };

  async function load(force = false) {
    if (force) invalidateCache("/macro/calendar");
    if (force) renderStatus("正在同步宏观日历", "loading");
    let payload = await api.getMacroCalendar(300);
    let items = filterCalendarItems(payload || []);
    if (false && !items.length && !force && !autoSyncedMacro) {
      autoSyncedMacro = true;
      renderStatus("正在同步宏观日历", "loading");
      await api.refreshMacro();
      invalidateCache("/macro/calendar");
      payload = await api.getMacroCalendar(300);
      items = filterCalendarItems(payload || []);
      renderStatus(items.length ? "数据已就绪" : "同步完成，但暂无宏观事件", items.length ? "success" : "warning");
    }
    if (disposed) return;

    document.getElementById("macro-calendar-container").innerHTML = `
      ${renderMacroCalendarCard(items, currentMonth, isCalendarCollapsed)}
      ${renderMacroDetailCard(items)}
    `;

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
      let fadeRaf = null;
      const FADE_DISTANCE = 40;
      const updateFade = () => {
        if (fadeRaf) return;
        fadeRaf = requestAnimationFrame(() => {
          fadeRaf = null;
          const card = weekdaysRow.closest(".macro-calendar-card");
          if (!card) return;
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

    document.getElementById("macro-calendar-toggle")?.addEventListener("click", () => {
      isCalendarCollapsed = !isCalendarCollapsed;
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
    });

    document.getElementById("calendar-prev-month").addEventListener("click", async () => {
      currentMonth = addMonths(currentMonth, -1);
      await load();
    });
    document.getElementById("calendar-next-month").addEventListener("click", async () => {
      currentMonth = addMonths(currentMonth, 1);
      await load();
    });
    document.getElementById("macro-sync-button").addEventListener("click", async () => {
      const button = document.getElementById("macro-sync-button");
      if (button) {
        button.disabled = true;
        button.textContent = "更新中";
      }
      try {
        renderStatus("正在更新宏观日历", "loading");
        await api.refreshMacro();
        await load(true);
        renderStatus("数据已就绪", "success");
      } finally {
        if (button) {
          button.disabled = false;
          button.textContent = "更新日历";
        }
      }
    });
  }

  const loadPromise = load().catch((error) => {
    if (!disposed) console.error("macro-calendar:initial-load:error", error);
  });
  return {
    async unmount() {
      disposed = true;
      if (weekdaysScrollHandler) {
        window.removeEventListener("scroll", weekdaysScrollHandler);
        weekdaysScrollHandler = null;
      }
      void loadPromise.catch(() => null);
    },
    async pause() {},
    async resume() {},
  };
}
