// P1-STATE-001: the shell health footer must reflect observable state, never
// a static optimistic default (INV-004). Two SEPARATE concepts live here:
//
//   service health — from GET /health (application + database readiness);
//   data quality   — from the outcome of actual /api/v1 data requests
//                    (tracked by core/api.js), NOT from /health, which cannot
//                    know whether market data sources are degraded.
//
// Both chips start as "unknown" and only turn positive on evidence. A failed
// health request shows 服务不可达 / keeps the last known data state honest;
// a green dot without evidence is a bug, not a default.

const SERVICE_LABELS = {
  ready: "服务正常",
  degraded: "服务降级",
  unreachable: "服务不可达",
  unknown: "服务状态未知",
};

const DATA_LABELS = {
  ok: "数据正常",
  degraded: "部分数据降级",
  unknown: "数据状态未知",
};

const POLL_INTERVAL_MS = 45000;

export function serviceLabels() {
  return { ...SERVICE_LABELS };
}

export function dataLabels() {
  return { ...DATA_LABELS };
}

export function deriveServiceState(payload, error) {
  if (error) return "unreachable";
  const status = String((payload || {}).status || "").toLowerCase();
  if (status === "ready") return "ready";
  if (status === "degraded") return "degraded";
  return "unknown";
}

export function deriveDataState(tracker) {
  if (!tracker) return "unknown";
  if (tracker.lastFailureAt > tracker.lastSuccessAt) return "degraded";
  if (tracker.successCount > 0) return "ok";
  return "unknown";
}

let started = false;
let dataTracker = null;
// Set by startShellHealth once the chip DOM is bound; lets the module-level
// tracker registration refresh an already-mounted footer.
let renderDataChip = null;

/** main.js wires core/api.js's tracker here once; the data chip then renders
 * from real request outcomes on every refresh cycle. */
export function registerDataQualityTracker(tracker) {
  dataTracker = tracker;
  if (renderDataChip) renderDataChip();
}

export function startShellHealth({
  documentRef = typeof document === "undefined" ? null : document,
  fetchImpl = typeof fetch === "undefined" ? null : fetch,
  intervalMs = POLL_INTERVAL_MS,
} = {}) {
  if (started || !documentRef || !fetchImpl) return null;
  started = true;

  const dots = {
    service: documentRef.querySelector('[data-shell-health-dot="service"]'),
    data: documentRef.querySelector('[data-shell-health-dot="data"]'),
  };
  const labels = {
    service: documentRef.querySelector('[data-shell-health-label="service"]'),
    data: documentRef.querySelector('[data-shell-health-label="data"]'),
  };

  const render = (kind, state, labelMap) => {
    const dot = dots[kind];
    const label = labels[kind];
    if (dot) dot.dataset.state = state;
    if (label) label.textContent = labelMap[state] || labelMap.unknown;
  };

  function refreshDataChip() {
    render("data", deriveDataState(dataTracker), DATA_LABELS);
  }
  renderDataChip = refreshDataChip;

  const pollService = async () => {
    let payload = null;
    let error = null;
    try {
      const response = await fetchImpl("/health", { cache: "no-store" });
      payload = response.ok ? await response.json() : null;
      if (!response.ok) error = new Error(`health_${response.status}`);
    } catch (err) {
      error = err;
    }
    render("service", deriveServiceState(payload, error), SERVICE_LABELS);
    refreshDataChip();
  };

  render("service", "unknown", SERVICE_LABELS);
  render("data", "unknown", DATA_LABELS);

  void pollService();
  // Early settle refresh: initial page data requests usually finish within a
  // few seconds; the regular 45 s cadence stays low-frequency as specified.
  const earlyRefresh = setTimeout(refreshDataChip, 4000);
  const timer = setInterval(pollService, intervalMs);
  return {
    stop: () => {
      clearTimeout(earlyRefresh);
      clearInterval(timer);
    },
    pollService,
    refreshDataChip,
  };
}
