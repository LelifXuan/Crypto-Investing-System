"""Tests for the ETF history NAV service + adapter.

The tests cover:
- Adapter payload parsing (kline CSV row → EtfKlinePoint)
- Snapshot serialization round-trip
- Incremental fetch (cold start full backfill, then partial window extension)
- Cache file persistence + corruption recovery
- Provider failure path (stale-but-readable cache is preserved)
"""

from __future__ import annotations

import json
from datetime import date, datetime, timezone
from pathlib import Path

import pytest

from app.integrations.cn_etf_history import (
    EastmoneyFundKlineClient,
    EtfHistoryFetchResult,
    EtfKlinePoint,
    _parse_kline_line,
)
from app.services.ashare_etf_history import (
    EtfHistoryService,
    EtfHistorySnapshot,
    _merge_points,
    _snapshot_from_dict,
    cache_dir,
    cache_path_for_code,
)

UTC = timezone.utc


# --- pure adapter parsing ----------------------------------------------


def test_parse_kline_line_happy_path() -> None:
    point = _parse_kline_line("2024-08-01,0.960,0.964,0.975,0.960,4883,472704.000,1.56")
    assert point is not None
    assert point.trade_date == date(2024, 8, 1)
    assert point.open == 0.960
    assert point.close == 0.964
    assert point.high == 0.975
    assert point.low == 0.960
    assert point.volume == 4883
    assert point.amount == 472704.0
    assert point.amplitude_pct == 1.56


def test_parse_kline_line_short_row_returns_none() -> None:
    assert _parse_kline_line("2024-08-01,0.960") is None


def test_parse_kline_line_bad_date_returns_none() -> None:
    assert _parse_kline_line("not-a-date,0.960,0.964,0.975,0.960,4883,472704.000,1.56") is None


def test_parse_kline_line_missing_close_returns_none() -> None:
    assert _parse_kline_line("2024-08-01,0.960,,0.975,0.960,4883,472704.000,1.56") is None


def test_parse_payload_with_empty_klines() -> None:
    points, name, total = EastmoneyFundKlineClient._parse_payload(
        {"data": {"name": "X", "dktotal": 0, "klines": []}}
    )
    assert points == []
    assert name == "X"
    assert total == 0


# --- snapshot dict round-trip ------------------------------------------


def _make_point(d: date, close: float) -> EtfKlinePoint:
    return EtfKlinePoint(
        trade_date=d,
        open=close,
        close=close,
        high=close,
        low=close,
        volume=1000.0,
        amount=close * 1000.0,
        amplitude_pct=0.0,
    )


def test_snapshot_round_trip_preserves_fields() -> None:
    today = date(2026, 8, 4)
    snapshot_dict = {
        "code": "563010",
        "market": "SH",
        "secid": "1.563010",
        "name": "电信ETF",
        "source": "eastmoney_kline",
        "coverage_start": "2024-01-02",
        "coverage_end": "2026-08-04",
        "last_updated": "2026-08-04T00:00:00+00:00",
        "points": [
            {
                "date": "2024-01-02",
                "open": 1.0,
                "close": 1.05,
                "high": 1.1,
                "low": 0.99,
                "volume": 100,
                "amount": 105.0,
                "amplitude_pct": 0.5,
            }
        ],
    }
    snap = _snapshot_from_dict(snapshot_dict)
    assert snap.code == "563010"
    assert snap.coverage_start == date(2024, 1, 2)
    assert snap.coverage_end == today
    assert snap.points[0].close == 1.05
    # Re-serialize
    out = {
        "code": snap.code,
        "market": snap.market,
        "secid": snap.secid,
        "name": snap.name,
        "source": snap.source,
        "coverage_start": snap.coverage_start.isoformat(),
        "coverage_end": snap.coverage_end.isoformat(),
        "last_updated": snap.last_updated.isoformat(),
        "points": [p.to_dict() for p in snap.points],
    }
    assert out == snapshot_dict


# --- merge helper ------------------------------------------------------


