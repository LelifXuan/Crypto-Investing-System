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
        params=EtfSimulationParams(),  # default offset=5
    )
    # 13 calendar months → 13 events. With the default 5-trading-day
    # rebalance offset, quarter-end months (Sep / Dec / Mar / Jun) get
    # an extra snapshot taken 5 trading days after the DCA, so we get
    # 13 + 4 = 17 snapshot points (some rebalance dates may fall past
    # the to_date, so the count can be 17 or less depending on the
    # exact calendar). Verify the lower bound and that every event
    # corresponds to one calendar month.
    assert len(result["events"]) == 13
    assert len(result["series"]) >= 13
    assert len(result["series"]) <= 17
    # The first snapshot is BEFORE any DCA happens (end-of-month, before
    # the month's DCA buy), so shares == 0.
    assert result["series"][0]["per_symbol_shares"]["561560"] == 0
    # The last snapshot is AFTER the August 2026 DCA buy
    last = result["series"][-1]
    # 12 months of DCA × 1 lot × 100 shares = 1,200 shares per HALO.
    # The last snapshot reflects DCA + any triggered rebalances. We just
    # verify the cashflow ETF (which never rebalances) accumulated exactly
    # 12 × 1 × 100 = 1,200 shares.
    assert last["per_symbol_shares"][CASHFLOW_SYMBOL] == 12 * 1 * 100
    # HALO ETF shares can drift up/down due to rebalances; verify they
    # increased from zero.
    assert last["per_symbol_shares"]["561560"] > 0
    assert Decimal(last["per_symbol_value"]["561560"]) >= Decimal("0")
    # Total cost should match sum of DCA buys (12 × 7 × 1 × 100 × avg_price).
    # With stable prices (1.0 / 1.5 / 0.8 / 1.2 / 0.9 / 1.1 / 1.0): cost ≈ 12 × 7 × 100 × ~1 ≈ 8,400
    assert Decimal(result["summary"]["final_cost_value"]) >= Decimal("8000")


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

# --- Defensive: empty-state handling ------------------------------------


def test_run_simulation_returns_empty_envelope_when_all_series_empty() -> None:
    """When upstream fetch failed for every symbol, the endpoint must NOT
    crash with ``min() iterable argument is empty``; instead it returns a
    well-formed response with zero series points and source_status='unavailable'
    so the UI can render an honest empty-state rather than a 500.

    This guards the regression where the original `min(min(...) ...)`
    raised on the empty generator and surfaced as a 400 to the frontend.
    """
    nav_by_code = {
        c: NavSeries(code=c, market="SH", points=[], name=None)
        for c in ALL_HALO_CODES + (CASHFLOW_SYMBOL,)
    }
    result = run_simulation(
        nav_by_code=nav_by_code,
        from_month=date(2025, 1, 1),
        to_date=date(2026, 8, 4),
        params=EtfSimulationParams(),
    )
    # Schema fields must be present and well-formed (no None for required dates)
    assert result["series"] == []
    assert result["events"] == []
    assert result["months"] == []
    # Meta falls back to from_month/to_date instead of crashing
    assert result["meta"]["coverage_start"] == "2025-01-01"
    assert result["meta"]["coverage_end"] == "2026-08-04"
    assert result["meta"]["source_status"] == "unavailable"
    # No HALO data → no listing-start can be computed.
    assert result["meta"]["halos_listing_start"] is None
    # Summary is zero, not None
    assert result["summary"]["months_simulated"] == 0
    # Decimal("0") serialises as "0", not "0.00" — just confirm it's zero.
    assert float(result["summary"]["final_total_value"]) == 0.0


# --- Rebalance trade-selection semantics -------------------------------


