import { setRoot, bindTooltipEscape, renderNavSkeleton, revealStagger, updatePageContext } from "./core/dom.js";
import { createCommandRegistry } from "./core/commandRegistry.js";
import { mountCommandPalette } from "./ui/commandPalette.js";
import { registerOverlay, LAYER, isTopOverlay } from "./ui/overlayCoordinator.js";

const assetVersion = window.__ASSET_VERSION__ ? `?v=${encodeURIComponent(window.__ASSET_VERSION__)}` : "";
const moduleLoadPromises = new Map();
const loadPageModule = (path) => {
  if (!moduleLoadPromises.has(path)) {
    const versionedPath = assetVersion
      ? `${path}${path.includes("?") ? "&" : "?"}${assetVersion.slice(1)}`
      : path;
    const p = import(versionedPath);
    moduleLoadPromises.set(path, p);
    // 2026-08-18: if the import fails (truncated network response →
    // "Unexpected end of input"), evict the rejected promise so the
    // next navigation retries instead of permanently serving the cached
    // failure until hard refresh.
    p.catch(() => {
      if (moduleLoadPromises.get(path) === p) {
        moduleLoadPromises.delete(path);
      }
    });
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
  "ai-strategy": () => loadPageModule("./pages/strategy.js?v=opportunity-matrix-v2"),
};

const PAGE_META = {
  "monitoring-overview": { title: "监控总览", group: "研究", route: "/monitoring-page", layout: "overview" },
  "market-events": { title: "市场事件", group: "研究", route: "/market-events-page", layout: "overview" },
  "macro-calendar": { title: "宏观日历", group: "研究", route: "/macro-calendar-page", layout: "overview" },
  "market-analysis": { title: "技术指标", group: "Crypto", route: "/indicators-page", layout: "analysis" },
  "market-structure": { title: "形态结构", group: "Crypto", route: "/structure-page", layout: "analysis" },
  "btc-derivatives": { title: "BTC 衍生品市场", group: "Crypto", route: "/btc-derivatives-page", layout: "analysis" },
  "ai-strategy": { title: "AI 策略", group: "Crypto", route: "/strategy-page", layout: "workbench" },
  "ashare-etf": { title: "A股 ETF", group: "配置", route: "/ashare-etf-page", layout: "workbench" },
  "gold-allocation": { title: "黄金配置", group: "配置", route: "/gold-allocation-page", layout: "workbench" },
  "knowledge-base": { title: "知识百科", group: "参考", route: "/knowledge-page", layout: "reference" },
};

let activeController = null;
const commands = createCommandRegistry();
let activeCommandScope = null;
let palette = null;
let activePageId = null;
let spaNavigationInFlight = false;
let routeEnterCleanupTimer = null;
let pageIdentityCleanupTimer = null;
// When a nav click lands while the previous page's boot() is still settling
// (mount() may await a data fetch), the click used to be silently dropped —
// the link felt dead and verify_pages' SPA-switch test timed out waiting for
// content that never came. Queue the pending navigation instead and flush it
// once the in-flight boot settles.
let pendingSpaNavigation = null;
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

function setActiveNavigation(pageId) {
  document.querySelectorAll("[data-page-link]").forEach((link) => {
    const isActive = link.getAttribute("data-page-link") === pageId;
    link.classList.toggle("is-active", isActive);
    link.classList.remove("is-pending");
    if (isActive) link.setAttribute("aria-current", "page");
    else link.removeAttribute("aria-current");
  });
}

function setPendingNavigation(pageId) {
  document.querySelectorAll("[data-page-link]").forEach((link) => {
    link.classList.toggle("is-pending", link.getAttribute("data-page-link") === pageId);
  });
}

function setDocumentTitleForPage(pageId) {
  const meta = PAGE_META[pageId] || { title: "Market Research Terminal", group: "研究", layout: "overview" };
  const title = meta.title;
  const heading = document.getElementById("app-page-title");
  if (heading) heading.textContent = title;
  const breadcrumb = document.getElementById("app-breadcrumb");
  if (breadcrumb) breadcrumb.textContent = meta.group;
  document.title = `${title} | Market Research Terminal`;
  document.body.dataset.pageTitle = title;
  document.body.dataset.pageLayout = meta.layout;
  setActiveNavigation(pageId);
  updatePageContext();
}

function transitionInPageIdentity(animate) {
  const identity = document.querySelector(".app-page-identity");
  if (pageIdentityCleanupTimer) {
    clearTimeout(pageIdentityCleanupTimer);
    pageIdentityCleanupTimer = null;
  }
  identity?.classList.remove("is-route-entering");
  if (!animate || !identity) return;
  void identity.offsetWidth;
  identity.classList.add("is-route-entering");
  pageIdentityCleanupTimer = setTimeout(() => {
    identity.classList.remove("is-route-entering");
    pageIdentityCleanupTimer = null;
  }, 220);
}

const FOCUSABLE_SELECTOR = 'a[href], button:not([disabled]), [tabindex]:not([tabindex="-1"])';
let shellReturnFocus = null;
let shellLayer = null;

function setShellPanel(panel, open, trigger = null, moveFocus = true) {
  if (panel !== "nav") return;
  const className = "is-nav-open";
  const target = document.getElementById("app-sidebar");
  const toggle = document.querySelector('[data-shell-action="open-nav"]');
  document.body.classList.toggle(className, open);
  target?.setAttribute("aria-hidden", open || matchMedia("(min-width: 1280px)").matches ? "false" : "true");
  toggle?.setAttribute("aria-expanded", open ? "true" : "false");
  if (open && target && !shellLayer) shellLayer = registerOverlay({ element: target, priority: LAYER.dialog, modal: true, close: () => closeShellPanels() });
  if (!open) { shellLayer?.destroy(); shellLayer = null; }
  if (open && moveFocus) {
    shellReturnFocus = trigger || document.activeElement;
    requestAnimationFrame(() => target?.querySelector(FOCUSABLE_SELECTOR)?.focus());
  } else if (shellReturnFocus instanceof HTMLElement) {
    if (moveFocus) shellReturnFocus.focus();
    shellReturnFocus = null;
  }
}

function closeShellPanels(moveFocus = true) {
  setShellPanel("nav", false, null, moveFocus);
}

function scrollPageToTop() {
  const reduceMotion = window.matchMedia?.("(prefers-reduced-motion: reduce)").matches;
  window.scrollTo({ top: 0, behavior: reduceMotion ? "auto" : "smooth" });
  document.getElementById("page-root")?.focus({ preventScroll: true });
}

function installAppShell() {
  const icons = {
    overview: '<svg viewBox="0 0 24 24"><path d="M4 13h6V4H4zM14 20h6v-9h-6zM4 20h6v-3H4zM14 7h6V4h-6z"/></svg>',
    events: '<svg viewBox="0 0 24 24"><path d="M5 4h14v16H5zM8 8h8M8 12h8M8 16h5"/></svg>',
    calendar: '<svg viewBox="0 0 24 24"><path d="M5 6h14v14H5zM8 3v6M16 3v6M5 10h14"/></svg>',
    analysis: '<svg viewBox="0 0 24 24"><path d="M4 18 9 12l4 3 7-9M4 20h16"/></svg>',
    structure: '<svg viewBox="0 0 24 24"><path d="M5 17 9 7l5 10 5-8M4 20h16"/></svg>',
    derivatives: '<svg viewBox="0 0 24 24"><path d="M5 6h14M5 12h14M5 18h14M8 4v4M15 10v4M11 16v4"/></svg>',
    strategy: '<svg viewBox="0 0 24 24"><path d="M12 3v4M12 17v4M4 12h4M16 12h4M7 7l2 2M15 15l2 2M17 7l-2 2M9 15l-2 2M9 12a3 3 0 1 0 6 0 3 3 0 0 0-6 0"/></svg>',
    etf: '<svg viewBox="0 0 24 24"><path d="M4 19h16M6 16V9M11 16V5M16 16v-4M20 16V7"/></svg>',
    gold: '<svg viewBox="0 0 24 24"><path d="m7 8 3-4h4l3 4 3 11H4zM8 8h8M10 4l2 4 2-4"/></svg>',
    knowledge: '<svg viewBox="0 0 24 24"><path d="M5 4h10a4 4 0 0 1 4 4v12H9a4 4 0 0 0-4-4zM5 4v12M9 8h6M9 12h6"/></svg>',
  };
  document.querySelectorAll("[data-nav-icon]").forEach((slot) => {
    slot.innerHTML = icons[slot.getAttribute("data-nav-icon")] || "";
  });
  document.addEventListener("click", (event) => {
    const control = event.target instanceof Element ? event.target.closest("[data-shell-action]") : null;
    if (!control) return;
    const action = control.getAttribute("data-shell-action");
    if (action === "open-nav") setShellPanel("nav", true, control);
    if (action === "close-nav") setShellPanel("nav", false);
    if (action === "back-to-top") scrollPageToTop();
    if (action === "toggle-sidebar") {
      if (matchMedia("(max-width: 1279px)").matches) {
        setShellPanel("nav", false);
      } else {
        const collapsed = document.body.classList.toggle("is-sidebar-collapsed");
        control.setAttribute("aria-expanded", collapsed ? "false" : "true");
        control.setAttribute("aria-label", collapsed ? "展开导航" : "收起导航");
      }
    }
  });
  document.addEventListener("keydown", (event) => {
    if (!isTopOverlay(document.getElementById("app-sidebar"))) return;
    if (event.key === "Escape") closeShellPanels();
    if (event.key !== "Tab") return;
    const openPanel = document.body.classList.contains("is-nav-open")
      ? document.getElementById("app-sidebar")
      : null;
    if (!openPanel) return;
    const focusable = [...openPanel.querySelectorAll(FOCUSABLE_SELECTOR)].filter((item) => item.offsetParent !== null);
    if (!focusable.length) return;
    const first = focusable[0];
    const last = focusable[focusable.length - 1];
    if (event.shiftKey && document.activeElement === first) { event.preventDefault(); last.focus(); }
    else if (!event.shiftKey && document.activeElement === last) { event.preventDefault(); first.focus(); }
  });
}

/**
 * Wait for a CSS animation to finish on an element.
 * Returns a promise that resolves after `fallbackMs` if the element
 * has no running animations (or if reduced-motion is enabled).
 */
function awaitAnimationEnd(el, fallbackMs) {
  if (!el || !el.getAnimations) return Promise.resolve();
  const animations = el.getAnimations({ subtree: false });
  if (!animations.length) return Promise.resolve();
  return Promise.allSettled(animations.map((a) => a.finished)).then(() => {});
}

function clearRouteAnimationClasses(pageRoot) {
  if (routeEnterCleanupTimer) {
    clearTimeout(routeEnterCleanupTimer);
    routeEnterCleanupTimer = null;
  }
  pageRoot?.classList.remove("page-transition", "page-transition-out", "page-transition-skeleton");
}

async function transitionOutCurrentPage(pageRoot) {
  if (!pageRoot || pageRoot.childElementCount === 0) return;
  clearRouteAnimationClasses(pageRoot);
  pageRoot.classList.add("page-transition-out");
  await Promise.race([
    awaitAnimationEnd(pageRoot, 80),
    new Promise((resolve) => setTimeout(resolve, 120)),
  ]).catch(() => {});
}

function mountRouteSkeleton(pageRoot, pageMeta) {
  if (!pageRoot) return;
  clearRouteAnimationClasses(pageRoot);
  pageRoot.innerHTML = renderNavSkeleton(pageMeta);
  pageRoot.setAttribute("aria-busy", "true");
  pageRoot.classList.add("page-transition-skeleton");
}

function transitionInNewPage(pageRoot, animate) {
  if (!pageRoot) return;
  clearRouteAnimationClasses(pageRoot);
  pageRoot.setAttribute("aria-busy", "false");
  if (!animate || pageRoot.childElementCount === 0) return;
  // The route skeleton and real page are separate visual states. Forcing a
  // layout boundary here makes the freshly mounted page start at the first
  // enter frame instead of inheriting the skeleton's final opacity.
  void pageRoot.offsetWidth;
  pageRoot.classList.add("page-transition");
  revealStagger(pageRoot);
  routeEnterCleanupTimer = setTimeout(() => {
    pageRoot.classList.remove("page-transition");
    routeEnterCleanupTimer = null;
  }, 260);
}

async function boot() {
  const pageId = document.body.dataset.page;
  const loadModule = pageModules[pageId];
  if (!loadModule) return;
  const pageRoot = document.getElementById("page-root");
  const pageMeta = PAGE_META[pageId] || { title: document.body.dataset.pageTitle || "页面", layout: "overview" };
  const isRouteTransition = activePageId !== null && activePageId !== pageId;
  const previousController = activeController;
  activeCommandScope?.destroy();
  activeCommandScope = null;
  closeShellPanels(false);
  if (pageRoot) pageRoot.dataset.layout = pageMeta.layout;
  // §16.D — install Escape->blur on tooltip anchors once per SPA boot.
  bindTooltipEscape(document);

  // Route motion must start before module/asset loading. The old flow replaced
  // the page with a skeleton in navigateToPage(), so the exit animation was
  // accidentally applied to that skeleton instead of the visible old page.
  if (isRouteTransition) {
    await transitionOutCurrentPage(pageRoot);
    if (previousController) await previousController.unmount();
    activeController = null;
    mountRouteSkeleton(pageRoot, pageMeta);
    window.scrollTo({ top: 0, behavior: "instant" });
  } else if (pageRoot && pageRoot.childElementCount === 0) {
    // Initial page load gets a stable shell but deliberately skips route
    // motion; repeated entrance animation on every reload adds no information.
    mountRouteSkeleton(pageRoot, pageMeta);
  }
  setDocumentTitleForPage(pageId);
  transitionInPageIdentity(isRouteTransition);

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
    transitionInNewPage(pageRoot, isRouteTransition);
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
    activeCommandScope = commands.createScope(pageId);
    const renderResult = await renderPage({ commands: activeCommandScope });
    activeController = normalizeController(renderResult);
    // Most legacy renderers perform their initial mount inside renderPage()
    // and return a teardown-only controller. Wrapper modules expose an
    // explicit mount() and opt into the second lifecycle step.
    if (renderResult && typeof renderResult.mount === "function") {
      await activeController.mount();
    }
    transitionInNewPage(pageRoot, isRouteTransition);
    if (pageId !== "ai-strategy") {
      // AI strategy has the largest local renderer graph. Warm it once after
      // the first visible page renders so opening the workbench remains within
      // the 500 ms SPA-shell budget even on a cold browser context.
      setTimeout(() => prefetchPage("ai-strategy"), 0);
    }
  } catch (error) {
    console.error("page:render:error", pageId, error);
    activeCommandScope?.destroy();
    activeCommandScope = null;
    activeController = null;
    renderFatalPageError("页面渲染失败", "页面初始化过程中出现运行时错误，请刷新或稍后重试。", "render");
    transitionInNewPage(pageRoot, isRouteTransition);
  }
}

