import {
  findKnowledgeTerm,
  knowledgeCatalogVersion,
  knowledgeLevelFilters,
  knowledgeSections,
} from "../core/knowledge.js";
import { escapeHtml, knowledgeTooltip, setRoot } from "../core/dom.js";
import { mountDropdown } from "../ui/dropdown.js";

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

let isMounted = false;
let hashListenerInstalled = false;
let searchTimer = null;
// 挂载时保存的渲染上下文:unmount 时用于拆除。
let activeRoot = null;

function visibleKnowledgeTags(item) {
  const tags = [item.family, ...(item.tags || [])].filter(Boolean);
  return [...new Set(tags.map((tag) => String(tag).trim()).filter(Boolean))]
    .filter((tag) => !HIDDEN_KNOWLEDGE_TAGS.has(String(tag).toLowerCase()))
    .slice(0, 3);
}

const state = {
  query: "",
  section: "all",
  level: "all",
};

// Catalog 是静态 import 的：摊平一次，后续筛选与术语索引直接复用，
// 避免每次渲染都重新 flatMap 146 项。
const ALL_ITEMS = knowledgeSections.flatMap((section) =>
  section.items.map((item) => ({ ...item, section_id: section.id, section_title: section.title })),
);
const ITEM_BY_ID = new Map(ALL_ITEMS.map((item) => [String(item.id), item]));

function normalize(value) {
  return String(value || "").trim().toLowerCase();
}

