"""Acceptance tests for monitoring dashboard cache refresh behavior.

The audit found that ``get_bundle`` logged a "refresh is needed"
message but never actually called ``refresh_bundle``, so the caller
was stuck with the stale payload. The user observed this live: the
JSON returned ``status: "stale"``, ``cache_state: "stale"`` and
``refreshed: false`` even when the API caller asked for a refresh.

Current contract: when ``allow_refresh`` is True and the cached bundle is
missing / error / updating / effectively empty, ``get_bundle`` calls
``refresh_bundle``. A stale but displayable payload is returned
immediately so the first screen does not block on a cold refresh.
"""

from __future__ import annotations

import asyncio
from datetime import UTC, datetime
from types import SimpleNamespace

from app.services.monitoring_dashboard import MonitoringDashboardService


def _fresh_cache(payload: dict, cache_state: str = "fresh"):
    # expires_at is set well in the future so is_page_cache_fresh returns
    # True regardless of when the test runs (the system clock advances).
    return SimpleNamespace(
        payload_json=payload,
        snapshot_at=datetime(2026, 6, 1, tzinfo=UTC),
        data_ts=datetime(2026, 6, 1, tzinfo=UTC),
        source_updated_at=datetime(2026, 6, 1, tzinfo=UTC),
        expires_at=datetime(2099, 1, 1, tzinfo=UTC),
        source_version="v3",
        cost_ms=12,
        cache_state=cache_state,
        status="ready",
    )


def _stale_cache(payload: dict | None = None):
    return _fresh_cache(payload or {}, cache_state="stale")


class _Repo:
    """Tracks which cache keys the service asks for, lets the test
    flip the cache_state on subsequent reads (e.g. stale → fresh
    after a refresh).
    """

    def __init__(self, initial: dict | None = None) -> None:
        self.snapshots: dict[str, SimpleNamespace] = initial or {}
        self.reads: list[str] = []
        self.writes: list[dict] = []
        self.refresh_called = False

    async def get_page_snapshot_cache(self, cache_key: str):
        self.reads.append(cache_key)
        return self.snapshots.get(cache_key)

    async def upsert_page_snapshot_cache(self, **kwargs):
        self.writes.append(kwargs)
        # Simulate a fresh write by returning a fresh cache for the
        # monitoring key.
        fresh = _fresh_cache(kwargs.get("payload_json") or {})
        self.snapshots[kwargs["cache_key"]] = fresh
        return fresh

    async def get_computed_dataset_cache(self, cache_key: str):  # noqa: D401
        return None

    async def upsert_computed_dataset_cache(self, **kwargs):
        return None

    async def list_indicator_observations(self, **_kwargs):
        return []

    async def list_alert_events(self, *_args, **_kwargs):
        return []

    async def list_monitoring_policies(self, *_args, **_kwargs):
        return []

    async def add_indicator_value(self, *_args, **_kwargs):
        return None

    async def get_latest_structure_snapshot(self, *_args, **_kwargs):
        return None

    async def list_instruments(self):
        return []


def _monitoring_key() -> str:
    from app.services.cache_registry import monitoring_dashboard_cache_key
    return monitoring_dashboard_cache_key("btc-usdt-perp", "1d")


def test_get_bundle_with_empty_stale_cache_and_allow_refresh_calls_refresh() -> None:
    repo = _Repo(
        initial={_monitoring_key(): _stale_cache()}
    )
    service = MonitoringDashboardService(repository=repo)  # type: ignore[arg-type]

    result = asyncio.run(
        service.get_bundle("btc-usdt-perp", "1d", allow_refresh=True)
    )

    assert repo.refresh_called or repo.writes, (
        "refresh_bundle should have written a fresh cache when stale + allow_refresh"
    )
    # The returned bundle should reflect the fresh cache_state, not the
    # original "stale".
    assert result.cache_state == "fresh"
    assert result.refreshed is True


def test_get_bundle_with_displayable_stale_cache_returns_immediately() -> None:
    payload = {
        "macro_overview": {
            "total_score": 45,
            "score_band": "温和偏紧",
            "growth_score": 50,
            "inflation_score": 40,
            "policy_score": 45,
            "liquidity_score": 50,
            "regime_summary": "宏观环境温和偏紧。",
            "regime_label_cn": "温和偏紧",
            "regime_key": "mild_tightening",
        },
        "technical_observations": [
            {
                "observation_id": "test:ema_20",
                "indicator_key": "ema_20",
                "category": "technical",
                "instrument_id": "btc-usdt-perp",
                "timeframe": "1d",
                "observation_ts": "2099-01-01T00:00:00Z",
                "value_num": 100,
                "value_json": {},
                "source_provider": "test",
                "is_preliminary": False,
                "quality_score": 95,
            },
        ],
    }
    repo = _Repo(initial={_monitoring_key(): _stale_cache(payload)})
    service = MonitoringDashboardService(repository=repo)  # type: ignore[arg-type]

    result = asyncio.run(service.get_bundle("btc-usdt-perp", "1d", allow_refresh=True))

    assert not repo.writes
    assert result.cache_state == "stale"
    assert result.refreshed is False
    assert result.technical_indicator_count == 1
    assert result.status_message


