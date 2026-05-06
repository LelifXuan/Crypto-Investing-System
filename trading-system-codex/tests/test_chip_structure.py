from __future__ import annotations

from datetime import UTC, datetime, timedelta
from decimal import Decimal
from pathlib import Path
from types import SimpleNamespace

import pytest
from fastapi.testclient import TestClient

from app.core.config import settings
from app.core.db import db_manager
from app.db.models.instrument import Instrument
from app.db.models.market import IndicatorObservation, MarketCandle
from app.main import create_app
from app.repositories.market_repository import MarketRepository
from app.services.chip_structure import (
    PRIMARY_TIMEFRAMES,
    TIMEFRAME_LABELS,
    ChipStructureService,
    TimeframeSnapshot,
)
from app.services.data_quality import DataQualityAssessment
from app.services.indicator_monitoring import IndicatorMonitoringService


def _quality(
    status: str = "good", *, can_analyze: bool = True, can_alert: bool = True
) -> DataQualityAssessment:
    score = {"good": 96.0, "fair": 78.0, "degraded": 58.0, "bad": 28.0, "missing": 0.0}[status]
    return DataQualityAssessment(
        data_quality_score=score,
        status=status,
        issues=[] if status == "good" else [status],
        can_analyze=can_analyze,
        can_alert=can_alert,
    )


def _snapshot(
    timeframe: str,
    *,
    bias: str = "neutral",
    range_position: str = "balanced",
    quality_status: str = "good",
    false_breakout: bool = False,
    false_breakdown: bool = False,
    breakout_up: bool = False,
    breakout_down: bool = False,
    bb_width: float = 0.05,
) -> TimeframeSnapshot:
    return TimeframeSnapshot(
        timeframe=timeframe,
        label=TIMEFRAME_LABELS[timeframe],
        candles=[
            SimpleNamespace(high=1, low=1, close=1, volume=1, ts_open=datetime.now(UTC))
            for _ in range(80)
        ],
        quality=_quality(
            quality_status,
            can_analyze=quality_status != "missing",
            can_alert=quality_status == "good",
        ),
        close=100.0,
        profile={
            "poc": 100.0,
            "vah": 103.0,
            "val": 97.0,
            "direction_score": 0.2,
            "balance_score": 0.7,
        },
        ema20=101.0,
        ema50=100.0,
        ema200=98.0,
        adx=24.0,
        bb_width=bb_width,
        bb_percent_b=0.62,
        obv_slope=0.12,
        range_position=range_position,
        bias=bias,
        summary=f"{TIMEFRAME_LABELS[timeframe]} {bias}",
        evidence=[f"{TIMEFRAME_LABELS[timeframe]} evidence"],
        breakout_up=breakout_up,
        breakout_down=breakout_down,
        false_breakout=false_breakout,
        false_breakdown=false_breakdown,
    )


async def _run_service(
    monkeypatch,
    snapshot_map: dict[str, TimeframeSnapshot],
    *,
    funding_rate=None,
    funding_zscore=None,
    basis_rate=None,
    basis_zscore=None,
    cvd_delta=None,
    open_interest_notional=None,
    depth_liquidity=None,
    slippage_bps=None,
):
    service = ChipStructureService(SimpleNamespace())

    async def fake_snapshot(_instrument_id: str, timeframe: str) -> TimeframeSnapshot:
        return snapshot_map[timeframe]

    async def fake_latest(_instrument_id: str, indicator_keys: tuple[str, ...]):
        mapping = {
            "funding_rate": funding_rate,
            "funding_rate_zscore": funding_zscore,
            "basis_rate": basis_rate,
            "basis_rate_zscore": basis_zscore,
            "cvd_delta": cvd_delta,
            "open_interest_notional": open_interest_notional,
            "depth_liquidity": depth_liquidity,
            "slippage_bps": slippage_bps,
        }
        return {key: mapping.get(key) for key in indicator_keys}

    monkeypatch.setattr(service, "_build_timeframe_snapshot", fake_snapshot)
    monkeypatch.setattr(service, "_latest_observations", fake_latest)
    return await service.analyze("btc-usdt-perp", "4h")


