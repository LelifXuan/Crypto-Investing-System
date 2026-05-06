export function createRequestGuard() {
  let controller = null;
  return {
    renew() {
      if (controller) {
        controller.abort();
      }
      controller = new AbortController();
      return controller.signal;
    },
    cancel() {
      if (controller) {
        controller.abort();
        controller = null;
      }
    },
  };
}