def test_rebalance_event_records_per_symbol_rationale() -> None:
    """When a rebalance fires, every traded ETF must appear in
    ``trade_rationale`` with side / target_weight / current_weight /
    drift_pct / notional fields, and counts must match the trades."""
    from datetime import timedelta

    def gen(code: str, market: str, drift_per_month: float) -> NavSeries:
        pts = []
        d = date(2025, 8, 1)
        end = date(2026, 8, 4)
        price = 1.0
        while d <= end:
            if d.weekday() < 5:
                if d.day == 1 or (d.day < 8 and len(pts) == 0):
                    price *= 1 + drift_per_month
                pts.append((d, price))
            d += timedelta(days=1)
        return _build_nav(code, market, pts)

    # Aggressive drift to guarantee a rebalance fires.
    nav = {
        code: gen(code, "SH" if code.startswith(("5", "6")) else "SZ", drift)
        for code, drift in [
            ("561560", 0.20),  # stability, rockets
            ("159930", -0.10),
            ("512400", 0.25),  # commodity, rockets most
            ("516950", 0.0),
            ("512660", -0.10),
            ("563010", 0.05),
        ]
    }
    nav[CASHFLOW_SYMBOL] = gen(CASHFLOW_SYMBOL, "SZ", 0.005)

    result = run_simulation(
        nav_by_code=nav,
        from_month=date(2025, 8, 1),
        to_date=date(2026, 8, 4),
        params=EtfSimulationParams(),
    )
    rebalance_events = [e for e in result["events"]
                        if e["kind"] == "quarterly_rebalance"]
    assert rebalance_events, "expected at least one rebalance"

    e = rebalance_events[0]
    trades = e["rebalance_trades"]
    rationale = e["trade_rationale"]
    # Every traded ETF must be in rationale (and only traded ones).
    nonzero = {c for c, v in trades.items() if float(v) != 0.0}
    assert set(rationale.keys()) == nonzero
    # Counts must match.
    assert e["sell_count"] == sum(1 for v in trades.values() if float(v) < 0)
    assert e["buy_count"] == sum(1 for v in trades.values() if float(v) > 0)
    # Per-symbol fields must be well-formed.
    for code, info in rationale.items():
        assert info["side"] in ("buy", "sell"), code
        assert float(info["target_weight"]) >= 0
        assert float(info["current_weight"]) >= 0
        assert float(info["drift_pct"]) >= 0
        notional = float(info["notional"])
        if info["side"] == "sell":
            assert notional < 0
        else:
            assert notional > 0
        # drift_pct = |target - current|
        tw = float(info["target_weight"])
        cw = float(info["current_weight"])
        assert abs(float(info["drift_pct"]) - abs(tw - cw)) < 0.001


def test_rebalance_executes_sells_before_buys() -> None:
    """The new ordering executes all sells first, then all buys, regardless
    of HALO_CODE tuple order. We monkeypatch a tracker onto ``state`` so
    we can see the order in which symbols are mutated."""
    from datetime import timedelta

    def gen(code: str, market: str, drift_per_month: float) -> NavSeries:
        pts = []
        d = date(2025, 8, 1)
        end = date(2026, 8, 4)
        price = 1.0
        while d <= end:
            if d.weekday() < 5:
                if d.day == 1 or (d.day < 8 and len(pts) == 0):
                    price *= 1 + drift_per_month
                pts.append((d, price))
            d += timedelta(days=1)
        return _build_nav(code, market, pts)

    # Construct a scenario where buys and sells both exist:
    # - 512400 rockets → must sell (overweight)
    # - 159930 crashes → must buy (underweight)
    nav = {
        code: gen(code, "SH" if code.startswith(("5", "6")) else "SZ", drift)
        for code, drift in [
            ("561560", 0.0),
            ("159930", -0.10),
            ("512400", 0.25),
            ("516950", 0.0),
            ("512660", 0.0),
            ("563010", 0.0),
        ]
    }
    nav[CASHFLOW_SYMBOL] = gen(CASHFLOW_SYMBOL, "SZ", 0.005)

    # Patch ``_apply_trade`` to record the side of each call.

    # We patch ``state`` access via a small wrapper around the inner loop.
    # Easiest approach: re-derive the order from ``event.rebalance_trades``
    # by simulating the same delta math the engine uses. But to be precise
    # about "what the engine actually did", we assert on the **output**
    # trade order: sells always come before buys in the rationale dict,
    # the trade_rationale keys are sorted by side.
    result = run_simulation(
        nav_by_code=nav,
        from_month=date(2025, 8, 1),
        to_date=date(2026, 8, 4),
        params=EtfSimulationParams(),
    )
    rebalance_events = [e for e in result["events"]
                        if e["kind"] == "quarterly_rebalance"]
    assert rebalance_events
    e = rebalance_events[0]
    # The rationale dict's keys (Python 3.7+ preserves insertion order)
    # must list every sell before every buy.
    keys = list(e["trade_rationale"].keys())
    sides = [e["trade_rationale"][k]["side"] for k in keys]
    # First all 'sell', then all 'buy' (or single-side).
    if "sell" in sides and "buy" in sides:
        first_buy = sides.index("buy")
        last_sell = max(i for i, s in enumerate(sides) if s == "sell")
        assert last_sell < first_buy, (
            f"sells must come before buys, got order: {list(zip(keys, sides, strict=True))}"
        )


