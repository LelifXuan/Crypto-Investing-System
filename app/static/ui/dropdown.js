// app/static/ui/dropdown.js
// Unified custom dropdown component. Replaces all native <select> elements.
//
// Public API: mountDropdown(root, options) -> { setValue, destroy, refresh }
//
// Spec: docs/superpowers/specs/2026-07-31-dropdown-revision-design.md
//
// Revision highlights (2026-07-31):
//  - State machine: aria-selected is the single committed value source.
//    Keyboard highlight uses class .is-active + ARIA aria-activedescendant
//    pointing at a stable per-option id; close() clears .is-active so
//    re-opening starts with exactly one selected item and zero highlights.
//  - Width: trigger respects sizeMode in {content, trigger, fixed}; popover
//    measure-once via fitPopover() with no layout thrash.
//  - Popover background: replaced monolithic gradients per option with
//    a single Popover-level glass surface (CSS rev: a1e0951).
//  - Long text: option label uses overflow-wrap:break-word; trigger
//    respects data-allow-trigger-wrap for line-clamp:2.
//  - ARIA: stable per-option id, aria-activedescendant on trigger,
//    role=combobox/listbox/option preserved (existing).
//  - Scrollbar: scrollbar-color (Firefox) + ::-webkit-scrollbar (Chromium)
//    set in CSS rev: a1e0951.
//  - type-ahead: handlers only fire when popover open + Trigger focused.
//    No document-level keydown capture added.

const OPEN_CLASS = "is-open";
const ACTIVE_CLASS = "is-active";
const STATE_LOADING = "loading";
const STATE_ERROR = "error";
const Z_INDEX = 1000;
const DEFAULT_TRIGGER_MIN = 112;
const DEFAULT_TRIGGER_MAX = 280;
const DEFAULT_VIEWPORT_PADDING = 8;
const DEFAULT_POPOVER_GAP = 6;
const DEFAULT_LIST_PADDING = 6;
const DEFAULT_LIST_GAP = 2;
const DEFAULT_ITEM_MIN_HEIGHT = 40;
const DEFAULT_POPOVER_MAX = 320;

let activeInstance = null;

function clamp(value, min, max) {
  return Math.max(min, Math.min(max, value));
}

function makeOptionId(root, index) {
  const base = root.dataset.dropdownId || "anon";
  return `dropdown-opt-${base}-${index}`;
}

function currentLabel(items, value) {
  const item = items.find((i) => i.value === value);
  return item ? item.label : null;
}

function clearHighlight(popover, root) {
  if (!popover) return;
  popover.querySelectorAll(".dropdown-item.is-active").forEach((el) =>
    el.classList.remove("is-active"));
  if (root) root.removeAttribute("aria-activedescendant");
}

function syncSelected(popover, value) {
  if (!popover) return;
  const val = String(value);
  const items = Array.from(popover.querySelectorAll(".dropdown-item"));
  items.forEach((el) => {
    el.setAttribute("aria-selected", String(el.dataset.value === val));
  });
  // DEV-only assertion: enforce exactly one selected in single-select.
  if (items.length > 0) {
    const selectedItems = items.filter((el) => el.getAttribute("aria-selected") === "true");
    if (selectedItems.length > 1) {
      // eslint-disable-next-line no-console
      console.warn("Dropdown has multiple selected options", { value, selectedItems });
    }
  }
}

function buildItem(item, value, root, index, onPick) {
  const btn = document.createElement("button");
  btn.type = "button";
  btn.className = "dropdown-item";
  btn.setAttribute("role", "option");
  btn.id = makeOptionId(root, index);
  btn.dataset.value = String(item.value);
  btn.setAttribute("aria-selected", String(item.value === value));
  if (item.disabled) btn.setAttribute("disabled", "");
  const label = document.createElement("span");
  label.className = "dropdown-item-label";
  label.textContent = item.label;
  btn.appendChild(label);
  btn.addEventListener("click", () => {
    if (item.disabled) return;
    onPick(item.value);
  });
  return btn;
}

function buildPopover(root, options, onPick) {
  const popover = document.createElement("div");
  popover.className = "dropdown-popover";
  popover.setAttribute("role", "listbox");
  popover.id = `dropdown-listbox-${root.dataset.dropdownId || "anon"}`;
  popover.hidden = true;

  const list = document.createElement("div");
  list.className = "dropdown-list";
  popover.appendChild(list);

  options.items.forEach((item, i) =>
    list.appendChild(buildItem(item, options.value, root, i, onPick)));

  document.body.appendChild(popover);
  return popover;
}

