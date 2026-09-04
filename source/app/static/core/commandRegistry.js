const allowed = (value) => typeof value === "function" ? value() !== false : value !== false;
const normalize = (text) => String(text || "").normalize("NFKC").trim().toLocaleLowerCase();

// Do not log arbitrary Error.message/stack: providers may embed URLs, headers
// or payloads there. The original cause stays available on the thrown wrapper.
function commandDiagnostic(entry, error) {
  const safeId = (value) => /^[a-z0-9:_-]{1,100}$/i.test(String(value)) ? String(value) : "[redacted]";
  const knownNames = new Set(["Error", "TypeError", "RangeError", "ReferenceError", "SyntaxError", "AbortError"]);
  const frames = String(error?.stack || '').split('\n').slice(1)
    .map((line) => line.match(/\/static\/[a-z0-9_./-]+\.js(?:\?[^\s):]*)?:\d+:\d+/i)?.[0])
    .filter(Boolean).slice(0, 6).map((frame) => frame.replace(/\?[^:]*?(?=:\d+:\d+$)/, ''));
  return { id: safeId(entry.id), scope: safeId(entry.scope),
    name: knownNames.has(error?.name) ? error.name : "Error", message: "Command execution failed", frames };
}

function score(entry, query) {
  if (!query) return 1;
  const label = normalize(entry.label);
  if (label === query) return 100;
  if (label.startsWith(query)) return 80;
  if (label.includes(query)) return 60;
  return entry.keywords.some((word) => normalize(word).includes(query)) ? 40 : 0;
}

/** App-owned registry. Page scopes own closures and release them on abort. */
export function createCommandRegistry() {
  const entries = new Map();
  const listeners = new Set();
  let destroyed = false;
  const visible = (entry) => !destroyed && entry.alive() && allowed(entry.visible);
  const publicEntry = (entry) => ({ id: entry.id, label: entry.label, group: entry.group,
    scope: entry.scope, shortcut: entry.shortcut, enabled: !entry.busy && allowed(entry.enabled) });
  const notify = () => { if (!destroyed) listeners.forEach((listener) => listener()); };
  const register = (command, scope = "global", alive = () => true) => {
    if (destroyed || !alive()) return () => {};
    if (!command?.id || !command.label || typeof command.run !== "function") throw new TypeError("Invalid command");
    if (entries.has(command.id)) throw new Error("Duplicate command: " + command.id);
    const entry = { ...command, scope, alive, keywords: command.keywords || [], group: command.group || (scope === "global" ? "导航" : "当前页面"), busy: false };
    entries.set(entry.id, entry); notify();
    return () => { if (entries.get(entry.id) === entry) { entries.delete(entry.id); notify(); } };
  };
  return {
    register,
    unregister(id) { entries.delete(id); notify(); },
    createScope(scopeId, { signal } = {}) {
      let live = !signal?.aborted && !destroyed;
      const disposers = new Set();
      const destroy = () => {
        live = false; disposers.forEach((dispose) => dispose()); disposers.clear();
        signal?.removeEventListener("abort", destroy);
      };
      signal?.addEventListener("abort", destroy, { once: true });
      return {
        register(command) {
          const dispose = register(command, scopeId, () => live);
          disposers.add(dispose);
          return () => { dispose(); disposers.delete(dispose); };
        },
        destroy,
      };
    },
    query(text = "") {
      const query = normalize(text);
      return [...entries.values()].filter(visible)
        .map((entry) => ({ entry, score: score(entry, query) }))
        .filter((row) => row.score > 0)
        .sort((a, b) => b.score - a.score)
        .map(({ entry }) => publicEntry(entry));
    },
    async run(id) {
      const entry = entries.get(id);
      if (!entry || !visible(entry) || entry.busy || !allowed(entry.enabled)) return false;
      entry.busy = true; notify();
      try { await entry.run(); return !destroyed && entry.alive() && entries.get(id) === entry; }
      catch (error) {
        if (destroyed || !entry.alive() || entries.get(id) !== entry) return false;
        console.error("[commands] execution failed", commandDiagnostic(entry, error));
        throw new Error("操作未完成，请检查当前页面状态后重试。", { cause: error });
      }
      finally { entry.busy = false; notify(); }
    },
    subscribe(listener) {
      if (destroyed) return () => {};
      listeners.add(listener); listener();
      return () => listeners.delete(listener);
    },
    destroy() { destroyed = true; entries.clear(); listeners.clear(); },
  };
}
