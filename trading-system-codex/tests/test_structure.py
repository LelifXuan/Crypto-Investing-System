from __future__ import annotations

from datetime import UTC, datetime, timedelta
from decimal import Decimal
from pathlib import Path

import pytest
from fastapi.testclient import TestClient

from app.core.config import settings
from app.core.db import db_manager
from app.db.models.instrument import Instrument
from app.db.models.market import MarketCandle
from app.main import create_app
from app.repositories.market_repository import MarketRepository
from app.services.structure import (
    ScoreBundle,
    ScoringConfig,
    StructureFusionEngine,
    StructureSnapshotService,
)
from app.services.structure.events import build_fused_events


@pytest.fixture()
async def structure_db(tmp_path: Path, monkeypatch):
    db_path = tmp_path / "structure.db"
    monkeypatch.setattr(settings, "database_url", f"sqlite+aiosqlite:///{db_path.as_posix()}")
    await db_manager.disconnect()
    await db_manager.connect()
    await db_manager.create_schema()
    async with db_manager.session() as session:
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
        start = datetime(2026, 1, 1, tzinfo=UTC)
        base = Decimal("100")
        candles: list[MarketCandle] = []
        for idx in range(80):
            open_price = base + Decimal(idx * 1.5)
            high = open_price + Decimal("3.5")
            low = open_price - Decimal("2.5")
            close = open_price + (Decimal("1.8") if idx % 5 else Decimal("-0.6"))
            if 30 <= idx <= 36:
                high = Decimal("150")
            if 60 <= idx <= 66:
                low = Decimal("170")
                high = Decimal("182")
                close = Decimal("179") + Decimal(idx - 60) * Decimal("0.2")
            candles.append(
                MarketCandle(
                    instrument_id="btc-usdt-perp",
                    timeframe="1h",
                    ts_open=start + timedelta(hours=idx),
                    open=open_price,
                    high=high,
                    low=low,
                    close=close,
                    volume=Decimal("1000") + Decimal(idx * 15),
                    source="test",
                )
            )
        session.add_all(candles)
    try:
        yield
    finally:
        await db_manager.disconnect()


@pytest.mark.asyncio
async def test_structure_service_builds_snapshot(structure_db) -> None:
    async with db_manager.session() as session:
        service = StructureSnapshotService(MarketRepository(session))
        snapshot = await service.refresh_snapshot(
            "btc-usdt-perp", "1h", include_geometry=True, include_diagnostics=True
        )
        events = await service.list_events("btc-usdt-perp", "1h", limit=20)
        alerts = await service.list_alerts("btc-usdt-perp", "1h", limit=20)

    assert snapshot.instrument_id == "btc-usdt-perp"
    assert snapshot.timeframe == "1h"
    assert len(snapshot.systems) == 3
    assert snapshot.overall.overall_bias in {
        "bullish",
        "weak_bullish",
        "bearish",
        "weak_bearish",
        "neutral",
        "uncertain",
        "no_clear_structure",
    }
    assert snapshot.overall.regime in {"trend", "balance", "transition"}
    assert snapshot.overall.weight_template in {"trend", "balance", "transition"}
    assert snapshot.overall.weights
    assert snapshot.overall.contribution_breakdown
    assert all(item.effective_score is not None for item in snapshot.systems)
    assert all(item.weight is not None for item in snapshot.systems)
    assert all(item.weighted_contribution is not None for item in snapshot.systems)
    assert snapshot.geometry
    assert snapshot.diagnostics is not None
    assert events
    assert any(item.event_name.startswith("market.structure.") for item in events)
    assert alerts


