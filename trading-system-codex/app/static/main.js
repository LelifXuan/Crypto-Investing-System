const assetVersion = window.__ASSET_VERSION__ ? `?v=${encodeURIComponent(window.__ASSET_VERSION__)}` : "";
const loadPageModule = (path) => import(`${path}${assetVersion}`);

const pageModules = {
  "market-analysis": () => loadPageModule("./pages/analysis.js"),
  "monitoring-overview": () => loadPageModule("./pages/monitoring.js"),
  "market-structure": () => loadPageModule("./pages/structure/index.js"),
  "market-events": () => loadPageModule("./pages/market_events.js"),
  "macro-calendar": () => loadPageModule("./pages/macro_calendar.js"),
  "alert-center": () => loadPageModule("./pages/alerts.js"),
  "knowledge-base": () => loadPageModule("./pages/knowledge.js"),
  "cn-etf": () => loadPageModule("./pages/ashare_etf.js"),
  "ashare-etf": () => loadPageModule("./pages/ashare_etf.js"),
  "ai-strategy": () => loadPageModule("./pages/strategy.js"),
};

let activeController = null;
let activePageId = null;
let spaNavigationInFlight = false;

function renderFatalPageError(title, detail, code) {
  const root = document.getElementById("page-root");
  if (!root) return;
  root.innerHTML = `
    <section class="card">
      <div class="section-head">
        <div>
          <p class="eyebrow">RENDER ERROR</p>
          <h2>${title}</h2>
        </div>
      </div>
      <div class="error-state">
        <p>${detail}</p>
        ${code ? `<small>错误类型：${code}</small>` : ""}
      </div>
    </section>
  `;
}

function normalizeController(result) {
  if (typeof result === "function") {
    return {
      mount: async () => {},
      unmount: async () => result(),
      pause: async () => {},
      resume: async () => {},
    };
  }
  if (result && typeof result === "object") {
    return {
      mount: typeof result.mount === "function" ? result.mount : async () => {},
      unmount: typeof result.unmount === "function" ? result.unmount : async () => {},
      pause: typeof result.pause === "function" ? result.pause : async () => {},
      resume: typeof result.resume === "function" ? result.resume : async () => {},
    };
  }
  return {
    mount: async () => {},
    unmount: async () => {},
    pause: async () => {},
    resume: async () => {},
  };
}

async function boot() {
  const pageId = document.body.dataset.page;
  const loadModule = pageModules[pageId];
  if (!loadModule) return;
  if (activeController) {
    await activeController.unmount();
    activeController = null;
  }
  let module;
  try {
    module = await loadModule();
  } catch (error) {
    console.error("page:module-load:error", pageId, error);
    renderFatalPageError(
      "页面模块加载失败",
      `页面静态资源加载失败。${error?.message ? `详情：${error.message}` : ""}`,
      "module-load",
    );
    return;
  }
  const renderPage =
    module.renderPage ||
    module.renderStructure ||
    module.renderAnalysis ||
    module.renderMonitoring ||
    module.renderMarketEvents ||
    module.renderMacroCalendar ||
    module.renderAlerts ||
    module.renderKnowledge ||
    module.renderAshareEtf ||
    module.renderStrategy;
  if (typeof renderPage !== "function") {
    console.error("page:render-missing", pageId);
    renderFatalPageError("页面入口缺失", "当前页面模块没有导出可执行的渲染函数。", "render-missing");
    return;
  }
  activePageId = pageId;
  try {
    activeController = normalizeController(await renderPage());
    await activeController.mount();
  } catch (error) {
    console.error("page:render:error", pageId, error);
    activeController = null;
    renderFatalPageError("页面渲染失败", "页面初始化过程中出现运行时错误。", "render");
  }
}

// V1.5.4 D1: progressive SPA routing.
// Intercept clicks on [data-page-link] so that switching tabs does
// NOT trigger a full page reload (which would re-download the
// 116 KB stylesheet, the main.js module, and the page module).
// The backend /<page>-page routes still work as deep-link fallbacks
// for browser refresh, deep linking, and crawler indexing.
const PAGE_TITLES = {
  "macro-calendar": "宏观日历",
  "market-events": "市场事件",
  "monitoring-overview": "监控总览",
  "market-structure": "形态结构",
  "market-analysis": "技术指标",
  "alert-center": "告警中心",
  "knowledge-base": "知识百科",
  "ashare-etf": "A股ETF",
  "ai-strategy": "AI策略",
};

function ensureStylesheetForPage(pageId) {
  if (pageId !== "ai-strategy") return;
  const href = `/static/styles-v15.css${assetVersion}`;
  const existing = document.querySelector(`link[rel="stylesheet"][href*="styles-v15"]`);
  if (existing) return;
  const link = document.createElement("link");
  link.rel = "stylesheet";
  link.href = href;
  document.head.appendChild(link);
}

function setDocumentTitleForPage(pageId) {
  const title = PAGE_TITLES[pageId] || "Market Research Terminal";
  const heading = document.querySelector(".shell-header h1");
  if (heading) heading.textContent = title;
  document.title = `${title} | Market Research Terminal`;
  document.body.dataset.pageTitle = title;
}

function installSpaRouter() {
  if (!window.history || !window.history.pushState) return;
  document.addEventListener("click", (event) => {
    if (event.defaultPrevented) return;
    if (event.button !== 0) return;
    if (event.metaKey || event.ctrlKey || event.shiftKey || event.altKey) return;
    const target = event.target;
    if (!(target instanceof Element)) return;
    const link = target.closest("[data-page-link]");
    if (!link) return;
    const pageId = link.getAttribute("data-page-link");
    if (!pageId || !pageModules[pageId]) return;
    if (activePageId === pageId) {
      event.preventDefault();
      return;
    }
    if (spaNavigationInFlight) {
      event.preventDefault();
      return;
    }
    const href = link.getAttribute("href") || `/${pageId}-page`;
    event.preventDefault();
    spaNavigationInFlight = true;
    window.history.pushState({ pageId, href }, "", href);
    document.body.dataset.page = pageId;
    ensureStylesheetForPage(pageId);
    setDocumentTitleForPage(pageId);
    boot().finally(() => {
      spaNavigationInFlight = false;
    });
  });

  window.addEventListener("popstate", (event) => {
    const state = event.state;
    const pageId = (state && state.pageId) || document.body.dataset.page;
    if (!pageId || !pageModules[pageId]) return;
    if (pageId === activePageId) return;
    spaNavigationInFlight = true;
    document.body.dataset.page = pageId;
    ensureStylesheetForPage(pageId);
    setDocumentTitleForPage(pageId);
    boot().finally(() => {
      spaNavigationInFlight = false;
    });
  });
}

document.addEventListener("visibilitychange", async () => {
  if (!activeController || !activePageId) return;
  if (document.hidden) {
    await activeController.pause();
    return;
  }
  await activeController.resume();
});

window.addEventListener("beforeunload", () => {
  if (activeController) {
    void activeController.unmount();
  }
});

installSpaRouter();
void boot();
