from __future__ import annotations

from datetime import UTC, datetime, timedelta
from decimal import Decimal
from types import SimpleNamespace

import pytest

from app.cache.shared_query_cache import shared_query_cache
from app.services.market_context import MarketContextBuilder


def _observation(
    indicator_key: str,
    *,
    value: Decimal | None = Decimal("100"),
    observation_ts: datetime | None = None,
) -> SimpleNamespace:
    return SimpleNamespace(
        indicator_key=indicator_key,
        category="onchain",
        observation_ts=observation_ts or datetime(2026, 7, 1, tzinfo=UTC),
        value_num=value,
        value_json={"source": "defillama"},
        signal_state="neutral",
        source_provider="defillama",
        source_ref=f"defillama:{indicator_key}",
        source_granularity="1d",
        quality_score=Decimal("90"),
    )


@pytest.mark.asyncio
async def test_market_context_builder_reuses_chip_and_macro_for_same_key(monkeypatch) -> None:
    await shared_query_cache.clear()
    calls = {"chip": 0, "macro": 0}

    async def fake_analyze(self, instrument_id: str, timeframe: str):
        calls["chip"] += 1
        return {"evidence_quality": "structure_snapshot", "instrument_id": instrument_id}

    async def fake_macro(self):
        calls["macro"] += 1
        return SimpleNamespace(
            model_dump=lambda mode="json": {
                "regime_key": "risk_on",
                "operation_bias": "bullish",
                "confidence": "high",
            }
        )

    monkeypatch.setattr("app.services.market_context.ChipStructureService.analyze", fake_analyze)
    monkeypatch.setattr(
        "app.services.market_context.MacroOverviewService.build_overview", fake_macro
    )

    builder = MarketContextBuilder(SimpleNamespace())
    try:
        first = await builder.get_context("btc-usdt-perp", "4h")
        second = await builder.get_context("btc-usdt-perp", "4h")
    finally:
        await shared_query_cache.clear()

    assert first.chip_structure == second.chip_structure
    assert first.macro_overview == second.macro_overview
    assert set(first.__dict__) >= {
        "market_data",
        "indicator_features",
        "vwap_features",
        "structure_features",
        "derivatives_features",
        "macro_features",
        "event_features",
        "onchain_features",
        "execution_features",
        "cache_meta",
    }
    assert calls == {"chip": 1, "macro": 1}


@pytest.mark.asyncio
async def test_market_context_cache_meta_tracks_source_pages_and_freshness(monkeypatch) -> None:
    await shared_query_cache.clear()
    now = datetime.now(UTC)

    async def fake_analyze(self, instrument_id: str, timeframe: str):
        return {
            "evidence_quality": "structure_snapshot",
            "execution_score": 72,
            "execution_label": "ok",
            "components": {"structure_overall": {"overall_bias": "bullish"}},
        }

    async def fake_macro(self, now=None):  # noqa: ANN001
        return SimpleNamespace(
            model_dump=lambda mode="json": {
                "regime_key": "risk_on",
                "operation_bias": "bullish",
                "confidence": "high",
                "event_window_status": "normal",
                "generated_at": "2026-07-01T00:00:00+00:00",
            }
        )

    class _Dashboard:
        snapshot_state = "live"
        data_timestamp = now - timedelta(seconds=30)
        joint_analysis = {
            "derivatives_axes": {
                "key_levels_axis": {
                    "status": "ready",
                    "summary": "关键价位正常",
                    "cache_state": "fresh",
                }
            }
        }

    async def fake_dashboard(*, force=False):  # noqa: ANN001
        return _Dashboard()

    monkeypatch.setattr("app.services.market_context.ChipStructureService.analyze", fake_analyze)
    monkeypatch.setattr(
        "app.services.market_context.MacroOverviewService.build_overview", fake_macro
    )
    monkeypatch.setattr(
        "app.services.market_context.btc_derivatives_live_service.dashboard", fake_dashboard
    )

    builder = MarketContextBuilder(SimpleNamespace())
    try:
        context = await builder.get_context("btc-usdt-perp", "4h")
    finally:
        await shared_query_cache.clear()

    assert context.cache_meta["source"] == "market_context_builder"
    assert set(context.cache_meta["sources"]) >= {"chip_structure", "macro", "btc_derivatives"}
    assert context.cache_meta["cache_state"] in {"fresh", "ready", "degraded", "usable_stale"}
    assert context.cache_meta["source_age_seconds"] is not None
    assert context.data_quality["dependencies"]["chip_structure"]["cache_state"] == "fresh"
    assert context.data_quality["dependencies"]["btc_derivatives"]["cache_state"] == "fresh"


