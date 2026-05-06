import { api, invalidateCache } from "../core/api.js";
import { appState, persistState } from "../core/state.js";
import { escapeHtml, formatDateOnly, metricCard, setRoot, statusBanner } from "../core/dom.js";

const MOJIBAKE_REPLACEMENTS = [
  [/â€™/g, "’"],
  [/â€˜/g, "‘"],
  [/â€œ/g, "“"],
  [/â€/g, "”"],
  [/â€“/g, "–"],
  [/â€”/g, "—"],
  [/â€¦/g, "…"],
  [/Â /g, " "],
  [/Â/g, ""],
];

export function decodePossiblyBrokenText(value) {
  if (typeof value !== "string" || !value) return value;
  let normalized = value;
  MOJIBAKE_REPLACEMENTS.forEach(([pattern, replacement]) => {
    normalized = normalized.replace(pattern, replacement);
  });
  try {
    const bytes = Uint8Array.from([...normalized].map((char) => char.charCodeAt(0) & 0xff));
    const decoded = new TextDecoder("utf-8", { fatal: false }).decode(bytes);
    if (decoded && !decoded.includes("\uFFFD") && /[’“”–—…]/.test(decoded)) {
      normalized = decoded;
    }
  } catch {
    // Keep the best-effort normalized text below.
  }
  return normalized
    .replace(/([A-Za-z])[\uFFFD□]([A-Za-z])/g, "$1’$2")
    .replace(/[\uFFFD□]([^�□]{2,80}?)[\uFFFD□]/g, "“$1”")
    .replace(/[\uFFFD□]/g, "")
    .replace(/\s{2,}/g, " ")
    .trim();
}

function text(value, fallback = "-") {
  if (value === null || value === undefined || value === "") return fallback;
  return decodePossiblyBrokenText(String(value));
}

function groupEvents(items) {
  const macro = [];
  const exchange = [];
  const other = [];
  items.forEach((item) => {
    if (item.category === "macro" || item.category === "regulatory") {
      macro.push(item);
    } else if (item.category === "exchange") {
      exchange.push(item);
    } else {
      other.push(item);
    }
  });
  return { macro, exchange, other };
}

function eventCategoryLabel(value) {
  if (value === "macro") return "宏观";
  if (value === "regulatory") return "监管";
  if (value === "exchange") return "交易所";
  return "其他";
}

function eventCategoryTone(value) {
  if (value === "macro" || value === "regulatory") return "chip-event";
  if (value === "exchange") return "chip-bullish-soft";
  return "chip-neutral";
}

function renderEventFeed(items) {
  return `
    <article class="card events-feed-card">
      <div class="section-head">
        <div>
          <p class="eyebrow">EVENT FEED</p>
          <h2>最新信息流</h2>
        </div>
      </div>
      <div class="event-feed">
        ${
          items.length
            ? items
                .map((item) => {
                  const summary = text(item.summary, "");
                  return `
                    <article class="event-card event-feed-item">
                      <div class="event-feed-meta">
                        <div class="event-feed-tags">
                          <span class="status-chip ${eventCategoryTone(item.category)}">${escapeHtml(eventCategoryLabel(item.category))}</span>
                          ${item.source ? `<span class="event-feed-source">${escapeHtml(text(item.source, ""))}</span>` : ""}
                        </div>
                        <small>${escapeHtml(formatDateOnly(item.ts_event))}</small>
                      </div>
                      <strong>${escapeHtml(text(item.title, "-"))}</strong>
                      ${summary ? `<p>${escapeHtml(summary)}</p>` : ""}
                    </article>
                  `;
                })
                .join("")
            : '<div class="compact-empty">当前信息流暂无内容。</div>'
        }
      </div>
    </article>
  `;
}

let autoSyncedEvents = false;

export async function renderMarketEvents() {
  setRoot(`
    <section id="events-statusbar"></section>
    <section class="card events-hero">
      <div class="section-head">
        <div>
          <p class="eyebrow">EVENT STREAM</p>
          <h2>最近市场事件与新闻</h2>
        </div>
        <div class="toolbar compact-toolbar">
          <button id="events-translate-toggle" type="button">${appState.translateEvents ? "关闭中文翻译" : "开启中文翻译"}</button>
          <button id="events-refresh" type="button">刷新信息流</button>
        </div>
      </div>
    </section>
    <section class="grid cols-4 events-metrics-grid" id="events-metrics"></section>
    <section class="events-feed-shell" id="events-feed"></section>
  `);

  const renderStatus = (message, tone = "neutral") => {
    const el = document.getElementById("events-statusbar");
    if (el) el.innerHTML = statusBanner(message, tone);
  };

  async function load(force = false) {
    if (force) invalidateCache("/marketevents");
    const response = await api.getMarketEvents(50, appState.translateEvents);
    let items = response.items || response || [];
    if (!items.length && !force && !autoSyncedEvents) {
      autoSyncedEvents = true;
      renderStatus("正在同步市场信息流", "loading");
      await api.syncMarketEvents();
      invalidateCache("/marketevents");
      const refreshed = await api.getMarketEvents(50, appState.translateEvents);
      items = refreshed.items || refreshed || [];
      renderStatus(items.length ? "数据已就绪" : "同步完成，但暂无市场事件", items.length ? "success" : "warning");
    }

    const groups = groupEvents(items);
    const orderedItems = [...items].sort(
      (left, right) => new Date(right.ts_event || 0).getTime() - new Date(left.ts_event || 0).getTime(),
    );

    document.getElementById("events-metrics").innerHTML = [
      metricCard("事件总数", items.length, "当前信息流规模"),
      metricCard("近 24 小时", items.filter((item) => ((Date.now() - new Date(item.ts_event).getTime()) / 3600000) <= 24).length, "最近发布"),
      metricCard("宏观类", groups.macro.length, "政策与宏观信号"),
      metricCard("交易所 / 平台", groups.exchange.length, "平台与制度事件"),
    ].join("");

    document.getElementById("events-feed").innerHTML = renderEventFeed(orderedItems);
  }

  document.getElementById("events-refresh").addEventListener("click", async () => {
    const button = document.getElementById("events-refresh");
    if (button) {
      button.disabled = true;
      button.textContent = "同步中";
    }
    try {
      renderStatus("正在同步市场信息流", "loading");
      await api.syncMarketEvents();
      await load(true);
      renderStatus("数据已就绪", "success");
    } finally {
      if (button) {
        button.disabled = false;
        button.textContent = "刷新信息流";
      }
    }
  });

  document.getElementById("events-translate-toggle").addEventListener("click", async () => {
    appState.translateEvents = !appState.translateEvents;
    persistState();
    await renderMarketEvents();
  });

  await load();
}
