const ANALYSIS_INSTRUMENTS = [
  { id: "btc-usdt-perp", code: "BTC", name: "Bitcoin" },
  { id: "eth-usdt-perp", code: "ETH", name: "Ethereum" },
  { id: "hype-usdt-perp", code: "HYPE", name: "Hyperliquid" },
  { id: "bnb-usdt-perp", code: "BNB", name: "Binance Coin" },
  { id: "okb-usdt-perp", code: "OKB", name: "OKX Token" },
];

const TIMEFRAME_WINDOWS = {
  "1h": {
    defaultView: "default",
    windows: {
      short: { visibleBars: 96, calcBars: 360 },
      default: { visibleBars: 240, calcBars: 720 },
      long: { visibleBars: 480, calcBars: 1200 },
    },
  },
  "4h": {
    defaultView: "default",
    windows: {
      short: { visibleBars: 90, calcBars: 300 },
      default: { visibleBars: 180, calcBars: 480 },
      long: { visibleBars: 360, calcBars: 900 },
    },
  },
  "1d": {
    defaultView: "default",
    windows: {
      short: { visibleBars: 90, calcBars: 240 },
      default: { visibleBars: 180, calcBars: 420 },
      long: { visibleBars: 360, calcBars: 900 },
    },
  },
  "1w": {
    defaultView: "default",
    windows: {
      short: { visibleBars: 52, calcBars: 156 },
      default: { visibleBars: 104, calcBars: 260 },
      long: { visibleBars: 208, calcBars: 520 },
    },
  },
  "1M": {
    defaultView: "default",
    windows: {
      short: { visibleBars: 36, calcBars: 120 },
      default: { visibleBars: 60, calcBars: 180 },
      long: { visibleBars: 120, calcBars: 360 },
    },
  },
};

const STORAGE_KEYS = {
  instrumentId: "terminal.instrument_id",
  timeframe: "terminal.timeframe",
  viewWindow: "terminal.view_window",
  eventsTranslate: "terminal.events.translate",
};

function safeRead(key, fallback) {
  try {
    return localStorage.getItem(key) || fallback;
  } catch {
    return fallback;
  }
}

export const appState = {
  accountId: "demo_account",
  instruments: ANALYSIS_INSTRUMENTS,
  timeframeWindows: TIMEFRAME_WINDOWS,
  selectedInstrumentId: safeRead(STORAGE_KEYS.instrumentId, ANALYSIS_INSTRUMENTS[0].id),
  selectedTimeframe: safeRead(STORAGE_KEYS.timeframe, "1d"),
  selectedViewWindow: safeRead(STORAGE_KEYS.viewWindow, "default"),
  translateEvents: safeRead(STORAGE_KEYS.eventsTranslate, "false") === "true",
};

export function persistState() {
  try {
    localStorage.setItem(STORAGE_KEYS.instrumentId, appState.selectedInstrumentId);
    localStorage.setItem(STORAGE_KEYS.timeframe, appState.selectedTimeframe);
    localStorage.setItem(STORAGE_KEYS.viewWindow, appState.selectedViewWindow);
    localStorage.setItem(STORAGE_KEYS.eventsTranslate, String(appState.translateEvents));
  } catch {
    // ignore localStorage failures in local desktop mode
  }
}

export function getWindowProfile(timeframe, viewWindow) {
  const profile = TIMEFRAME_WINDOWS[timeframe] || TIMEFRAME_WINDOWS["1d"];
  return profile.windows[viewWindow] || profile.windows[profile.defaultView];
}

export function getInstrumentMeta(instrumentId) {
  return ANALYSIS_INSTRUMENTS.find((item) => item.id === instrumentId) || ANALYSIS_INSTRUMENTS[0];
}