@pytest.mark.asyncio
async def test_market_context_reuses_monitoring_onchain_observations(monkeypatch) -> None:
    await shared_query_cache.clear()
    now = datetime.now(UTC)

    async def fake_analyze(self, instrument_id: str, timeframe: str):
        return {"evidence_quality": "structure_snapshot", "components": {}}

    async def fake_macro(self):
        return SimpleNamespace(model_dump=lambda mode="json": {"confidence": "high"})

    async def fake_dashboard(*, force=False):  # noqa: ANN001
        raise RuntimeError("derivatives unavailable")

    async def forbidden_provider_call(*args, **kwargs):  # noqa: ANN001
        raise AssertionError("strategy market context must not call external onchain providers")

    class Repo:
        async def list_latest_observations_by_key(self, **kwargs):  # noqa: ANN003
            assert kwargs["category"] == "onchain"
            return [
                _observation("defi_total_tvl", observation_ts=now - timedelta(minutes=10)),
                _observation("stablecoin_total_mcap", observation_ts=now - timedelta(minutes=8)),
                _observation("dex_volume_24h", observation_ts=now - timedelta(minutes=6)),
                _observation("protocol_fees_24h", observation_ts=now - timedelta(minutes=4)),
            ]

    monkeypatch.setattr("app.services.market_context.ChipStructureService.analyze", fake_analyze)
    monkeypatch.setattr(
        "app.services.market_context.MacroOverviewService.build_overview", fake_macro
    )
    monkeypatch.setattr(
        "app.services.market_context.btc_derivatives_live_service.dashboard", fake_dashboard
    )
    monkeypatch.setattr(
        "app.services.onchain.providers.defillama.DefiLlamaProvider.fetch_snapshot",
        forbidden_provider_call,
    )

    builder = MarketContextBuilder(Repo())
    try:
        context = await builder.get_context("btc-usdt-perp", "1d")
    finally:
        await shared_query_cache.clear()

    assert context.onchain_features["data_status"] == "fresh"
    assert context.onchain_features["source_page"] == "monitoring/onchain"
    assert context.onchain_features["metrics"]["defi_total_tvl"]["source_provider"] == "defillama"
    assert context.data_quality["dependencies"]["onchain"]["cache_state"] == "fresh"


@pytest.mark.asyncio
async def test_market_context_marks_onchain_upstream_missing_without_provider_call(
    monkeypatch,
) -> None:
    await shared_query_cache.clear()

    async def fake_analyze(self, instrument_id: str, timeframe: str):
        return {"evidence_quality": "structure_snapshot", "components": {}}

    async def fake_macro(self):
        return SimpleNamespace(model_dump=lambda mode="json": {"confidence": "high"})

    async def fake_dashboard(*, force=False):  # noqa: ANN001
        raise RuntimeError("derivatives unavailable")

    async def forbidden_provider_call(*args, **kwargs):  # noqa: ANN001
        raise AssertionError("strategy market context must not call external onchain providers")

    class Repo:
        async def list_latest_observations_by_key(self, **kwargs):  # noqa: ANN003
            return []

    monkeypatch.setattr("app.services.market_context.ChipStructureService.analyze", fake_analyze)
    monkeypatch.setattr(
        "app.services.market_context.MacroOverviewService.build_overview", fake_macro
    )
    monkeypatch.setattr(
        "app.services.market_context.btc_derivatives_live_service.dashboard", fake_dashboard
    )
    monkeypatch.setattr(
        "app.services.onchain.providers.defillama.DefiLlamaProvider.fetch_snapshot",
        forbidden_provider_call,
    )

    builder = MarketContextBuilder(Repo())
    try:
        context = await builder.get_context("btc-usdt-perp", "1d")
    finally:
        await shared_query_cache.clear()

    assert context.onchain_features["data_status"] == "upstream_missing"
    assert context.onchain_features["source_page"] == "monitoring/onchain"
    assert context.onchain_features["missing_inputs"]
    assert context.data_quality["dependencies"]["onchain"]["cache_state"] == "upstream_missing"


@pytest.mark.asyncio
async def test_market_context_returns_low_confidence_on_chip_failure(monkeypatch) -> None:
    """When ChipStructureService.analyze() raises, MarketContextBuilder
    must still return a usable snapshot with degraded chip_structure."""
    from unittest.mock import AsyncMock, patch

    await shared_query_cache.clear()

    async def fake_macro(self):
        return SimpleNamespace(
            model_dump=lambda mode="json": {
                "regime_key": "risk_on",
                "operation_bias": "bullish",
                "confidence": "high",
            }
        )

    async def fake_dashboard(*, force=False):  # noqa: ANN001
        raise RuntimeError("derivatives unavailable")

    monkeypatch.setattr(
        "app.services.market_context.MacroOverviewService.build_overview", fake_macro
    )
    monkeypatch.setattr(
        "app.services.market_context.btc_derivatives_live_service.dashboard", fake_dashboard
    )

    builder = MarketContextBuilder(SimpleNamespace())
    try:
        with patch(
            "app.services.chip_structure.ChipStructureService.analyze",
            new=AsyncMock(side_effect=RuntimeError("chip db error")),
        ):
            snapshot = await builder.get_context("btc-usdt-perp", "1d")
    finally:
        await shared_query_cache.clear()

    assert snapshot is not None
    assert snapshot.chip_structure.get("state") in {"missing", "low_confidence", "error"}
    assert snapshot.freshness_breakdown is not None
    assert "chip_structure" in snapshot.freshness_breakdown


