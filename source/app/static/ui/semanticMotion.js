const VALUE_CLASS = "is-semantic-value-change";
const STATE_CLASS = "is-semantic-state-change";

function normalized(value) {
  if (value === null || value === undefined) return "";
  if (typeof value === "number" && Number.isFinite(value)) return String(value);
  return String(value).trim();
}

function reducedMotion() {
  return window.matchMedia?.("(prefers-reduced-motion: reduce)").matches === true;
}

function pulse(element, className, signal, duration = 180) {
  if (!element) return false;
  if (signal?.aborted) return false;
  element.classList.remove(className);
  if (reducedMotion()) {
    element.dataset.semanticChanged = "true";
    queueMicrotask(() => delete element.dataset.semanticChanged);
    return true;
  }
  void element.offsetWidth;
  element.classList.add(className);
  const onAbort = () => {
    window.clearTimeout(timer);
    cleanup();
  };
  const cleanup = () => {
    element.classList.remove(className);
    signal?.removeEventListener("abort", onAbort);
  };
  const timer = window.setTimeout(cleanup, duration);
  signal?.addEventListener("abort", onAbort, { once: true });
  return true;
}

export function animateValueChange(element, previous, next, { signal } = {}) {
  if (normalized(previous) === normalized(next)) return false;
  return pulse(element, VALUE_CLASS, signal);
}

export function animateStateChange(element, previous, next, { signal } = {}) {
  if (normalized(previous) === normalized(next)) return false;
  return pulse(element, STATE_CLASS, signal);
}

export function clearRelated(root = document) {
  root.querySelectorAll?.("[data-workbench-related]").forEach((element) => {
    element.removeAttribute("data-workbench-related");
  });
}

export function markRelated(root, ids, mode = "preview") {
  clearRelated(root);
  const wanted = new Set((ids || []).map(String));
  if (!wanted.size) return;
  root.querySelectorAll?.("[data-workbench-id]").forEach((element) => {
    if (wanted.has(element.dataset.workbenchId)) {
      element.dataset.workbenchRelated = mode;
    }
  });
}

/** Keep committed and preview relationships distinct when content is pinned. */
export function markWorkbenchRelations(root, snapshot) {
  clearRelated(root);
  const selected = snapshot.selection;
  const preview = snapshot.previewSelection;
  const chosen = snapshot.isPinned ? selected : snapshot.activeSelection;
  const selectedIds = new Set(chosen ? [chosen.id, ...(chosen.relatedIds || [])] : []);
  const previewIds = new Set(preview ? [preview.id, ...(preview.relatedIds || [])] : []);
  root.querySelectorAll?.("[data-workbench-id]").forEach((element) => {
    const id = element.dataset.workbenchId;
    if (selectedIds.has(id)) element.dataset.workbenchRelated = snapshot.hasCommittedSelection ? "selected" : "preview";
    else if (snapshot.isPinned && previewIds.has(id)) element.dataset.workbenchRelated = "preview";
  });
}
