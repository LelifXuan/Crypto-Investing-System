from __future__ import annotations

UI_TO_PROVIDER_TIMEFRAME = {
    "1m": "1m",
    "5m": "5m",
    "15m": "15m",
    "1h": "1h",
    "4h": "4h",
    "1d": "1d",
    "1w": "1w",
    "1M": "30d",
    "30d": "30d",
}

PROVIDER_TO_UI_TIMEFRAME = {
    "1m": "1m",
    "5m": "5m",
    "15m": "15m",
    "1h": "1h",
    "4h": "4h",
    "1d": "1d",
    "1w": "1w",
    "30d": "1M",
}

CACHE_TIMEFRAME_ALIAS = {
    "1M": "30d",
    "30d": "30d",
}

LIMIT_BUCKETS = (120, 240, 500, 1000, 1500)


def normalize_timeframe_for_provider(timeframe: str) -> str:
    normalized = str(timeframe or "").strip()
    if normalized not in UI_TO_PROVIDER_TIMEFRAME:
        raise ValueError(f"unsupported timeframe: {timeframe}")
    return UI_TO_PROVIDER_TIMEFRAME[normalized]


def normalize_timeframe_for_cache(timeframe: str) -> str:
    provider_value = normalize_timeframe_for_provider(timeframe)
    return CACHE_TIMEFRAME_ALIAS.get(provider_value, provider_value)


def normalize_timeframe_for_ui(timeframe: str) -> str:
    provider_value = normalize_timeframe_for_provider(timeframe)
    return PROVIDER_TO_UI_TIMEFRAME.get(provider_value, provider_value)


def normalize_instrument_id(instrument_id: str) -> str:
    return str(instrument_id or "").strip().lower()


def bucket_limit(limit: int) -> int:
    requested = max(int(limit or 0), 1)
    for bucket in LIMIT_BUCKETS:
        if requested <= bucket:
            return bucket
    return LIMIT_BUCKETS[-1]
