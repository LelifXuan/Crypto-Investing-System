/** Identity only. No payload, pin or research filters are persisted. */
export function createWorkbenchUrlState({ state, resolve, trigger = () => null, onUnavailable = () => {}, environment = window }) {
  const path = environment.location.pathname;
  let pending = new URL(environment.location.href).searchParams.get('inspect');
  let settled = false;
  let destroyed = false;
  let suppress = false;
  let lastId = state.getSnapshot().selection?.id || null;
  const current = () => !destroyed && environment.location.pathname === path;
  const write = (id) => {
    if (!current()) return;
    const url = new URL(environment.location.href);
    if (id) url.searchParams.set('inspect', id);
    else url.searchParams.delete('inspect');
    environment.history.replaceState(environment.history.state, '', `${url.pathname}${url.search}${url.hash}`);
  };
  const select = (dto) => {
    suppress = true;
    try {
      if (dto) state.select(dto, { trigger: trigger(dto.id) });
      else state.clearSelection({ restoreFocus: false });
    } finally { suppress = false; }
    lastId = dto?.id || null;
  };
  const reconcile = () => {
    if (!current() || !pending) return;
    const dto = resolve(pending);
    if (dto) { pending = null; select(dto); write(dto.id); }
    else if (settled) {
      pending = null; select(null); write(null); onUnavailable();
    }
  };
  const unsubscribe = state.subscribe((snapshot) => {
    const id = snapshot.selection?.id || null;
    if (suppress || !current() || id === lastId) return;
    lastId = id; pending = null; write(id);
  }, { emitInitial: false });
  const popstate = () => {
    if (!current()) return;
    pending = new URL(environment.location.href).searchParams.get('inspect');
    select(null);
    if (pending) reconcile();
  };
  environment.addEventListener('popstate', popstate);
  return {
    dataReady({ terminal = true } = {}) { settled = terminal; reconcile(); },
    clearContext() { pending = null; settled = false; select(null); write(null); },
    destroy() { destroyed = true; unsubscribe(); environment.removeEventListener('popstate', popstate); },
  };
}

/** Shared DOM adapter; resolution still belongs exclusively to each page registry. */
export function mountWorkbenchUrlState(state, registry, { fallbackId = null } = {}) {
  let notice = null;
  const url = createWorkbenchUrlState({
    state,
    resolve: (id) => registry.get(id),
    trigger: (id) => document.querySelector(`[data-workbench-id="${CSS.escape(id)}"]`) || document.getElementById(fallbackId),
    onUnavailable: () => {
      if (!notice?.isConnected) {
        notice = document.createElement('p'); notice.className = 'workbench-recovery-note';
        notice.setAttribute('role', 'status'); document.getElementById('page-root')?.prepend(notice);
      }
      notice.textContent = '未能恢复详情：当前研究上下文中已无此对象。';
    },
  });
  return { ...url, destroy() { url.destroy(); notice?.remove(); } };
}