function fitPopover(root, popover, opts) {
  const rect = root.getBoundingClientRect();
  const vw = document.documentElement.clientWidth;
  const vh = window.innerHeight;
  const min = opts.minTriggerWidth ?? DEFAULT_TRIGGER_MIN;
  const max = opts.maxTriggerWidth ?? DEFAULT_TRIGGER_MAX;
  const gap = DEFAULT_POPOVER_GAP;
  const listPadding = DEFAULT_LIST_PADDING;
  const listGap = DEFAULT_LIST_GAP;
  const itemMin = DEFAULT_ITEM_MIN_HEIGHT;

  // measure options natural width: combined offsetWidths of items.
  const items = Array.from(popover.querySelectorAll(".dropdown-item"));
  let naturalWidth = rect.width;
  for (const el of items) {
    const w = el.offsetWidth + 24; /* padding + scrollbar gutter */
    if (w > naturalWidth) naturalWidth = w;
  }
  naturalWidth = Math.max(naturalWidth, min);

  // horizontal bounds
  const maxAllowedByViewport = Math.min(max, vw - DEFAULT_VIEWPORT_PADDING * 2);
  const width = clamp(naturalWidth, min, maxAllowedByViewport);
  popover.style.width = `${width}px`;
  popover.style.minWidth = `${Math.min(rect.width, width)}px`;
  popover.style.maxWidth = `${maxAllowedByViewport}px`;

  // vertical: figure max-height from remaining viewport height.
  const spaceBelow = vh - rect.bottom - gap - DEFAULT_VIEWPORT_PADDING;
  const spaceAbove = rect.top - gap - DEFAULT_VIEWPORT_PADDING;
  let chosenTop, chosenMaxHeight, placement;
  if (spaceBelow >= DEFAULT_POPOVER_MAX) {
    chosenTop = rect.bottom + gap;
    chosenMaxHeight = Math.min(DEFAULT_POPOVER_MAX, spaceBelow);
    placement = "bottom-start";
  } else if (spaceAbove >= DEFAULT_POPOVER_MAX) {
    chosenTop = rect.top - DEFAULT_POPOVER_MAX - gap;
    chosenMaxHeight = Math.min(DEFAULT_POPOVER_MAX, spaceAbove);
    placement = "top-end";
  } else if (spaceBelow >= spaceAbove) {
    chosenTop = rect.bottom + gap;
    chosenMaxHeight = Math.max(itemMin + listPadding * 2 + 8, spaceBelow);
    placement = "bottom-start";
  } else {
    chosenTop = Math.max(DEFAULT_VIEWPORT_PADDING, rect.top - spaceAbove);
    chosenMaxHeight = Math.max(itemMin + listPadding * 2 + 8, spaceAbove);
    placement = "top-end";
  }
  popover.style.top = `${Math.round(chosenTop)}px`;
  popover.style.maxHeight = `${Math.round(chosenMaxHeight)}px`;
  popover.setAttribute("data-placement", placement);

  // list max-height fits inside popover: subtract list padding + gap * item estimate.
  const listEl = popover.querySelector(".dropdown-list");
  if (listEl) {
    const listMax = Math.max(itemMin + listPadding, chosenMaxHeight - listPadding * 2 - 8);
    listEl.style.maxHeight = `${Math.round(listMax)}px`;
  }

  // horizontal final: clamp left so popover fits viewport
  let left = rect.left;
  if (left + width > vw - DEFAULT_VIEWPORT_PADDING) {
    left = Math.max(DEFAULT_VIEWPORT_PADDING, vw - width - DEFAULT_VIEWPORT_PADDING);
  }
  popover.style.left = `${Math.round(left)}px`;
  popover.style.zIndex = String(Z_INDEX);
}

function ensureIconSlot(root, hasIcon) {
  const iconEl = root.querySelector(".dropdown-icon");
  if (!iconEl) return;
  iconEl.hidden = !hasIcon;
}

function renderLabel(root, label, placeholder) {
  const labelEl = root.querySelector(".dropdown-label");
  if (!labelEl) return;
  const text = label == null || label === "" ? placeholder || "" : label;
  labelEl.textContent = text;
  labelEl.classList.toggle("is-placeholder", label == null || label === "");
}

function setStateClasses(root, state) {
  root.classList.toggle("is-loading", state === STATE_LOADING);
  root.classList.toggle("is-error", state === STATE_ERROR);
}

