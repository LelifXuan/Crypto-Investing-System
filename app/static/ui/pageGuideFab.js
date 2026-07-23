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
  fab.title = "页面使用指南";
  fab.textContent = "📘";

  const panel = document.createElement("aside");
  panel.className = "page-guide-panel";
  panel.setAttribute("role", "region");
  panel.setAttribute("aria-label", "页面使用指南");
  panel.hidden = true;
  panel.innerHTML = `
    <header>
      <span class="knowledge-guide-tag">📘 使用指南</span>
      <button type="button" class="page-guide-close" aria-label="收起使用指南">×</button>
    </header>
    <h3 style="margin:4px 0 12px 0;font-size:16px;font-weight:600;">${escapeHtml(item.term || "")}</h3>
    <div class="knowledge-guide-body">${renderPanelBody(item)}</div>
  `;

  const closeBtn = panel.querySelector(".page-guide-close");

  function setExpanded(expanded) {
    panel.hidden = !expanded;
    fab.setAttribute("aria-expanded", expanded ? "true" : "false");
    writeGuideExpanded(termId, expanded);
  }

  function toggle() {
    setExpanded(panel.hidden);
  }

  fab.addEventListener("click", toggle);
  closeBtn.addEventListener("click", () => setExpanded(false));

  document.body.appendChild(fab);
  document.body.appendChild(panel);

  // Honor persisted preference
  setExpanded(readGuideExpanded(termId));

  return {
    unmount() {
      fab.removeEventListener("click", toggle);
      closeBtn.removeEventListener("click", () => setExpanded(false));
      fab.remove();
      panel.remove();
    },
  };
}