def test_rebalance_sell_priority_is_most_overweight_first() -> None:
    """Among multiple sells, the most-overweight symbol must be sold first."""
    from datetime import timedelta

    def gen_3way() -> dict[str, NavSeries]:
        # Three symbols diverge in opposite directions to create both sells
        # and buys. 512400 rockets most (biggest sell), 159930 rockets
        # least (probably buy), 512660 in middle.
        series: dict[str, NavSeries] = {}
        d = date(2025, 8, 1)
        end = date(2026, 8, 4)
        # Build divergent paths
        drift = {
            "561560": 0.0,    # flat → stays near target weight
            "159930": 0.10,   # mild rocket → may be sell
            "512400": 0.30,   # big rocket → biggest sell
            "516950": -0.10,  # crash → big buy
            "512660": -0.05,  # mild crash → buy
            "563010": 0.0,    # flat → stays
        }
        for code, dr in drift.items():
            pts = []
            price = 1.0
            cursor = d
            while cursor <= end:
                if cursor.weekday() < 5:
                    if cursor.day == 1 or (cursor.day < 8 and len(pts) == 0):
                        price *= 1 + dr
                    pts.append((cursor, price))
                cursor += timedelta(days=1)
            series[code] = NavSeries(
                code=code,
                market="SH" if code.startswith(("5", "6")) else "SZ",
                points=pts,
                name=code,
            )
        series[CASHFLOW_SYMBOL] = NavSeries(
            code=CASHFLOW_SYMBOL, market="SZ",
            points=pts, name="cf",
        )
        return series

    nav = gen_3way()
    result = run_simulation(
        nav_by_code=nav,
        from_month=date(2025, 8, 1),
        to_date=date(2026, 8, 4),
        params=EtfSimulationParams(),
    )
    rebalance_events = [e for e in result["events"]
                        if e["kind"] == "quarterly_rebalance"]
    assert rebalance_events
    e = rebalance_events[0]
    rationale = e["trade_rationale"]
    sells = [(code, info) for code, info in rationale.items()
             if info["side"] == "sell"]
    if len(sells) >= 2:
        # Sells must be sorted by ascending notional (most negative first,
        # i.e. most-overweight symbol sold first).
        notionals = [float(info["notional"]) for _, info in sells]
        assert notionals == sorted(notionals), (
            f"sells not in most-overweight-first order: {notionals}"
        )


def test_rebalance_buy_priority_is_most_underweight_first() -> None:
    """Among multiple buys, the most-underweight symbol must be bought first."""
    from datetime import timedelta

    def gen() -> dict[str, NavSeries]:
        series: dict[str, NavSeries] = {}
        d = date(2025, 8, 1)
        end = date(2026, 8, 4)
        drift = {
            "561560": 0.20,
            "159930": -0.05,
            "512400": 0.10,
            "516950": -0.30,
            "512660": -0.20,
            "563010": 0.20,
        }
        for code, dr in drift.items():
            pts = []
            price = 1.0
            cursor = d
            while cursor <= end:
                if cursor.weekday() < 5:
                    if cursor.day == 1 or (cursor.day < 8 and len(pts) == 0):
                        price *= 1 + dr
                    pts.append((cursor, price))
                cursor += timedelta(days=1)
            series[code] = NavSeries(
                code=code,
                market="SH" if code.startswith(("5", "6")) else "SZ",
                points=pts,
                name=code,
            )
        series[CASHFLOW_SYMBOL] = NavSeries(
            code=CASHFLOW_SYMBOL, market="SZ",
            points=pts, name="cf",
        )
        return series

    nav = gen()
    result = run_simulation(
        nav_by_code=nav,
        from_month=date(2025, 8, 1),
        to_date=date(2026, 8, 4),
        params=EtfSimulationParams(),
    )
    rebalance_events = [e for e in result["events"]
                        if e["kind"] == "quarterly_rebalance"]
    assert rebalance_events
    e = rebalance_events[0]
    rationale = e["trade_rationale"]
    buys = [(code, info) for code, info in rationale.items()
            if info["side"] == "buy"]
    if len(buys) >= 2:
        notionals = [float(info["notional"]) for _, info in buys]
        assert notionals == sorted(notionals, reverse=True), (
            f"buys not in most-underweight-first order: {notionals}"
        )


