import { setRoot, bindTooltipEscape } from "./core/dom.js";

const assetVersion = window.__ASSET_VERSION__ ? `?v=${encodeURIComponent(window.__ASSET_VERSION__)}` : "";
const moduleLoadPromises = new Map();
const loadPageModule = (path) => {
  if (!moduleLoadPromises.has(path)) {
    moduleLoadPromises.set(path, import(`${path}${assetVersion}`));
  }
  return moduleLoadPromises.get(path);
};

const pageModules = {
  "market-analysis": () => loadPageModule("./pages/analysis.js"),
  "monitoring-overview": () => loadPageModule("./pages/monitoring.js"),
  "market-structure": () => loadPageModule("./pages/structure/index.js"),
  "market-events": () => loadPageModule("./pages/market_events.js"),
  "macro-calendar": () => loadPageModule("./pages/macro_calendar.js"),
  "knowledge-base": () => loadPageModule("./pages/knowledge.js"),
  "cn-etf": () => loadPageModule("./pages/ashare_etf.js"),
  "ashare-etf": () => loadPageModule("./pages/ashare_etf.js"),
  "gold-allocation": () => loadPageModule("./pages/gold_v5.js"),
  "btc-derivatives": () => loadPageModule("./pages/btc_derivatives.js"),
  "ai-strategy": () => loadPageModule("./pages/strategy.js?v=trade-4h-v1"),
};

const PAGE_TITLES = {
  "macro-calendar": "宏观日历",
  "market-events": "市场事件",
  "monitoring-overview": "监控总览",
  "market-structure": "形态结构",
  "market-analysis": "技术指标",
  "knowledge-base": "知识百科",
  "ashare-etf": "A股ETF",
  "gold-allocation": "黄金配置",
  "btc-derivatives": "BTC 衍生品市场",
  "ai-strategy": "AI策略",
};

let activeController = null;
let activePageId = null;
let spaNavigationInFlight = false;
const assetLoadPromises = new Map();

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
  // Function-typed returns are legacy page exports. Some pages used to return
  // the render function itself, so calling the function during unmount would
  // render the old page again. Pages that need teardown should return the
  // explicit controller object shape below.
  if (typeof result === "function") {
    return {
      mount: async () => {},
      unmount: async () => {},
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

function ensureStylesheetOnce(href, key) {
  const existing = document.querySelector(`link[rel="stylesheet"][href*="${key}"]`);
  if (existing) return;
  const link = document.createElement("link");
  link.rel = "stylesheet";
  link.href = href;
  document.head.appendChild(link);
}

function loadScriptOnce(src, globalName) {
  if (globalName && window[globalName]) return Promise.resolve();
  if (assetLoadPromises.has(src)) return assetLoadPromises.get(src);
  const promise = new Promise((resolve, reject) => {
    const existing = document.querySelector(`script[src="${src}"]`);
    if (existing) {
      existing.addEventListener("load", resolve, { once: true });
      existing.addEventListener("error", () => reject(new Error(`脚本加载失败：${src}`)), { once: true });
      if (globalName && window[globalName]) resolve();
      return;
    }
    const script = document.createElement("script");
    script.src = src;
    script.defer = true;
    script.onload = resolve;
    script.onerror = () => reject(new Error(`脚本加载失败：${src}`));
    document.head.appendChild(script);
  }).then(() => {
    if (globalName && !window[globalName]) {
      throw new Error(`脚本已加载，但 ${globalName} 不可用`);
    }
  });
  assetLoadPromises.set(src, promise);
  return promise;
}

async function ensureAssetsForPage(pageId) {
  if (
    pageId === "market-analysis" ||
    pageId === "btc-derivatives" ||
    pageId === "gold-allocation" ||
    pageId === "ashare-etf" ||
    pageId === "cn-etf"
  ) {
    await loadScriptOnce(`/static/vendor/chart.umd.js${assetVersion}`, "Chart");
  }
}

function prefetchPage(pageId) {
  const loadModule = pageModules[pageId];
  if (!loadModule) return;
  void Promise.all([ensureAssetsForPage(pageId), loadModule()]).catch((error) => {
    console.debug("page:prefetch:skipped", pageId, error);
  });
}

function setDocumentTitleForPage(pageId) {
  const title = PAGE_TITLES[pageId] || "Market Research Terminal";
  const heading = document.querySelector(".shell-header h1");
  if (heading) heading.textContent = title;
  document.title = `${title} | Market Research Terminal`;
  document.body.dataset.pageTitle = title;
}

async function boot() {
  const pageId = document.body.dataset.page;
  const loadModule = pageModules[pageId];
  if (!loadModule) return;
  // §16.D — install Escape->blur on tooltip anchors once per SPA boot.
  bindTooltipEscape(document);
  let module;
  try {
    await ensureAssetsForPage(pageId);
    module = await loadModule();
  } catch (error) {
    console.error("page:asset-or-module-load:error", pageId, error);
    renderFatalPageError(
      "页面资源加载失败",
      `当前页面所需的静态资源加载失败，请刷新或稍后重试。${error?.message ? `详情：${error.message}` : ""}`,
      "asset-or-module-load",
    );
    return;
  }
  if (activeController) {
    await activeController.unmount();
    activeController = null;
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
    module.renderGoldV5 ||
    module.renderBtcDerivatives ||
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
    if (pageId !== "ai-strategy") {
      // AI strategy has the largest local renderer graph. Warm it once after
      // the first visible page renders so opening the workbench remains within
      // the 500 ms SPA-shell budget even on a cold browser context.
      setTimeout(() => prefetchPage("ai-strategy"), 0);
    }
  } catch (error) {
    console.error("page:render:error", pageId, error);
    activeController = null;
    renderFatalPageError("页面渲染失败", "页面初始化过程中出现运行时错误，请刷新或稍后重试。", "render");
  }
}

function installSpaRouter() {
  if (!window.history || !window.history.pushState) return;
  const scheduleBoot = () => {
    document.body.classList.add("is-page-loading");
    void boot().finally(() => {
      spaNavigationInFlight = false;
      document.body.classList.remove("is-page-loading");
    });
  };
  document.addEventListener("pointerover", (event) => {
    const target = event.target;
    if (!(target instanceof Element)) return;
    const link = target.closest("[data-page-link]");
    const pageId = link?.getAttribute("data-page-link");
    if (pageId && pageId !== activePageId) prefetchPage(pageId);
  }, { passive: true });
  document.addEventListener("focusin", (event) => {
    const target = event.target;
    if (!(target instanceof Element)) return;
    const link = target.closest("[data-page-link]");
    const pageId = link?.getAttribute("data-page-link");
    if (pageId && pageId !== activePageId) prefetchPage(pageId);
  });
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
    setDocumentTitleForPage(pageId);
    scheduleBoot();
  });

  window.addEventListener("popstate", (event) => {
    const state = event.state;
    const pageId = (state && state.pageId) || document.body.dataset.page;
    if (!pageId || !pageModules[pageId]) return;
    if (pageId === activePageId) return;
    spaNavigationInFlight = true;
    document.body.dataset.page = pageId;
    setDocumentTitleForPage(pageId);
    scheduleBoot();
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
