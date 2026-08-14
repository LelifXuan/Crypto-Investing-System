"""Tests for the equity-curve builder.

Covers:
- Pure-math: summary stats (peak / trough / drawdown / return)
- Single-symbol happy path
- Multi-symbol union of dates
- Missing dates → last-known-good carry-forward
- Missing symbol → recorded in meta.symbols_missing
- Empty positions + cash-only → renderable
- from_date > to_date → ValueError
- Decimal end-to-end (no float drift)
"""

from __future__ import annotations

from datetime import date, datetime, timezone
from decimal import Decimal

import pytest

from app.integrations.cn_etf_history import EtfHistoryFetchResult, EtfKlinePoint
from app.services.ashare_etf_equity import (
    PositionRequest,
    _normalize_positions,
    _summarize,
    build_equity_curve,
)
from app.services.ashare_etf_history import EtfHistoryService

UTC = timezone.utc


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


class _StubHistoryService(EtfHistoryService):
    """Stubbed service: returns canned snapshots, no I/O.

    Symbols not in ``by_code`` are treated as having no data — the stub
    returns an empty snapshot so the equity builder can record them in
    ``meta.symbols_missing`` rather than raising.
    """

    def __init__(self, by_code: dict[str, EtfHistoryFetchResult]) -> None:
        self.by_code = by_code

    async def get_snapshot(self, code, *, from_date=None, to_date=None, force_refresh=False):  # noqa: ANN001
        from app.services.ashare_etf_history import EtfHistorySnapshot

        result = self.by_code.get(code)
        if result is None:
            today = datetime.now(tz=UTC).date()
            return EtfHistorySnapshot(
                code=code,
                market="SH",
                secid=code,
                name=None,
                source="stub",
                coverage_start=today,
                coverage_end=today,
                last_updated=datetime.now(tz=UTC),
                points=[],
            )
        points = [p for p in result.points if from_date <= p.trade_date <= to_date]
        return EtfHistorySnapshot(
            code=result.code,
            market=result.market,
            secid=result.secid,
            name=result.name,
            source="eastmoney_kline",
            coverage_start=result.points[0].trade_date,
            coverage_end=result.points[-1].trade_date,
            last_updated=result.fetched_at,
            points=points,
        )


def _fetch(code: str, market: str, points: list[EtfKlinePoint]) -> EtfHistoryFetchResult:
    return EtfHistoryFetchResult(
        code=code,
        market=market,
        secid=f"{market}.{code}",
        name=code,
        total_bars=len(points),
        points=points,
        fetched_at=datetime(2026, 8, 4, tzinfo=UTC),
    )


# --- pure summary stats --------------------------------------------------


def test_summarize_max_drawdown_and_total_return() -> None:
    series = [Decimal("100"), Decimal("120"), Decimal("80"), Decimal("110")]
    summary = _summarize(
        sorted_dates=[date(2026, 8, i) for i in range(1, 5)],
        total_series=series,
        cash=Decimal("0"),
        positions=[],
    )
    # peak=120, then 80 → drawdown = (80-120)/120 = -1/3
    assert summary["peak_total_value"] == Decimal("120")
    assert summary["trough_total_value"] == Decimal("80")
    # max drawdown is the deepest peak→trough of running peaks; here running peaks
    # are 100→120→120→120 and values 100,120,80,110 → DD = (80-120)/120 = -1/3.
    assert summary["max_drawdown_pct"] == pytest.approx(Decimal("-0.3333333333333333"))
    # total return = (110-100)/100 = 10%
    assert summary["total_return_pct"] == Decimal("0.10")
    assert summary["days_observed"] == 4


def test_summarize_zero_starting_avoids_division() -> None:
    summary = _summarize(
        sorted_dates=[date(2026, 8, 1)],
        total_series=[Decimal("0")],
        cash=Decimal("0"),
        positions=[],
    )
    assert summary["max_drawdown_pct"] == Decimal("0")
    assert summary["total_return_pct"] == Decimal("0")