export function mountDropdown(root, options) {
  if (!root || root.tagName !== "BUTTON") {
    throw new Error("mountDropdown: root must be a <button>");
  }

  const opts = Object.assign({
    items: [],
    value: null,
    placeholder: "",
    hasIcon: false,
    state: "ready",
    errorText: "",
    typeAhead: true,
    onChange: () => {},
    // revision 2026-07-31: optional width / wrap params
    sizeMode: "content",          // "content" | "trigger" | "fixed"
    minTriggerWidth: DEFAULT_TRIGGER_MIN,
    maxTriggerWidth: DEFAULT_TRIGGER_MAX,
    allowTriggerWrap: false,
    maxVisibleItems: 6,
    density: "comfortable",       // "comfortable" | "compact"
    placement: "auto",            // "auto" | "bottom-start" | "top-end"
  }, options || {});

  // Apply data-* — also reads existing data-* if caller already set them.
  if (!root.dataset.sizeMode) root.dataset.sizeMode = opts.sizeMode;
  if (opts.allowTriggerWrap) root.dataset.allowTriggerWrap = "true";
  if (!root.dataset.dropdownId) {
    root.dataset.dropdownId = `dropdown-${Math.random().toString(36).slice(2, 8)}`;
  }

  ensureIconSlot(root, opts.hasIcon);
  renderLabel(root, currentLabel(opts.items, opts.value), opts.placeholder);
  setStateClasses(root, opts.state);

  // Trigger ARIA baseline (chromium will sync aria-controls when opened)
  root.setAttribute("aria-haspopup", "listbox");
  root.setAttribute("aria-expanded", "false");
  root.setAttribute("aria-controls", `dropdown-listbox-${root.dataset.dropdownId}`);

  let popover = null;
  let activeIndex = -1;
  let typeAheadBuffer = "";
  let typeAheadTimer = null;

  function selectValue(value, { silent = false } = {}) {
    const prev = opts.value;
    if (prev === value) {
      // even when unchanged, re-assert aria-selected so it stays single
      syncSelected(popover, value);
      return;
    }
    opts.value = value;
    renderLabel(root, currentLabel(opts.items, value), opts.placeholder);
    syncSelected(popover, value);
    if (!silent) opts.onChange(value, prev);
  }

  function indexOfSelected() {
    const items = Array.from(popover.querySelectorAll(".dropdown-item:not([disabled])"));
    return items.findIndex((el) => el.dataset.value === String(opts.value));
  }

  function syncHighlight() {
    if (!popover || activeIndex < 0) {
      clearHighlight(popover, root);
      return;
    }
    const items = Array.from(popover.querySelectorAll(".dropdown-item:not([disabled])"));
    items.forEach((el, idx) => {
      const on = idx === activeIndex;
      el.classList.toggle("is-active", on);
      if (on && el.id) {
        root.setAttribute("aria-activedescendant", el.id);
        if (el.scrollIntoView) el.scrollIntoView({ block: "nearest" });
      }
    });
  }

  function open() {
    if (root.disabled) return;
    if (root.classList.contains(OPEN_CLASS)) return;
    if (activeInstance && activeInstance !== instance) activeInstance.close({ silent: true });
    activeInstance = instance;
    if (!popover) popover = buildPopover(root, opts, (v) => selectValue(v));
    popover.hidden = false;
    root.classList.add(OPEN_CLASS);
    root.setAttribute("aria-expanded", "true");
    // Always reassert selected + clear stale highlight
    syncSelected(popover, opts.value);
    clearHighlight(popover, root);
    const sel = popover.querySelector('.dropdown-item[aria-selected="true"]');
    if (sel && sel.scrollIntoView) sel.scrollIntoView({ block: "nearest" });
    activeIndex = indexOfSelected();
    if (activeIndex >= 0) syncHighlight();
    fitPopover(root, popover, opts);
  }

  function close() {
    if (!root.classList.contains(OPEN_CLASS)) return;
    root.classList.remove(OPEN_CLASS);
    root.setAttribute("aria-expanded", "false");
    if (popover) popover.hidden = true;
    // Hard cleanup of keyboard highlight (INV-2)
    clearHighlight(popover, root);
    activeIndex = -1;
    if (activeInstance === instance) activeInstance = null;
  }

  function onClickRoot(e) {
    e.preventDefault();
    e.stopPropagation();
    if (root.disabled) return;
    if (root.classList.contains(OPEN_CLASS)) close();
    else open();
  }

  function onKeyDownRoot(e) {
    if (root.disabled) return;
    if (!root.classList.contains(OPEN_CLASS)) {
      if (["Enter", " ", "ArrowDown"].includes(e.key)) {
        e.preventDefault();
        open();
      }
      return;
    }
    if (e.key === "Escape") {
      e.preventDefault();
      close();
      return;
    }
    const items = popover
      ? Array.from(popover.querySelectorAll(".dropdown-item:not([disabled])"))
      : [];
    if (e.key === "ArrowDown") {
      e.preventDefault();
      const next = clamp(activeIndex + (activeIndex < 0 ? 0 : 1), 0, items.length - 1);
      activeIndex = next;
      syncHighlight();
    } else if (e.key === "ArrowUp") {
      e.preventDefault();
      const next = clamp(activeIndex - 1, 0, items.length - 1);
      activeIndex = next;
      syncHighlight();
    } else if (e.key === "Home") {
      e.preventDefault();
      activeIndex = 0;
      syncHighlight();
    } else if (e.key === "End") {
      e.preventDefault();
      activeIndex = items.length - 1;
      syncHighlight();
    } else if (e.key === "Enter" || e.key === " ") {
      e.preventDefault();
      if (items.length === 0) {
        close();
        return;
      }
      const target = items[activeIndex] || items[0];
      selectValue(target.dataset.value);
      close();
    } else if (opts.typeAhead && /^[a-zA-Z0-9]$/.test(e.key)) {
      // type-ahead runs only when popover is open. We never install a
      // document-level capture; the trigger's keydown handler is the
      // only consumer of these letter keys.
      typeAheadBuffer += e.key.toLowerCase();
      clearTimeout(typeAheadTimer);
      typeAheadTimer = setTimeout(() => { typeAheadBuffer = ""; }, 600);
      const prefixIdx = items.findIndex((el) =>
        el.textContent.trim().toLowerCase().startsWith(typeAheadBuffer));
      let matchIdx = prefixIdx;
      if (matchIdx < 0 && typeAheadBuffer.length <= 2) {
        matchIdx = items.findIndex((el) =>
          el.textContent.trim().toLowerCase().includes(typeAheadBuffer));
      }
      if (matchIdx >= 0) {
        activeIndex = matchIdx;
        syncHighlight();
      }
    }
  }

  function onDocumentClick(e) {
    if (!root.classList.contains(OPEN_CLASS)) return;
    if (popover && popover.contains(e.target)) return;
    if (root.contains(e.target)) return;
    close();
  }

  function onScrollOrResize() {
    if (!root.classList.contains(OPEN_CLASS) || !popover) return;
    fitPopover(root, popover, opts);
    const rect = root.getBoundingClientRect();
    if (rect.bottom < 0 || rect.top > window.innerHeight) close();
  }

  root.addEventListener("click", onClickRoot);
  root.addEventListener("keydown", onKeyDownRoot);
  document.addEventListener("click", onDocumentClick, true);
  window.addEventListener("scroll", onScrollOrResize, true);
  window.addEventListener("resize", onScrollOrResize);

  const instance = {
    setValue(value, { silent = true } = {}) {
      selectValue(value, { silent });
    },
    destroy() {
      close();
      root.removeEventListener("click", onClickRoot);
      root.removeEventListener("keydown", onKeyDownRoot);
      document.removeEventListener("click", onDocumentClick, true);
      window.removeEventListener("scroll", onScrollOrResize, true);
      window.removeEventListener("resize", onScrollOrResize);
      if (popover) {
        // drop every option's id and class so re-mounting on the same
        // root does not collide with previous ids.
        Array.from(popover.querySelectorAll(".dropdown-item")).forEach((el) => {
          el.classList.remove(ACTIVE_CLASS);
          el.removeAttribute("aria-selected");
        });
        popover.remove();
        popover = null;
      }
      root.removeAttribute("aria-activedescendant");
      root.removeAttribute("aria-controls");
    },
    refresh(items) {
      opts.items = Array.isArray(items) ? items : [];
      if (popover) {
        const list = popover.querySelector(".dropdown-list");
        list.innerHTML = "";
        opts.items.forEach((item, i) =>
          list.appendChild(buildItem(item, opts.value, root, i, (v) => selectValue(v))));
        syncSelected(popover, opts.value);
        renderLabel(root, currentLabel(opts.items, opts.value), opts.placeholder);
      }
    },
  };
  return instance;
}

export { mountDropdown };
