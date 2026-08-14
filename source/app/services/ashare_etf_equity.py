"""ETF equity-curve builder.

Reconstructs the historical mark-to-market value of a portfolio across a
[from_date, to_date] window by combining each position's shares with the
ETF's daily NAV series. The result is a faithful replay — there is no
projection, no Monte Carlo, no future extrapolation.

Design rules (all enforced here, never delegated to UI):

1. ``Decimal`` math end-to-end. We never multiply float shares × float NAV;
   we coerce to ``Decimal`` once at the boundary and stay there.
2. Missing dates fall back to the **last known NAV** (last-known-good).
   This biases the curve conservatively when a single trading day is
   missing. The list of substituted dates is returned in
   ``meta.missing_dates``.
3. Symbols with no data at all (``coverage_start > from_date`` and empty
   series) are reported in ``meta.symbols_missing`` and contribute zero
   value across the window — the user is told explicitly rather than
   getting a misleading flat line.
4. ``summary`` is computed on the resolved ``total_value`` series, not on
   per-symbol segments.
"""

from __future__ import annotations

import logging
from dataclasses import dataclass
from datetime import date, datetime, timedelta, timezone
from decimal import Decimal
from typing import Iterable

from app.services.ashare_etf_history import EtfHistoryService

logger = logging.getLogger(__name__)

UTC = timezone.utc

DEFAULT_LOOKBACK_YEARS = 5


@dataclass(slots=True)
class PositionRequest:
    """Internal-normalized view of one position for the builder."""

    symbol: str
    code: str
    shares: int
    cost_price: Decimal


def _position_from_request(req) -> PositionRequest:  # noqa: ANN001
    """Adapter: accepts pydantic EtfEquityCurvePosition or dict-like."""
    if hasattr(req, "symbol"):
        symbol = str(req.symbol)
        code = str(getattr(req, "code", None) or symbol.split(".")[0])
        shares = int(req.shares)
        cost = getattr(req, "cost_price", None)
    else:
        symbol = str(req["symbol"])
        code = str(req.get("code") or symbol.split(".")[0])
        shares = int(req["shares"])
        cost = req.get("cost_price")
    if cost is None:
        cost_dec = Decimal("0")
    else:
        cost_dec = Decimal(str(cost))
    return PositionRequest(
        symbol=symbol,
        code=code,
        shares=shares,
        cost_price=cost_dec,
    )


def _normalize_positions(positions: Iterable) -> list[PositionRequest]:  # noqa: ANN001
    return [_position_from_request(p) for p in positions]


def _default_window() -> tuple[date, date]:
    today = datetime.now(tz=UTC).date()
    return today - timedelta(days=365 * DEFAULT_LOOKBACK_YEARS), today


