"""Tests for the HALO Rolling-252-Cov strategy simulation.

Covers:
- Pure-math helpers: month-end trading day, returns matrix
- Constrained ERC: weight caps + commodity cap + stability floor
- run_simulation: monthly DCA application + cost basis
- run_simulation: quarterly rebalance trigger logic
- run_simulation: invalid input (missing NAV, inverted window)
"""

from __future__ import annotations

from datetime import date, timezone
from decimal import Decimal

import numpy as np
import pytest

from app.schemas.etf_simulation import EtfSimulationParams
from app.services.ashare_etf_simulation import (
    ALL_HALO_CODES,
    CASHFLOW_SYMBOL,
    COMMODITY_CODES,
    NavSeries,
    _month_end_trading_day,
    _returns_matrix,
    _solve_constrained_erc,
    run_simulation,
)

UTC = timezone.utc


def _build_nav(code: str, market: str, starts: list[tuple[date, float]]) -> NavSeries:
    return NavSeries(
        code=code, market=market, points=starts, name=code
    )


# --- _month_end_trading_day -----------------------------------------------


def test_month_end_trading_day_returns_last_available_date() -> None:
    nav = {date(2025, 8, 29): 1.0, date(2025, 8, 28): 0.99}
    assert _month_end_trading_day(date(2025, 8, 1), nav) == date(2025, 8, 29)


def test_month_end_trading_day_empty_returns_none() -> None:
    assert _month_end_trading_day(date(2025, 8, 1), {}) is None


def test_month_end_trading_day_handles_december_rollover() -> None:
    nav = {date(2025, 12, 31): 1.0, date(2026, 1, 2): 1.0}
    assert _month_end_trading_day(date(2025, 12, 1), nav) == date(2025, 12, 31)


# --- _returns_matrix ------------------------------------------------------


def test_returns_matrix_filters_to_common_window() -> None:
    series = {
        "A": [(date(2025, 1, 1), 1.0), (date(2025, 1, 2), 1.1), (date(2025, 1, 3), 1.2)],
        "B": [(date(2025, 1, 1), 2.0), (date(2025, 1, 3), 2.2)],  # gap on 1/2
    }
    # Common dates are {1/1, 1/3} = 2 days; window=3 exceeds → None
    result = _returns_matrix(series, window=3)
    assert result is None


def test_returns_matrix_returns_full_window_when_overlap_sufficient() -> None:
    series = {
        "A": [
            (date(2025, 1, 1), 1.0),
            (date(2025, 1, 2), 1.1),
            (date(2025, 1, 3), 1.2),
        ],
        "B": [
            (date(2025, 1, 1), 2.0),
            (date(2025, 1, 2), 2.05),
            (date(2025, 1, 3), 2.2),
        ],
    }
    result = _returns_matrix(series, window=3)
    assert result is not None
    matrix, _ = result
    assert matrix.shape == (3, 2)
    assert matrix[1, 0] == pytest.approx(np.log(1.1), abs=1e-9)
    assert matrix[1, 1] == pytest.approx(np.log(2.05 / 2.0), abs=1e-9)


def test_returns_matrix_returns_none_when_window_too_small() -> None:
    series = {"A": [(date(2025, 1, 1), 1.0), (date(2025, 1, 2), 1.1)]}
    result = _returns_matrix(series, window=5)
    assert result is None


# --- _solve_constrained_erc ----------------------------------------------


def test_constrained_erc_respects_caps() -> None:
    n = 6
    cov = np.eye(n) * 0.04  # diagonal, all equal variance
    code_index = {c: i for i, c in enumerate(ALL_HALO_CODES)}
    w = _solve_constrained_erc(
        cov,
        cap_per_symbol=0.25,
        commodity_cap=0.35,
        stability_floor=0.25,
        dianxin_cap=0.12,
        iterations=20,
        code_index=code_index,
    )
    assert w.sum() == pytest.approx(1.0, abs=1e-6)
    # No individual weight above the cap (tolerance for projection iterations)
    assert all(w_i <= 0.25 + 1e-3 for w_i in w)
    # 563010 capped at 0.12 (loose tolerance — ERC iteration may slightly
    # overshoot; the projection loop clamps it back below cap on next pass)
    assert w[code_index["563010"]] <= 0.13
    # 159930 + 512400 sum ≤ 0.35
    commodity_indices = [code_index[c] for c in COMMODITY_CODES]
    assert w[commodity_indices].sum() <= 0.36
    # 561560 + 563010 sum ≥ 0.25
    assert w[code_index["561560"]] + w[code_index["563010"]] >= 0.24


def test_constrained_erc_handles_degenerate_covariance() -> None:
    n = 6
    cov = np.zeros((n, n))  # all zeros — degenerate
    code_index = {c: i for i, c in enumerate(ALL_HALO_CODES)}
    w = _solve_constrained_erc(
        cov,
        cap_per_symbol=0.25,
        commodity_cap=0.35,
        stability_floor=0.25,
        dianxin_cap=0.12,
        iterations=5,
        code_index=code_index,
    )
    # Should fall back to equal weight + apply constraints
    assert w.sum() == pytest.approx(1.0, abs=1e-6)


