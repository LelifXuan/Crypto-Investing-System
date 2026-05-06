import { api, invalidateCache } from "../core/api.js";
import {
  formatDateOnly,
  formatNumber,
  impactChip,
  knowledgeTooltip,
  metricCard,
  setRoot,
  statusBanner,
  tooltipWrap,
} from "../core/dom.js";

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
    <article class="card">
      <div class="calendar-head">
        <button id="calendar-prev-month" type="button">←</button>
        <strong>${activeMonth.getFullYear()} 年 ${MONTH_NAMES[activeMonth.getMonth()]}</strong>
        <button id="calendar-next-month" type="button">→</button>
      </div>
      <div class="calendar-weekdays">${WEEKDAY_NAMES.map((name) => `<span>${name}</span>`).join("")}</div>
      <div class="calendar-grid">${cells.join("")}</div>
    </article>
  `;
}

function renderCalendarTable(items) {
  return `
    <section class="card">
      <div class="section-head">
        <div>
          <p class="eyebrow">RELEASE BOARD</p>
          <h2>宏观事件明细 ${knowledgeTooltip("Macro Sync / 宏观同步 与 Event Window / 事件窗口", "tone-neutral", "展示过去三个月与未来六个月的宏观事件。", { extra: "展示过去三个月与未来六个月的宏观事件。" })}</h2>
          <p class="section-summary">按时间顺序查看发布安排与实际结果，便于复盘宏观扰动。</p>
        </div>
        <div class="toolbar compact-toolbar">
          <button id="macro-sync-button" type="button">同步宏观</button>
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
    </section>
  `;
}

let autoSyncedMacro = false;

export async function renderMacroCalendar() {
  let currentMonth = monthStart(new Date());
  setRoot(`
    <section id="macro-statusbar"></section>
    <section class="grid cols-4" id="macro-summary-cards"></section>
    <section id="macro-calendar-module"></section>
    <section id="macro-calendar-detail"></section>
  `);

  const renderStatus = (message, tone = "neutral") => {
    const el = document.getElementById("macro-statusbar");
    if (el) el.innerHTML = statusBanner(message, tone);
  };

  async function load(force = false) {
    if (force) invalidateCache("/macro/calendar");
    let payload = await api.getMacroCalendar(300);
    let items = filterCalendarItems(payload || []);
    if (!items.length && !force && !autoSyncedMacro) {
      autoSyncedMacro = true;
      renderStatus("正在同步宏观日历", "loading");
      await api.refreshMacro();
      invalidateCache("/macro/calendar");
      payload = await api.getMacroCalendar(300);
      items = filterCalendarItems(payload || []);
      renderStatus(items.length ? "数据已就绪" : "同步完成，但暂无宏观事件", items.length ? "success" : "warning");
    }
    const released = items.filter((item) => item.status === "released").length;
    const scheduled = items.filter((item) => item.status !== "released").length;
    const fomc = items.filter((item) => String(item.event_key || "").includes("fomc")).length;
    const core = items.filter((item) => ["us_cpi", "us_nfp", "ism_mfg", "ism_srv"].includes(item.event_key)).length;

    document.getElementById("macro-summary-cards").innerHTML = [
      metricCard("已发布", released, "事件数"),
      metricCard("待发布", scheduled, "事件数"),
      metricCard("FOMC", fomc, "日历节点"),
      metricCard("CPI / NFP / ISM", core, "核心发布"),
    ].join("");

    document.getElementById("macro-calendar-module").innerHTML = renderMonthGrid(items, currentMonth);
    document.getElementById("macro-calendar-detail").innerHTML = renderCalendarTable(items);

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
        button.textContent = "同步中";
      }
      try {
        renderStatus("正在同步宏观日历", "loading");
        await api.refreshMacro();
        await load(true);
        renderStatus("数据已就绪", "success");
      } finally {
        if (button) {
          button.disabled = false;
          button.textContent = "同步宏观";
        }
      }
    });
  }

  await load();
}
