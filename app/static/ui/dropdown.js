// app/static/ui/dropdown.js
// Unified custom dropdown component. Replaces all native <select> elements.
// Public API: mountDropdown(root, options) -> { setValue, destroy, refresh }
// Pure DOM/ARIA logic; does NOT read or write appState.

const OPEN_CLASS = "is-open";
const ACTIVE_CLASS = "is-active";
const STATE_LOADING = "loading";
const STATE_ERROR = "error";
const Z_INDEX = 1000;
const POPOVER_MAX_HEIGHT = 280; // px
const ITEM_HEIGHT = 44; // px (contract)
const FADEOUT_HEIGHT = 8;

let activeInstance = null;

function clamp(value, min, max) {
  return Math.max(min, Math.min(max, value));
}

function computePlacement(root) {
  const rect = root.getBoundingClientRect();
  const spaceBelow = window.innerHeight - rect.bottom;
  const spaceAbove = rect.top;
  if (spaceBelow >= POPOVER_MAX_HEIGHT + 16) return "bottom-start";
  if (spaceAbove >= POPOVER_MAX_HEIGHT + 16) return "top-end";
  return spaceBelow >= spaceAbove ? "bottom-start" : "top-end";
}

function positionPopover(root, popover) {
  const rect = root.getBoundingClientRect();
  const placement = computePlacement(root);
  const popHeight = Math.min(POPOVER_MAX_HEIGHT, popover.scrollHeight || POPOVER_MAX_HEIGHT);
  popover.setAttribute("data-placement", placement);
  popover.style.zIndex = String(Z_INDEX);
  popover.style.minWidth = `${Math.round(rect.width)}px`;
  popover.style.maxHeight = `${POPOVER_MAX_HEIGHT}px`;
  popover.style.left = `${Math.round(rect.left)}px`;
  popover.style.width = `${Math.round(rect.width)}px`;
  if (placement === "top-end") {
    popover.style.top = `${Math.round(rect.top - popHeight - 6)}px`;
  } else {
    popover.style.top = `${Math.round(rect.bottom + 6)}px`;
  }
  const vw = document.documentElement.clientWidth;
  if (rect.left + rect.width > vw - 8) {
    popover.style.left = `${Math.max(8, Math.round(vw - rect.width - 8))}px`;
  }
}

function renderLabel(root, label, placeholder) {
  const labelEl = root.querySelector(".dropdown-label");
  if (!labelEl) return;
  const text = label == null || label === "" ? placeholder || "" : label;
  labelEl.textContent = text;
  labelEl.classList.toggle("is-placeholder", label == null || label === "");
}

function ensureIconSlot(root, hasIcon) {
  const iconEl = root.querySelector(".dropdown-icon");
  if (!iconEl) return;
  iconEl.hidden = !hasIcon;
}

function setStateClasses(root, state) {
  root.classList.toggle("is-loading", state === STATE_LOADING);
  root.classList.toggle("is-error", state === STATE_ERROR);
}

function buildItem(item, value, onPick) {
  const btn = document.createElement("button");
  btn.type = "button";
  btn.className = "dropdown-item";
  btn.setAttribute("role", "option");
  btn.dataset.value = String(item.value);
  btn.setAttribute("aria-selected", String(item.value === value));
  if (item.disabled) btn.setAttribute("disabled", "");
  btn.textContent = item.label;
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

  options.items.forEach((item) => {
    list.appendChild(buildItem(item, options.value, onPick));
  });

  const fade = document.createElement("div");
  fade.className = "dropdown-fadeout";
  fade.hidden = true;
  popover.appendChild(fade);

  document.body.appendChild(popover);
  return popover;
}

function showFadeout(popover) {
  const fade = popover.querySelector(".dropdown-fadeout");
  const list = popover.querySelector(".dropdown-list");
  if (!fade || !list) return;
  const overflows = list.scrollHeight > list.clientHeight;
  const atBottom = list.scrollTop + list.clientHeight >= list.scrollHeight - 2;
  fade.hidden = !(overflows && !atBottom);
  if (!fade.hidden) {
    fade.style.bottom = "0";
  }
}

function updateFadeout(popover) {
  if (popover.hidden) return;
  showFadeout(popover);
}

