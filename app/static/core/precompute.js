import { api } from "./api.js";

export function scheduleIdlePrecompute(options = {}) {
  const page = options.page ?? options.current_page;
  const instrumentId = options.instrumentId ?? options.instrument_id;
  const timeframe = options.timeframe;
  const viewWindow = options.viewWindow ?? options.view_window ?? "default";
  const visible = options.visible ?? true;
  const candidates = options.candidates ?? [];
  const reason = options.reason ?? "idle_after_first_paint";
  const priority = options.priority ?? 5;
  if (!page || !instrumentId || !timeframe) {
    return Promise.resolve();
  }
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

export function schedulePageWarmup({ page, instrumentId, timeframe, instruments = [], reason = "first_paint_warmup" }) {
  const important = [instrumentId, "btc-usdt-perp", "eth-usdt-perp", "sol-usdt-perp", ...instruments]
    .filter(Boolean)
    .filter((value, index, arr) => arr.indexOf(value) === index)
    .slice(0, 5);
  const timeframes = [timeframe, "1h", "4h", "1d"]
    .map((item) => (item === "1M" ? "30d" : item))
    .filter(Boolean)
    .filter((value, index, arr) => arr.indexOf(value) === index);
  const jobs = [];
  important.forEach((targetInstrument, i) => {
    timeframes.forEach((targetTimeframe, j) => {
      jobs.push(() => api.precomputeHint({
        current_page: page,
        instrument_id: targetInstrument,
        timeframe: targetTimeframe,
        view_window: "default",
        visible: i === 0 && j === 0,
        candidates: ["analysis", "structure", "alerts", "monitoring"],
        reason,
        priority: i === 0 ? 5 : 7,
      }).catch(() => null));
    });
  });
  const run = () => jobs.reduce((chain, job) => chain.then(job), Promise.resolve());
  if ("requestIdleCallback" in window) {
    window.requestIdleCallback(() => run(), { timeout: 1500 });
  } else {
    window.setTimeout(() => run(), 500);
  }
}