@pytest.mark.asyncio
async def test_chip_structure_balanced_auction_degraded(monkeypatch) -> None:
    snapshots = {tf: _snapshot(tf) for tf in PRIMARY_TIMEFRAMES}
    payload = await _run_service(monkeypatch, snapshots)

    assert payload["primary_regime"] == "balanced_auction"
    assert payload["state"] == "degraded"
    assert payload["state_label"] in {"数据不完整", "信息缺失", "风险受限", "流动性不足"}
    assert payload["recommended_action"] == "wait_confirmation"
    assert payload["capital_allocation_label"]
    assert payload["capital_allocation_pct_max"] >= payload["capital_allocation_pct_min"]
    assert payload["spot_allocation_label"]
    assert payload["futures_allocation_label"]
    assert payload["probe_position_label"]
    assert payload["missing_inputs"]
    assert payload["allow_futures_long"] is False
    assert payload["futures_allocation_pct_min"] == 0
    assert payload["futures_allocation_pct_max"] == 0
    assert payload["why_no_futures_long"]
    assert payload["timeframes"][0]["timeframe"] == "1W"


@pytest.mark.asyncio
async def test_chip_structure_accumulation_candidate(monkeypatch) -> None:
    snapshots = {
        "1w": _snapshot("1w", bias="neutral"),
        "1d": _snapshot("1d", bias="neutral", range_position="lower_half"),
        "4h": _snapshot("4h", bias="bullish", range_position="lower_half"),
        "1h": _snapshot("1h", bias="bullish", range_position="balanced"),
    }
    payload = await _run_service(monkeypatch, snapshots)

    assert payload["primary_regime"] == "accumulation_proxy"
    assert payload["evidence_quality"] == "proxy_only"
    assert payload["recommended_action"] == "range_long_bias"
    assert payload["direction_score"] > 0


@pytest.mark.asyncio
async def test_chip_structure_distribution_candidate(monkeypatch) -> None:
    snapshots = {
        "1w": _snapshot("1w", bias="neutral"),
        "1d": _snapshot("1d", bias="neutral", range_position="upper_half"),
        "4h": _snapshot("4h", bias="bearish", range_position="upper_half"),
        "1h": _snapshot("1h", bias="bearish", range_position="balanced"),
    }
    payload = await _run_service(monkeypatch, snapshots)

    assert payload["primary_regime"] == "distribution_proxy"
    assert payload["recommended_action"] == "range_short_bias"
    assert payload["direction_score"] < 0
    assert payload["spot_allocation_pct_max"] <= 5


@pytest.mark.asyncio
async def test_chip_structure_accumulation_confirmed(monkeypatch) -> None:
    snapshots = {
        "1w": _snapshot("1w", bias="neutral"),
        "1d": _snapshot("1d", bias="neutral", range_position="lower_half"),
        "4h": _snapshot("4h", bias="bullish", range_position="lower_half"),
        "1h": _snapshot("1h", bias="bullish", range_position="balanced"),
    }
    payload = await _run_service(
        monkeypatch,
        snapshots,
        funding_rate=0.001,
        cvd_delta=2500,
        open_interest_notional=100000,
        depth_liquidity=500000,
        slippage_bps=3,
    )

    assert payload["primary_regime"] == "accumulation_confirmed"
    assert payload["evidence_quality"] == "confirmed"
    assert payload["confidence_label"] in {"watch_only", "usable", "high", "execution_ready"}
    assert payload["recommended_action_v2"] in {
        "observe",
        "probe",
        "normal_trade",
        "add_on_confirmation",
        "wait_for_confirmation",
    }