function allItems() {
  return ALL_ITEMS;
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

// 单一渲染源:首次挂载与筛选更新共用,避免两处几乎相同的 HTML 生成逻辑漂移。
function renderSectionsHtml(sections) {
  if (!sections.length) {
    return '<section class="card empty-state"><h3>没有匹配的术语</h3><p>请更换关键词，或放宽分区、等级过滤。</p></section>';
  }
  return sections
    .map((section) => `
      <section class="knowledge-section-card" id="section-${escapeHtml(section.id)}">
        <div class="section-head">
          <div>
            <p class="eyebrow">${escapeHtml(section.id.toUpperCase())}</p>
            <h2>${escapeHtml(section.title)}</h2>
            <p class="section-summary">${escapeHtml(section.summary)}</p>
          </div>
          <div class="knowledge-section-count"><strong>${section.items.length}</strong><span>条目</span></div>
        </div>
        <div class="knowledge-entry-list knowledge-card-grid">
          ${section.items.map((item) => (item.type === "guide" ? renderGuideCard(item) : renderTermCard(item))).join("")}
        </div>
      </section>
    `)
    .join("");
}

// 事件委托:整个 .knowledge-sections 容器只挂一个 click 监听器,innerHTML
// 重建卡片后监听器依然有效,无需每次重绑 146 个按钮。防御性:渲染 HTML 是
// 主职责,监听器只在真实 DOM 元素上挂载(stub/测试环境无 addEventListener
// 或 dataset 时静默跳过,不影响 HTML 输出)。
function bindKnowledgeDelegates(root) {
  if (!root || typeof root.querySelector !== "function") return;
  const sectionsEl = root.querySelector(".knowledge-sections");
  if (!sectionsEl || typeof sectionsEl.addEventListener !== "function") return;
  if (sectionsEl.dataset && sectionsEl.dataset.knowledgeDelegates === "1") return;
  sectionsEl.addEventListener("click", (event) => {
    const button = event.target?.closest?.("[data-toggle-knowledge]");
    if (!button || !sectionsEl.contains(button)) return;
    const id = String(button.dataset.toggleKnowledge || "").replace(/^#/, "");
    const card = document.getElementById(id);
    if (!card) return;
    if (!card.querySelector(".knowledge-body")) {
      const item = ITEM_BY_ID.get(id);
      if (item) card.insertAdjacentHTML("beforeend", renderTermBody(item));
    }
    const isOpen = card.classList.toggle("is-open");
    button.setAttribute("aria-expanded", String(isOpen));
    const label = button.querySelector("[data-toggle-label]");
    if (label) label.textContent = isOpen ? "收起" : "阅读";
  });
  if (sectionsEl.dataset) sectionsEl.dataset.knowledgeDelegates = "1";
}

function updateMetrics() {
  const metricsEl = document.querySelector(".knowledge-catalog-stats")
    || document.querySelector(".knowledge-metrics");
  if (!metricsEl) return;
  const sections = filteredSections();
  const visibleTerms = sections.reduce((sum, s) => sum + s.items.length, 0);
  // 快照去重:数值/查询没变就不重建 metrics。
  const key = [knowledgeCatalogVersion, ALL_ITEMS.length, visibleTerms, state.query].join("|");
  if (metricsEl.dataset.metricsKey === key) return;
  metricsEl.dataset.metricsKey = key;
  metricsEl.innerHTML = `
    <span><small>目录版本</small><strong>${escapeHtml(knowledgeCatalogVersion)}</strong></span>
    <span><small>全部条目</small><strong>${ALL_ITEMS.filter((item) => item.display_mode !== "hidden").length}</strong></span>
    <span><small>当前匹配</small><strong>${visibleTerms}</strong></span>
  `;
}

function updateKnowledgeContent() {
  const sections = filteredSections();
  updateMetrics();

  const contentEl = document.querySelector(".knowledge-sections");
  if (contentEl) {
    // rAF:同步 146 卡重渲染不阻塞触发的 input/change 事件。
    const html = renderSectionsHtml(sections);
    if (typeof window.requestAnimationFrame === "function") {
      window.requestAnimationFrame(() => {
        contentEl.innerHTML = html;
      });
    } else {
      contentEl.innerHTML = html;
    }
  }
}

const helpers = { escapeHtml };

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

function renderGuideCard(item) {
  const { escapeHtml: esc } = helpers;
  const guideBadge = `<span class="knowledge-guide-tag">使用指南</span>`;
  const purposeBlock = item.purpose
    ? `<section class="knowledge-guide-purpose">
         <h4>何时用</h4>
         <p>${esc(item.purpose)}</p>
       </section>`
    : "";
  const whenBlock = item.when_to_use && item.when_to_use.length
    ? `<section class="knowledge-guide-purpose knowledge-guide-when">
         <h4>典型场景</h4>
         <ul>${item.when_to_use.map((s) => `<li>${esc(s)}</li>`).join("")}</ul>
       </section>`
    : "";
  const walkthroughBlock = item.page_walkthrough && item.page_walkthrough.length
    ? `<section class="knowledge-guide-walkthrough">
         <h4>看什么顺序</h4>
         <ol>${item.page_walkthrough.map((s) => `<li>${esc(s)}</li>`).join("")}</ol>
       </section>`
    : "";

  return `
    <article class="knowledge-guide-card is-open" id="${esc(item.id)}">
      <header class="knowledge-guide-header">
        ${guideBadge}
        <h3>${esc(item.term)}</h3>
      </header>
      <div class="knowledge-guide-body">
        ${purposeBlock}
        ${whenBlock}
        ${walkthroughBlock}
      </div>
    </article>
  `;
}

// Map page_refs keys (the catalog uses these) to human-readable labels
// shown in the term card's "appears on" badge. We intentionally do NOT
// link these labels to SPA routes: doing so would break the long-standing
// "knowledge-page replaces its parent page" contract (other pages' URLs
// must not appear in the rendered knowledge-page DOM, as enforced by
// tests/test_knowledge_catalog.py::test_knowledge_page_remounts_when_spa_dom_belongs_to_previous_page).
const KNOWLEDGE_PAGE_LABEL = {
  "market-analysis": "市场分析",
  "market-structure": "形态结构",
  "alert-center": "告警中心",
  "monitoring-overview": "监控总览",
  "macro-calendar": "宏观日历",
  "market-events": "市场事件",
  "knowledge-base": "知识百科",
  "risk": "风险管理",
  "ashare-etf": "A股ETF",
  "btc-derivatives": "BTC 衍生品",
};
const KNOWLEDGE_PAGE_NOTE = {
  "market-analysis": "技术指标页",
  "market-structure": "摆动 / 突破 / 回踩",
  "alert-center": "信号 / 风险 / 决策",
  "monitoring-overview": "终端摘要 / 宏观 + 技术汇总",
  "macro-calendar": "宏观日历与观察项",
  "market-events": "新闻 / 事件流",
  "knowledge-base": "知识百科（本页）",
  "risk": "风险 / 仓位 / 失效位",
  "ashare-etf": "A 股 ETF 行情",
  "btc-derivatives": "期货 / 期权 / 资金费率",
};

function renderPageRefsBadge(item) {
  // Skip self-reference (the term's own knowledge-base page) and unknown
  // page keys (only well-known SPA pages get a label).
  const pageRefs = (item.page_refs || []).filter(
    (key) => key !== "knowledge-base" && KNOWLEDGE_PAGE_LABEL[key],
  );
  if (!pageRefs.length) return "";
  // Popover is rendered eagerly but hidden via CSS until the trigger is
  // hovered or focused. No JS state, no <a> links, no data-page-link —
  // V1.5.x contract: the knowledge page must not surface other SPA routes
  // in its DOM.
  const items = pageRefs
    .map((key) => {
      const label = KNOWLEDGE_PAGE_LABEL[key];
      const note = KNOWLEDGE_PAGE_NOTE[key] || "";
      return `<li><strong>${escapeHtml(label)}</strong><span> — ${escapeHtml(note)}</span></li>`;
    })
    .join("");
  return `
    <div class="knowledge-page-refs" data-test="page-refs">
      <button type="button"
              class="knowledge-page-refs-trigger"
              aria-haspopup="dialog"
              aria-expanded="false"
              data-page-refs-popover>
        <span class="knowledge-page-refs-icon" aria-hidden="true">i</span>
        <span class="knowledge-page-refs-text">${pageRefs.length} 页可用</span>
        <span class="knowledge-page-refs-caret" aria-hidden="true">▾</span>
      </button>
      <div class="knowledge-page-refs-popover" role="dialog" aria-label="术语被引用的页面">
        <p class="knowledge-page-refs-popover-title">该术语被引用：</p>
        <ul class="knowledge-page-refs-popover-list">${items}</ul>
      </div>
    </div>
  `;
}

function renderTermBody(item) {
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
  return `<div class="knowledge-body">
        ${renderField("定义", item.definition)}
        ${renderField("为什么重要", item.why_it_matters)}
        ${renderField("公式 / 口径", item.formula)}
        ${renderField("如何使用", item.how_to_use)}
        ${renderField("适用场景", item.useful_when)}
        ${renderField("关键阈值", item.thresholds)}
        ${renderField("风险提示", item.risk_note)}
        ${renderField("示例", item.example)}
        ${related ? `<div class="knowledge-field"><strong>相关术语</strong><div class="knowledge-chip-row">${related}</div></div>` : ""}
      </div>`;
}

function renderTermCard(item) {
  const tags = visibleKnowledgeTags(item);
  const isCompact = item.display_mode === "compact";
  return `
    <article class="knowledge-item-card ${isCompact ? "is-compact" : ""}" id="${escapeHtml(item.id)}">
      <div class="list-card-head">
        <div class="knowledge-entry-copy">
          <strong>${escapeHtml(item.term)}</strong>
          ${item.summary ? `<p class="knowledge-card-summary">${escapeHtml(item.summary)}</p>` : ""}
          <div class="knowledge-meta-row">
            ${renderTags(tags)}
          </div>
        </div>
        <div class="knowledge-card-actions">
          ${renderPageRefsBadge(item)}
          ${isCompact ? "" : `<button class="ghost-button knowledge-toggle-button" data-toggle-knowledge="#${escapeHtml(item.id)}" aria-expanded="false">
            <span data-toggle-label>阅读</span>
            <svg viewBox="0 0 16 16" aria-hidden="true"><path d="m5 6 3 3 3-3"/></svg>
          </button>`}
        </div>
      </div>
    </article>
  `;
}

function openTermCard(card) {
  if (!card || card.classList.contains("is-compact")) return;
  if (!card.querySelector(".knowledge-body")) {
    const item = ITEM_BY_ID.get(String(card.id || ""));
    if (item) card.insertAdjacentHTML("beforeend", renderTermBody(item));
  }
  card.classList.add("is-open");
  const button = card.querySelector("[data-toggle-knowledge]");
  if (button) {
    button.setAttribute("aria-expanded", "true");
    const label = button.querySelector("[data-toggle-label]");
    if (label) label.textContent = "收起";
  }
}

function focusHashTarget() {
  const rawHash = decodeURIComponent(window.location.hash || "").replace(/^#/, "");
  if (!rawHash) return;
  // If the target card is not in the DOM (filter hid it), clear
  // the filter so the card becomes visible. Without this, related-
  // term clicks from a filtered view silently do nothing.
  if (!ensureTargetVisible(rawHash)) return;
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

// V1.5.x: ensure the URL hash resolves to a visible card. If the
// active filter (section / level / search) hides
// the target term, reset all filters so the term becomes visible
// again. Without this, navigating from a filtered view to a
// related-term anchor silently does nothing because the card is
// not in the DOM.
function ensureTargetVisible(hashId) {
  if (!hashId) return false;
  if (document.getElementById(hashId)) return true;
  let mutated = false;
  if (state.query) { state.query = ""; mutated = true; }
  if (state.section !== "all") { state.section = "all"; mutated = true; }
  if (state.level !== "all") { state.level = "all"; mutated = true; }
  if (mutated) {
    updateKnowledgeContent();
    syncFilterControls();
  }
  return Boolean(document.getElementById(hashId));
}

function syncFilterControls() {
  const search = document.getElementById("knowledge-search");
  if (search) search.value = state.query;
  const section = document.getElementById("knowledge-section-filter");
  if (section) section.value = state.section;
  const level = document.getElementById("knowledge-level-filter");
  if (level) level.value = state.level;
}

function resetState() {
  state.query = "";
  state.section = "all";
  state.level = "all";
}

function renderKnowledgeLayout() {
  const sections = filteredSections();
  const totalTerms = ALL_ITEMS.filter((item) => item.display_mode !== "hidden").length;
  const visibleTerms = sections.reduce((sum, section) => sum + section.items.length, 0);
  setRoot(`
    <div id="knowledge-top" class="knowledge-top-anchor"></div>
    <section class="knowledge-hero">
      <div class="section-head">
        <div>
          <p class="eyebrow">KNOWLEDGE BASE</p>
          <h1>研究参考手册 ${knowledgeTooltip("Knowledge Base / 知识百科", "tone-neutral")}</h1>
          <p class="section-summary">从概念、计算口径到执行边界，集中查阅交易系统中真正影响判断的术语与方法。</p>
        </div>
      </div>
      <div class="knowledge-catalog-stats knowledge-metrics">
        <span><small>目录版本</small><strong>${escapeHtml(knowledgeCatalogVersion)}</strong></span>
        <span><small>全部条目</small><strong>${totalTerms}</strong></span>
        <span><small>当前匹配</small><strong>${visibleTerms}</strong></span>
      </div>
    </section>
    <div class="knowledge-workspace">
      <aside class="knowledge-index-rail" aria-label="知识百科目录与筛选">
        <label class="field">
          <span>搜索</span>
          <input id="knowledge-search" type="search" placeholder="搜索术语或口径" value="${escapeHtml(state.query)}" />
        </label>
        <nav class="knowledge-section-nav" aria-label="章节目录">
          <span class="knowledge-rail-label">章节</span>
          ${knowledgeSections.map((section) => `<a href="#section-${escapeHtml(section.id)}"><span>${escapeHtml(section.title)}</span><small>${section.items.length}</small></a>`).join("")}
        </nav>
        <div class="knowledge-toolbar knowledge-toolbar-extended">
        <label class="field">
          <span>分区</span>
          <button class="dropdown"
                  data-dropdown-id="knowledge-section-filter"
                  data-dropdown-size="default"
                  type="button"
                  aria-haspopup="listbox"
                  aria-expanded="false">
            <span class="dropdown-icon" data-slot="icon" hidden></span>
            <span class="dropdown-label">${escapeHtml(((knowledgeSections.find(i => i.id === state.section)) || {}).title || "全部分区")}</span>
            <span class="dropdown-arrow" aria-hidden="true"><svg viewBox="0 0 10 10" width="11" height="11"><path d="M2 4l3 3 3-3" fill="none" stroke="currentColor" stroke-width="1.4" stroke-linecap="round" stroke-linejoin="round"/></svg></span>
          </button>
        </label>
        <label class="field">
          <span>等级</span>
          <button class="dropdown"
                  data-dropdown-id="knowledge-level-filter"
                  data-dropdown-size="default"
                  type="button"
                  aria-haspopup="listbox"
                  aria-expanded="false">
            <span class="dropdown-icon" data-slot="icon" hidden></span>
            <span class="dropdown-label">${escapeHtml(((knowledgeLevelFilters.find(i => i.key === state.level)) || {}).label || "")}</span>
            <span class="dropdown-arrow" aria-hidden="true"><svg viewBox="0 0 10 10" width="11" height="11"><path d="M2 4l3 3 3-3" fill="none" stroke="currentColor" stroke-width="1.4" stroke-linecap="round" stroke-linejoin="round"/></svg></span>
          </button>
        </label>
        </div>
      </aside>
      <main class="knowledge-content-column">
        <div class="knowledge-sections">
        ${renderSectionsHtml(sections)}
        </div>
      </main>
      <aside class="knowledge-reference-rail" aria-label="阅读说明">
        <section>
          <p class="eyebrow">READING GUIDE</p>
          <h2>如何使用</h2>
          <ol>
            <li><span>01</span><p><strong>先查定义</strong><small>确认术语及计算口径。</small></p></li>
            <li><span>02</span><p><strong>再看用途</strong><small>理解它回答什么问题。</small></p></li>
            <li><span>03</span><p><strong>最后核对风险</strong><small>避免把指标当成单独结论。</small></p></li>
          </ol>
        </section>
        <section class="knowledge-reference-note">
          <p class="eyebrow">EDITORIAL NOTE</p>
          <p>标签只用于索引；页面引用说明术语出现在哪里，不代表该页面采用它作为唯一判断依据。</p>
        </section>
      </aside>
    </div>
  `);
  activeRoot = document;
  bindKnowledgeDelegates(document);

  document.getElementById("knowledge-search")?.addEventListener("input", (event) => {
    state.query = event.target.value || "";
    window.clearTimeout(searchTimer);
    searchTimer = window.setTimeout(() => renderKnowledge(), 300);
  });
  const sectionRoot = document.querySelector('.dropdown[data-dropdown-id="knowledge-section-filter"]');
  if (sectionRoot) {
    mountDropdown(sectionRoot, {
      items: [{ value: "all", label: "全部分区" }, ...knowledgeSections.map((i) => ({ value: i.id, label: i.title }))],
      value: state.section,
      placeholder: "选择分区",
      onChange: (v) => {
        state.section = v || "all";
        renderKnowledge();
      },
    });
  }
  const levelRoot = document.querySelector('.dropdown[data-dropdown-id="knowledge-level-filter"]');
  if (levelRoot) {
    mountDropdown(levelRoot, {
      items: knowledgeLevelFilters.map((i) => ({ value: i.key, label: i.label })),
      value: state.level,
      placeholder: "选择等级",
      onChange: (v) => {
        state.level = v || "all";
        renderKnowledge();
      },
    });
  }

  focusHashTarget();
}

export async function renderKnowledge() {
  const hasKnowledgeRoot = Boolean(document.getElementById("knowledge-top"));
  if (!isMounted || !hasKnowledgeRoot) {
    renderKnowledgeLayout();
    isMounted = true;
    if (!hashListenerInstalled) {
      window.addEventListener("hashchange", focusHashTarget);
      hashListenerInstalled = true;
    }
  } else {
    updateKnowledgeContent();
  }
  return {
    async unmount() {
      // 拆除:移除 hashchange 监听、清防抖 timer、重置状态与挂载标记,
      // 避免 SPA 切走后监听器泄漏 / 悬空 timer 触发脏渲染。
      if (hashListenerInstalled) {
        const remove = window.removeEventListener?.bind(window);
        if (typeof remove === "function") {
          remove("hashchange", focusHashTarget);
        }
        hashListenerInstalled = false;
      }
      if (searchTimer) {
        window.clearTimeout(searchTimer);
        searchTimer = null;
      }
      isMounted = false;
      activeRoot = null;
      resetState();
    },
    async pause() {
      // 页面隐藏:不触发防抖渲染。
      if (searchTimer) {
        window.clearTimeout(searchTimer);
        searchTimer = null;
      }
    },
    async resume() {
      // 知识百科无轮询;回到前台时若有 hash 需重新定位(挂载状态保留)。
      if (window.location.hash) {
        window.requestAnimationFrame(() => focusHashTarget());
      }
    },
  };
}