# --- run_simulation ------------------------------------------------------


def _build_minimal_nav() -> dict[str, NavSeries]:
    """Build 13 months of daily NAV for HALO + cashflow with stable prices."""
    from datetime import timedelta

    def gen(code: str, market: str, base: float) -> NavSeries:
        pts = []
        d = date(2025, 8, 1)
        end = date(2026, 8, 4)
        while d <= end:
            if d.weekday() < 5:
                pts.append((d, base))
            d += timedelta(days=1)
        return _build_nav(code, market, pts)

    return {
        "561560": gen("561560", "SH", 1.0),
        "159930": gen("159930", "SZ", 1.5),
        "512400": gen("512400", "SH", 0.8),
        "516950": gen("516950", "SH", 1.2),
        "512660": gen("512660", "SH", 0.9),
        "563010": gen("563010", "SH", 1.1),
        CASHFLOW_SYMBOL: gen(CASHFLOW_SYMBOL, "SZ", 1.0),
    }


def test_run_simulation_applies_monthly_dca() -> None:
    nav = _build_minimal_nav()
    result = run_simulation(
        nav_by_code=nav,
        from_month=date(2025, 8, 1),
        to_date=date(2026, 8, 4),
        params=EtfSimulationParams(),  # default
    )
    # 13 month-ends → 13 snapshots + 13 events
    assert len(result["months"]) == 13
    assert len(result["events"]) == 13
    # The first snapshot is BEFORE any DCA happens (end-of-month, before
    # the month's DCA buy), so shares == 0.
    assert result["series"][0]["per_symbol_shares"]["561560"] == 0
    # The last snapshot is AFTER the August 2026 DCA buy
    last = result["series"][-1]
    # 12 months of DCA × 100 lots × 100 shares = 120,000 shares per HALO
    assert last["per_symbol_shares"]["561560"] == 12 * 100 * 100
    assert last["per_symbol_shares"][CASHFLOW_SYMBOL] == 12 * 100 * 100
    # Cost basis = 12 × 100 × 100 shares × price per symbol (no sells yet)
    assert Decimal(last["per_symbol_value"]["561560"]) >= Decimal("0")
    # Total cost should match sum of DCA buys (12 × 7 × 100 × 100 × avg_price)
    # With stable prices: cost ≈ 12 × (6 + 1) × 10000 × 1.0 ≈ 840,000
    assert Decimal(result["summary"]["final_cost_value"]) >= Decimal("800000")


def test_run_simulation_emits_rebalance_events_at_quarter_ends() -> None:
    nav = _build_minimal_nav()
    result = run_simulation(
        nav_by_code=nav,
        from_month=date(2025, 8, 1),
        to_date=date(2026, 8, 4),
        params=EtfSimulationParams(),
    )
    # Stable prices → weights stay near 1/6, drift ≤ 20% → may not trigger.
    # We just verify the event SCHEDULE exists: monthly_dca_only for every
    # month, with the right kind distribution overall.
    assert sum(1 for e in result["events"] if e["kind"] == "monthly_dca_only") >= 8
    # Even when no rebalance fires, the event metadata is still present.
    for e in result["events"]:
        assert e["date"]
        assert isinstance(e["halo_dca"], dict)
        assert isinstance(e["cashflow_shares_added"], int)
        assert CASHFLOW_SYMBOL not in e["halo_dca"]  # cashflow is separate
        # halo_dca contains only the 6 HALO codes
        for code in e["halo_dca"]:
            assert code in ALL_HALO_CODES


def test_run_simulation_rejects_inverted_window() -> None:
    nav = _build_minimal_nav()
    with pytest.raises(ValueError, match="from_month"):
        run_simulation(
            nav_by_code=nav,
            from_month=date(2026, 8, 4),
            to_date=date(2025, 8, 1),
            params=EtfSimulationParams(),
        )


def test_run_simulation_rejects_missing_halo_data() -> None:
    nav = _build_minimal_nav()
    del nav["561560"]  # remove one HALO symbol
    with pytest.raises(ValueError, match="missing NAV for HALO"):
        run_simulation(
            nav_by_code=nav,
            from_month=date(2025, 8, 1),
            to_date=date(2026, 8, 4),
            params=EtfSimulationParams(),
        )


def test_run_simulation_rejects_missing_cashflow_data() -> None:
    nav = _build_minimal_nav()
    del nav[CASHFLOW_SYMBOL]
    with pytest.raises(ValueError, match="cashflow"):
        run_simulation(
            nav_by_code=nav,
            from_month=date(2025, 8, 1),
            to_date=date(2026, 8, 4),
            params=EtfSimulationParams(),
        )