@pytest.mark.asyncio
async def test_observe_only_never_has_futures_minimum(monkeypatch) -> None:
    snapshots = {tf: _snapshot(tf, quality_status="fair") for tf in PRIMARY_TIMEFRAMES}
    payload = await _run_service(monkeypatch, snapshots)

    assert payload["recommended_action"] in {"observe_only", "wait_confirmation"}
    assert payload["futures_allocation_pct_min"] == 0
    assert payload["futures_allocation_pct_max"] == 0


@pytest.mark.asyncio
async def test_range_position_does_not_directly_change_direction_score() -> None:
    service = ChipStructureService(SimpleNamespace())
    bullish = _snapshot("4h", bias="bullish", range_position="upper_half")
    lower = _snapshot("4h", bias="bullish", range_position="lower_half")

    upper_score = service._direction_score(bullish, bullish, bullish, bullish, None, None)
    lower_score = service._direction_score(lower, lower, lower, lower, None, None)

    assert upper_score == lower_score


@pytest.mark.asyncio
async def test_chip_structure_missing_payload_explain_is_chinese(monkeypatch) -> None:
    snapshots = {
        tf: _snapshot(tf, quality_status="missing", bb_width=0.0)
        for tf in PRIMARY_TIMEFRAMES
    }
    for snapshot in snapshots.values():
        snapshot.candles = []
        snapshot.quality = _quality("missing", can_analyze=False, can_alert=False)
    payload = await _run_service(monkeypatch, snapshots)

    assert "缺少可用 K 线" in "".join(payload["explain"])
    assert "No usable candles" not in "".join(payload["explain"])


@pytest.mark.asyncio
async def test_chip_structure_distribution_confirmed(monkeypatch) -> None:
    snapshots = {
        "1w": _snapshot("1w", bias="neutral"),
        "1d": _snapshot("1d", bias="neutral", range_position="upper_half"),
        "4h": _snapshot("4h", bias="bearish", range_position="upper_half"),
        "1h": _snapshot("1h", bias="bearish", range_position="balanced"),
    }
    payload = await _run_service(
        monkeypatch,
        snapshots,
        funding_rate=0.001,
        cvd_delta=-2500,
        open_interest_notional=100000,
        depth_liquidity=500000,
        slippage_bps=3,
    )

    assert payload["primary_regime"] == "distribution_confirmed"
    assert payload["evidence_quality"] == "confirmed"


@pytest.mark.asyncio
@pytest.mark.parametrize(
    ("flag", "expected_regime", "expected_action"),
    [
        ("false_breakout", "false_breakout", "breakdown_watch"),
        ("false_breakdown", "false_breakdown", "breakout_watch"),
    ],
)
async def test_chip_structure_false_break_signals(
    monkeypatch, flag: str, expected_regime: str, expected_action: str
) -> None:
    h4 = _snapshot("4h", bias="neutral")
    h1 = _snapshot("1h", bias="neutral")
    setattr(h1, flag, True)
    snapshots = {
        "1w": _snapshot("1w", bias="neutral"),
        "1d": _snapshot("1d", bias="neutral"),
        "4h": h4,
        "1h": h1,
    }
    payload = await _run_service(monkeypatch, snapshots)

    assert payload["primary_regime"] == expected_regime
    assert payload["recommended_action"] == expected_action


@pytest.fixture()
async def chip_db(tmp_path: Path, monkeypatch):
    db_path = tmp_path / "chip.db"
    monkeypatch.setattr(settings, "database_url", f"sqlite+aiosqlite:///{db_path.as_posix()}")
    monkeypatch.setattr(settings, "monitoring_scheduler_enabled", False)
    await db_manager.disconnect()
    await db_manager.connect()
    await db_manager.create_schema()
    try:
        yield
    finally:
        await db_manager.disconnect()