@pytest.mark.asyncio
async def test_structure_api_endpoints(structure_db) -> None:
    with TestClient(create_app(enable_lifespan=False)) as client:
        refresh_response = client.post(
            "/api/v1/structure/tab/refresh",
            params={"instrument_id": "btc-usdt-perp", "timeframe": "1h"},
        )
        snapshot_response = client.get(
            "/api/v1/structure/tab/snapshot",
            params={
                "instrument_id": "btc-usdt-perp",
                "timeframe": "1h",
                "include_geometry": "true",
                "include_diagnostics": "true",
            },
        )
        events_response = client.get(
            "/api/v1/structure/tab/events",
            params={"instrument_id": "btc-usdt-perp", "timeframe": "1h", "limit": 10},
        )
        alerts_response = client.get(
            "/api/v1/structure/tab/alerts",
            params={"instrument_id": "btc-usdt-perp", "timeframe": "1h", "limit": 10},
        )
        diagnostics_response = client.get(
            "/api/v1/structure/tab/diagnostics",
            params={"instrument_id": "btc-usdt-perp", "timeframe": "1h"},
        )
        bundle_response = client.get(
            "/api/v1/structure/tab/bundle",
            params={
                "instrument_id": "btc-usdt-perp",
                "timeframe": "1h",
                "include_geometry": "true",
                "include_diagnostics": "true",
            },
        )
        page_response = client.get("/structure-page")

    assert refresh_response.status_code == 200
    assert snapshot_response.status_code == 200
    assert events_response.status_code == 200
    assert alerts_response.status_code == 200
    assert diagnostics_response.status_code == 200
    assert bundle_response.status_code == 200
    assert page_response.status_code == 200

    snapshot_payload = snapshot_response.json()
    assert snapshot_payload["timeframe"] == "1h"
    assert len(snapshot_payload["systems"]) == 3
    assert "overall" in snapshot_payload
    assert isinstance(snapshot_payload["active_items"], list)
    assert snapshot_payload["overall"]["regime"] in {"trend", "balance", "transition"}
    assert "weights" in snapshot_payload["overall"]
    assert "contribution_breakdown" in snapshot_payload["overall"]
    assert all("effective_score" in item for item in snapshot_payload["systems"])
    assert all("weight" in item for item in snapshot_payload["systems"])
    assert all("weighted_contribution" in item for item in snapshot_payload["systems"])

    event_payload = events_response.json()
    assert event_payload
    assert event_payload[0]["event_name"].startswith("market.structure.")

    alert_payload = alerts_response.json()
    assert alert_payload
    assert "alert_name" in alert_payload[0]

    diagnostics_payload = diagnostics_response.json()
    assert diagnostics_payload["profile_precision"] == "ohlcv_approx"

    bundle_payload = bundle_response.json()
    assert bundle_payload["snapshot"]["timeframe"] == "1h"
    assert isinstance(bundle_payload["candles"], list)
    assert bundle_payload["candles"]
    assert isinstance(bundle_payload["events"], list)
    assert isinstance(bundle_payload["alerts"], list)
    assert isinstance(bundle_payload["diagnostics"], dict)
    assert "mode" in bundle_payload["snapshot"]["overall"]
    assert "suggested_action" in bundle_payload["snapshot"]["overall"]


def _bundle(
    system: str,
    direction: str,
    score: float,
    *,
    metadata: dict | None = None,
    flags: list[str] | None = None,
) -> ScoreBundle:
    return ScoreBundle(
        system=system,
        direction=direction,
        direction_score=score,
        confidence=0.82,
        quality=0.88,
        freshness=0.92,
        evidence_count=5,
        top_reasons=[f"{system}:{direction}"],
        conflict_flags=flags or [],
        metadata=metadata or {},
    )


def test_structure_fusion_timeframe_conflict_exposes_explanation_fields() -> None:
    engine = StructureFusionEngine(ScoringConfig())
    result = engine.fuse(
        "1h",
        {
            "swing": _bundle("swing", "bullish", 0.18),
            "classic": _bundle("classic", "neutral", 0.02, metadata={"candidate_weight": 0.65}),
            "profile": _bundle("profile", "neutral", 0.01, metadata={"balance_score": 0.45}),
        },
    )

    assert result.conflict_type == "timeframe_conflict"
    assert result.meaning
    assert result.risk
    assert result.need_confirmation
    assert result.invalidation
    assert result.suggested_mode
    assert result.suggested_action


def test_neutral_structure_fusion_builds_event_without_alert_semantics() -> None:
    engine = StructureFusionEngine(ScoringConfig())
    result = engine.fuse(
        "1d",
        {
            "swing": _bundle("swing", "neutral", 0.14),
            "classic": _bundle("classic", "neutral", 0.12),
            "profile": _bundle("profile", "neutral", 0.13),
        },
    )

    assert result.overall_bias == "neutral"
    events = build_fused_events("eth-usdt-perp", "1d", result, datetime.now(UTC))
    assert len(events) == 1
    assert events[0].bias == "neutral"
    assert events[0].event_name == "market.structure.fused.no_clear_structure.confirmed"


def test_structure_fusion_system_and_momentum_conflicts_expose_rich_output() -> None:
    engine = StructureFusionEngine(ScoringConfig())
    result = engine.fuse(
        "4h",
        {
            "swing": _bundle("swing", "bullish", 0.65, flags=["momentum_divergence"]),
            "classic": _bundle("classic", "bearish", -0.58, flags=["momentum_divergence"]),
            "profile": _bundle("profile", "neutral", 0.04),
        },
    )

    assert result.conflict_state is True
    assert result.conflict_type in {"system_conflict", "momentum_divergence"}
    assert result.meaning
    assert result.risk
    assert result.need_confirmation
    assert result.invalidation
    assert result.suggested_mode
    assert result.suggested_action