def test_get_bundle_with_fresh_cache_skips_refresh() -> None:
    """A fresh cache with a non-empty payload is returned as-is; the
    refresh path is skipped because the cache is already up to date.
    """
    payload = {
        "macro_overview": {
            "total_score": 45,
            "score_band": "温和偏紧",
            "growth_score": 50,
            "inflation_score": 40,
            "policy_score": 45,
            "liquidity_score": 50,
            "regime_summary": "宏观环境温和偏紧。",
            "regime_label_cn": "温和偏紧",
            "regime_key": "mild_tightening",
        },
        "technical_observations": [],
        "structure": {},
        "terminal_summary": None,
    }
    repo = _Repo(
        initial={_monitoring_key(): _fresh_cache(payload, cache_state="fresh")}
    )
    service = MonitoringDashboardService(repository=repo)  # type: ignore[arg-type]

    result = asyncio.run(
        service.get_bundle("btc-usdt-perp", "1d", allow_refresh=True)
    )

    # Fresh cache with real data → no refresh writes.
    assert not repo.writes
    assert result.refreshed is False
    assert result.cache_state == "fresh"


def test_get_bundle_with_stale_cache_and_no_allow_refresh_returns_stale() -> None:
    repo = _Repo(
        initial={_monitoring_key(): _stale_cache()}
    )
    service = MonitoringDashboardService(repository=repo)  # type: ignore[arg-type]

    result = asyncio.run(
        service.get_bundle("btc-usdt-perp", "1d", allow_refresh=False)
    )

    # No refresh writes.
    assert not repo.writes
    # The user gets the stale snapshot with the warning message.
    assert result.cache_state == "stale"
    assert result.status_message


def test_get_bundle_reports_final_technical_indicator_count() -> None:
    payload = {
        "macro_overview": None,
        "technical_observations": [
            {
                "observation_id": "test:ema_20",
                "indicator_key": "ema_20",
                "category": "technical",
                "instrument_id": "btc-usdt-perp",
                "timeframe": "1d",
                "observation_ts": "2099-01-01T00:00:00Z",
                "value_num": 100,
                "value_json": {},
                "source_provider": "test",
                "is_preliminary": False,
                "quality_score": 95,
            },
            {
                "observation_id": "test:rsi_14",
                "indicator_key": "rsi_14",
                "category": "technical",
                "instrument_id": "btc-usdt-perp",
                "timeframe": "1d",
                "observation_ts": "2099-01-01T00:00:00Z",
                "value_num": 24,
                "value_json": {},
                "source_provider": "test",
                "is_preliminary": False,
                "quality_score": 95,
            },
        ],
    }
    repo = _Repo(initial={_monitoring_key(): _fresh_cache(payload, cache_state="fresh")})
    service = MonitoringDashboardService(repository=repo)  # type: ignore[arg-type]

    result = asyncio.run(service.get_bundle("btc-usdt-perp", "1d", allow_refresh=False))

    assert result.technical_indicator_count == 2
    assert result.technical_indicator_count == len(result.technical_observations)


def test_get_bundle_falls_back_to_stale_when_refresh_fails() -> None:
    """If refresh_bundle raises, get_bundle still returns the cached
    payload so the user does not get a 500. The warning is logged.
    """
    repo = _Repo(
        initial={_monitoring_key(): _stale_cache()}
    )
    service = MonitoringDashboardService(repository=repo)  # type: ignore[arg-type]

    # Make refresh_bundle raise (simulate a DB outage). We patch the
    # bound method on the instance.
    async def boom(*_args, **_kwargs):
        raise RuntimeError("db down")

    service.refresh_bundle = boom  # type: ignore[method-assign]

    result = asyncio.run(
        service.get_bundle("btc-usdt-perp", "1d", allow_refresh=True)
    )

    # The fallback path returns the cached payload.
    assert result.cache_state == "stale"
    assert result.refreshed is False


def test_get_bundle_triggers_refresh_when_cache_missing() -> None:
    """When the cache is missing entirely, get_bundle must still
    trigger a refresh so the first user request does not see an
    empty snapshot.
    """
    repo = _Repo(initial={})  # no cache at all
    service = MonitoringDashboardService(repository=repo)  # type: ignore[arg-type]

    result = asyncio.run(
        service.get_bundle("btc-usdt-perp", "1d", allow_refresh=True)
    )

    assert repo.writes, "refresh_bundle should have run when cache is missing"
    assert result.refreshed is True