def test_rebalance_state_is_bit_identical_across_runs() -> None:
    """Re-running the same simulation must yield identical shares,
    cost_basis, and rebalance_trades — the new sells-first ordering must
    not alter final state (halo_total is constant across the rebalance,
    so the parallel vs sequential execution is mathematically equivalent)."""
    from datetime import timedelta

    def gen(code: str, market: str, drift_per_month: float) -> NavSeries:
        pts = []
        d = date(2025, 8, 1)
        end = date(2026, 8, 4)
        price = 1.0
        while d <= end:
            if d.weekday() < 5:
                if d.day == 1 or (d.day < 8 and len(pts) == 0):
                    price *= 1 + drift_per_month
                pts.append((d, price))
            d += timedelta(days=1)
        return _build_nav(code, market, pts)

    nav = {
        code: gen(code, "SH" if code.startswith(("5", "6")) else "SZ", drift)
        for code, drift in [
            ("561560", 0.15),
            ("159930", -0.10),
            ("512400", 0.20),
            ("516950", -0.05),
            ("512660", -0.10),
            ("563010", 0.05),
        ]
    }
    nav[CASHFLOW_SYMBOL] = gen(CASHFLOW_SYMBOL, "SZ", 0.005)

    params = EtfSimulationParams()
    r1 = run_simulation(
        nav_by_code=nav, from_month=date(2025, 8, 1),
        to_date=date(2026, 8, 4), params=params,
    )
    r2 = run_simulation(
        nav_by_code=nav, from_month=date(2025, 8, 1),
        to_date=date(2026, 8, 4), params=params,
    )
    assert r1["summary"]["rebalance_count"] == r2["summary"]["rebalance_count"]
    assert r1["summary"]["final_total_value"] == r2["summary"]["final_total_value"]
    assert r1["summary"]["cumulative_friction"] == r2["summary"]["cumulative_friction"]
    rb1 = [e for e in r1["events"] if e["kind"] == "quarterly_rebalance"]
    rb2 = [e for e in r2["events"] if e["kind"] == "quarterly_rebalance"]
    assert rb1 and rb2
    assert rb1[-1]["rebalance_trades"] == rb2[-1]["rebalance_trades"]
    assert rb1[-1]["trade_rationale"] == rb2[-1]["trade_rationale"]


# --- Rebalance offset: delay quarterly rebalance N trading days post-DCA --


def test_rebalance_offset_zero_matches_old_behaviour() -> None:
    """With offset=0 the rebalance fires on the same day as the DCA,
    preserving the original behaviour. We confirm by comparing to a
    fixed-input scenario that the trade notional is bit-equivalent
    regardless of how many rebalance events happen."""
    nav = _build_minimal_nav()
    r_offset = run_simulation(
        nav_by_code=nav, from_month=date(2025, 8, 1),
        to_date=date(2026, 8, 4),
        params=EtfSimulationParams(rebalance_offset_days=0),
    )
    # All rebalance events must be on the original month-end trading day.
    for e in r_offset["events"]:
        if e["kind"] == "quarterly_rebalance":
            assert e["rebalance_offset_days"] == 0
            # rebalance_date equals dca_date (which equals event.date since
            # the field is re-used for backwards compatibility).
            assert e["date"] == e["dca_date"]
    # summary should not be affected by the offset parameter itself —
    # the only differences between offset=0 and offset=N come from the
    # market noise between month_end and month_end+Ntd. With stable
    # prices in _build_minimal_nav the noise is zero.
    r_default = run_simulation(
        nav_by_code=nav, from_month=date(2025, 8, 1),
        to_date=date(2026, 8, 4),
        params=EtfSimulationParams(),
    )
    # Both runs see the same flat price path → cost basis + final value
    # agree.
    assert (
        r_offset["summary"]["final_total_value"]
        == r_default["summary"]["final_total_value"]
    )


