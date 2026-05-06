from __future__ import annotations

from app.core.timeframes import (
    bucket_limit,
    normalize_instrument_id,
    normalize_timeframe_for_cache,
    normalize_timeframe_for_provider,
    normalize_timeframe_for_ui,
)
from app.services.cache_registry import analysis_cache_key


def test_month_timeframes_share_cache_key() -> None:
    assert normalize_timeframe_for_provider("1M") == "30d"
    assert normalize_timeframe_for_cache("1M") == "30d"
    assert normalize_timeframe_for_cache("30d") == "30d"
    assert normalize_timeframe_for_ui("30d") == "1M"
    assert analysis_cache_key("BTC-USDT-PERP", "1M", 220) == analysis_cache_key(
        "btc-usdt-perp", "30d", 240
    )


def test_limit_and_instrument_normalization() -> None:
    assert bucket_limit(1) == 120
    assert bucket_limit(120) == 120
    assert bucket_limit(220) == 240
    assert bucket_limit(240) == 240
    assert bucket_limit(501) == 1000
    assert normalize_instrument_id(" BTC-USDT-PERP ") == "btc-usdt-perp"