def test_normalize_positions_handles_dict_or_pydantic() -> None:
    from app.schemas.etf_equity_curve import EtfEquityCurvePosition

    payload = [
        EtfEquityCurvePosition(symbol="563010.SH", shares=100, cost_price=Decimal("1.234")),
        {"symbol": "512660.SH", "code": "512660", "shares": 200},
    ]
    out = _normalize_positions(payload)
    assert out[0].symbol == "563010.SH"
    assert out[0].cost_price == Decimal("1.234")
    assert out[1].shares == 200
    assert out[1].cost_price == Decimal("0")  # missing → 0


# --- async integration paths -------------------------------------------


@pytest.mark.asyncio
async def test_build_equity_curve_single_symbol_happy_path() -> None:
    points = [
        _make_point(date(2026, 8, 1), 1.00),
        _make_point(date(2026, 8, 2), 1.05),
        _make_point(date(2026, 8, 3), 0.95),
        _make_point(date(2026, 8, 4), 1.10),
    ]
    service = _StubHistoryService({"563010": _fetch("563010", "SH", points)})

    result = await build_equity_curve(
        history_service=service,
        positions=[PositionRequest("563010.SH", "563010", 1000, Decimal("1.0"))],
        cash=Decimal("0"),
        from_date=date(2026, 8, 1),
        to_date=date(2026, 8, 4),
        now=datetime(2026, 8, 4, 12, 0, tzinfo=UTC),
    )

    assert result["from_date"] == date(2026, 8, 1)
    assert result["to_date"] == date(2026, 8, 4)
    assert result["total_value"] == [
        Decimal("1000"),
        Decimal("1050"),
        Decimal("950"),
        Decimal("1100"),
    ]
    assert result["summary"]["current_total_value"] == Decimal("1100")
    assert result["summary"]["starting_total_value"] == Decimal("1000")
    assert result["summary"]["peak_total_value"] == Decimal("1100")
    assert result["summary"]["trough_total_value"] == Decimal("950")
    assert result["meta"]["source_status"] == "ok"
    assert result["meta"]["symbols_missing"] == []
    assert result["meta"]["symbols_with_data"] == ["563010.SH"]


@pytest.mark.asyncio
async def test_build_equity_curve_multi_symbol_uses_union_of_dates() -> None:
    pts_563 = [
        _make_point(date(2026, 8, 1), 1.00),
        _make_point(date(2026, 8, 3), 1.05),
    ]
    pts_512 = [
        _make_point(date(2026, 8, 2), 2.00),
        _make_point(date(2026, 8, 3), 2.10),
    ]
    service = _StubHistoryService(
        {
            "563010": _fetch("563010", "SH", pts_563),
            "512660": _fetch("512660", "SH", pts_512),
        }
    )

    result = await build_equity_curve(
        history_service=service,
        positions=[
            PositionRequest("563010.SH", "563010", 100, Decimal("1.0")),
            PositionRequest("512660.SH", "512660", 200, Decimal("2.0")),
        ],
        cash=Decimal("50"),
        from_date=date(2026, 8, 1),
        to_date=date(2026, 8, 3),
        now=datetime(2026, 8, 3, 12, 0, tzinfo=UTC),
    )

    # Union dates = {8/1, 8/2, 8/3}; cash=50 added every day
    assert [d.isoformat() for d in result["labels"]] == [
        "2026-08-01",
        "2026-08-02",
        "2026-08-03",
    ]
    # 8/1: only 563010 (100), no 512660 → 50 + 100 = 150
    assert result["total_value"][0] == Decimal("150")
    # 8/2: only 512660 (400), 563010 carries last-known (1.00 → 100) → 50 + 100 + 400 = 550
    assert result["total_value"][1] == Decimal("550")
    # 8/3: 563010 (105) + 512660 (420) + 50 = 575
    assert result["total_value"][2] == Decimal("575")
    # Missing dates: 8/2 (563010 missing, with prior last-known). 8/1 is
    # 512660's first-ever day so we don't flag it (no last-known to carry).
    assert date(2026, 8, 2) in result["meta"]["missing_dates"]
    assert date(2026, 8, 1) not in result["meta"]["missing_dates"]
    assert result["meta"]["source_status"] == "partial"