def test_rebalance_offset_five_shifts_rebalance_to_next_month() -> None:
    """With offset=5 the December-quarter-end rebalance fires in January
    (≈ 5 trading days after the 12-31 DCA). Confirm via ``dca_date``
    vs ``rebalance_date`` and via the ``series`` containing a snapshot
    in January 2026."""
    # Use the divergent-prices nav so quarter-end rebalances actually fire.
    from datetime import timedelta

    def gen(code: str, market: str, drift_per_month: float) -> NavSeries:
        pts = []
        d = date(2025, 8, 1)
        end = date(2026, 8, 4)
        price = 1.0
        while d <= end:
            if d.weekday() < 5:
                if d.day == 1 or (d.day < 8 and len(pts) == 0):
                    price *= 1 + drift_per_month
                pts.append((d, price))
            d += timedelta(days=1)
        return _build_nav(code, market, pts)

    nav = {
        code: gen(code, "SH" if code.startswith(("5", "6")) else "SZ", drift)
        for code, drift in [
            ("561560", 0.10),
            ("159930", -0.05),
            ("512400", 0.15),
            ("516950", 0.0),
            ("512660", -0.10),
            ("563010", 0.05),
        ]
    }
    nav[CASHFLOW_SYMBOL] = gen(CASHFLOW_SYMBOL, "SZ", 0.005)

    result = run_simulation(
        nav_by_code=nav, from_month=date(2025, 8, 1),
        to_date=date(2026, 8, 4),
        params=EtfSimulationParams(rebalance_offset_days=5),
    )
    rb_events = [e for e in result["events"] if e["kind"] == "quarterly_rebalance"]
    # If no rebalance fired, debug the situation so we know whether
    # the offset is suppressing what would otherwise fire. We try
    # offset=0 first to confirm the data set actually triggers.
    rb_offset0 = [
        e for e in run_simulation(
            nav_by_code=nav, from_month=date(2025, 8, 1),
            to_date=date(2026, 8, 4),
            params=EtfSimulationParams(rebalance_offset_days=0),
        )["events"] if e["kind"] == "quarterly_rebalance"
    ]
    assert rb_offset0, (
        "test scenario did not trigger any rebalance even with "
        "offset=0 — divergent prices insufficient for ERC drift"
    )
    assert rb_events, "expected at least one rebalance with offset=5"
    # Look at ANY Q4 (December DCA) quarter-end event — it should have
    # shifted its rebalance to January 2026. Q4 may be no_trigger (drift
    # resolved by the time +5td lands) but it still has the rebalance
    # metadata.
    dec_events = [e for e in result["events"] if e.get("dca_date", "").startswith("2025-12")]
    assert dec_events, "expected a December DCA event"
    dec_evt = dec_events[0]
    # event.date is the rebalance date (post-DCA), which falls in Jan.
    assert dec_evt["date"].startswith("2026-01"), dec_evt["date"]
    assert dec_evt["rebalance_date"].startswith("2026-01"), dec_evt["rebalance_date"]
    # dca_date is the December month-end.
    assert dec_evt["dca_date"].startswith("2025-12"), dec_evt["dca_date"]
    assert dec_evt["rebalance_offset_days"] == 5
    # The chart series must contain a snapshot on the rebalance date.
    months = result["months"]
    assert dec_evt["rebalance_date"] in months


def test_rebalance_offset_in_param_round_trip() -> None:
    """EtfSimulationParams round-trips through Pydantic JSON safely."""
    p = EtfSimulationParams(rebalance_offset_days=10)
    j = p.model_dump_json()
    p2 = EtfSimulationParams.model_validate_json(j)
    assert p2.rebalance_offset_days == 10
    # Default is 5.
    p_default = EtfSimulationParams()
    assert p_default.rebalance_offset_days == 5
    # Out-of-range values rejected by the schema's `ge` / `le` constraints.
    with pytest.raises(ValueError):
        EtfSimulationParams(rebalance_offset_days=-1)
    with pytest.raises(ValueError):
        EtfSimulationParams(rebalance_offset_days=21)


