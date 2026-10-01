const PARAM = "opportunity";
const TIMEFRAMES = new Set(["1w", "1d", "4h"]);

export function readOpportunityUrl(location = window.location) {
  const raw = new URLSearchParams(location.search).get(PARAM);
  if (!raw) return null;
  const match = /^([a-z0-9]+(?:-[a-z0-9]+)*):(1w|1d|4h)$/.exec(raw);
  return match && TIMEFRAMES.has(match[2])
    ? { instrumentId: match[1], timeframe: match[2] }
    : null;
}

export function writeOpportunityUrl(instrumentId, timeframe, { location = window.location, history = window.history } = {}) {
  if (location.pathname !== "/strategy-page") return;
  const url = new URL(location.href);
  if (instrumentId && TIMEFRAMES.has(timeframe)) url.searchParams.set(PARAM, `${instrumentId}:${timeframe}`);
  else url.searchParams.delete(PARAM);
  history.replaceState(history.state, "", `${url.pathname}${url.search}${url.hash}`);
}

export function isRestorableOpportunity(item) {
  // The URL identifies a published period decision, including a rejected
  // research decision. Trade eligibility is checked separately by the scan.
  return item?.cache_state === "fresh";
}