def test_structure_fusion_volume_and_volatility_conflicts_are_explained() -> None:
    engine = StructureFusionEngine(ScoringConfig())
    volume_conflict = engine.fuse(
        "1d",
        {
            "swing": _bundle("swing", "bullish", 0.50),
            "classic": _bundle("classic", "neutral", 0.02),
            "profile": _bundle("profile", "bearish", -0.40, metadata={"balance_score": 0.72}),
        },
    )
    volatility_conflict = engine.fuse(
        "4h",
        {
            "swing": _bundle("swing", "bullish", 0.32),
            "classic": _bundle("classic", "bullish", 0.20),
            "profile": _bundle("profile", "bearish", -0.28, metadata={"imbalance": 0.55}),
        },
    )

    assert volume_conflict.conflict_type == "volume_conflict"
    assert volume_conflict.meaning and volume_conflict.risk and volume_conflict.suggested_mode
    assert volatility_conflict.conflict_type == "volatility_conflict"
    assert (
        volatility_conflict.meaning
        and volatility_conflict.risk
        and volatility_conflict.need_confirmation
    )


def test_structure_fusion_risk_veto_conflict_blocks_directional_action() -> None:
    engine = StructureFusionEngine(ScoringConfig())
    result = engine.fuse(
        "1d",
        {
            "swing": _bundle("swing", "bullish", 0.48, metadata={"risk_veto": True}),
            "classic": _bundle("classic", "bullish", 0.31),
            "profile": _bundle("profile", "bullish", 0.24),
        },
    )

    assert result.conflict_type == "risk_veto_conflict"
    assert result.risk
    assert result.need_confirmation
    assert result.suggested_mode
    assert result.suggested_action
    assert any(token in result.suggested_action for token in ("暂停", "风险", "观望", "等待"))


@pytest.mark.asyncio
async def test_structure_bundle_contains_mode_confirmation_invalidation_and_action(
    structure_db,
) -> None:
    async with db_manager.session() as session:
        service = StructureSnapshotService(MarketRepository(session))
        await service.refresh_snapshot(
            "btc-usdt-perp", "1h", include_geometry=True, include_diagnostics=True
        )
        bundle = await service.get_bundle(
            "btc-usdt-perp",
            "1h",
            include_geometry=True,
            candles_limit=60,
        )

    assert bundle.snapshot.overall.mode is not None
    assert bundle.snapshot.overall.suggested_action is not None
    assert bundle.snapshot.overall.meaning is not None


@pytest.mark.asyncio
async def test_structure_bundle_returns_missing_cache_state_without_implicit_refresh(
    structure_db,
) -> None:
    async with db_manager.session() as session:
        service = StructureSnapshotService(MarketRepository(session))
        bundle = await service.get_bundle(
            "btc-usdt-perp",
            "1h",
            include_geometry=True,
            candles_limit=60,
        )

    assert bundle.snapshot is None
    assert bundle.cache_state == "missing"
    assert bundle.is_stale is False
    assert bundle.candles
    assert bundle.status_message is not None


@pytest.mark.asyncio
async def test_structure_bundle_reports_stale_snapshot_when_newer_local_candle_exists(
    structure_db,
) -> None:
    async with db_manager.session() as session:
        repo = MarketRepository(session)
        service = StructureSnapshotService(repo)
        snapshot = await service.refresh_snapshot(
            "btc-usdt-perp", "1h", include_geometry=True, include_diagnostics=True
        )
        session.add(
            MarketCandle(
                instrument_id="btc-usdt-perp",
                timeframe="1h",
                ts_open=snapshot.generated_at + timedelta(hours=1),
                open=Decimal("220"),
                high=Decimal("225"),
                low=Decimal("218"),
                close=Decimal("223"),
                volume=Decimal("1500"),
                source="test",
            )
        )
        await session.commit()
        bundle = await service.get_bundle(
            "btc-usdt-perp", "1h", include_geometry=True, candles_limit=100
        )

    assert bundle.snapshot is not None
    assert bundle.cache_state == "stale"
    assert bundle.is_stale is True
    assert bundle.status_message is not None
    assert bundle.last_candle_ts is not None
    assert bundle.freshness_state in {"fresh", "lagging", "stale"}


@pytest.mark.asyncio
async def test_structure_api_accepts_month_cache_timeframe(structure_db) -> None:
    with TestClient(create_app(enable_lifespan=False)) as client:
        response = client.get(
            "/api/v1/structure/tab/bundle",
            params={
                "instrument_id": "btc-usdt-perp",
                "timeframe": "30d",
                "include_geometry": "true",
                "candles_limit": 120,
            },
        )

    assert response.status_code == 200
    payload = response.json()
    assert "freshness_state" in payload
    assert payload["cache_state"] in {"missing", "ready", "stale", "fresh"}