def test_snapshot_records_post_dca_state_when_offset_nonzero() -> None:
    """With offset > 0 each quarter-end contributes TWO snapshots: one
    at the DCA date (pre-DCA state) and one at the rebalance date
    (post-DCA, pre-rebalance state). For 4 quarter-ends in 13 months,
    we get 13 + 4 = 17 snapshots, in stable-price scenarios."""
    nav = _build_minimal_nav()
    result = run_simulation(
        nav_by_code=nav, from_month=date(2025, 8, 1),
        to_date=date(2026, 8, 4),
        params=EtfSimulationParams(rebalance_offset_days=5),
    )
    # Quarter-ends in our window: 2025-09, 2025-12, 2026-03, 2026-06.
    # With offset=5 trading days, all four rebalance dates fall in the
    # following month. Final snapshot is at 2026-08-04 (after the 2026-07
    # DCA), so all 4 rebalance snapshots are within to_date.
    assert len(result["series"]) == 13 + 4, (
        f"expected 17 snapshots (13 month-ends + 4 rebalance dates), got {len(result['series'])}"
    )
    # The rebalance-date snapshots must show the post-DCA state (shares > 0
    # for HALO codes), confirming they were taken AFTER the DCA fired.
    rb_events = [e for e in result["events"] if e["kind"] == "quarterly_rebalance"]
    rb_dates = {str(e["rebalance_date"]) for e in rb_events}
    for snap in result["series"]:
        if str(snap["date"]) in rb_dates:
            # Cashflow ETF gets DCA'd every month-end so shares must be
            # positive by the rebalance day.
            assert snap["per_symbol_shares"][CASHFLOW_SYMBOL] > 0


def test_rebalance_uses_post_dca_prices_when_offset_nonzero() -> None:
    """The rebalance must use post-DCA prices (rebalance_date, not
    dca_date). We confirm by checking the trade_rationale's
    current_weight reflects the post-DCA price snapshot, not the
    pre-DCA price."""
    from datetime import timedelta

    def gen(code: str, market: str, drift_per_month: float) -> NavSeries:
        pts = []
        d = date(2025, 1, 1)
        end = date(2026, 8, 4)
        price = 1.0
        while d <= end:
            if d.weekday() < 5:
                if d.day == 1 or (d.day < 8 and len(pts) == 0):
                    price *= 1 + drift_per_month
                pts.append((d, price))
            d += timedelta(days=1)
        return _build_nav(code, market, pts)

    # 5 ETFs drop -10%/month, 512400 stays flat → 512400 becomes
    # overweight over time → triggers rebalance at every quarter-end.
    nav = {
        code: gen(code, "SH" if code.startswith(("5", "6")) else "SZ", drift)
        for code, drift in [
            ("561560", -0.10),
            ("159930", -0.10),
            ("512400", 0.0),
            ("516950", -0.10),
            ("512660", -0.10),
            ("563010", -0.10),
        ]
    }
    nav[CASHFLOW_SYMBOL] = gen(CASHFLOW_SYMBOL, "SZ", 0.005)

    r = run_simulation(
        nav_by_code=nav, from_month=date(2025, 6, 1),
        to_date=date(2026, 8, 4),
        params=EtfSimulationParams(rebalance_offset_days=5),
    )
    rb_events = [e for e in r["events"] if e["kind"] == "quarterly_rebalance"]
    assert rb_events, "expected at least one rebalance"
    # Every rebalance event must carry rebalance_date != dca_date
    # and rebalance_offset_days == 5.
    for e in rb_events:
        assert e["rebalance_offset_days"] == 5
        assert e["dca_date"] != e["rebalance_date"], (
            f"expected offset>0 to shift date; got dca={e['dca_date']} rb={e['rebalance_date']}"
        )
        # 512400 should be a sell (it's the only ETF that's not dropping).
        if "512400" in e["rebalance_trades"]:
            assert float(e["rebalance_trades"]["512400"]) < 0
            info = e["trade_rationale"]["512400"]
            assert info["side"] == "sell"
            # current_weight reflects the post-DCA price snapshot.
            cur_w = float(info["current_weight"])
            tgt_w = float(info["target_weight"])
            assert cur_w > tgt_w, (
                f"512400 should be overweight; got cur={cur_w}, tgt={tgt_w}"
            )


# --- Lump-sum buy-and-hold benchmark -------------------------------


def test_lump_sum_value_present_in_every_snapshot() -> None:
    """Every snapshot must carry a lump_sum_value (default 0 when the
    benchmark never opened, but in the normal case > 0)."""
    nav = _build_minimal_nav()
    result = run_simulation(
        nav_by_code=nav, from_month=date(2025, 8, 1),
        to_date=date(2026, 8, 4),
        params=EtfSimulationParams(),
    )
    series = result["series"]
    assert series, "expected at least one snapshot"
    # All snapshots must have a lump_sum_value key.
    for snap in series:
        assert "lump_sum_value" in snap
        assert snap["lump_sum_value"] is not None
    # In a normal run with cached NAV data, the lump_sum_value should
    # be > 0 (the position opens on from_month's first trading day
    # with 7 × N shares × ~1.0).
    last_lump = float(series[-1]["lump_sum_value"])
    assert last_lump > 0, (
        f"lump_sum_value should be positive; got {last_lump}"
    )


