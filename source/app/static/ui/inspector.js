import { escapeHtml, formatDateTime } from "../core/dom.js";
import { registerOverlay, LAYER, isTopOverlay } from "./overlayCoordinator.js";
import { mountInspectorResize } from "./inspectorResize.js";

const FOCUSABLE = 'button:not([disabled]), a[href], [tabindex]:not([tabindex="-1"])';

function tone(value) {
  return ["bullish", "bearish", "neutral"].includes(value) ? value : "neutral";
}

function systemLabel(value) {
  return {
    live: "实时",
    stale: "已过期",
    degraded: "降级",
    unavailable: "不可用",
  }[value] || "状态待确认";
}

function section(title, content, className = "") {
  if (!content) return "";
  return `<section class="workbench-inspector-section ${className}"><h3>${title}</h3>${content}</section>`;
}

function renderCurrent(current) {
  if (!current || (!current.label && current.value === undefined)) return "";
  const value = current.value === undefined || current.value === null ? "" : String(current.value);
  return `
    <div class="workbench-inspector-current" data-market-tone="${tone(current.marketTone)}">
      ${current.label ? `<span>${escapeHtml(current.label)}</span>` : ""}
      ${value ? `<strong>${escapeHtml(value)}${current.unit ? `<small>${escapeHtml(current.unit)}</small>` : ""}</strong>` : ""}
    </div>
  `;
}

function renderEvidence(items) {
  if (!items?.length) return "";
  return `<div class="workbench-inspector-list">${items.map((item) => `
    <article data-market-tone="${tone(item.marketTone)}">
      <span>${escapeHtml(item.label || "证据")}</span>
      ${item.value !== undefined && item.value !== null ? `<strong>${escapeHtml(String(item.value))}</strong>` : ""}
    </article>
  `).join("")}</div>`;
}

function renderImpacts(items) {
  if (!items?.length) return "";
  return `<div class="workbench-inspector-impact">${items.map((item) => `
    <article data-market-tone="${tone(item.marketTone)}">
      <strong>${escapeHtml(item.label || "影响")}</strong>
      ${item.summary ? `<p>${escapeHtml(item.summary)}</p>` : ""}
    </article>
  `).join("")}</div>`;
}

function renderSources(items, updatedAt) {
  if (!items?.length && !updatedAt) return "";
  const rows = (items || []).map((item) => `
    <div class="workbench-inspector-source" data-system-status="${escapeHtml(item.status || "unavailable")}">
      <span>${escapeHtml(item.name || "数据源")}</span>
      <strong>${systemLabel(item.status)}</strong>
      ${item.updatedAt ? `<time datetime="${escapeHtml(item.updatedAt)}">${escapeHtml(formatDateTime(item.updatedAt))}</time>` : ""}
    </div>
  `).join("");
  const timestamp = updatedAt
    ? `<p class="workbench-inspector-updated">对象更新：${escapeHtml(formatDateTime(updatedAt))}</p>`
    : "";
  return `<div class="workbench-inspector-sources">${rows}${timestamp}</div>`;
}

function renderInspection(item, titleId) {
  return `
    <div class="workbench-inspector-head">
      <div>
        <span>${escapeHtml(item.type)}</span>
        <h2 id="${titleId}">${escapeHtml(item.title)}</h2>
      </div>
      <div>
        <button class="icon-button workbench-inspector-close" type="button" aria-label="关闭上下文详情">
          <svg viewBox="0 0 20 20" aria-hidden="true"><path d="M5 5l10 10M15 5 5 15"/></svg>
        </button>
        <button class="secondary workbench-inspector-pin" type="button" aria-label="固定当前详情" aria-pressed="false">固定</button>
      </div>
    </div>
    <div class="workbench-inspector-body">
      ${section("当前状态", renderCurrent(item.current))}
      ${section("解读", item.interpretation ? `<p>${escapeHtml(item.interpretation)}</p>` : "")}
      ${section("证据", renderEvidence(item.evidence))}
      ${section("影响", renderImpacts(item.impacts))}
      ${section("来源与新鲜度", renderSources(item.sources, item.updatedAt))}
    </div>
  `;
}