const scheduleBoot = () => {
  document.body.classList.add("is-page-loading");
  void boot().finally(() => {
    spaNavigationInFlight = false;
    document.body.classList.remove("is-page-loading");
    // Flush a navigation that was queued while this boot was in flight.
    if (pendingSpaNavigation) {
      const pending = pendingSpaNavigation;
      pendingSpaNavigation = null;
      navigateToPage(pending.pageId, pending.href);
    }
  });
};

function navigateToPage(pageId, href) {
  palette?.close({ restoreFocus: false });
  activeCommandScope?.destroy();
  spaNavigationInFlight = true;
  window.history.pushState({ pageId, href }, "", href);
  document.body.dataset.page = pageId;
  // Selection responds on the click frame while the topbar/content keep their
  // own motion cadence. The old page remains mounted until boot() completes
  // its short exit transition.
  setActiveNavigation(pageId);
  scheduleBoot();
}

function requestNavigation(pageId, href = PAGE_META[pageId]?.route) {
  if (!PAGE_META[pageId] || !href || pageId === activePageId) return;
  if (spaNavigationInFlight) {
    pendingSpaNavigation = { pageId, href };
    setPendingNavigation(pageId);
    return;
  }
  navigateToPage(pageId, href);
}

function installSpaRouter() {
  if (!window.history || !window.history.pushState) return;
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
    const href = link.getAttribute("href") || PAGE_META[pageId]?.route || `/${pageId}-page`;
    event.preventDefault();
    requestNavigation(pageId, href);
  });

  window.addEventListener("popstate", (event) => {
    const state = event.state;
    const pageId = (state && state.pageId) || document.body.dataset.page;
    if (!pageId || !pageModules[pageId]) return;
    if (pageId === activePageId) return;
    // A queued nav click is moot once the user navigates via back/forward —
    // clear it so the boot finally doesn't bounce back to the stale target.
    pendingSpaNavigation = null;
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
  activeCommandScope?.destroy();
  palette?.destroy();
  commands.destroy();
  if (activeController) {
    void activeController.unmount();
  }
});

installAppShell();
palette = mountCommandPalette({ registry: commands });
// Page navigation already has a persistent, structured sidebar. Repeating every
// route as a flat command list obscures the actions that are specific to the
// current workflow, so the palette is intentionally scoped to page actions.
if (!history.state?.pageId) history.replaceState({ ...history.state, pageId: document.body.dataset.page, href: location.href }, "", location.href);
installSpaRouter();
scheduleBoot();