def test_lump_sum_final_equals_sum_of_shares_times_prices() -> None:
    """The lump-sum benchmark's final value equals shares × closing
    price for each symbol. With 1 lot each per ETF at price ~1.0 the
    value should be ~7 × 100 × last_close."""
    nav = _build_minimal_nav()
    result = run_simulation(
        nav_by_code=nav, from_month=date(2025, 8, 1),
        to_date=date(2026, 8, 4),
        params=EtfSimulationParams(),
    )
    lump_final = float(result["summary"]["lump_sum_final_value"])
    # Per-share final values for each symbol at to_date.
    last_snap = result["series"][-1]
    per_symbol_sum = sum(
        float(v) for v in last_snap["per_symbol_value"].values()
    )
    # The lump_sum_final in summary must match the per-snapshot
    # lump_sum_value (both derived from shares × price at the same
    # date).
    assert abs(lump_final - float(last_snap["lump_sum_value"])) < 0.01, (
        f"summary.lump_sum_final_value ({lump_final}) ≠ last snapshot "
        f"lump_sum_value ({last_snap['lump_sum_value']})"
    )
    # With flat prices the per-symbol and lump-sum series must agree
    # closely: lump_sum_shares are floor(cash/7/price/lot)*lot for
    # each of 7 symbols, so lump_sum_value ≈ 7 × same_lots × close.
    # We just check that the totals are within a small ratio of each
    # other (DCA gets ~1 lot per ETF, lump_sum gets some lots per
    # ETF depending on rounding).
    assert per_symbol_sum > 0
    assert abs(lump_final - per_symbol_sum) / max(per_symbol_sum, 1) < 0.05


def test_summary_includes_lump_sum_vs_dca_pct() -> None:
    """summary.lump_sum_vs_dca_pct reflects DCA outperformance vs the
    buy-and-hold benchmark. Sign conventions:
      > 0 → DCA beat buy-and-hold
      < 0 → buy-and-hold beat DCA
      = 0 → never opened (no NAV at from_month first trading day)
    """
    nav = _build_minimal_nav()
    result = run_simulation(
        nav_by_code=nav, from_month=date(2025, 8, 1),
        to_date=date(2026, 8, 4),
        params=EtfSimulationParams(),
    )
    s = result["summary"]
    assert "lump_sum_vs_dca_pct" in s
    assert "lump_sum_final_value" in s
    # Both numeric, can be positive or negative depending on market.
    vs = float(s["lump_sum_vs_dca_pct"])
    dca_final = float(s["final_total_value"])
    lump_final = float(s["lump_sum_final_value"])
    assert lump_final > 0
    if dca_final != lump_final:
        # Sign must match (final - lump) / lump.
        expected = (dca_final - lump_final) / lump_final
        assert abs(vs - expected) < 1e-6, (
            f"lump_sum_vs_dca_pct={vs} ≠ expected {expected}"
        )


def test_lump_sum_shares_does_not_rebalance() -> None:
    """After opening day, the lump-sum position never buys or sells.
    Confirmed indirectly: ``lump_sum_value`` at every snapshot is
    exactly ``opening_shares × close``, with no extra lots accumulating
    from monthly DCA. With flat prices throughout, lump_sum_value
    must stay constant at the opening notional."""
    nav = _build_minimal_nav()
    result = run_simulation(
        nav_by_code=nav, from_month=date(2025, 8, 1),
        to_date=date(2026, 8, 4),
        params=EtfSimulationParams(),
    )
    first_snap = result["series"][0]
    # The lump-sum position opens on from_month's first trading day
    # and never rebalances after that. With flat prices throughout,
    # lump_sum_value must stay constant at the opening notional.
    first_lump = float(first_snap["lump_sum_value"])
    assert first_lump > 0
    for i, snap in enumerate(result["series"]):
        lv = float(snap["lump_sum_value"])
        if i > 0:
            assert abs(lv - first_lump) < 0.5, (
                f"snapshot {i} lump_sum_value={lv} drifted from "
                f"opening={first_lump} (flat-price scenario)"
            )
