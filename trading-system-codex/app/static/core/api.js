const API_PREFIX = "/api/v1";
const cacheStore = new Map();
const inflightStore = new Map();

const DEFAULT_GET_TIMEOUT_MS = 12000;
const DEFAULT_POST_TIMEOUT_MS = 20000;
const STRATEGY_CLIENT_TTL_SECONDS = {
  "15m": 30,
  "1h": 60,
  "4h": 180,
  "1d": 300,
  "1w": 900,
  "30d": 1800,
  "1M": 1800,
};

function buildUrl(path, params = {}) {
  const url = new URL(`${window.location.origin}${API_PREFIX}${path}`);
  Object.entries(params).forEach(([key, value]) => {
    if (value !== undefined && value !== null && value !== "") {
      url.searchParams.set(key, String(value));
    }
  });
  return url.toString();
}

function sleep(ms) {
  return new Promise((resolve) => window.setTimeout(resolve, ms));
}

function shouldRetry(method, retry) {
  return method === "GET" && Number(retry || 0) > 0;
}

function composeAbortSignal(signal, timeoutMs) {
  const controller = new AbortController();
  let timer = null;

  const abortFromParent = () => {
    controller.abort(signal?.reason || new DOMException("Aborted", "AbortError"));
  };

  if (signal) {
    if (signal.aborted) {
      abortFromParent();
    } else {
      signal.addEventListener("abort", abortFromParent, { once: true });
    }
  }

  if (timeoutMs > 0) {
    timer = window.setTimeout(() => {
      controller.abort(new DOMException("Request timeout", "TimeoutError"));
    }, timeoutMs);
  }

  return {
    signal: controller.signal,
    cleanup() {
      if (timer) window.clearTimeout(timer);
      if (signal) signal.removeEventListener("abort", abortFromParent);
    },
  };
}

function isAbortLikeError(error) {
  return error?.name === "AbortError" || error?.name === "TimeoutError";
}

export async function requestJson(
  path,
  {
    method = "GET",
    params = {},
    body,
    ttl = 0,
    force = false,
    signal,
    timeoutMs,
    retry = 0,
    retryDelayMs = 250,
  } = {},
) {
  const url = buildUrl(path, params);
  const cacheKey = `${method}:${url}:${body ? JSON.stringify(body) : ""}`;
  const now = Date.now();
  if (!force && ttl > 0) {
    const cached = cacheStore.get(cacheKey);
    if (cached && cached.expiresAt > now) {
      return cached.value;
    }
  }
  if (!force && !signal && inflightStore.has(cacheKey)) {
    return inflightStore.get(cacheKey);
  }
  const request = (async () => {
    let attempt = 0;
    const maxAttempts = shouldRetry(method, retry) ? Number(retry) + 1 : 1;
    while (attempt < maxAttempts) {
      const timeout = timeoutMs ?? (method === "GET" ? DEFAULT_GET_TIMEOUT_MS : DEFAULT_POST_TIMEOUT_MS);
      const composed = composeAbortSignal(signal, timeout);
      try {
        const response = await fetch(url, {
          method,
          headers: body ? { "Content-Type": "application/json" } : undefined,
          body: body ? JSON.stringify(body) : undefined,
          signal: composed.signal,
        });
        if (!response.ok) {
          const text = await response.text();
          throw new Error(text || `${response.status}`);
        }
        const data = await response.json();
        if (ttl > 0) {
          cacheStore.set(cacheKey, { value: data, expiresAt: Date.now() + ttl * 1000 });
        }
        return data;
      } catch (error) {
        if (isAbortLikeError(error) || attempt >= maxAttempts - 1) {
          throw error;
        }
        await sleep(retryDelayMs * (attempt + 1));
      } finally {
        composed.cleanup();
      }
      attempt += 1;
    }
    throw new Error("request_failed");
  })().finally(() => inflightStore.delete(cacheKey));
  if (!signal) {
    inflightStore.set(cacheKey, request);
  }
  return request;
}