function mountDropdown(root, options) {
  if (!root || root.tagName !== "BUTTON") {
    throw new Error("mountDropdown: root must be a <button>");
  }
  const opts = {
    items: Array.isArray(options.items) ? options.items : [],
    value: options.value ?? null,
    placeholder: options.placeholder ?? "",
    hasIcon: !!options.hasIcon,
    state: options.state || "ready",
    errorText: options.errorText || "",
    typeAhead: options.typeAhead !== false,
    onChange: typeof options.onChange === "function" ? options.onChange : () => {},
  };

  ensureIconSlot(root, opts.hasIcon);
  renderLabel(root, currentLabel(), opts.placeholder);
  setStateClasses(root, opts.state);
  root.setAttribute("aria-expanded", "false");

  function currentLabel() {
    const item = opts.items.find((i) => i.value === opts.value);
    return item ? item.label : null;
  }

  let popover = null;
  let activeIndex = -1;
  let typeAheadBuffer = "";
  let typeAheadTimer = null;

  function selectValue(value, { silent = false } = {}) {
    const prev = opts.value;
    if (prev === value) return;
    opts.value = value;
    renderLabel(root, currentLabel(), opts.placeholder);
    syncSelected();
    if (!silent) opts.onChange(value, prev);
  }

  function syncSelected() {
    if (!popover) return;
    Array.from(popover.querySelectorAll(".dropdown-item")).forEach((el) => {
      el.setAttribute("aria-selected", String(el.dataset.value === String(opts.value)));
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
    syncSelected();
    const sel = popover.querySelector('.dropdown-item[aria-selected="true"]');
    if (sel && sel.scrollIntoView) sel.scrollIntoView({ block: "nearest" });
    activeIndex = indexOfSelected();
    moveActive(activeIndex);
    positionPopover(root, popover);
    updateFadeout(popover);
  }

  function indexOfSelected() {
    const items = Array.from(popover.querySelectorAll(".dropdown-item:not([disabled])"));
    return items.findIndex((el) => el.dataset.value === String(opts.value));
  }

  function moveActive(idx) {
    if (!popover) return;
    const items = Array.from(popover.querySelectorAll(".dropdown-item:not([disabled])"));
    items.forEach((el) => el.classList.remove(ACTIVE_CLASS));
    if (idx < 0 || idx >= items.length) {
      activeIndex = -1;
      return;
    }
    items[idx].classList.add(ACTIVE_CLASS);
    items[idx].scrollIntoView({ block: "nearest" });
    activeIndex = idx;
  }

  function close() {
    if (!root.classList.contains(OPEN_CLASS)) return;
    root.classList.remove(OPEN_CLASS);
    root.setAttribute("aria-expanded", "false");
    if (popover) popover.hidden = true;
    if (activeInstance === instance) activeInstance = null;
  }

  function onClickRoot(e) {
    e.preventDefault();
    e.stopPropagation();
    if (root.disabled) return;
    if (root.classList.contains(OPEN_CLASS)) {
      close();
    } else {
      open();
    }
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
    } else if (e.key === "ArrowDown") {
      e.preventDefault();
      const items = popover.querySelectorAll(".dropdown-item:not([disabled])");
      moveActive(clamp(activeIndex + 1, 0, items.length - 1));
    } else if (e.key === "ArrowUp") {
      e.preventDefault();
      const items = popover.querySelectorAll(".dropdown-item:not([disabled])");
      moveActive(clamp(activeIndex - 1, 0, items.length - 1));
    } else if (e.key === "Home") {
      e.preventDefault();
      moveActive(0);
    } else if (e.key === "End") {
      e.preventDefault();
      const items = popover.querySelectorAll(".dropdown-item:not([disabled])");
      moveActive(items.length - 1);
    } else if (e.key === "Enter" || e.key === " ") {
      e.preventDefault();
      const items = Array.from(popover.querySelectorAll(".dropdown-item:not([disabled])"));
      const target = items[activeIndex];
      if (target) selectValue(target.dataset.value);
      close();
    } else if (opts.typeAhead && /^[a-zA-Z0-9]$/.test(e.key)) {
      typeAheadBuffer += e.key.toLowerCase();
      clearTimeout(typeAheadTimer);
      typeAheadTimer = setTimeout(() => { typeAheadBuffer = ""; }, 600);
      const items = Array.from(popover.querySelectorAll(".dropdown-item:not([disabled])"));
      const matchIdx = items.findIndex((el) =>
        el.textContent.trim().toLowerCase().startsWith(typeAheadBuffer));
      if (matchIdx >= 0) moveActive(matchIdx);
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
    positionPopover(root, popover);
    const rect = root.getBoundingClientRect();
    if (rect.bottom < 0 || rect.top > window.innerHeight) close();
  }

  function onListScroll() {
    updateFadeout(popover);
  }

  root.addEventListener("click", onClickRoot);
  root.addEventListener("keydown", onKeyDownRoot);
  document.addEventListener("click", onDocumentClick, true);
  window.addEventListener("scroll", onScrollOrResize, true);
  window.addEventListener("resize", onScrollOrResize);
  if (popover) popover.addEventListener("scroll", onListScroll);

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
        popover.removeEventListener("scroll", onListScroll);
        popover.remove();
        popover = null;
      }
    },
    refresh(items) {
      opts.items = Array.isArray(items) ? items : [];
      if (popover) {
        const list = popover.querySelector(".dropdown-list");
        list.innerHTML = "";
        opts.items.forEach((item) =>
          list.appendChild(buildItem(item, opts.value, (v) => selectValue(v))));
        syncSelected();
        renderLabel(root, currentLabel(), opts.placeholder);
      }
    },
  };
  return instance;
}

export { mountDropdown };