import {
  findKnowledgeTerm,
  knowledgeCatalogVersion,
  knowledgeLevelFilters,
  knowledgePageFilters,
  knowledgeSections,
} from "../core/knowledge.js";
import { escapeHtml, knowledgeTooltip, metricCard, setRoot } from "../core/dom.js";

const HIDDEN_KNOWLEDGE_TAGS = new Set([
  "technical",
  "ashare-etf",
  "intermediate",
  "basic",
  "advanced",
  "knowledge-base",
  "market-analysis",
  "market-structure",
]);

function visibleKnowledgeTags(item) {
  const tags = [item.family, ...(item.tags || [])].filter(Boolean);
  return tags
    .filter((tag) => !HIDDEN_KNOWLEDGE_TAGS.has(String(tag).toLowerCase()))
    .slice(0, 5);
}

const state = {
  query: "",
  page: "all",
  section: "all",
  family: "all",
  level: "all",
};

function normalize(value) {
  return String(value || "").trim().toLowerCase();
}

function allItems() {
  return knowledgeSections.flatMap((section) =>
    section.items.map((item) => ({ ...item, section_id: section.id, section_title: section.title })),
  );
}

function familyOptions() {
  const families = [...new Set(allItems().map((item) => item.family).filter(Boolean))].sort();
  return [{ key: "all", label: "全部家族" }, ...families.map((value) => ({ key: value, label: value }))];
}

function matchesQuery(item, query) {
  if (!query) return true;
  const haystacks = [
    item.term,
    item.summary,
    item.definition,
    item.how_to_use,
    item.formula,
    ...(item.aliases || []),
    ...(item.tags || []),
    ...(item.related_terms || []),
  ]
    .filter(Boolean)
    .map((value) => normalize(value));
  return haystacks.some((value) => value.includes(query));
}

function matchesFilter(item) {
  if (state.page !== "all" && !(item.page_refs || []).includes(state.page)) return false;
  if (state.family !== "all" && item.family !== state.family) return false;
  if (state.level !== "all" && item.level !== state.level) return false;
  return item.display_mode !== "hidden";
}

function filteredSections() {
  const query = normalize(state.query);
  return knowledgeSections
    .filter((section) => state.section === "all" || state.section === section.id)
    .map((section) => {
      const items = section.items
        .map((item) => ({ ...item, section_title: section.title }))
        .filter((item) => matchesFilter(item) && matchesQuery(item, query));
      return { ...section, items };
    })
    .filter((section) => section.items.length);
}

function renderTags(values, className = "status-chip chip-neutral") {
  if (!values?.length) return "";
  return `<div class="knowledge-chip-row">${values.map((value) => `<span class="${className}">${escapeHtml(value)}</span>`).join("")}</div>`;
}

function renderField(label, value) {
  if (!value || (Array.isArray(value) && !value.length)) return "";
  if (Array.isArray(value)) {
    return `<div class="knowledge-field"><strong>${escapeHtml(label)}</strong><ul>${value.map((entry) => `<li>${escapeHtml(entry)}</li>`).join("")}</ul></div>`;
  }
  return `<p class="knowledge-field"><strong>${escapeHtml(label)}：</strong>${escapeHtml(value)}</p>`;
}

function renderTermCard(item) {
  const related = (item.related_terms || [])
    .slice(0, 5)
    .map((term) => {
      const target = findKnowledgeTerm(term);
      return target
        ? `<a class="status-chip chip-neutral" href="#${escapeHtml(target.id)}">${escapeHtml(term)}</a>`
        : "";
    })
    .filter(Boolean)
    .join("");
  const tags = visibleKnowledgeTags(item);
  const isCompact = item.display_mode === "compact";
  return `
    <article class="knowledge-item-card ${isCompact ? "is-compact" : ""}" id="${escapeHtml(item.id)}">
      <div class="list-card-head">
        <div>
          <strong>${escapeHtml(item.term)}</strong>
          ${item.summary ? `<p class="knowledge-card-summary">${escapeHtml(item.summary)}</p>` : ""}
          <div class="knowledge-meta-row">
            ${renderTags(tags)}
          </div>
        </div>
        <div class="knowledge-card-actions">
          ${isCompact ? "" : `<button class="ghost-button knowledge-toggle-button" data-toggle-knowledge="#${escapeHtml(item.id)}">展开详情</button>`}
        </div>
      </div>
      ${isCompact ? "" : `<div class="knowledge-body">
        ${renderField("定义", item.definition)}
        ${renderField("为什么重要", item.why_it_matters)}
        ${renderField("公式 / 口径", item.formula)}
        ${renderField("如何使用", item.how_to_use)}
        ${renderField("适用场景", item.useful_when)}
        ${renderField("关键阈值", item.thresholds)}
        ${renderField("风险提示", item.risk_note)}
        ${renderField("示例", item.example)}
        ${related ? `<div class="knowledge-field"><strong>相关术语</strong><div class="knowledge-chip-row">${related}</div></div>` : ""}
      </div>`}
    </article>
  `;
}


function bindToggleButtons() {
  document.querySelectorAll("[data-toggle-knowledge]").forEach((button) => {
    button.addEventListener("click", () => {
      const card = document.querySelector(button.dataset.toggleKnowledge);
      if (!card) return;
      const isOpen = card.classList.toggle("is-open");
      button.textContent = isOpen ? "收起详情" : "展开详情";
    });
  });
}

function openTermCard(card) {
  if (!card || card.classList.contains("is-compact")) return;
  card.classList.add("is-open");
  const button = card.querySelector("[data-toggle-knowledge]");
  if (button) button.textContent = "收起详情";
}

