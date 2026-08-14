"""Acceptance tests for T07: monitoring dashboard stops overwriting caller inputs.

The audit found that ``MonitoringDashboardService.get_bundle`` and
``refresh_bundle`` were unconditionally resetting the caller's instrument
and timeframe to the hard-coded ``MONITORING_TECH_INSTRUMENT_ID`` /
``MONITORING_TECH_TIMEFRAME`` constants. A 4h ETH dashboard request was
silently redirected to btc/1d. The fix is to honor the caller's
arguments; the constants are kept as a default fallback for the API
layer and the indicator scheduler.
"""

from __future__ import annotations

from datetime import UTC, datetime
from types import SimpleNamespace
from typing import Any

import pytest

from app.services.monitoring_dashboard import (
    MONITORING_TECH_INSTRUMENT_ID,
    MONITORING_TECH_TIMEFRAME,
    MonitoringDashboardService,
)


def _fake_cache(payload: dict[str, Any] | None = None) -> SimpleNamespace:
    return SimpleNamespace(
        payload_json=payload or {},
        snapshot_at=datetime(2026, 6, 1, tzinfo=UTC),
        data_ts=datetime(2026, 6, 1, tzinfo=UTC),
        source_updated_at=datetime(2026, 6, 1, tzinfo=UTC),
        expires_at=datetime(2026, 6, 2, tzinfo=UTC),
        source_version="v3",
        cost_ms=12,
        cache_state="fresh",
        status="ready",
    )


class _Repo:
    """Records the cache keys the service asks for, returns empty otherwise."""

    def __init__(self, snapshot_by_key: dict[str, Any] | None = None) -> None:
        self.snapshot_by_key = snapshot_by_key or {}
        self.requests: list[str] = []

    async def get_page_snapshot_cache(self, cache_key: str):
        self.requests.append(cache_key)
        payload = self.snapshot_by_key.get(cache_key)
        if payload is None:
            return None
        return _fake_cache(payload)


@pytest.mark.asyncio
async def test_get_bundle_honors_eth_instrument() -> None:
    repo = _Repo(
        snapshot_by_key={
            "monitoring_dashboard:eth-usdt-perp:4h:v3": _fake_cache({}).payload_json
        }
    )
    service = MonitoringDashboardService(repository=repo)  # type: ignore[arg-type]
    bundle = await service.get_bundle("eth-usdt-perp", "4h", allow_refresh=False)
    assert bundle.instrument_id == "eth-usdt-perp"
    assert bundle.timeframe == "4h"
    # Confirm the service asked for the eth/4h key, NOT the btc/1d key.
    assert any(
        key.startswith("monitoring_dashboard:eth-usdt-perp:4h:")
        for key in repo.requests
    )
    assert not any(
        key.startswith("monitoring_dashboard:btc-usdt-perp:1d:")
        for key in repo.requests
    )


@pytest.mark.asyncio
async def test_get_bundle_honors_4h_timeframe() -> None:
    repo = _Repo()
    service = MonitoringDashboardService(repository=repo)  # type: ignore[arg-type]
    bundle = await service.get_bundle("btc-usdt-perp", "4h", allow_refresh=False)
    assert bundle.instrument_id == "btc-usdt-perp"
    assert bundle.timeframe == "4h"


@pytest.mark.asyncio
async def test_get_bundle_falls_back_to_constants_when_empty() -> None:
    repo = _Repo()
    service = MonitoringDashboardService(repository=repo)  # type: ignore[arg-type]
    bundle = await service.get_bundle("", "", allow_refresh=False)
    assert bundle.instrument_id == MONITORING_TECH_INSTRUMENT_ID
    assert bundle.timeframe == MONITORING_TECH_TIMEFRAME


