from __future__ import annotations

from datetime import datetime, timedelta, timezone
from decimal import Decimal
from types import SimpleNamespace

import pytest

from app.services.volatility_research.dvol import DeribitDvolClient
from app.services.volatility_research.estimators import (
    OhlcBar,
    annualization_factor,
    atr_natr,
    bipower_and_jump_volatility,
    bollinger_bandwidth,
    empirical_percentile,
    ewma_volatility,
    range_volatility,
    realized_volatility,
    yang_zhang_volatility,
)
from app.services.volatility_research.service import (
    FORMULA_VERSION,
    VolatilityResearchService,
)
from app.services.volatility_research.volmex import VolmexVolatilityClient

UTC = timezone.utc


def _bars() -> list[OhlcBar]:
    return [
        OhlcBar(Decimal("100"), Decimal("103"), Decimal("99"), Decimal("102")),
        OhlcBar(Decimal("102"), Decimal("106"), Decimal("101"), Decimal("105")),
        OhlcBar(Decimal("105"), Decimal("107"), Decimal("102"), Decimal("103")),
        OhlcBar(Decimal("103"), Decimal("110"), Decimal("102"), Decimal("109")),
    ]


def test_realized_estimators_are_decimal_annualized_and_non_negative() -> None:
    bars = _bars()
    assert annualization_factor(86400) == Decimal(365)
    values = [
        realized_volatility(bars, 86400),
        ewma_volatility(bars, 86400, Decimal("0.94")),
        range_volatility(bars, 86400, "parkinson"),
        range_volatility(bars, 86400, "garman_klass"),
        range_volatility(bars, 86400, "rogers_satchell"),
        range_volatility(bars, 86400, "realized_range"),
        yang_zhang_volatility(bars, 86400),
    ]
    bipower, jump = bipower_and_jump_volatility(bars, 86400)
    values.extend((bipower, jump))
    assert all(isinstance(value, Decimal) and value >= 0 for value in values)


def test_wilder_atr_and_natr_keep_price_and_percent_units() -> None:
    bars = _bars() * 5
    atr, natr = atr_natr(bars, 14)
    assert isinstance(atr, Decimal) and atr > 0
    assert natr == atr / bars[-1].close * Decimal(100)
    assert atr_natr(bars[:14], 14) == (None, None)


def test_flat_market_has_zero_close_and_range_volatility() -> None:
    bars = [OhlcBar(Decimal(100), Decimal(100), Decimal(100), Decimal(100))] * 4
    assert realized_volatility(bars, 3600) == 0
    assert range_volatility(bars, 3600, "parkinson") == 0
    assert yang_zhang_volatility(bars, 3600) == 0


def test_invalid_ohlc_is_excluded_and_short_history_is_explicitly_missing() -> None:
    invalid = OhlcBar(Decimal(100), Decimal(90), Decimal(110), Decimal(100))
    assert realized_volatility([invalid], 3600) is None
    assert yang_zhang_volatility(_bars()[:2], 3600) is None
    with pytest.raises(ValueError, match="bar_seconds"):
        realized_volatility(_bars(), 0)
    with pytest.raises(ValueError, match="decay"):
        ewma_volatility(_bars(), 3600, Decimal(1))


def test_empirical_percentile_is_midrank_not_ratio_to_mean() -> None:
    history = [Decimal(1), Decimal(2), Decimal(2), Decimal(4)]
    assert empirical_percentile(history, Decimal(2)) == Decimal(50)
    assert empirical_percentile([], Decimal(2)) is None


def test_bollinger_bandwidth_handles_window_and_zero_mean() -> None:
    assert bollinger_bandwidth([Decimal(1)], 2) is None
    assert bollinger_bandwidth([Decimal(0), Decimal(0)], 2) is None
    value = bollinger_bandwidth([Decimal(100), Decimal(102), Decimal(98)], 3)
    assert isinstance(value, Decimal)
    assert value > 0


class _FakeHttp:
    def __init__(self) -> None:
        self.success: tuple[str, float] | None = None

    async def request(self, provider, endpoint, **kwargs):
        assert provider.key == "deribit_dvol"
        assert endpoint.params["currency"] == "BTC"
        assert kwargs["decimal_json"] is True
        return {
            "result": {
                "data": [
                    [1724457600000, 50.1, 51.2, 49.8, 50.7],
                    [1724461200000, None, 52, 50, 51],
                ]
            }
        }, 12.5, 200

    def record_success(self, provider: str, latency_ms: float) -> None:
        self.success = provider, latency_ms


