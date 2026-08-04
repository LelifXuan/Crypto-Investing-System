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

import httpx  # noqa: F401  # used in forward-ref type hints below
import pytest

from app.integrations.cn_etf_history import (
    EastmoneyFundKlineClient,
    EtfHistoryFetchResult,
    EtfKlinePoint,
    SinaFundKlineClient,
    _parse_kline_line,
    _parse_sina_payload,
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


# --- Sina Finance adapter parsing --------------------------------------


def test_parse_sina_payload_happy_path() -> None:
    payload = [
        {"day": "2024-08-01", "open": "0.960", "close": "0.964",
         "high": "0.975", "low": "0.960", "volume": "4883"},
        {"day": "2024-08-02", "open": "0.970", "close": "0.980",
         "high": "0.985", "low": "0.965", "volume": "5021"},
    ]
    points = _parse_sina_payload(payload)
    assert len(points) == 2
    assert points[0].trade_date == date(2024, 8, 1)
    assert points[0].close == 0.964
    assert points[0].volume == 4883
    assert points[0].amount is None  # Sina doesn't provide amount
    assert points[0].amplitude_pct is None
    # Sina returns most-recent first; parser must sort ascending.
    assert points[0].trade_date < points[1].trade_date


def test_parse_sina_payload_skips_bad_rows() -> None:
    payload = [
        {"day": "2024-08-01", "close": "1.0"},  # happy
        {"day": "garbage", "close": "1.0"},     # bad date
        {"day": "2024-08-02", "close": None},   # missing close
        {"day": "2024-08-03"},                   # no close
        "not a dict",                            # wrong shape
    ]
    points = _parse_sina_payload(payload)
    assert len(points) == 1
    assert points[0].trade_date == date(2024, 8, 1)


def test_parse_sina_payload_empty_input() -> None:
    assert _parse_sina_payload([]) == []
    assert _parse_sina_payload(None) == []  # type: ignore[arg-type]
    assert _parse_sina_payload({"oops": 1}) == []  # wrong shape


# --- Sina client end-to-end (with httpx transport patched) -------------


@pytest.mark.asyncio
async def test_sina_client_parses_httpx_json(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """SinaFundKlineClient parses httpx Response JSON without a real HTTP call."""
    import httpx

    sample_payload = [
        {"day": "2024-08-01", "open": "1.0", "close": "1.05",
         "high": "1.06", "low": "0.99", "volume": "100"},
        {"day": "2024-08-02", "open": "1.05", "close": "1.07",
         "high": "1.08", "low": "1.04", "volume": "120"},
    ]

    class _FakeClient:
        def __init__(self, source_key: str = "x", **kwargs) -> None:
            pass

        async def __aenter__(self) -> "_FakeClient":
            return self

        async def __aexit__(self, *args) -> None:
            pass

        async def get(self, url: str, params: dict[str, str]) -> httpx.Response:
            request = httpx.Request("GET", url, params=params)
            return httpx.Response(200, json=sample_payload, request=request)

    monkeypatch.setattr(
        "app.integrations.cn_etf_history.client_for_source", _FakeClient
    )
    client = SinaFundKlineClient()
    result = await client.fetch_history("561560")
    assert result.code == "561560"
    assert result.market == "SH"
    assert len(result.points) == 2
    assert result.points[0].trade_date == date(2024, 8, 1)
    assert result.points[1].close == 1.07


@pytest.mark.asyncio
async def test_sina_client_uses_sz_prefix_for_sz_codes(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """Verify SZ ETFs use sz159xxx prefix, not sh."""
    captured: dict[str, str] = {}

    class _FakeClient:
        def __init__(self, source_key: str = "x", **kwargs) -> None:
            pass

        async def __aenter__(self) -> "_FakeClient":
            return self

        async def __aexit__(self, *args) -> None:
            pass

        async def get(self, url: str, params: dict[str, str]) -> httpx.Response:
            captured["symbol"] = params["symbol"]
            request = httpx.Request("GET", url, params=params)
            return httpx.Response(200, json=[], request=request)

    monkeypatch.setattr(
        "app.integrations.cn_etf_history.client_for_source", _FakeClient
    )
    client = SinaFundKlineClient()
    with pytest.raises(RuntimeError):
        await client.fetch_history("159201")
    assert captured["symbol"] == "sz159201"


# --- Eastmoney → Sina chain fallback ------------------------------------


@pytest.mark.asyncio
async def test_eastmoney_falls_through_to_sina_when_all_urls_fail(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """When every Eastmoney URL fails, the chain falls through to Sina."""

    class _FailingEMClient:
        def __init__(self, source_key: str = "x", **kwargs) -> None:
            pass

        async def __aenter__(self) -> "_FailingEMClient":
            return self

        async def __aexit__(self, *args) -> None:
            pass

        async def get(self, *args, **kwargs) -> None:
            raise RuntimeError("eastmoney unreachable")

    class _OkSinaClient:
        def __init__(self) -> None:
            self.called_with: list[str] = []

        async def fetch_history(self, code: str, **_):
            self.called_with.append(code)
            return EtfHistoryFetchResult(
                code=code,
                market="SH",
                secid=f"1.{code}",
                name=None,
                total_bars=1,
                points=[_make_point(date(2026, 8, 4), 1.234)],
                fetched_at=datetime(2026, 8, 4, tzinfo=UTC),
            )

    monkeypatch.setattr(
        "app.integrations.cn_etf_history.client_for_source", _FailingEMClient
    )

    sina = _OkSinaClient()
    em = EastmoneyFundKlineClient(sina_fallback=sina)
    result = await em.fetch_history("561560")
    assert sina.called_with == ["561560"]
    assert len(result.points) == 1
    assert em.last_success_source == "sina_kline"


@pytest.mark.asyncio
async def test_eastmoney_does_not_call_sina_when_em_succeeds(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """Verify chain doesn't pay the Sina cost when Eastmoney returns data."""

    em_payload = {
        "data": {
            "name": "电力ETF",
            "dktotal": 1,
            "klines": ["2026-08-04,1.0,1.05,1.06,0.99,100,105,1.5"],
        }
    }

    class _OkEMClient:
        def __init__(self, source_key: str = "x", **kwargs) -> None:
            pass

        async def __aenter__(self) -> "_OkEMClient":
            return self

        async def __aexit__(self, *args) -> None:
            pass

        async def get(self, *args, **kwargs):
            import httpx
            request = httpx.Request("GET", "https://push2his.eastmoney.com/")
            return httpx.Response(200, json=em_payload, request=request)

    sina_called = {"v": False}

    class _TrackingSina:
        async def fetch_history(self, code: str, **_):
            sina_called["v"] = True
            raise AssertionError("should not be called when EM succeeds")

    monkeypatch.setattr(
        "app.integrations.cn_etf_history.client_for_source", _OkEMClient
    )
    em = EastmoneyFundKlineClient(sina_fallback=_TrackingSina())
    result = await em.fetch_history("561560")
    assert em.last_success_source == "eastmoney_kline"
    assert len(result.points) == 1
    assert result.points[0].close == 1.05
    assert not sina_called["v"]


@pytest.mark.asyncio
async def test_eastmoney_raises_when_both_sources_fail(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """Final error message must surface BOTH the EM and Sina failures."""

    class _FailingEMClient:
        def __init__(self, source_key: str = "x", **kwargs) -> None:
            pass

        async def __aenter__(self) -> "_FailingEMClient":
            return self

        async def __aexit__(self, *args) -> None:
            pass

        async def get(self, *args, **kwargs) -> None:
            raise RuntimeError("eastmoney boom")

    class _FailingSina:
        async def fetch_history(self, code: str, **_):
            raise RuntimeError("sina boom")

    monkeypatch.setattr(
        "app.integrations.cn_etf_history.client_for_source", _FailingEMClient
    )
    em = EastmoneyFundKlineClient(sina_fallback=_FailingSina())
    with pytest.raises(RuntimeError) as excinfo:
        await em.fetch_history("561560")
    msg = str(excinfo.value)
    assert "eastmoney" in msg
    assert "sina" in msg
    assert "boom" in msg


@pytest.mark.asyncio
async def test_eastmoney_treats_empty_payload_as_failure(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """If Eastmoney returns 200 but klines=[] we must not silently succeed."""

    class _EmptyEMClient:
        def __init__(self, source_key: str = "x", **kwargs) -> None:
            pass

        async def __aenter__(self) -> "_EmptyEMClient":
            return self

        async def __aexit__(self, *args) -> None:
            pass

        async def get(self, *args, **kwargs):
            import httpx
            request = httpx.Request("GET", "https://push2his.eastmoney.com/")
            return httpx.Response(200, json={"data": {"klines": []}}, request=request)

    class _OkSina:
        async def fetch_history(self, code: str, **_):
            return EtfHistoryFetchResult(
                code=code,
                market="SH",
                secid=f"1.{code}",
                name=None,
                total_bars=1,
                points=[_make_point(date(2026, 8, 4), 1.0)],
                fetched_at=datetime(2026, 8, 4, tzinfo=UTC),
            )

    monkeypatch.setattr(
        "app.integrations.cn_etf_history.client_for_source", _EmptyEMClient
    )
    em = EastmoneyFundKlineClient(sina_fallback=_OkSina())
    result = await em.fetch_history("561560")
    assert em.last_success_source == "sina_kline"
    assert len(result.points) == 1