export function mountInspector(container, { state, returnFocus = null } = {}) {
  if (!container || !state) return { destroy() {} };
  const titleId = `${container.id || "workbench-inspector"}-title`;
  const media = window.matchMedia("(max-width: 1180px)");
  let committed = false;
  let destroyed = false;
  let lastContent = "";
  let layer = null;
  const resize = mountInspectorResize(container);

  const focusFallback = () => {
    const target = typeof returnFocus === "function" ? returnFocus() : returnFocus;
    if (target?.isConnected && typeof target.focus === "function") {
      target.focus({ preventScroll: true });
    }
  };

  const syncBodyState = () => {
    document.body.classList.toggle("is-workbench-inspector-open", committed);
    document.body.classList.toggle("is-workbench-inspector-drawer-open", committed && media.matches);
  };

  const applySemantics = () => {
    const drawer = media.matches;
    container.setAttribute("role", drawer ? "dialog" : "complementary");
    container.setAttribute("aria-modal", drawer ? "true" : "false");
    container.setAttribute("aria-labelledby", titleId);
    if (committed) {
      const options = { priority: drawer ? LAYER.inspector : LAYER.dock, modal: drawer };
      if (!layer) layer = registerOverlay({ element: container, close, ...options });
      else layer.update(options);
    }
    syncBodyState();
  };

  const close = () => {
    const before = document.activeElement;
    state.clearSelection();
    // Desktop keyboard selection may leave focus on its origin already.
    // Do not replace that valid restored focus with the page fallback.
    if ((document.activeElement === before && container.contains(before))
      || document.activeElement === document.body) focusFallback();
  };
  const render = (snapshot) => {
    if (destroyed) return;
    const wasCommitted = committed;
    committed = snapshot.hasCommittedSelection;
    if (!committed) {
      layer?.destroy(); layer = null;
      container.hidden = true;
      resize.update();
      container.replaceChildren();
      lastContent = "";
      syncBodyState();
      return;
    }
    container.hidden = false;
    const item = snapshot.activeSelection || snapshot.selection;
    if (!container.querySelector(".workbench-inspector-head")) {
      container.innerHTML = renderInspection(item, titleId);
    }
    const pin = container.querySelector(".workbench-inspector-pin");
    pin.setAttribute("aria-pressed", String(snapshot.isPinned));
    pin.setAttribute("aria-label", snapshot.isPinned ? "取消固定当前详情" : "固定当前详情");
    pin.textContent = snapshot.isPinned ? "已固定" : "固定";
    const content = JSON.stringify(item);
    if (content !== lastContent) {
      container.querySelector(".workbench-inspector-head span").textContent = item.type;
      container.querySelector(".workbench-inspector-head h2").textContent = item.title;
      const template = document.createElement("template");
      template.innerHTML = renderInspection(item, titleId);
      container.querySelector(".workbench-inspector-body").innerHTML = template.content.querySelector(".workbench-inspector-body").innerHTML;
      lastContent = content;
    }
    applySemantics();
    resize.update();
    if (!wasCommitted && media.matches) {
      queueMicrotask(() => {
        if (!destroyed && committed && container.isConnected) container.querySelector(".workbench-inspector-close")?.focus({ preventScroll: true });
      });
    }
  };

  const unsubscribe = state.subscribe(render);
  const onClick = (event) => {
    if (event.target.closest(".workbench-inspector-pin")) state.togglePinned();
    if (event.target.closest(".workbench-inspector-close")) close();
  };
  const onKeydown = (event) => {
    if (!committed || !isTopOverlay(container)) return;
    if (event.key === "Escape") {
      // The coordinator consumes Escape once, above all page handlers.
      return;
    }
    if (!media.matches || event.key !== "Tab") return;
    const focusable = [...container.querySelectorAll(FOCUSABLE)].filter((item) => item.offsetParent !== null);
    if (!focusable.length) return;
    const first = focusable[0];
    const last = focusable[focusable.length - 1];
    if (event.shiftKey && document.activeElement === first) { event.preventDefault(); last.focus(); }
    else if (!event.shiftKey && document.activeElement === last) { event.preventDefault(); first.focus(); }
  };
  container.addEventListener("click", onClick);
  document.addEventListener("keydown", onKeydown, true);
  media.addEventListener?.("change", applySemantics);

  return {
    destroy() {
      destroyed = true;
      resize.destroy();
      layer?.destroy(); layer = null;
      unsubscribe();
      container.removeEventListener("click", onClick);
      document.removeEventListener("keydown", onKeydown, true);
      media.removeEventListener?.("change", applySemantics);
      document.body.classList.remove("is-workbench-inspector-open");
      document.body.classList.remove("is-workbench-inspector-drawer-open");
      container.replaceChildren();
    },
  };
}