@pytest.mark.asyncio
async def test_deribit_dvol_adapter_preserves_decimal_and_timestamp() -> None:
    http = _FakeHttp()
    rows = await DeribitDvolClient(http=http).fetch(
        start_ms=1724457600000, end_ms=1724461200000
    )
    assert len(rows) == 1
    assert rows[0].close == Decimal("50.7")
    assert rows[0].timestamp.tzinfo is UTC
    assert http.success == ("deribit_dvol", 12.5)


class _FakeVolmexHttp(_FakeHttp):
    async def request(self, provider, endpoint, **kwargs):
        assert provider.key == "volmex"
        assert endpoint.params["symbol"] == "BVIV"
        assert kwargs["decimal_json"] is True
        return {
            "s": "ok",
            "t": [1724457600, 1724461200],
            "o": [50.1, None],
            "h": [51.2, 52.0],
            "l": [49.8, 50.0],
            "c": [50.7, 51.0],
        }, 10.0, 200


@pytest.mark.asyncio
async def test_volmex_adapter_preserves_symbol_source_and_decimal() -> None:
    rows = await VolmexVolatilityClient(http=_FakeVolmexHttp()).fetch(
        symbol="BVIV", start_seconds=1724457600, end_seconds=1724461200
    )
    assert len(rows) == 1
    assert rows[0].close == Decimal("50.7")
    with pytest.raises(ValueError, match="unsupported Volmex"):
        await VolmexVolatilityClient(http=_FakeVolmexHttp()).fetch(
            symbol="UNKNOWN", start_seconds=1, end_seconds=2
        )
    with pytest.raises(ValueError, match="unsupported Volmex"):
        await VolmexVolatilityClient(http=_FakeVolmexHttp()).fetch(
            symbol="BVIV30D", start_seconds=1, end_seconds=2
        )


class _FakeRepository:
    def __init__(self, candles) -> None:
        self.candles = candles
        self.snapshot = None
        self.observations = []

    async def list_candles(self, instrument_id, timeframe, limit=200):
        assert instrument_id == "btc-usdt-perp"
        assert timeframe == "1d"
        return self.candles[-limit:]

    async def append_volatility_research_snapshot(self, snapshot, observations):
        self.snapshot = snapshot
        self.observations = observations
        return snapshot

    async def latest_volatility_research_snapshot(self, instrument_id, timeframe):
        return self.snapshot


@pytest.mark.asyncio
async def test_shadow_snapshot_is_append_only_decimal_and_has_no_canonical_effect() -> None:
    start = datetime(2025, 1, 1, tzinfo=UTC)
    candles = []
    price = Decimal(50000)
    for index in range(140):
        close = price + Decimal(index * 7 + (index % 5) * 11)
        candles.append(
            SimpleNamespace(
                ts_open=start + timedelta(days=index),
                open=close - Decimal(20),
                high=close + Decimal(100),
                low=close - Decimal(120),
                close=close,
                source="fixture",
                created_at=start + timedelta(days=index, minutes=1),
            )
        )
    repository = _FakeRepository(candles)
    snapshot = await VolatilityResearchService(repository).build_shadow_snapshot(
        "btc-usdt-perp", "1d"
    )
    assert snapshot.integration_status == "shadow"
    assert snapshot.formula_version == FORMULA_VERSION
    assert snapshot.quality_json["no_canonical_effect"] is True
    assert snapshot.timestamp_contract_json["valid"] is True
    assert snapshot.options_expectations_json["status"] == "data_insufficient"
    assert repository.observations
    assert all(
        row.value_num is None or isinstance(row.value_num, Decimal)
        for row in repository.observations
    )
    percentile = snapshot.price_volatility_json["features"][
        "bollinger_bandwidth_empirical_percentile"
    ]
    assert percentile["parameters"]["rank_method"] == "midrank"
    assert snapshot.price_volatility_json["legacy_semantics"]["strategy_effect"] == (
        "unchanged_shadow_only"
    )
