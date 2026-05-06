import { api } from "./api.js";

export function scheduleIdlePrecompute({
  page,
  instrumentId,
  timeframe,
  viewWindow = "default",
  visible = true,
  candidates = [],
  reason = "idle_after_first_paint",
  priority = 5,
}) {
  const run = () =>
    api.precomputeHint({
      current_page: page,
      instrument_id: instrumentId,
      timeframe,
      view_window: viewWindow,
      visible,
      candidates,
      reason,
      priority,
    }).catch(() => null);
  return new Promise((resolve) => {
    const invoke = () => {
      run().finally(() => resolve());
    };
    if ("requestIdleCallback" in window) {
      window.requestIdleCallback(invoke, { timeout: 1000 });
      return;
    }
    window.setTimeout(invoke, 300);
  });
}