def test_merge_points_combines_existing_and_new() -> None:
    today = datetime(2026, 8, 4, tzinfo=UTC)
    existing = EtfHistorySnapshot(
        code="563010",
        market="SH",
        secid="1.563010",
        name="电信ETF",
        source="eastmoney_kline",
        coverage_start=date(2026, 8, 1),
        coverage_end=date(2026, 8, 3),
        last_updated=today,
        points=[
            _make_point(date(2026, 8, 1), 1.0),
            _make_point(date(2026, 8, 2), 1.01),
            _make_point(date(2026, 8, 3), 1.02),
        ],
    )
    latest = EtfHistoryFetchResult(
        code="563010",
        market="SH",
        secid="1.563010",
        name="电信ETF",
        total_bars=4,
        points=[
            _make_point(date(2026, 8, 3), 1.025),  # overrides old
            _make_point(date(2026, 8, 4), 1.03),
        ],
        fetched_at=today,
    )
    merged = _merge_points(existing, latest)
    assert merged.coverage_start == date(2026, 8, 1)
    assert merged.coverage_end == date(2026, 8, 4)
    assert len(merged.points) == 4
    # Overlapping date gets the fresh value (1.025), not the old (1.02).
    on_aug3 = next(p for p in merged.points if p.trade_date == date(2026, 8, 3))
    assert on_aug3.close == 1.025


def test_merge_points_handles_empty_existing() -> None:
    today = datetime(2026, 8, 4, tzinfo=UTC)
    latest = EtfHistoryFetchResult(
        code="563010",
        market="SH",
        secid="1.563010",
        name="电信ETF",
        total_bars=2,
        points=[
            _make_point(date(2026, 8, 1), 1.0),
            _make_point(date(2026, 8, 2), 1.01),
        ],
        fetched_at=today,
    )
    merged = _merge_points(None, latest)
    assert len(merged.points) == 2
    assert merged.coverage_start == date(2026, 8, 1)
    assert merged.coverage_end == date(2026, 8, 2)


# --- cache persistence + service layer ---------------------------------


class _StubClient:
    """Minimal stub replacing ``EastmoneyFundKlineClient`` for unit tests."""

    provider_id = "stub_kline"

    def __init__(self, responses: dict[str, EtfHistoryFetchResult]) -> None:
        self.responses = responses
        self.calls: list[tuple[str, date, date]] = []

    async def fetch_history(self, code: str, *, beg: date, end: date) -> EtfHistoryFetchResult:
        self.calls.append((code, beg, end))
        if code not in self.responses:
            raise RuntimeError(f"stub_no_response:{code}")
        return self.responses[code]


@pytest.mark.asyncio
async def test_get_snapshot_full_backfill_on_cold_start(tmp_path: Path, monkeypatch) -> None:
    import app.services.ashare_etf_history as history_module

    # Redirect cache to a temp dir so we don't touch the user's runtime.
    def _tmp_cache_dir() -> Path:
        target = tmp_path / "fund_history"
        target.mkdir(parents=True, exist_ok=True)
        return target

    monkeypatch.setattr(history_module, "cache_dir", _tmp_cache_dir)

    today = datetime(2026, 8, 4, tzinfo=UTC)
    stub = _StubClient(
        {
            "563010": EtfHistoryFetchResult(
                code="563010",
                market="SH",
                secid="1.563010",
                name="电信ETF",
                total_bars=3,
                points=[
                    _make_point(date(2026, 8, 1), 1.00),
                    _make_point(date(2026, 8, 2), 1.01),
                    _make_point(date(2026, 8, 4), 1.03),
                ],
                fetched_at=today,
            )
        }
    )
    service = EtfHistoryService(client=stub)

    snap = await service.get_snapshot(
        "563010", from_date=date(2026, 8, 1), to_date=date(2026, 8, 4)
    )

    assert len(snap.points) == 3
    assert snap.code == "563010"
    assert snap.coverage_start == date(2026, 8, 1)
    assert snap.coverage_end == date(2026, 8, 4)
    assert stub.calls and stub.calls[0][0] == "563010"
    # Cache file must exist after fetch.
    assert cache_path_for_code("563010").exists()


@pytest.mark.asyncio
async def test_get_snapshot_skips_fetch_when_cached_covers_window(
    tmp_path: Path, monkeypatch
) -> None:
    import app.services.ashare_etf_history as history_module

    def _tmp_cache_dir() -> Path:
        target = tmp_path / "fund_history"
        target.mkdir(parents=True, exist_ok=True)
        return target

    monkeypatch.setattr(history_module, "cache_dir", _tmp_cache_dir)

    today = datetime(2026, 8, 4, tzinfo=UTC)
    seed = EtfHistorySnapshot(
        code="563010",
        market="SH",
        secid="1.563010",
        name="电信ETF",
        source="eastmoney_kline",
        coverage_start=date(2026, 8, 1),
        coverage_end=date(2026, 8, 4),
        last_updated=today,
        points=[
            _make_point(date(2026, 8, 1), 1.00),
            _make_point(date(2026, 8, 4), 1.03),
        ],
    )
    seed_path = cache_path_for_code("563010")
    seed_path.write_text(
        json.dumps(
            {
                "code": seed.code,
                "market": seed.market,
                "secid": seed.secid,
                "name": seed.name,
                "source": seed.source,
                "coverage_start": seed.coverage_start.isoformat(),
                "coverage_end": seed.coverage_end.isoformat(),
                "last_updated": seed.last_updated.isoformat(),
                "points": [p.to_dict() for p in seed.points],
            }
        ),
        encoding="utf-8",
    )

    stub = _StubClient(responses={})
    service = EtfHistoryService(client=stub)

    snap = await service.get_snapshot(
        "563010",
        from_date=date(2026, 8, 1),
        to_date=date(2026, 8, 4),
    )
    assert len(snap.points) == 2
    assert stub.calls == []  # no upstream call when cache covers window