@pytest.mark.asyncio
async def test_market_context_returns_empty_macro_on_failure(monkeypatch) -> None:
    from unittest.mock import AsyncMock, patch

    await shared_query_cache.clear()

    async def fake_analyze(self, instrument_id: str, timeframe: str):
        return {"evidence_quality": "structure_snapshot", "components": {}}

    async def fake_dashboard(*, force=False):  # noqa: ANN001
        raise RuntimeError("derivatives unavailable")

    monkeypatch.setattr(
        "app.services.market_context.ChipStructureService.analyze", fake_analyze
    )
    monkeypatch.setattr(
        "app.services.market_context.btc_derivatives_live_service.dashboard", fake_dashboard
    )

    builder = MarketContextBuilder(SimpleNamespace())
    try:
        with patch(
            "app.services.market_context.MacroOverviewService.build_overview",
            new=AsyncMock(side_effect=RuntimeError("macro db error")),
        ):
            snapshot = await builder.get_context("btc-usdt-perp", "1d")
    finally:
        await shared_query_cache.clear()

    assert snapshot is not None
    assert snapshot.macro_features.get("regime_key") in {None, "unknown"}
    assert "macro" in snapshot.freshness_breakdown
    assert snapshot.freshness_breakdown["macro"]["cache_state"] == "missing"


@pytest.mark.asyncio
async def test_market_context_returns_missing_onchain_on_failure(monkeypatch) -> None:
    from unittest.mock import AsyncMock, patch

    await shared_query_cache.clear()

    async def fake_analyze(self, instrument_id: str, timeframe: str):
        return {"evidence_quality": "structure_snapshot", "components": {}}

    async def fake_macro(self):
        return SimpleNamespace(
            model_dump=lambda mode="json": {
                "regime_key": "risk_on",
                "confidence": "high",
            }
        )

    async def fake_dashboard(*, force=False):  # noqa: ANN001
        raise RuntimeError("derivatives unavailable")

    monkeypatch.setattr(
        "app.services.market_context.ChipStructureService.analyze", fake_analyze
    )
    monkeypatch.setattr(
        "app.services.market_context.MacroOverviewService.build_overview", fake_macro
    )
    monkeypatch.setattr(
        "app.services.market_context.btc_derivatives_live_service.dashboard", fake_dashboard
    )

    builder = MarketContextBuilder(SimpleNamespace())
    try:
        with patch(
            "app.services.onchain.feature_engine.OnchainFeatureEngine.build",
            new=AsyncMock(side_effect=RuntimeError("onchain db error")),
        ):
            snapshot = await builder.get_context("btc-usdt-perp", "1d")
    finally:
        await shared_query_cache.clear()

    assert snapshot is not None
    assert snapshot.onchain_features.get("data_status") in {"missing", None, "error"}


@pytest.mark.asyncio
async def test_market_context_marks_stale_onchain_observations(monkeypatch) -> None:
    await shared_query_cache.clear()
    stale_ts = datetime(2026, 6, 28, tzinfo=UTC)

    async def fake_analyze(self, instrument_id: str, timeframe: str):
        return {"evidence_quality": "structure_snapshot", "components": {}}

    async def fake_macro(self):
        return SimpleNamespace(model_dump=lambda mode="json": {"confidence": "high"})

    async def fake_dashboard(*, force=False):  # noqa: ANN001
        raise RuntimeError("derivatives unavailable")

    class Repo:
        async def list_latest_observations_by_key(self, **kwargs):  # noqa: ANN003
            return [_observation("defi_total_tvl", observation_ts=stale_ts)]

    monkeypatch.setattr("app.services.market_context.ChipStructureService.analyze", fake_analyze)
    monkeypatch.setattr(
        "app.services.market_context.MacroOverviewService.build_overview", fake_macro
    )
    monkeypatch.setattr(
        "app.services.market_context.btc_derivatives_live_service.dashboard", fake_dashboard
    )

    builder = MarketContextBuilder(Repo())
    try:
        context = await builder.get_context("btc-usdt-perp", "1d")
    finally:
        await shared_query_cache.clear()

    assert context.onchain_features["data_status"] == "stale"
    assert context.onchain_features["source_age_seconds"] is not None
    assert context.data_quality["dependencies"]["onchain"]["cache_state"] == "stale"