@pytest.mark.asyncio
async def test_build_equity_curve_symbol_with_no_data_reported() -> None:
    """A symbol that has no history at all is recorded but doesn't break the response."""
    service = _StubHistoryService(
        {
            "563010": _fetch(
                "563010",
                "SH",
                [_make_point(date(2026, 8, 1), 1.00), _make_point(date(2026, 8, 2), 1.05)],
            )
        }
    )

    result = await build_equity_curve(
        history_service=service,
        positions=[
            PositionRequest("563010.SH", "563010", 100, Decimal("1.0")),
            PositionRequest("159201.SZ", "159201", 50, Decimal("2.0")),  # no history
        ],
        cash=Decimal("0"),
        from_date=date(2026, 8, 1),
        to_date=date(2026, 8, 2),
        now=datetime(2026, 8, 2, tzinfo=UTC),
    )

    assert "159201.SZ" in result["meta"]["symbols_missing"]
    assert "563010.SH" in result["meta"]["symbols_with_data"]
    assert result["meta"]["source_status"] == "partial"
    # 159201 contributes 0 every day
    assert result["total_value"] == [Decimal("100"), Decimal("105")]


@pytest.mark.asyncio
async def test_build_equity_curve_cash_only_succeeds() -> None:
    service = _StubHistoryService({})  # no symbols queried
    result = await build_equity_curve(
        history_service=service,
        positions=[],
        cash=Decimal("5000"),
        from_date=date(2026, 8, 1),
        to_date=date(2026, 8, 4),
        now=datetime(2026, 8, 4, tzinfo=UTC),
    )
    # No symbol data → only from_date + to_date endpoints, both at cash level
    assert result["total_value"] == [Decimal("5000"), Decimal("5000")]
    assert "所有持仓 ETF 都没有历史净值数据" in result["warnings"][1]
    assert result["meta"]["source_status"] == "unavailable"


@pytest.mark.asyncio
async def test_build_equity_curve_rejects_inverted_window() -> None:
    service = _StubHistoryService({})
    with pytest.raises(ValueError, match="from_date"):
        await build_equity_curve(
            history_service=service,
            positions=[],
            cash=Decimal("100"),
            from_date=date(2026, 8, 5),
            to_date=date(2026, 8, 1),
        )


@pytest.mark.asyncio
async def test_build_equity_curve_rejects_empty_input() -> None:
    service = _StubHistoryService({})
    with pytest.raises(ValueError, match="at least one"):
        await build_equity_curve(
            history_service=service,
            positions=[],
            cash=Decimal("0"),
            from_date=date(2026, 8, 1),
            to_date=date(2026, 8, 2),
        )


@pytest.mark.asyncio
async def test_build_equity_curve_decimal_end_to_end() -> None:
    """No float drift: values must be Decimal, not float, throughout."""
    points = [_make_point(date(2026, 8, i), 0.001 * i) for i in range(1, 6)]
    service = _StubHistoryService({"563010": _fetch("563010", "SH", points)})

    result = await build_equity_curve(
        history_service=service,
        positions=[PositionRequest("563010.SH", "563010", 333, Decimal("0.003"))],
        cash=Decimal("0.1"),
        from_date=date(2026, 8, 1),
        to_date=date(2026, 8, 5),
        now=datetime(2026, 8, 5, tzinfo=UTC),
    )
    for v in result["total_value"]:
        assert isinstance(v, Decimal)
    # Last bar = 333 shares × 0.005 NAV + 0.1 cash
    expected_last = Decimal("333") * Decimal("0.005") + Decimal("0.1")
    assert result["summary"]["current_total_value"] == expected_last