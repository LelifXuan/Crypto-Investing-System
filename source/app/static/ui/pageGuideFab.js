import { findKnowledgeTerm } from "../core/knowledge.js";
import { readGuideExpanded, writeGuideExpanded } from "../core/state.js";

function escapeHtml(value) {
  return String(value ?? "")
    .replace(/&/g, "&amp;")
    .replace(/</g, "&lt;")
    .replace(/>/g, "&gt;")
    .replace(/"/g, "&quot;")
    .replace(/'/g, "&#39;");
}

function renderPanelBody(item) {
  const blocks = [];
  if (item.purpose) {
    blocks.push(`
      <section class="knowledge-guide-purpose">
        <h4>何时用</h4>
        <p>${escapeHtml(item.purpose)}</p>
      </section>
    `);
  }
  if (Array.isArray(item.when_to_use) && item.when_to_use.length) {
    blocks.push(`
      <section class="knowledge-guide-purpose knowledge-guide-when">
        <h4>典型场景</h4>
        <ul>${item.when_to_use.map((s) => `<li>${escapeHtml(s)}</li>`).join("")}</ul>
      </section>
    `);
  }
  if (Array.isArray(item.page_walkthrough) && item.page_walkthrough.length) {
    blocks.push(`
      <section class="knowledge-guide-walkthrough">
        <h4>看什么顺序</h4>
        <ol>${item.page_walkthrough.map((s) => `<li>${escapeHtml(s)}</li>`).join("")}</ol>
      </section>
    `);
  }
  if (Array.isArray(item.data_lineage) && item.data_lineage.length) {
    blocks.push(`
      <section class="knowledge-guide-lineage">
        <h4>数据链路</h4>
        <ul>${item.data_lineage.map((s) => `<li>${escapeHtml(s)}</li>`).join("")}</ul>
      </section>
    `);
  }
  if (Array.isArray(item.caveats) && item.caveats.length) {
    blocks.push(`
      <section class="knowledge-guide-caveats">
        <h4>注意事项</h4>
        <ul>${item.caveats.map((s) => `<li>${escapeHtml(s)}</li>`).join("")}</ul>
      </section>
    `);
  }
  return blocks.join("");
}

export function mountPageGuide(termId) {
  const item = termId ? findKnowledgeTerm(termId) : null;
  if (!item) {
    if (typeof console !== "undefined") {
      console.warn(`pageGuideFab: term not found: ${termId}`);
    }
    return { unmount() {} };
  }

  const fab = document.createElement("button");
  fab.type = "button";
  fab.className = "page-guide-fab";
  fab.setAttribute("aria-label", "页面使用指南");
  fab.setAttribute("aria-expanded", "false");
  const panelId = `page-guide-panel-${String(termId).replace(/[^a-zA-Z0-9_-]/g, "-")}`;
  fab.setAttribute("aria-controls", panelId);
  fab.title = "页面使用指南";
  fab.innerHTML = '<svg viewBox="0 0 24 24" aria-hidden="true"><path d="M5 4h10a4 4 0 0 1 4 4v12H9a4 4 0 0 0-4-4zM5 4v12M9 8h6M9 12h6"/></svg><span>页面使用指南</span>';

  const panel = document.createElement("aside");
  panel.className = "page-guide-panel";
  panel.id = panelId;
  panel.setAttribute("role", "region");
  panel.setAttribute("aria-label", "页面使用指南");
  panel.hidden = true;
  panel.innerHTML = `
    <header class="page-guide-panel-head">
      <span class="knowledge-guide-tag">使用指南</span>
      <h3 class="page-guide-title">${escapeHtml(item.term || "")}</h3>
    </header>
    <div class="page-guide-scroll-body">
      <div class="knowledge-guide-body">${renderPanelBody(item)}</div>
    </div>
  `;

  function setExpanded(expanded) {
    panel.hidden = !expanded;
    fab.setAttribute("aria-expanded", expanded ? "true" : "false");
    writeGuideExpanded(termId, expanded);
  }

  function toggle() {
    setExpanded(panel.hidden);
  }

  function closeGuide({ restoreFocus = false } = {}) {
    if (panel.hidden) return;
    setExpanded(false);
    if (restoreFocus) fab.focus();
  }

  function handleOutsidePointer(event) {
    if (panel.hidden || panel.contains(event.target) || fab.contains(event.target)) return;
    closeGuide();
  }

  function handleKeydown(event) {
    if (event.key === "Escape") closeGuide({ restoreFocus: true });
  }

  fab.addEventListener("click", toggle);
  document.addEventListener("pointerdown", handleOutsidePointer, true);
  document.addEventListener("keydown", handleKeydown);

  const sidebarHost = document.getElementById("app-sidebar-guide");
  (sidebarHost || document.body).appendChild(fab);
  document.body.appendChild(panel);

  // Honor persisted preference
  setExpanded(readGuideExpanded(termId));

  return {
    unmount() {
      fab.removeEventListener("click", toggle);
      document.removeEventListener("pointerdown", handleOutsidePointer, true);
      document.removeEventListener("keydown", handleKeydown);
      fab.remove();
      panel.remove();
    },
  };
}