@pytest.mark.asyncio
async def test_provider_failure_keeps_stale_cache(tmp_path: Path, monkeypatch) -> None:
    """If upstream fails after we've cached, we must return cached data, not raise."""

    import app.services.ashare_etf_history as history_module

    def _tmp_cache_dir() -> Path:
        target = tmp_path / "fund_history"
        target.mkdir(parents=True, exist_ok=True)
        return target

    monkeypatch.setattr(history_module, "cache_dir", _tmp_cache_dir)

    today = datetime(2026, 8, 4, tzinfo=UTC)
    seed = EtfHistorySnapshot(
        code="563010",
        market="SH",
        secid="1.563010",
        name="电信ETF",
        source="eastmoney_kline",
        coverage_start=date(2026, 8, 1),
        coverage_end=date(2026, 8, 3),
        last_updated=today,
        points=[
            _make_point(date(2026, 8, 1), 1.00),
            _make_point(date(2026, 8, 2), 1.01),
            _make_point(date(2026, 8, 3), 1.02),
        ],
    )
    seed_path = cache_path_for_code("563010")
    seed_path.write_text(
        json.dumps(
            {
                "code": seed.code,
                "market": seed.market,
                "secid": seed.secid,
                "name": seed.name,
                "source": seed.source,
                "coverage_start": seed.coverage_start.isoformat(),
                "coverage_end": seed.coverage_end.isoformat(),
                "last_updated": seed.last_updated.isoformat(),
                "points": [p.to_dict() for p in seed.points],
            }
        ),
        encoding="utf-8",
    )

    class _FailingClient:
        provider_id = "failing"

        async def fetch_history(self, code: str, *, beg: date, end: date) -> EtfHistoryFetchResult:
            raise RuntimeError("upstream_down")

    service = EtfHistoryService(client=_FailingClient())  # type: ignore[arg-type]
    # Window extends past coverage_end → service tries to fetch → fails.
    snap = await service.get_snapshot(
        "563010", from_date=date(2026, 8, 1), to_date=date(2026, 8, 5)
    )
    # Stale cache still served; no exception.
    assert snap.code == "563010"
    assert snap.coverage_end == date(2026, 8, 3)
    assert len(snap.points) == 3


@pytest.mark.asyncio
async def test_corrupt_cache_triggers_reload(tmp_path: Path, monkeypatch) -> None:
    import app.services.ashare_etf_history as history_module

    def _tmp_cache_dir() -> Path:
        target = tmp_path / "fund_history"
        target.mkdir(parents=True, exist_ok=True)
        return target

    monkeypatch.setattr(history_module, "cache_dir", _tmp_cache_dir)

    cache_path_for_code("563010").write_text("{not-json", encoding="utf-8")

    today = datetime(2026, 8, 4, tzinfo=UTC)
    stub = _StubClient(
        {
            "563010": EtfHistoryFetchResult(
                code="563010",
                market="SH",
                secid="1.563010",
                name="电信ETF",
                total_bars=1,
                points=[_make_point(date(2026, 8, 4), 1.0)],
                fetched_at=today,
            )
        }
    )
    service = EtfHistoryService(client=stub)
    snap = await service.get_snapshot("563010")
    assert len(snap.points) == 1


def test_cache_dir_creates_subdir(tmp_path: Path, monkeypatch) -> None:
    import app.services.ashare_etf_history as history_module

    target_dir = tmp_path / "fund_history"

    def _fake_cache_dir() -> Path:
        target_dir.mkdir(parents=True, exist_ok=True)
        return target_dir

    monkeypatch.setattr(history_module, "cache_dir", _fake_cache_dir)
    result = cache_dir()
    assert result.exists()
    assert result.name == "fund_history"