export const INSPECTOR_WIDTH_KEY = "cis.workbench.inspector.width.v1";
export function widthBounds(viewport) {
  return { min: 320, max: Math.max(320, Math.min(520, viewport * 0.42)) };
}
export function clampWidth(value, viewport) {
  const { min, max } = widthBounds(viewport);
  return Math.min(max, Math.max(min, value));
}
export function readPreferredWidth(storage) {
  try {
    const raw = storage.getItem(INSPECTOR_WIDTH_KEY);
    const value = Number(raw);
    return raw !== null && Number.isFinite(value) && value >= 320 && value <= 520 ? value : null;
  } catch { return null; }
}

/** Owns only a local layout variable. Chart ResizeObservers see normal layout changes. */
export function mountInspectorResize(container) {
  const layout = container.closest('.workbench-page-layout');
  const lifetime = new AbortController();
  let preferred = null;
  try { preferred = readPreferredWidth(window.localStorage); } catch { /* storage disabled */ }
  let handle = null;
  let drag = null;
  let frame = 0;
  let pendingWidth = null;
  const desktop = () => window.innerWidth > 1180;
  const persist = () => {
    try { window.localStorage.setItem(INSPECTOR_WIDTH_KEY, String(preferred)); } catch { /* session-only width */ }
  };
  const sync = () => {
    if (!layout || lifetime.signal.aborted) return;
    if (preferred !== null && desktop()) layout.style.setProperty('--inspector-preferred-width', `${clampWidth(preferred, window.innerWidth)}px`);
    else layout.style.removeProperty('--inspector-preferred-width');
    if (!container.hidden && !container.querySelector('.workbench-inspector-resize')) {
      handle = document.createElement('div');
      handle.className = 'workbench-inspector-resize';
      handle.setAttribute('role', 'separator');
      handle.setAttribute('aria-orientation', 'vertical');
      handle.setAttribute('aria-label', '调整详情宽度');
      container.append(handle);
    }
    if (!handle) return;
    handle.hidden = !desktop();
    handle.tabIndex = desktop() ? 0 : -1;
    const { min, max } = widthBounds(window.innerWidth);
    handle.setAttribute('aria-valuemin', String(min));
    handle.setAttribute('aria-valuemax', String(Math.floor(max)));
    handle.setAttribute('aria-valuenow', String(Math.round(preferred === null ? container.getBoundingClientRect().width : clampWidth(preferred, window.innerWidth))));
  };
  const flush = () => {
    cancelAnimationFrame(frame); frame = 0;
    if (pendingWidth !== null) { preferred = pendingWidth; pendingWidth = null; sync(); }
  };
  const resize = (width) => {
    pendingWidth = clampWidth(width, window.innerWidth);
    if (!frame) frame = requestAnimationFrame(flush);
  };
  const finish = (save = true) => {
    if (!drag) return;
    const pointerId = drag.id;
    drag = null;
    if (handle?.hasPointerCapture(pointerId)) handle.releasePointerCapture(pointerId);
    flush();
    if (save && preferred !== null) persist();
  };
  container.addEventListener('pointerdown', (event) => {
    if (event.target !== handle || !desktop() || event.button !== 0) return;
    event.preventDefault(); handle.focus();
    drag = { id: event.pointerId, x: event.clientX, width: container.getBoundingClientRect().width };
    handle.setPointerCapture(event.pointerId);
  }, { signal: lifetime.signal });
  container.addEventListener('pointermove', (event) => {
    if (drag?.id === event.pointerId) resize(drag.width + drag.x - event.clientX);
  }, { signal: lifetime.signal });
  for (const name of ['pointerup', 'pointercancel', 'lostpointercapture']) {
    container.addEventListener(name, () => finish(name === 'pointerup'), { signal: lifetime.signal });
  }
  container.addEventListener('keydown', (event) => {
    if (event.target !== handle || !desktop()) return;
    const step = event.shiftKey ? 32 : 8;
    const { min, max } = widthBounds(window.innerWidth);
    const current = container.getBoundingClientRect().width;
    const next = { ArrowLeft: current + step, ArrowRight: current - step, Home: min, End: max }[event.key];
    if (next === undefined) return;
    event.preventDefault(); resize(next); flush(); persist();
  }, { signal: lifetime.signal });
  window.addEventListener('resize', () => { finish(false); sync(); }, { signal: lifetime.signal });
  return {
    update() { if (container.hidden) finish(false); sync(); },
    destroy() {
      finish(false); lifetime.abort(); cancelAnimationFrame(frame);
      layout?.style.removeProperty('--inspector-preferred-width'); handle?.remove();
    },
  };
}
