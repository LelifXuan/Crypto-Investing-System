import { api, invalidateCache } from "../core/api.js";
import { appState, persistState } from "../core/state.js";
import { escapeHtml, formatDateOnly, metricCard, setRoot, statusBanner } from "../core/dom.js";

let autoSyncedEvents = false;
let translationPollTimer = null;

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

function eventCategoryTone(value) {
  if (value === "macro" || value === "regulatory") return "chip-event";
  if (value === "exchange") return "chip-bullish-soft";
  return "chip-neutral";
}

function translationStatusLabel(value) {
  const mapping = {
    translated: "中文翻译完成",
    pending: "中文翻译排队中",
    queued: "中文翻译排队中",
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
  return label ? `<span class="status-chip chip-neutral">${escapeHtml(label)}</span>` : "";
}

function renderEventFeed(items) {
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
          return `
            <article class="event-card event-feed-item">
              <div class="event-feed-meta">
                <div class="event-feed-tags">
                  <span class="status-chip ${eventCategoryTone(item.category)}">${escapeHtml(eventCategoryLabel(item.category))}</span>
                  ${item.source ? `<span class="event-feed-source">${escapeHtml(text(item.source, ""))}</span>` : ""}
                  ${translationChipMarkup(payload, item)}
                </div>
                <small>${escapeHtml(formatDateOnly(item.ts_event))}</small>
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
      </div>
      <div class="event-feed">${cards}</div>
    </article>
  `;
}

function stopTranslationPolling() {
  if (translationPollTimer) {
    window.clearInterval(translationPollTimer);
    translationPollTimer = null;
  }
}

export async function renderMarketEvents() {
  stopTranslationPolling();
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
      renderStatus(
        items.length ? "数据已就绪" : "同步完成，但暂时没有市场事件",
        items.length ? "success" : "warning",
      );
    }

    const groups = groupEvents(items);
    const orderedItems = [...items].sort(
      (left, right) => new Date(right.ts_event || 0).getTime() - new Date(left.ts_event || 0).getTime(),
    );

    document.getElementById("events-metrics").innerHTML = [
      metricCard("事件总数", items.length, "当前信息流规模"),
      metricCard("最近 24 小时", items.filter((item) => (Date.now() - new Date(item.ts_event).getTime()) / 3600000 <= 24).length, "最近发布"),
      metricCard("宏观类", groups.macro.length, "政策与宏观信号"),
      metricCard("交易所 / 平台", groups.exchange.length, "平台与制度事件"),
    ].join("");
    document.getElementById("events-feed").innerHTML = renderEventFeed(orderedItems);
    return orderedItems;
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
        const translated = statusData.translated || 0;
        const total = (translated + pending) || statusData.total || 0;
        if (pending <= 0) {
          stopTranslationPolling();
          invalidateCache("/marketevents");
          await load(true);
          renderStatus(translated > 0 ? `中文翻译完成：${translated} 条已翻译` : "未发现需要翻译的内容", "success");
          return;
        }
        const progress = total > 0 ? `已完成 ${translated}/${total} 条` : `已翻译 ${translated} 条`;
        renderStatus(`翻译进度：${progress}，${pending} 条排队中`, "loading");
        if (pollCount >= maxPolls) {
          stopTranslationPolling();
          invalidateCache("/marketevents");
          await load(true);
          renderStatus(
            `翻译仍在继续：${progress}，${pending} 条等待中`,
            "warning",
          );
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
    const statusbar = document.getElementById("events-statusbar");
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

  document.getElementById("events-refresh").addEventListener("click", async () => {
    const button = document.getElementById("events-refresh");
    button.disabled = true;
    button.textContent = "同步中";
    try {
      renderStatus("正在同步市场信息流", "loading");
      await api.syncMarketEvents();
      await load(true);
      renderStatus("数据已就绪", "success");
    } finally {
      button.disabled = false;
      button.textContent = "刷新信息流";
    }
  });

  document.getElementById("events-translate-toggle").addEventListener("click", async () => {
    appState.translateEvents = !appState.translateEvents;
    persistState();
    const toggleBtn = document.getElementById("events-translate-toggle");
    if (toggleBtn) toggleBtn.textContent = appState.translateEvents ? "关闭中文翻译" : "开启中文翻译";
    if (appState.translateEvents) {
      renderStatus("已开启中文翻译，正在入队", "loading");
      api.refreshMarketEventTranslations({ limit: 50, maxBatches: 10 }).catch(() => {});
      await pollTranslations();
    } else {
      stopTranslationPolling();
      invalidateCache("/marketevents");
      await load(true);
    }
  });

  await load();
}