function focusHashTarget() {
  const rawHash = decodeURIComponent(window.location.hash || "").replace(/^#/, "");
  if (!rawHash) return;
  const card = document.getElementById(rawHash);
  if (!card) return;
  openTermCard(card);
  card.classList.remove("knowledge-highlight");
  window.requestAnimationFrame(() => {
    card.scrollIntoView({ behavior: "smooth", block: "center" });
    card.classList.add("knowledge-highlight");
    window.setTimeout(() => card.classList.remove("knowledge-highlight"), 1800);
  });
}

function renderKnowledgeLayout() {
  const sections = filteredSections();
  const items = allItems().filter((item) => item.display_mode !== "hidden");
  const totalTerms = items.length;
  const visibleTerms = sections.reduce((sum, section) => sum + section.items.length, 0);
  const familyFilterOptions = familyOptions();
  setRoot(`
    <div id="knowledge-top" class="knowledge-top-anchor"></div>
    <section class="card knowledge-hero">
      <div class="section-head">
        <div>
          <p class="eyebrow">KNOWLEDGE BASE</p>
          <h2>知识百科 ${knowledgeTooltip("Knowledge Base / 知识百科", "tone-neutral")}</h2>
          <p class="section-summary">只保留对判断、执行或排障有帮助的说明；页面筛选、标签和相关页面作为索引元数据使用。</p>
        </div>
      </div>
      <section class="grid cols-3 knowledge-metrics">
        ${[
          metricCard("目录版本", knowledgeCatalogVersion, "当前知识目录版本"),
          metricCard("术语总数", totalTerms, "可见术语数量"),
          metricCard("当前匹配", visibleTerms, state.query ? `搜索：${state.query}` : "当前过滤条件下的术语数量"),
        ].join("")}
      </section>
      <div class="knowledge-toolbar knowledge-toolbar-extended">
        <label class="field">
          <span>搜索</span>
          <input id="knowledge-search" type="search" placeholder="搜索指标、别名、缓存机制或风险标签" value="${escapeHtml(state.query)}" />
        </label>
        <label class="field">
          <span>页面</span>
          <select id="knowledge-page-filter">
            <option value="all">全部页面</option>
            ${knowledgePageFilters.map((item) => `<option value="${item.key}" ${state.page === item.key ? "selected" : ""}>${escapeHtml(item.label)}</option>`).join("")}
          </select>
        </label>
        <label class="field">
          <span>分区</span>
          <select id="knowledge-section-filter">
            <option value="all">全部分区</option>
            ${knowledgeSections.map((item) => `<option value="${item.id}" ${state.section === item.id ? "selected" : ""}>${escapeHtml(item.title)}</option>`).join("")}
          </select>
        </label>
        <label class="field">
          <span>家族</span>
          <select id="knowledge-family-filter">
            ${familyFilterOptions.map((item) => `<option value="${item.key}" ${state.family === item.key ? "selected" : ""}>${escapeHtml(item.label)}</option>`).join("")}
          </select>
        </label>
        <label class="field">
          <span>等级</span>
          <select id="knowledge-level-filter">
            ${knowledgeLevelFilters.map((item) => `<option value="${item.key}" ${state.level === item.key ? "selected" : ""}>${escapeHtml(item.label)}</option>`).join("")}
          </select>
        </label>
      </div>
      <div class="knowledge-section-chips">
        ${knowledgeSections.map((section) => `<a class="status-chip chip-neutral" href="#section-${escapeHtml(section.id)}">${escapeHtml(section.title)}</a>`).join("")}
      </div>
    </section>
    <div class="knowledge-sections">
        ${sections.length ? sections.map((section) => `
          <article class="card knowledge-section-card" id="section-${escapeHtml(section.id)}">
            <div class="section-head">
              <div>
                <p class="eyebrow">${escapeHtml(section.id.toUpperCase())}</p>
                <h2>${escapeHtml(section.title)}</h2>
                <p class="section-summary">${escapeHtml(section.summary)}</p>
              </div>
              <div class="knowledge-section-count">${section.items.length} 项</div>
            </div>
            <div class="knowledge-card-grid">
              ${section.items.map((item) => renderTermCard(item)).join("")}
            </div>
          </article>
        `).join("") : `<section class="card empty-state"><h3>没有匹配的术语</h3><p>请更换关键词，或放宽页面、分区、家族、等级过滤。</p></section>`}
      </div>
    <button type="button" class="knowledge-back-top" aria-label="返回知识百科顶部">返回顶部</button>
  `);

  document.getElementById("knowledge-search")?.addEventListener("input", (event) => {
    state.query = event.target.value || "";
    renderKnowledgeLayout();
  });
  document.getElementById("knowledge-page-filter")?.addEventListener("change", (event) => {
    state.page = event.target.value || "all";
    renderKnowledgeLayout();
  });
  document.getElementById("knowledge-section-filter")?.addEventListener("change", (event) => {
    state.section = event.target.value || "all";
    renderKnowledgeLayout();
  });
  document.getElementById("knowledge-family-filter")?.addEventListener("change", (event) => {
    state.family = event.target.value || "all";
    renderKnowledgeLayout();
  });
  document.getElementById("knowledge-level-filter")?.addEventListener("change", (event) => {
    state.level = event.target.value || "all";
    renderKnowledgeLayout();
  });

  bindToggleButtons();
  document.querySelector(".knowledge-back-top")?.addEventListener("click", () => {
    document.getElementById("knowledge-top")?.scrollIntoView({ behavior: "smooth", block: "start" });
  });
  focusHashTarget();
}

export async function renderKnowledge() {
  renderKnowledgeLayout();
  window.addEventListener("hashchange", focusHashTarget);
}