@pytest.mark.asyncio
async def test_get_bundle_uses_defaults_when_explicit_none_passed() -> None:
    repo = _Repo()
    service = MonitoringDashboardService(repository=repo)  # type: ignore[arg-type]
    # Python converts no-arg call to TypeError; verify the constant fallback
    # by calling with empty string and confirming the bundle uses defaults.
    bundle = await service.get_bundle("", "", allow_refresh=False)
    assert bundle.instrument_id == "btc-usdt-perp"
    assert bundle.timeframe == "1d"


@pytest.mark.asyncio
async def test_refresh_bundle_honors_eth_instrument() -> None:
    """refresh_bundle must propagate eth/4h through to its inner loaders."""

    repo = _Repo()
    service = MonitoringDashboardService(repository=repo)  # type: ignore[arg-type]

    observed: dict[str, str] = {}

    async def fake_load_cached_strategy_bundle(instrument_id, timeframe):
        observed["strategy"] = f"{instrument_id}:{timeframe}"
        return {}

    async def fake_load_cached_alerts_bundle(instrument_id, timeframe):
        observed["alerts"] = f"{instrument_id}:{timeframe}"
        return {}

    async def fake_load_cached_analysis_timeframes(instrument_id):
        observed["analysis"] = instrument_id
        return {}

    async def fake_technical_observations_from_analysis_bundle(
        instrument_id, timeframe, _now
    ):
        observed["technical"] = f"{instrument_id}:{timeframe}"
        return []

    async def fake_macro_overview():
        return None

    async def fake_cross_asset():
        return []

    async def fake_data_source_status():
        return {}

    async def fake_category_is_stale(_category):
        return False

    async def fake_persist(*_args, **_kwargs):
        return None

    async def fake_upsert_page_snapshot_cache(*_args, **_kwargs):
        return _fake_cache({})

    service._load_cached_strategy_bundle = fake_load_cached_strategy_bundle  # type: ignore[method-assign]  # noqa: SLF001
    service._load_cached_alerts_bundle = fake_load_cached_alerts_bundle  # type: ignore[method-assign]  # noqa: SLF001
    service._load_cached_analysis_timeframes = fake_load_cached_analysis_timeframes  # type: ignore[method-assign]  # noqa: SLF001
    service._technical_observations_from_analysis_bundle = (  # type: ignore[method-assign]  # noqa: SLF001
        fake_technical_observations_from_analysis_bundle
    )
    service._macro_overview_payload = fake_macro_overview  # type: ignore[method-assign]
    service._cross_asset_snapshot = fake_cross_asset  # type: ignore[method-assign]
    service._data_source_status = fake_data_source_status  # type: ignore[method-assign]
    service._category_is_stale = fake_category_is_stale  # type: ignore[method-assign]
    service._persist_decision_brief_snapshot = fake_persist  # type: ignore[method-assign]
    service._persist_bundle_cache = fake_persist  # type: ignore[method-assign]

    repo.upsert_page_snapshot_cache = fake_upsert_page_snapshot_cache  # type: ignore[attr-defined]

    async def fake_list_indicator_observations(*_args, **_kwargs):
        return []

    async def fake_list_alert_events(*_args, **_kwargs):
        return []

    repo.list_indicator_observations = fake_list_indicator_observations  # type: ignore[attr-defined]
    repo.list_alert_events = fake_list_alert_events  # type: ignore[attr-defined]

    bundle = await service.refresh_bundle("eth-usdt-perp", "4h")
    assert bundle.instrument_id == "eth-usdt-perp"
    assert bundle.timeframe == "4h"
    assert observed.get("strategy") == "eth-usdt-perp:4h", observed
    assert observed.get("alerts") == "eth-usdt-perp:4h", observed
    assert observed.get("analysis") == "eth-usdt-perp", observed
    assert observed.get("technical") == "eth-usdt-perp:4h", observed


def test_constants_are_still_exported_for_api_default() -> None:
    """The default constants are still the right defaults at the API layer."""
    assert MONITORING_TECH_INSTRUMENT_ID == "btc-usdt-perp"
    assert MONITORING_TECH_TIMEFRAME == "1d"
