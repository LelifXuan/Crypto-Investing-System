// Explicit priority; never rely on event-listener registration order.
export const LAYER = Object.freeze({ dock: 1500, inspector: 2000, dialog: 3000, palette: 5000 });
const layers = [];
const FOCUSABLE = 'button:not([disabled]),input:not([disabled]),textarea:not([disabled]),a[href],[tabindex]:not([tabindex="-1"])';
let savedOverflow = null;
let sequence = 0;
const top = () => layers.filter((layer) => layer.element.isConnected)
  .sort((a, b) => b.priority - a.priority || b.order - a.order)[0];

export function isTopOverlay(element) {
  const active = top();
  return !active || active.element === element;
}

export function overlayAllowsTarget(target) {
  const active = top();
  return !active?.modal || active.element.contains(target);
}

function syncLock() {
  const locked = layers.some((layer) => layer.modal);
  if (locked && savedOverflow === null) { savedOverflow = document.body.style.overflow; document.body.style.overflow = "hidden"; }
  if (!locked && savedOverflow !== null) { document.body.style.overflow = savedOverflow; savedOverflow = null; }
}

function focusables(layer) {
  return [...layer.element.querySelectorAll(FOCUSABLE)].filter((el) => el.getClientRects().length && !el.closest('[hidden],[inert]'));
}

function onKeydown(event) {
  const active = top();
  if (!active || event.isComposing) return;
  if (event.key === "Escape") {
    if (active.priority < LAYER.palette && event.target.closest?.('[aria-expanded="true"][role="combobox"]')) return;
    event.preventDefault(); event.stopImmediatePropagation(); active.close();
  } else if (event.key === "Tab" && active.modal) {
    const nodes = focusables(active);
    const first = nodes[0], last = nodes.at(-1);
    if (!first) { event.preventDefault(); return; }
    if (!active.element.contains(document.activeElement)) { event.preventDefault(); first.focus(); }
    else if (event.shiftKey && document.activeElement === first) { event.preventDefault(); last.focus(); }
    else if (!event.shiftKey && document.activeElement === last) { event.preventDefault(); first.focus(); }
  }
}

function onFocus(event) {
  const active = top();
  if (active?.modal && !active.element.contains(event.target)) focusables(active)[0]?.focus({ preventScroll: true });
}

export function registerOverlay({ element, priority, modal = false, close }) {
  const layer = { element, priority, modal, close, order: ++sequence };
  if (!layers.length) {
    document.addEventListener("keydown", onKeydown, true);
    document.addEventListener("focusin", onFocus, true);
  }
  layers.push(layer); syncLock();
  let disposed = false;
  return {
    update(options) { if (!disposed) { Object.assign(layer, options); syncLock(); } },
    destroy() {
      if (disposed) return;
      disposed = true;
      layers.splice(layers.indexOf(layer), 1); syncLock();
      if (!layers.length) {
        document.removeEventListener("keydown", onKeydown, true);
        document.removeEventListener("focusin", onFocus, true);
      }
    },
  };
}
