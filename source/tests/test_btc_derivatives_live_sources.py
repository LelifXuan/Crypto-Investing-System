from __future__ import annotations

from datetime import datetime, timezone
from pathlib import Path

import pytest

from app.schemas.btc_derivatives_sources import (
    LiveSnapshotEnvelope,
    NormalizedOptionQuote,
    NormalizedPerpSnapshot,
)
from app.services.btc_derivatives.chart_builder import REQUIRED_CHART_IDS
from app.services.btc_derivatives.archive import DerivativesArchive
from app.services.btc_derivatives.live_service import (
    BtcDerivativesLiveService,
    _merge_key_level_history,
)
from app.services.btc_derivatives.service import BtcDerivativesService
from app.services.btc_derivatives.sources.cache import LiveSourceCache
from app.services.btc_derivatives.sources.collector import LiveCollector
from app.services.btc_derivatives.sources.normalizer import (
    normalize_binance_perp,
    normalize_deribit_option,
    normalize_okx_options,
    normalize_simple_perp,
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


def test_deribit_future_instrument_expiry_is_parsed_for_term_structure() -> None:
    snapshot = normalize_simple_perp(
        "deribit",
        "BTC-24JUL26",
        mark_price=63_000,
        open_interest_contracts=120,
        timestamp=1_783_532_400_000,
    )

    assert snapshot.instrument_type == "future"
    assert snapshot.expiry == "2026-07-24"
    assert snapshot.funding_rate is None
    assert "funding_rate" not in snapshot.missing_fields


def test_dashboard_backfills_future_basis_from_spot_for_term_structure() -> None:
    now = datetime(2026, 7, 9, 8, tzinfo=timezone.utc)
    envelope = LiveSnapshotEnvelope(
        snapshot_state="live",
        data_timestamp=now,
        primary_option_provider="deribit",
        options=[
            NormalizedOptionQuote(
                provider="deribit",
                instrument="BTC-31JUL26-65000-C",
                expiry="2026-07-31",
                strike=65_000,
                option_type="call",
                bid=800,
                ask=900,
                mark_price=850,
                underlying_price=62_000,
                iv=0.45,
                delta=0.35,
                open_interest=100,
                collected_at=now,
            ),
            NormalizedOptionQuote(
                provider="deribit",
                instrument="BTC-31JUL26-60000-P",
                expiry="2026-07-31",
                strike=60_000,
                option_type="put",
                bid=700,
                ask=800,
                mark_price=750,
                underlying_price=62_000,
                iv=0.46,
                delta=-0.35,
                open_interest=80,
                collected_at=now,
            ),
        ],
        perps=[
            NormalizedPerpSnapshot(
                provider="deribit",
                instrument="BTC-31JUL26",
                instrument_type="future",
                expiry="2026-07-31",
                mark_price=63_240,
                collected_at=now,
            ),
            NormalizedPerpSnapshot(
                provider="deribit",
                instrument="BTC-PERPETUAL",
                mark_price=62_010,
                collected_at=now,
            ),
        ],
    )

    dashboard = BtcDerivativesService().build_dashboard(live_snapshot=envelope)
    term = dashboard.futures.charts["term_structure"]
    datasets = {dataset.label: dataset.data for dataset in term.datasets}

    assert term.labels == ["2026-07-31"]
    assert datasets["Basis"] == [0.02]
    assert datasets["年化 Basis"][0] == pytest.approx(0.3318181818)


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


def test_daily_history_keeps_independent_expiry_series_on_same_day(tmp_path: Path) -> None:
    cache = LiveSourceCache(tmp_path / "cache")
    first = {
        "timestamp": "2026-07-14T01:00:00Z",
        "series_key": "constant_maturity:30D:2026-07-31",
        "source_expiry": "2026-07-31",
    }
    second = {
        "timestamp": "2026-07-14T02:00:00Z",
        "series_key": "constant_maturity:60D:2026-09-25",
        "source_expiry": "2026-09-25",
    }
    cache.append_daily(first)
    history = cache.append_daily(second)
    assert len(history) == 2
    assert {item["series_key"] for item in history} == {
        first["series_key"],
        second["series_key"],
    }


def test_portable_history_recovers_from_durable_archive_after_cache_clear(
    tmp_path: Path,
) -> None:
    archive = DerivativesArchive(tmp_path / "data" / "derivatives_archive")
    first = {
        "timestamp": "2026-07-19T00:00:00+00:00",
        "series_key": "constant_maturity:60D:2026-09-25",
        "source_expiry": "2026-09-25",
        "spot_price": 64_000,
    }
    second = {
        **first,
        "timestamp": "2026-07-20T00:00:00+00:00",
        "spot_price": 65_000,
    }
    for item in (first, second):
        archive.append(
            provider="derived",
            underlying="BTC",
            data_type="daily_metrics",
            captured_at=datetime.fromisoformat(item["timestamp"]),
            records=[item],
        )

    recovered = _merge_key_level_history(
        archive.read_records(data_type="daily_metrics", underlying="BTC"),
        [],
    )

    assert [item["spot_price"] for item in recovered] == [64_000, 65_000]


def test_history_merge_keeps_rolls_separate_and_cache_wins_exact_duplicate() -> None:
    timestamp = "2026-07-19T00:00:00+00:00"
    archived = [
        {
            "timestamp": timestamp,
            "series_key": "constant_maturity:30D:2026-07-31",
            "source_expiry": "2026-07-31",
            "spot_price": 63_000,
        },
        {
            "timestamp": timestamp,
            "series_key": "constant_maturity:60D:2026-09-25",
            "source_expiry": "2026-09-25",
            "spot_price": 63_100,
        },
    ]
    cached = [{**archived[0], "spot_price": 63_500}]

    merged = _merge_key_level_history(archived, cached)

    assert len(merged) == 2
    assert next(item for item in merged if item["source_expiry"] == "2026-07-31")[
        "spot_price"
    ] == 63_500


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
