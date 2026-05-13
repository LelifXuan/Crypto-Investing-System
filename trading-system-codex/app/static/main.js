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
  "ai-strategy": () => loadPageModule("./pages/strategy.js"),
};

let activeController = null;
let activePageId = null;

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

void boot();