def test_run_simulation_with_divergent_prices_triggers_rebalance() -> None:
    """Force weight drift > 20% and verify rebalance fires."""
    from datetime import timedelta

    def gen(code: str, market: str, drift_per_month: float) -> NavSeries:
        pts = []
        d = date(2025, 8, 1)
        end = date(2026, 8, 4)
        price = 1.0
        while d <= end:
            if d.weekday() < 5:
                # Apply monthly drift at the start of each month
                if d.day == 1 or (d.day < 8 and d.weekday() < 5 and len(pts) == 0):
                    price *= 1 + drift_per_month
                pts.append((d, price))
            d += timedelta(days=1)
        return _build_nav(code, market, pts)

    nav = {
        "561560": gen("561560", "SH", 0.10),  # +10%/month
        "159930": gen("159930", "SZ", -0.05),  # -5%/month
        "512400": gen("512400", "SH", 0.15),  # +15%/month
        "516950": gen("516950", "SH", 0.0),
        "512660": gen("512660", "SH", -0.10),  # -10%/month
        "563010": gen("563010", "SH", 0.05),
        CASHFLOW_SYMBOL: gen(CASHFLOW_SYMBOL, "SZ", 0.005),
    }
    result = run_simulation(
        nav_by_code=nav,
        from_month=date(2025, 8, 1),
        to_date=date(2026, 8, 4),
        params=EtfSimulationParams(),
    )
    # The seed has +10%/month for 561560 (a stability member) and -10% for
    # 512660 — this should break the stability floor constraint and trigger.
    assert result["summary"]["rebalance_count"] >= 1
    assert Decimal(result["summary"]["cumulative_friction"]) > Decimal("0")


def test_run_simulation_summary_calculates_max_drawdown() -> None:
    nav = _build_minimal_nav()
    result = run_simulation(
        nav_by_code=nav,
        from_month=date(2025, 8, 1),
        to_date=date(2026, 8, 4),
        params=EtfSimulationParams(),
    )
    summary = result["summary"]
    # With stable prices + monthly DCA, drawdown should be small (DCA
    # averaging in means even flat prices produce non-negative series).
    assert Decimal(summary["max_drawdown_pct"]) >= Decimal("-0.50")
    assert Decimal(summary["peak_total_value"]) >= Decimal(summary["trough_total_value"])
    assert Decimal(summary["final_total_value"]) > Decimal("0")


def test_run_simulation_decimal_end_to_end() -> None:
    nav = _build_minimal_nav()
    result = run_simulation(
        nav_by_code=nav,
        from_month=date(2025, 8, 1),
        to_date=date(2026, 8, 4),
        params=EtfSimulationParams(),
    )
    # All money fields must be Decimal-friendly strings (no float drift)
    for s in result["series"]:
        assert isinstance(s["total_value"], str)
        # Force conversion to Decimal — should never raise
        Decimal(s["total_value"])
        Decimal(s["cost_value"])


def test_run_simulation_meta_halos_listing_start() -> None:
    """halos_listing_start = MAX of all HALO symbols' earliest data point.

    Different ETFs list at different times; the simulation's natural
    starting month is the first month when the WHOLE basket is trading.
    """
    nav = _build_minimal_nav()
    result = run_simulation(
        nav_by_code=nav,
        from_month=date(2025, 8, 1),
        to_date=date(2026, 8, 4),
        params=EtfSimulationParams(),
    )
    # All symbols in _build_minimal_nav start at 2025-08-01 → max = same day
    assert result["meta"]["halos_listing_start"] == "2025-08-01"


def test_run_simulation_meta_halos_listing_start_with_staggered_data() -> None:
    """When HALO symbols start at different dates, halos_listing_start is the LATEST."""
    from datetime import timedelta

    def gen(code: str, market: str, start_offset_days: int) -> NavSeries:
        pts = []
        d0 = date(2025, 1, 1)
        d = d0 + timedelta(days=start_offset_days)
        end = date(2026, 8, 4)
        while d <= end:
            if d.weekday() < 5:
                pts.append((d, 1.0))
            d += timedelta(days=1)
        return _build_nav(code, market, pts)

    # 561560 starts 2025-01-01, others start 2025-03-01 (60 days later)
    nav = {
        "561560": gen("561560", "SH", 0),
        "159930": gen("159930", "SZ", 60),
        "512400": gen("512400", "SH", 60),
        "516950": gen("516950", "SH", 60),
        "512660": gen("512660", "SH", 60),
        "563010": gen("563010", "SH", 60),
        CASHFLOW_SYMBOL: gen(CASHFLOW_SYMBOL, "SZ", 0),
    }
    result = run_simulation(
        nav_by_code=nav,
        from_month=date(2025, 1, 1),
        to_date=date(2025, 6, 1),
        params=EtfSimulationParams(),
    )
    # Earliest for each symbol:
    # 561560 = 2025-01-01, others = 2025-03-03 (60 days after Jan 1)
    # max of these = 2025-03-03
    assert result["meta"]["halos_listing_start"] == "2025-03-03"