async def build_equity_curve(
    *,
    history_service: EtfHistoryService,
    positions: list[PositionRequest],
    cash: Decimal,
    from_date: date | None = None,
    to_date: date | None = None,
    now: datetime | None = None,
) -> dict:
    """Build the equity-curve response payload.

    Returns a plain dict that matches ``EtfEquityCurveResponse`` schema.
    Kept as a dict (instead of the pydantic model) so the unit tests don't
    need a fully bootstrapped app; the endpoint layer is responsible for
    validating against the schema.
    """
    if from_date is None or to_date is None:
        default_beg, default_end = _default_window()
        from_date = from_date or default_beg
        to_date = to_date or default_end

    if from_date > to_date:
        raise ValueError(f"from_date {from_date} must be <= to_date {to_date}")

    if not positions and cash <= 0:
        raise ValueError("equity_curve requires at least one non-zero position or cash")

    now = now or datetime.now(tz=UTC)
    warnings: list[str] = []
    per_symbol_nav: dict[str, dict[date, Decimal]] = {}
    coverage_per_symbol: dict[str, tuple[date, date]] = {}
    missing_symbols: list[str] = []
    present_symbols: list[str] = []

    for pos in positions:
        if pos.shares == 0:
            present_symbols.append(pos.symbol)
            continue
        try:
            snap = await history_service.get_snapshot(
                pos.code, from_date=from_date, to_date=to_date
            )
        except Exception as exc:  # noqa: BLE001
            # Never let one bad symbol blow up the whole response. Mark it
            # missing and let the curve render with cash + the other symbols.
            logger.warning(
                "etf_equity_curve:symbol_fetch_failed symbol=%s err=%s",
                pos.symbol,
                exc,
            )
            missing_symbols.append(pos.symbol)
            present_symbols.append(pos.symbol)
            warnings.append(f"etf_equity_curve:symbol_fetch_failed:{pos.symbol}:{exc}")
            continue
        if not snap.points:
            missing_symbols.append(pos.symbol)
            present_symbols.append(pos.symbol)
            continue
        per_symbol_nav[pos.symbol] = {
            p.trade_date: Decimal(str(p.close)) for p in snap.points
        }
        coverage_per_symbol[pos.symbol] = (snap.coverage_start, snap.coverage_end)
        present_symbols.append(pos.symbol)

    # Build the union date index across all symbols with data.
    all_dates: set[date] = set()
    for nav_map in per_symbol_nav.values():
        all_dates.update(nav_map.keys())

    if not all_dates:
        # No symbol had data: fall back to the requested window endpoints so
        # the response is still renderable as a flat cash line over the
        # full window rather than a single point.
        all_dates = {from_date, to_date}
        warnings.extend(
            [
                "etf_equity_curve:no_symbol_data",
                "所有持仓 ETF 都没有历史净值数据,曲线只反映现金。",
            ]
        )

    sorted_dates = sorted(d for d in all_dates if from_date <= d <= to_date)
    if not sorted_dates:
        sorted_dates = [from_date]

    # Per-symbol series (Decimal or None for missing dates).
    per_symbol_series: dict[str, list[Decimal | None]] = {}
    missing_dates: list[date] = []
    for sym, nav_map in per_symbol_nav.items():
        series: list[Decimal | None] = []
        last_known: Decimal | None = None
        for d in sorted_dates:
            v = nav_map.get(d)
            if v is None:
                if last_known is not None:
                    series.append(last_known)
                    missing_dates.append(d)
                else:
                    series.append(None)
            else:
                last_known = v
                series.append(v)
        per_symbol_series[sym] = series

    # Total value series.
    total_series: list[Decimal] = []
    for i in range(len(sorted_dates)):
        day_total = cash
        for sym, series in per_symbol_series.items():
            shares = next((p.shares for p in positions if p.symbol == sym), 0)
            if shares == 0:
                continue
            v = series[i]
            if v is None:
                continue
            day_total += Decimal(shares) * v
        total_series.append(day_total)

    # Summary stats.
    summary = _summarize(
        sorted_dates=sorted_dates,
        total_series=total_series,
        cash=cash,
        positions=positions,
    )

    coverage_start = min(
        (c[0] for c in coverage_per_symbol.values()), default=from_date
    )
    coverage_end = max(
        (c[1] for c in coverage_per_symbol.values()), default=to_date
    )

    if missing_symbols:
        source_status = "partial" if total_series and any(total_series) else "unavailable"
        warnings.append(
            f"以下 ETF 缺少历史净值数据,贡献值按 0 处理: {', '.join(missing_symbols)}"
        )
    elif not per_symbol_nav:
        # No symbols had any data at all — distinguish this from "ok" so
        # the UI can show a "waiting for upstream" state.
        source_status = "unavailable"
    elif any(v is None for series in per_symbol_series.values() for v in series):
        source_status = "partial"
    else:
        source_status = "ok"

    return {
        "scope": "ashare-etf",
        "from_date": from_date,
        "to_date": to_date,
        "labels": sorted_dates,
        "total_value": total_series,
        "per_symbol": per_symbol_series,
        "summary": summary,
        "meta": {
            "data_source": "eastmoney_kline",
            "fetched_at": now,
            "coverage_start": coverage_start,
            "coverage_end": coverage_end,
            "missing_dates": sorted(set(missing_dates)),
            "symbols_with_data": present_symbols,
            "symbols_missing": missing_symbols,
            "source_status": source_status,
        },
        "warnings": warnings,
    }


def _summarize(
    *,
    sorted_dates: list[date],
    total_series: list[Decimal],
    cash: Decimal,
    positions: list[PositionRequest],
) -> dict:
    if not total_series:
        zero = Decimal("0")
        return {
            "current_total_value": zero,
            "starting_total_value": zero,
            "peak_total_value": zero,
            "trough_total_value": zero,
            "max_drawdown_pct": zero,
            "total_return_pct": zero,
            "cumulative_cost": zero,
            "days_observed": 0,
        }

    starting = total_series[0]
    current = total_series[-1]
    peak = max(total_series)
    trough = min(total_series)

    # Drawdown is computed against running peak, not global peak.
    running_peak = starting
    max_dd = Decimal("0")
    for v in total_series:
        if v > running_peak:
            running_peak = v
        if running_peak > 0:
            dd = (v - running_peak) / running_peak
            if dd < max_dd:
                max_dd = dd

    total_return_pct = (
        (current - starting) / starting if starting > 0 else Decimal("0")
    )

    # Cumulative cost = starting cost basis = cash + Σ shares × cost_price.
    cumulative_cost = cash + sum(
        (Decimal(p.shares) * p.cost_price for p in positions), start=Decimal("0")
    )

    return {
        "current_total_value": current,
        "starting_total_value": starting,
        "peak_total_value": peak,
        "trough_total_value": trough,
        "max_drawdown_pct": max_dd,
        "total_return_pct": total_return_pct,
        "cumulative_cost": cumulative_cost,
        "days_observed": len(sorted_dates),
    }


__all__ = [
    "DEFAULT_LOOKBACK_YEARS",
    "PositionRequest",
    "_normalize_positions",
    "build_equity_curve",
]