@pytest.mark.asyncio
async def test_chip_structure_endpoint_returns_payload(chip_db) -> None:
    base = datetime(2026, 4, 1, tzinfo=UTC)
    async with db_manager.session() as session:
        await IndicatorMonitoringService(MarketRepository(session)).seed_defaults()
        session.add(
            Instrument(
                instrument_id="btc-usdt-perp",
                venue="GATEIO",
                symbol="BTC_USDT",
                asset_class="PERP",
                base_ccy="BTC",
                quote_ccy="USDT",
                settle_ccy="USDT",
                tick_size=Decimal("0.1"),
                lot_size=Decimal("0.001"),
                contract_multiplier=Decimal("1"),
                margin_model="ISOLATED",
                metadata_json={
                    "gateio": {"product_type": "futures", "contract": "BTC_USDT", "settle": "usdt"}
                },
            )
        )
        for timeframe, step_hours in (("1h", 1), ("4h", 4), ("1d", 24), ("1w", 24 * 7)):
            candles = []
            for index in range(90):
                close = Decimal("100000") + Decimal(index * (200 if timeframe != "1w" else 600))
                candles.append(
                    MarketCandle(
                        instrument_id="btc-usdt-perp",
                        timeframe=timeframe,
                        ts_open=base + timedelta(hours=index * step_hours),
                        open=close - Decimal("120"),
                        high=close + Decimal("260"),
                        low=close - Decimal("240"),
                        close=close,
                        volume=Decimal("1000") + Decimal(index * 10),
                        source="test",
                    )
                )
            session.add_all(candles)
        observations = [
            IndicatorObservation(
                observation_id="obs-funding-rate",
                dedupe_key="obs-funding-rate",
                indicator_key="funding_rate",
                category="technical",
                instrument_id="btc-usdt-perp",
                timeframe="1h",
                observation_ts=base + timedelta(days=30),
                value_num=Decimal("0.002"),
                value_json={},
                source_provider="test",
            ),
            IndicatorObservation(
                observation_id="obs-funding-z",
                dedupe_key="obs-funding-z",
                indicator_key="funding_rate_zscore",
                category="technical",
                instrument_id="btc-usdt-perp",
                timeframe="1h",
                observation_ts=base + timedelta(days=30),
                value_num=Decimal("1.25"),
                value_json={},
                source_provider="test",
            ),
            IndicatorObservation(
                observation_id="obs-basis-rate",
                dedupe_key="obs-basis-rate",
                indicator_key="basis_rate",
                category="technical",
                instrument_id="btc-usdt-perp",
                timeframe="1h",
                observation_ts=base + timedelta(days=30),
                value_num=Decimal("0.0018"),
                value_json={},
                source_provider="test",
            ),
            IndicatorObservation(
                observation_id="obs-basis-z",
                dedupe_key="obs-basis-z",
                indicator_key="basis_rate_zscore",
                category="technical",
                instrument_id="btc-usdt-perp",
                timeframe="1h",
                observation_ts=base + timedelta(days=30),
                value_num=Decimal("1.10"),
                value_json={},
                source_provider="test",
            ),
        ]
        session.add_all(observations)
        await session.commit()

    with TestClient(create_app(enable_lifespan=False)) as client:
        response = client.get(
            "/api/v1/alerts/chip-structure",
            params={"instrument_id": "btc-usdt-perp", "timeframe": "4h"},
        )
    payload = response.json()
    assert response.status_code == 200
    assert "direction_label" in payload
    assert "confidence_label" in payload
    assert "execution_score" in payload
    assert "risk_score" in payload
    assert "components" in payload

    assert response.status_code == 200
    payload = response.json()
    assert payload["instrument_id"] == "btc-usdt-perp"
    assert payload["timeframe"] == "4h"
    assert payload["primary_regime"]
    assert "data_quality" in payload
    assert payload["state_label"]
    assert payload["state_reason"]
    assert payload["capital_allocation_label"]
    assert payload["spot_allocation_label"]
    assert payload["futures_allocation_label"]
    assert payload["probe_position_label"]
    assert "direction_permission" in payload
    assert "execution_readiness" in payload
    assert len(payload["timeframes"]) == 4