export function invalidateCache(prefix = "") {
  [...cacheStore.keys()].forEach((key) => {
    if (!prefix || key.includes(prefix)) {
      cacheStore.delete(key);
    }
  });
}

export const api = {
  precomputeHint(payload) {
    return requestJson("/precompute/hint", { method: "POST", body: payload });
  },
  getPrecomputeStatus() {
    return requestJson("/precompute/status", { ttl: 3, retry: 1 });
  },
  getTaskStatus(taskKey, options = {}) {
    return requestJson(`/precompute/tasks/${encodeURIComponent(taskKey)}`, {
      ttl: 2,
      retry: 1,
      force: options.force ?? false,
    });
  },
  getEtfCatalog(options = {}) {
    return requestJson("/etf/catalog", {
      ttl: 60,
      force: options.force ?? false,
      signal: options.signal,
      retry: 1,
    });
  },
  getAshareEtfQuotes(group = "all", options = {}) {
    return requestJson("/ashare-etf/quotes", {
      params: { group, force: options.force ? "true" : "false" },
      ttl: options.force ? 0 : 10,
      force: options.force ?? false,
      signal: options.signal,
      retry: 1,
    });
  },
  getEtfQuotes(group = "all", options = {}) {
    return requestJson("/etf/quotes", {
      params: { group, force: options.force ? "true" : "false" },
      ttl: options.force ? 0 : 10,
      force: options.force ?? false,
      signal: options.signal,
      retry: 1,
    });
  },
  refreshEtfQuotes(group = "all", options = {}) {
    invalidateCache("/etf/quotes");
    invalidateCache("/ashare-etf/quotes");
    return requestJson("/etf/quotes/refresh", {
      method: "POST",
      params: { group },
      signal: options.signal,
      timeoutMs: options.timeoutMs ?? 12000,
    });
  },
  getAnalysisBundle(instrumentId, timeframe, viewWindow = "default", options = {}) {
    return requestJson("/analysis/bundle", {
      params: {
        instrument_id: instrumentId,
        timeframe: timeframe === "1M" ? "30d" : timeframe,
        view_window: viewWindow,
      },
      ttl: 20,
      force: options.force ?? false,
      signal: options.signal,
      timeoutMs: options.timeoutMs ?? 30000,
      retry: 1,
    });
  },
  refreshAnalysisBundle(instrumentId, timeframe, viewWindow = "default", options = {}) {
    invalidateCache("/analysis/bundle");
    return requestJson("/analysis/refresh", {
      method: "POST",
      params: {
        instrument_id: instrumentId,
        timeframe: timeframe === "1M" ? "30d" : timeframe,
        view_window: viewWindow,
      },
      signal: options.signal,
      timeoutMs: options.timeoutMs ?? 30000,
    });
  },
  getLatestMark(instrumentId, options = {}) {
    return requestJson("/market-prices/marks/latest", {
      params: {
        instrument_id: instrumentId,
        prefer_live: options.preferLive ? "true" : "false",
      },
      ttl: 300,
      force: options.force ?? false,
      signal: options.signal,
    });
  },
  getCandles(instrumentId, timeframe, limit, options = {}) {
    return requestJson("/marketdata/candles", {
      params: {
        instrument_id: instrumentId,
        timeframe: timeframe === "1M" ? "30d" : timeframe,
        limit,
        prefer_live: options.preferLive ? "true" : "false",
      },
      ttl: 20,
      force: options.force ?? false,
      signal: options.signal,
      timeoutMs: options.timeoutMs ?? 12000,
      retry: 1,
    });
  },
  getMarketEvents(limit = 60, translate = false) {
    return requestJson("/marketevents", { params: { limit, translate }, ttl: translate ? 5 : 30, retry: 1 });
  },
  syncMarketEvents() {
    return requestJson("/market-events/sync", { method: "POST" });
  },
  getMarketEventTranslationStatus() {
    return requestJson("/market-events/translations/status", { ttl: 3, force: true });
  },
  refreshMarketEventTranslations(options = {}) {
    return requestJson("/market-events/translations/refresh", {
      method: "POST",
      params: {
        limit: options.limit ?? 50,
        max_batches: options.maxBatches ?? 5,
        force: options.force ? "true" : "false",
      },
      force: true,
    });
  },
    getMacroOverview(options = {}) {
      return requestJson("/monitoring/macro-overview", {
        ttl: options.force ? 0 : 60,
        retry: 1,
        force: options.force ?? false,
        signal: options.signal,
        timeoutMs: options.timeoutMs,
      });
  },
  getMonitoringDashboard(instrumentId, timeframe, options = {}) {
    return requestJson("/monitoring/dashboard", {
      params: {
        instrument_id: instrumentId,
        timeframe: timeframe === "1M" ? "30d" : timeframe,
      },
        ttl: 20,
        force: options.force ?? false,
        signal: options.signal,
        timeoutMs: options.timeoutMs,
        retry: 1,
      });
  },
  refreshMonitoringDashboard(instrumentId, timeframe, options = {}) {
    invalidateCache("/monitoring/dashboard");
    return requestJson("/monitoring/dashboard/refresh", {
      method: "POST",
      params: {
        instrument_id: instrumentId,
        timeframe: timeframe === "1M" ? "30d" : timeframe,
      },
      signal: options.signal,
      timeoutMs: options.timeoutMs ?? 30000,
    });
  },
  getObservations(params) {
    return requestJson("/indicators/observations", { params, ttl: 30 });
  },
  refreshTechnical(instrumentId = "btc-usdt-perp", timeframe = "1h", options = {}) {
    invalidateCache("/indicators/observations");
    invalidateCache("/analysis/bundle");
    invalidateCache("/alerts/bundle");
    invalidateCache("/monitoring/dashboard");
    return requestJson("/indicators/refresh", {
      method: "POST",
      body: {
        instrument_id: instrumentId,
        timeframe,
        source_preference: options.sourcePreference || "gateio",
        fetch_limit: options.fetchLimit || 300,
        persist_candles: options.persistCandles ?? true,
        price_kind: options.priceKind || "last",
      },
    });
  },
  refreshMonitoringTechnical(instrumentId = "btc-usdt-perp", timeframe = "1h") {
    invalidateCache("/indicators/observations");
    invalidateCache("/monitoring/dashboard");
    return requestJson("/indicators/backfill", {
      method: "POST",
      params: { instrument_id: instrumentId, timeframe },
    });
  },
    refreshMacro() {
      invalidateCache("/macro");
      invalidateCache("/monitoring/macro-overview");
      invalidateCache("/monitoring/dashboard");
      invalidateCache("monitoring:macro_overview");
      invalidateCache("monitoring_dashboard");
      return requestJson("/macro/sync", { method: "POST" });
    },
  refreshOnchain() {
    invalidateCache("monitoring:observations");
    return requestJson("/onchain/sync", { method: "POST" });
  },
  getMacroCalendar(limit = 200) {
    return requestJson("/macro/calendar", { params: { limit }, ttl: 60 });
  },
  getAlertEvents(limit = 100) {
    return requestJson("/alerts/events", { params: { limit }, ttl: 20 });
  },
  getDivergenceSummary(instrumentId, timeframe, limit = 220) {
    return requestJson("/alerts/divergence", {
      params: { instrument_id: instrumentId, timeframe, limit },
      ttl: 20,
    });
  },
  getAlertsBundle(instrumentId, timeframe, options = {}) {
    return requestJson("/alerts/bundle", {
      params: {
        instrument_id: instrumentId,
        timeframe: timeframe === "1M" ? "30d" : timeframe,
      },
      ttl: 20,
      force: options.force ?? false,
      signal: options.signal,
      retry: 1,
    });
  },
  refreshAlertsBundle(instrumentId, timeframe, options = {}) {
    invalidateCache("/alerts/bundle");
    return requestJson("/alerts/refresh", {
      method: "POST",
      params: {
        instrument_id: instrumentId,
        timeframe: timeframe === "1M" ? "30d" : timeframe,
      },
      signal: options.signal,
      timeoutMs: options.timeoutMs ?? 30000,
    });
  },
  updateAlertEventStatus(alertEventId, status) {
    invalidateCache("/alerts/events");
    return requestJson(`/alerts/events/${encodeURIComponent(alertEventId)}/status`, {
      method: "PATCH",
      body: { status },
    });
  },
  getStructureSnapshot(instrumentId, timeframe, options = {}) {
    return requestJson("/structure/tab/snapshot", {
      params: {
        instrument_id: instrumentId,
        timeframe,
        include_geometry: options.includeGeometry ?? true,
        include_diagnostics: options.includeDiagnostics ?? false,
      },
      ttl: 20,
    });
  },
  getStructureBundle(instrumentId, timeframe, options = {}) {
    return requestJson("/structure/tab/bundle", {
      params: {
        instrument_id: instrumentId,
        timeframe,
        include_geometry: options.includeGeometry ?? true,
        candles_limit: options.candlesLimit ?? 220,
      },
      ttl: 20,
      force: options.force ?? false,
      signal: options.signal,
      retry: 1,
    });
  },
  getStructureEvents(instrumentId, timeframe, limit = 80) {
    return requestJson("/structure/tab/events", {
      params: { instrument_id: instrumentId, timeframe, limit },
      ttl: 15,
    });
  },
  getStructureAlerts(instrumentId, timeframe, limit = 80) {
    return requestJson("/structure/tab/alerts", {
      params: { instrument_id: instrumentId, timeframe, limit },
      ttl: 15,
    });
  },
  getStructureDiagnostics(instrumentId, timeframe) {
    return requestJson("/structure/tab/diagnostics", {
      params: { instrument_id: instrumentId, timeframe },
      ttl: 20,
      retry: 1,
    });
  },
  refreshStructure(instrumentId, timeframe) {
    invalidateCache("/analysis/bundle");
    invalidateCache("/alerts/bundle");
    invalidateCache("/monitoring/dashboard");
    invalidateCache("/structure/tab/");
    invalidateCache("/marketdata/candles");
    invalidateCache("/market-prices/marks/latest");
    return requestJson("/structure/tab/refresh", {
      method: "POST",
      params: { instrument_id: instrumentId, timeframe },
    });
  },
  getStrategyBundle(instrumentId, timeframe, options = {}) {
    const normalizedTimeframe = timeframe === "1M" ? "30d" : timeframe;
    return requestJson("/strategy/bundle", {
      params: {
        instrument_id: instrumentId,
        timeframe: normalizedTimeframe,
      },
      ttl: STRATEGY_CLIENT_TTL_SECONDS[normalizedTimeframe] || 300,
      force: options.force ?? false,
      timeoutMs: options.timeoutMs ?? 12000,
      signal: options.signal,
      retry: 1,
    });
  },
  refreshStrategyBundle(instrumentId, timeframe, options = {}) {
    const normalizedTimeframe = timeframe === "1M" ? "30d" : timeframe;
    invalidateCache("/strategy/bundle");
    return requestJson("/strategy/refresh", {
      method: "POST",
      params: {
        instrument_id: instrumentId,
        timeframe: normalizedTimeframe,
      },
      signal: options.signal,
      timeoutMs: options.timeoutMs ?? 12000,
    });
  },
  saveStrategySnapshot(instrumentId, timeframe) {
    invalidateCache("/strategy/");
    return requestJson("/strategy/signals", {
      method: "POST",
      body: {
        instrument_id: instrumentId,
        timeframe: timeframe === "1M" ? "30d" : timeframe,
        position: { side: "flat" },
      },
    });
  },
  getStrategyReview(instrumentId, timeframe, options = {}) {
    return requestJson("/strategy/review", {
      params: {
        instrument_id: instrumentId,
        timeframe: timeframe === "1M" ? "30d" : timeframe,
      },
      ttl: 20,
      signal: options.signal,
      retry: 1,
    });
  },
  seedDemo() {
    return requestJson("/bootstrap/seed", { method: "POST" });
  },
};
