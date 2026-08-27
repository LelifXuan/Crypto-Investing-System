import { api } from "./api.js";

function abortError() {
  return new DOMException("The operation was aborted", "AbortError");
}

export function waitForAbortableDelay(ms, signal) {
  if (signal?.aborted) return Promise.reject(abortError());
  return new Promise((resolve, reject) => {
    const timer = window.setTimeout(() => {
      signal?.removeEventListener("abort", onAbort);
      resolve();
    }, ms);
    function onAbort() {
      window.clearTimeout(timer);
      reject(abortError());
    }
    signal?.addEventListener("abort", onAbort, { once: true });
  });
}

/**
 * Wait for a tracked precompute task without leaving timers behind when the
 * SPA page is unmounted. Completed tasks intentionally disappear from the
 * in-memory queue, so `missing` after a known task key means "re-read the
 * published snapshot"; failures remain available as `error`.
 */
export async function waitForPrecomputeTask(taskKey, options = {}) {
  if (!taskKey) return { status: "untracked" };
  const signal = options.signal;
  const intervalMs = options.intervalMs ?? 1000;
  const maxAttempts = options.maxAttempts ?? 90;
  for (let attempt = 0; attempt < maxAttempts; attempt += 1) {
    if (signal?.aborted) throw abortError();
    const status = await api.getTaskStatus(taskKey, {
      force: true,
      signal,
      timeoutMs: options.timeoutMs ?? 10000,
    });
    if (status?.status === "error") {
      throw new Error(status.last_error || "后台数据任务失败");
    }
    if (status?.status === "missing") return status;
    await waitForAbortableDelay(intervalMs, signal);
  }
  throw new Error("后台数据任务等待超时");
}

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

/**
 * Submit the analysis page's default 5 x 5 cache matrix without allowing
 * background combinations to outrank the combination the user can see.
 * Submission is intentionally sequential: the server owns execution
 * concurrency and SQLite keeps a single writer boundary.
 */
export function buildAnalysisWarmupPairs({ instruments = [], selectedInstrumentId, selectedTimeframe } = {}) {
  const instrumentIds = instruments
    .map((item) => typeof item === "string" ? item : item?.id)
    .filter(Boolean)
    .filter((value, index, values) => values.indexOf(value) === index)
    .slice(0, 5);
  const timeframes = ["1h", "4h", "1d", "1w", "30d"];
  const selectedTf = selectedTimeframe === "1M" ? "30d" : selectedTimeframe;
  const pairs = [];
  const addPair = (instrumentId, timeframe, priority) => {
    if (!instrumentId || !timeframe) return;
    const key = `${instrumentId}:${timeframe}`;
    if (pairs.some((item) => item.key === key)) return;
    pairs.push({ key, instrumentId, timeframe, priority });
  };

  addPair(selectedInstrumentId, selectedTf, 3);
  timeframes.forEach((timeframe) => addPair(selectedInstrumentId, timeframe, 5));
  instrumentIds.forEach((instrumentId) => addPair(instrumentId, selectedTf, 6));
  instrumentIds.forEach((instrumentId) => {
    timeframes.forEach((timeframe) => addPair(instrumentId, timeframe, 8));
  });
  return pairs;
}

export function scheduleAnalysisMatrixWarmup({
  instruments = [],
  selectedInstrumentId,
  selectedTimeframe,
  signal,
  reason = "analysis_matrix_idle_warmup",
} = {}) {
  const pairs = buildAnalysisWarmupPairs({ instruments, selectedInstrumentId, selectedTimeframe });

  const run = async () => {
    for (const pair of pairs) {
      if (signal?.aborted) return;
      try {
        await api.precomputeHint({
          current_page: "analysis",
          instrument_id: pair.instrumentId,
          timeframe: pair.timeframe,
          view_window: "default",
          visible: pair.instrumentId === selectedInstrumentId && pair.timeframe === selectedTf,
          candidates: ["analysis"],
          reason,
          priority: pair.priority,
        }, { signal, timeoutMs: 10000 });
      } catch (error) {
        if (error?.name === "AbortError") return;
      }
    }
  };

  if ("requestIdleCallback" in window) {
    window.requestIdleCallback(() => void run(), { timeout: 1500 });
  } else {
    window.setTimeout(() => void run(), 500);
  }
}
