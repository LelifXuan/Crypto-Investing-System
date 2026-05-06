export function createStructureState() {
  return {
    mounted: false,
    pendingResume: null,
  };
}

export function debounce(fn, waitMs) {
  let handle = null;
  return (...args) => {
    if (handle) {
      window.clearTimeout(handle);
    }
    handle = window.setTimeout(() => {
      handle = null;
      fn(...args);
    }, waitMs);
    return () => {
      if (handle) {
        window.clearTimeout(handle);
        handle = null;
      }
    };
  };
}
