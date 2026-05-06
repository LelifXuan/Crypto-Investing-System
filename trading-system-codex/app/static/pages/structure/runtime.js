export function createPageRuntime() {
  const disposers = new Set();
  return {
    addDisposer(disposer) {
      if (typeof disposer === "function") {
        disposers.add(disposer);
      }
    },
    disposeAll() {
      for (const disposer of disposers) {
        try {
          disposer();
        } catch (error) {
          console.warn("structure:runtime:dispose:error", error);
        }
      }
      disposers.clear();
    },
  };
}
