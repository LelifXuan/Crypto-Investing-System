function normalizeList(value) {
  return Array.isArray(value) ? value.filter(Boolean) : [];
}

function normalizeInspection(value) {
  if (!value || typeof value !== "object" || !value.id || !value.title) return null;
  return {
    id: String(value.id),
    type: String(value.type || "research-object"),
    title: String(value.title),
    current: value.current && typeof value.current === "object" ? { ...value.current } : null,
    interpretation: value.interpretation ? String(value.interpretation) : "",
    evidence: normalizeList(value.evidence).map((item) => ({ ...item })),
    impacts: normalizeList(value.impacts).map((item) => ({ ...item })),
    sources: normalizeList(value.sources).map((item) => ({ ...item })),
    updatedAt: value.updatedAt || null,
    relatedIds: normalizeList(value.relatedIds).map(String),
  };
}

function focusOrigin(origin) {
  if (!origin || typeof origin.focus !== "function") return;
  if (typeof origin.isConnected === "boolean" && !origin.isConnected) return;
  origin.focus({ preventScroll: true });
}

/**
 * Small page-scoped selection store. A new instance is created by each
 * workbench page, so selections and DOM origins can never leak across SPA
 * routes. Hover/focus preview is deliberately separate from committed state.
 */
export function createWorkbenchState({ scopeId = "workbench" } = {}) {
  let selection = null;
  let isPinned = false;
  let previewSelection = null;
  let selectionOrigin = null;
  let revision = 0;
  let destroyed = false;
  const subscribers = new Set();

  const snapshot = () => Object.freeze({
    scopeId,
    revision,
    selection,
    isPinned,
    previewSelection,
    activeSelection: isPinned && selection ? selection : previewSelection || selection,
    hasCommittedSelection: Boolean(selection),
  });

  const emit = () => {
    if (destroyed) return;
    const next = snapshot();
    subscribers.forEach((listener) => listener(next));
  };

  const update = (callback) => {
    if (destroyed) return snapshot();
    callback();
    revision += 1;
    emit();
    return snapshot();
  };

  return {
    setPinned(value) {
      if (destroyed) return snapshot();
      const next = Boolean(value && selection);
      if (next === isPinned) return snapshot();
      return update(() => { isPinned = next; });
    },
    togglePinned() { return this.setPinned(!isPinned); },
    select(value, { trigger = null } = {}) {
      const normalized = normalizeInspection(value);
      if (!normalized) return snapshot();
      return update(() => {
        selection = normalized;
        previewSelection = null;
        selectionOrigin = trigger || selectionOrigin;
      });
    },
    preview(value) {
      const normalized = normalizeInspection(value);
      if (!normalized) return snapshot();
      return update(() => { previewSelection = normalized; });
    },
    clearPreview() {
      if (!previewSelection) return snapshot();
      return update(() => { previewSelection = null; });
    },
    clearSelection({ restoreFocus = true } = {}) {
      if (destroyed) return snapshot();
      const origin = selectionOrigin;
      const next = update(() => {
        selection = null;
        isPinned = false;
        previewSelection = null;
        selectionOrigin = null;
      });
      if (restoreFocus) focusOrigin(origin);
      return next;
    },
    subscribe(listener, { emitInitial = true } = {}) {
      if (destroyed || typeof listener !== "function") return () => {};
      subscribers.add(listener);
      if (emitInitial) listener(snapshot());
      return () => subscribers.delete(listener);
    },
    getSnapshot: snapshot,
    destroy() {
      if (destroyed) return;
      destroyed = true;
      selection = null;
      isPinned = false;
      previewSelection = null;
      selectionOrigin = null;
      subscribers.clear();
    },
  };
}
