import { escapeHtml } from "../core/dom.js";
import { registerOverlay, LAYER } from "./overlayCoordinator.js";

export function mountCommandPalette({ registry }) {
  const lifetime = new AbortController();
  const overlay = document.createElement("div");
  overlay.className = "workbench-command-overlay";
  overlay.hidden = true;
  overlay.innerHTML = `
    <section class="workbench-command-dialog" role="dialog" aria-modal="true" aria-labelledby="workbench-command-title">
      <header><h2 id="workbench-command-title">工作台命令</h2><button type="button" data-command-close aria-label="关闭命令菜单">关闭</button></header>
      <label for="workbench-command-input">搜索当前页面操作</label>
      <input id="workbench-command-input" type="search" role="combobox" aria-autocomplete="list" aria-expanded="true" aria-controls="workbench-command-results" autocomplete="off" placeholder="输入操作名称">
      <div id="workbench-command-results" role="listbox" aria-label="可用命令"></div>
      <p data-command-empty hidden>没有匹配的命令</p>
      <footer>↑↓ 选择 · Enter 执行 · Esc 关闭</footer>
    </section>`;
  const status = document.createElement("p");
  status.className = "workbench-command-status";
  status.setAttribute("role", "status");
  status.hidden = true;
  document.body.append(overlay, status);
  const dialog = overlay.querySelector("section");
  const input = overlay.querySelector("input");
  const resultsEl = overlay.querySelector('[role="listbox"]');
  let results = [], activeIndex = 0, layer = null, origin = null, destroyed = false;
  const highlight = () => {
    resultsEl.querySelectorAll('[role="option"]').forEach((el, index) => {
      el.setAttribute("aria-selected", String(index === activeIndex));
    });
    const active = resultsEl.children[activeIndex];
    if (active) {
      input.setAttribute("aria-activedescendant", active.id);
      active.scrollIntoView({ block: "nearest" });
    } else input.removeAttribute("aria-activedescendant");
  };
  const render = () => {
    if (overlay.hidden || destroyed) return;
    const activeId = results[activeIndex]?.id;
    results = registry.query(input.value);
    activeIndex = Math.max(0, results.findIndex((item) => item.id === activeId));
    resultsEl.innerHTML = results.map((item, index) => `
      <div role="option" id="workbench-command-option-${index}" data-command-id="${escapeHtml(item.id)}" aria-disabled="${!item.enabled}" aria-selected="false">
        <strong>${escapeHtml(item.label)}</strong><small>${escapeHtml(item.group)}${item.shortcut ? " · " + escapeHtml(item.shortcut) : ""}</small>
      </div>`).join("");
    overlay.querySelector("[data-command-empty]").hidden = results.length !== 0;
    highlight();
  };
  const close = ({ restoreFocus = true } = {}) => {
    if (overlay.hidden) return;
    overlay.hidden = true;
    layer?.destroy(); layer = null;
    document.body.classList.remove("is-command-palette-open");
    input.value = "";
    if (restoreFocus && origin?.isConnected) origin.focus({ preventScroll: true });
  };
  const open = () => {
    if (destroyed || !overlay.hidden || registry.query("").length === 0) return;
    origin = document.activeElement;
    status.hidden = true;
    overlay.hidden = false;
    document.body.classList.add("is-command-palette-open");
    layer = registerOverlay({ element: dialog, priority: LAYER.palette, modal: true, close });
    render(); input.focus({ preventScroll: true });
  };
  const execute = async (id) => {
    const target = registry.query(input.value).find((item) => item.id === id);
    if (!target?.enabled) return;
    // Release focus scope before an action focuses a control or navigates.
    close({ restoreFocus: true });
    try { await registry.run(id); }
    catch {
      if (!destroyed) { status.textContent = "操作未完成，请检查当前页面状态后重试。"; status.hidden = false; }
    }
  };
  document.addEventListener("keydown", (event) => {
    if (event.isComposing || event.altKey || !event.key) return;
    if ((event.ctrlKey || event.metaKey) && event.key.toLowerCase() === "k") {
      event.preventDefault(); event.stopImmediatePropagation();
      if (overlay.hidden) open(); else close();
    }
  }, { capture: true, signal: lifetime.signal });
  input.addEventListener("input", () => { activeIndex = 0; render(); }, { signal: lifetime.signal });
  input.addEventListener("keydown", (event) => {
    if (event.isComposing) return;
    if (event.key === "ArrowDown" || event.key === "ArrowUp") {
      event.preventDefault();
      if (results.length) activeIndex = (activeIndex + (event.key === "ArrowDown" ? 1 : -1) + results.length) % results.length;
      highlight();
    }
    if (event.key === "Enter") { event.preventDefault(); void execute(results[activeIndex]?.id); }
  }, { signal: lifetime.signal });
  overlay.addEventListener("click", (event) => {
    if (event.target === overlay || event.target.closest("[data-command-close]")) close();
    const item = event.target.closest("[data-command-id]");
    if (item) void execute(item.dataset.commandId);
  }, { signal: lifetime.signal });
  const unsubscribe = registry.subscribe(render);
  return { open, close, destroy() { close(); destroyed = true; unsubscribe(); lifetime.abort(); overlay.remove(); status.remove(); } };
}
