from __future__ import annotations

from datetime import datetime, timezone
from pathlib import Path

import pytest

from app.schemas.btc_derivatives_sources import LiveSnapshotEnvelope
from app.services.btc_derivatives.chart_builder import REQUIRED_CHART_IDS
from app.services.btc_derivatives.live_service import BtcDerivativesLiveService
from app.services.btc_derivatives.sources.cache import LiveSourceCache
from app.services.btc_derivatives.sources.collector import LiveCollector
from app.services.btc_derivatives.sources.normalizer import (
    normalize_binance_perp,
    normalize_deribit_option,
    normalize_okx_options,
)
from app.services.btc_derivatives.sources.registry import PROVIDER_REGISTRY


def test_registry_contains_six_no_key_p0_providers() -> None:
    assert set(PROVIDER_REGISTRY) == {
        "deribit",
        "okx",
        "bybit",
        "binance_futures",
        "bitget",
        "hyperliquid",
    }
    assert all(not provider.requires_auth for provider in PROVIDER_REGISTRY.values())
    assert all(provider.endpoints for provider in PROVIDER_REGISTRY.values())


def test_deribit_option_premium_is_converted_to_usd_without_losing_native_quote() -> None:
    quote = normalize_deribit_option(
        {
            "instrument_name": "BTC-25SEP26-65000-C",
            "bid_price": 0.02,
            "ask_price": 0.024,
            "mark_price": 0.022,
            "mark_iv": 58.2,
            "open_interest": 120,
            "underlying_price": 61_000,
            "timestamp": 1_782_345_600_000,
            "greeks": {"delta": 0.31},
        },
        collected_at=datetime(2026, 6, 24, tzinfo=timezone.utc),
    )

    assert quote.bid == 1_220
    assert quote.ask == 1_464
    assert quote.native_bid == 0.02
    assert quote.premium_currency == "BTC"
    assert quote.iv == 0.582
    assert quote.missing_fields == []


def test_okx_options_prefer_bs_greeks_and_record_pa_fallback() -> None:
    instruments = [
        {
            "instId": "BTC-USD-260925-65000-C",
            "expTime": "1790294400000",
            "stk": "65000",
            "optType": "C",
        },
        {
            "instId": "BTC-USD-260925-55000-P",
            "expTime": "1790294400000",
            "stk": "55000",
            "optType": "P",
        },
    ]
    tickers = [
        {
            "instId": "BTC-USD-260925-65000-C",
            "bidPx": "0.02",
            "askPx": "0.024",
            "markPx": "0.022",
            "idxPx": "61000",
            "oi": "100",
            "ts": "1782345600000",
        },
        {
            "instId": "BTC-USD-260925-55000-P",
            "bidPx": "0.03",
            "askPx": "0.035",
            "markPx": "0.032",
            "idxPx": "61000",
            "oi": "80",
            "ts": "1782345600000",
        },
    ]
    summaries = [
        {
            "instId": "BTC-USD-260925-65000-C",
            "deltaBS": "0.32",
            "deltaPA": "0.29",
            "markVol": "0.58",
        },
        {
            "instId": "BTC-USD-260925-55000-P",
            "deltaPA": "-0.36",
            "markVol": "0.62",
        },
    ]

    quotes = normalize_okx_options(instruments, tickers, summaries)

    assert quotes[0].delta == 0.32
    assert "greeks_pa_fallback" not in quotes[0].quality_notes
    assert quotes[1].delta == -0.36
    assert "greeks_pa_fallback" in quotes[1].quality_notes


def test_missing_numeric_values_remain_null_and_do_not_become_zero() -> None:
    snapshot = normalize_binance_perp(
        {"symbol": "BTCUSDT", "markPrice": "61000", "time": 1_782_345_600_000},
        open_interest={},
        ticker={},
    )

    assert snapshot.open_interest_contracts is None
    assert snapshot.open_interest_usd is None
    assert snapshot.funding_rate is None
    assert "open_interest_contracts" in snapshot.missing_fields


def test_daily_live_history_overwrites_same_day_and_keeps_400_points(
    tmp_path: Path,
) -> None:
    cache = LiveSourceCache(tmp_path)
    for index in range(405):
        day = datetime.fromordinal(datetime(2025, 1, 1).toordinal() + index)
        cache.append_daily({"timestamp": day.date().isoformat(), "spot_price": index})
    cache.append_daily({"timestamp": day.date().isoformat(), "spot_price": 999})

    history = cache.read_history()

    assert len(history) == 400
    assert history[-1]["spot_price"] == 999


@pytest.mark.asyncio
async def test_collector_uses_only_recent_real_cache_when_live_collection_fails(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    cache = LiveSourceCache(tmp_path)
    cached = LiveSnapshotEnvelope(
        snapshot_state="live",
        data_timestamp=datetime.now(timezone.utc),
        primary_option_provider="deribit",
    )
    cache.write_snapshot(cached.model_dump(mode="json"))
    collector = LiveCollector(cache=cache)

    async def failed_collect(*, force: bool = False) -> LiveSnapshotEnvelope:
        return LiveSnapshotEnvelope(
            snapshot_state="data_insufficient",
            missing_reasons=["network unavailable"],
        )

    monkeypatch.setattr(collector, "collect", failed_collect)

    result = await collector.snapshot(force=True)

    assert result.snapshot_state == "stale"
    assert result.primary_option_provider == "deribit"


@pytest.mark.asyncio
async def test_collector_never_falls_back_to_fixture_without_real_cache(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    collector = LiveCollector(cache=LiveSourceCache(tmp_path))

    async def failed_collect(*, force: bool = False) -> LiveSnapshotEnvelope:
        return LiveSnapshotEnvelope(
            snapshot_state="data_insufficient",
            missing_reasons=["network unavailable"],
        )

    monkeypatch.setattr(collector, "collect", failed_collect)

    result = await collector.snapshot(force=True)

    assert result.snapshot_state == "data_insufficient"
    assert result.options == []
    assert "fixture" not in result.model_dump_json()


@pytest.mark.asyncio
async def test_live_service_keeps_six_chart_contract_when_all_sources_fail() -> None:
    class FailedCollector:
        async def snapshot(
            self,
            *,
            force: bool = False,
            allow_network: bool = True,
        ) -> LiveSnapshotEnvelope:
            return LiveSnapshotEnvelope(
                snapshot_state="data_insufficient",
                missing_reasons=["all providers failed"],
            )

    dashboard = await BtcDerivativesLiveService(
        collector=FailedCollector()  # type: ignore[arg-type]
    ).dashboard()
    charts = {**dashboard.futures.charts, **dashboard.options.charts}

    assert set(charts) == REQUIRED_CHART_IDS
    assert dashboard.snapshot_state == "data_insufficient"
    assert all(chart.status == "data_insufficient" for chart in charts.values())
    assert "fixture" not in dashboard.model_dump_json()


@pytest.mark.asyncio
async def test_collector_disabled_mode_does_not_call_provider_adapters(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    collector = LiveCollector(cache=LiveSourceCache(tmp_path))
    called = False

    async def should_not_run(*, force: bool = False):
        nonlocal called
        called = True

    for adapter in collector.adapters.values():
        monkeypatch.setattr(adapter, "collect", should_not_run)
    monkeypatch.setattr(
        "app.services.btc_derivatives.sources.collector.settings.btc_derivatives_live_enabled",
        False,
    )

    snapshot = await collector.collect(force=True)

    assert called is False
    assert snapshot.snapshot_state == "data_insufficient"
