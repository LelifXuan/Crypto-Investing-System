"""Tests for the ETF 资金投入 strategy simulation (定稿 2026-08-06).

Covers:
- Fixed target weights (表1) + per-symbol bandwidth derivation
- run_simulation: initial build at target weights + whole-lot/cash constraints
- run_simulation: monthly DCA only-buys, under-allocated first, HOLD rollover
- run_simulation: quarter-end bandwidth review, sells-then-buys rebalance
- New return convention: cash-on-cash on invested capital
- Universe fixed at 6 ETFs (no cashflow ETF, no 159201)
- Invalid input validation + empty-state envelope
"""

from __future__ import annotations

from datetime import date, timedelta, timezone
from decimal import Decimal
from itertools import pairwise

import pytest

from app.schemas.etf_simulation import (
    DEFAULT_BANDWIDTHS,
    DEFAULT_TARGET_WEIGHTS,
    EtfSimulationParams,
)
from app.services.ashare_etf_simulation import (
    ALL_HALO_CODES,
    NavSeries,
    _bandwidth_for,
    _buy_underallocated,
    _month_end_trading_day,
    _target_shares,
    run_simulation,
)

UTC = timezone.utc


def _build_nav(code: str, market: str, points: list[tuple[date, float]]) -> NavSeries:
    return NavSeries(code=code, market=market, points=points, name=code)


# --- Fixed target weights (表1, 定稿 2026-08-06) -------------------------


def test_default_target_weights_sum_to_one() -> None:
    total = sum(DEFAULT_TARGET_WEIGHTS.values())
    assert total == pytest.approx(Decimal("1.0"), abs=Decimal("0.0001"))
    assert set(DEFAULT_TARGET_WEIGHTS) == set(ALL_HALO_CODES)


def test_default_target_weights_match_document_table() -> None:
    """表1 weights: 电力25.00 / 能源18.98 / 有色10.59 / 基建19.08 /
    军工14.35 / 电信12.00 (%)."""
    expected = {
        "561560": Decimal("0.2500"),
        "159930": Decimal("0.1898"),
        "512400": Decimal("0.1059"),
        "516950": Decimal("0.1908"),
        "512660": Decimal("0.1435"),
        "563010": Decimal("0.1200"),
    }
    for code, w in expected.items():
        assert DEFAULT_TARGET_WEIGHTS[code] == pytest.approx(w, abs=Decimal("0.0001"))


def test_per_symbol_bandwidth_matches_document_table() -> None:
    """有效带宽 = max(目标权重×20%, 2.5pp) → 5.00 / ≈3.80 / 2.50 / ≈3.82 /
    ≈2.87 / 2.50 (%)."""
    params = EtfSimulationParams()
    for code in ALL_HALO_CODES:
        bw = _bandwidth_for(code, params)
        assert bw == pytest.approx(DEFAULT_BANDWIDTHS[code], abs=Decimal("0.0002")), code
    # 电力(25%) lands on 5.00pp; 有色/电信 (small weights) land on the 2.5pp floor.
    assert _bandwidth_for("561560", params) == Decimal("0.0500")
    assert _bandwidth_for("512400", params) == Decimal("0.0250")
    assert _bandwidth_for("563010", params) == Decimal("0.0250")


def test_bandwidth_floor_and_pct_are_parametrised() -> None:
    params = EtfSimulationParams(bandwidth_pct=Decimal("0.10"), bandwidth_floor_pp=Decimal("0.03"))
    # 电力: 25% × 10% = 2.5pp < 3pp floor → 3pp
    assert _bandwidth_for("561560", params) == Decimal("0.0300")
    # 能源: 18.98% × 10% = 1.9pp < 3pp floor → 3pp
    assert _bandwidth_for("159930", params) == Decimal("0.0300")


# --- _month_end_trading_day -----------------------------------------------


def test_month_end_trading_day_returns_last_available_date() -> None:
    nav = {date(2025, 8, 29): 1.0, date(2025, 8, 28): 0.99}
    assert _month_end_trading_day(date(2025, 8, 1), nav) == date(2025, 8, 29)


def test_month_end_trading_day_empty_returns_none() -> None:
    assert _month_end_trading_day(date(2025, 8, 1), {}) is None


def test_month_end_trading_day_handles_december_rollover() -> None:
    nav = {date(2025, 12, 31): 1.0, date(2026, 1, 2): 1.0}
    assert _month_end_trading_day(date(2025, 12, 1), nav) == date(2025, 12, 31)


# --- run_simulation ------------------------------------------------------


def _build_minimal_nav(
    base: float = 1.0,
    end: date = date(2026, 8, 4),
    start: date = date(2025, 8, 1),
) -> dict[str, NavSeries]:
    """Build ~13 months of flat daily NAV for the 6 HALO symbols."""
    def gen(code: str, market: str) -> NavSeries:
        pts = []
        d = start
        while d <= end:
            if d.weekday() < 5:
                pts.append((d, base))
            d += timedelta(days=1)
        return _build_nav(code, market, pts)

    return {
        "561560": gen("561560", "SH"),
        "159930": gen("159930", "SZ"),
        "512400": gen("512400", "SH"),
        "516950": gen("516950", "SH"),
        "512660": gen("512660", "SH"),
        "563010": gen("563010", "SH"),
    }


def test_run_simulation_universe_is_six_etfs() -> None:
    """The strategy universe is FIXED at 6 ETFs — no cashflow ETF (159201)
    appears anywhere in events or snapshots."""
    nav = _build_minimal_nav()
    result = run_simulation(
        nav_by_code=nav,
        from_month=date(2025, 8, 1),
        to_date=date(2026, 8, 4),
        params=EtfSimulationParams(),
    )
    assert set(nav) == set(ALL_HALO_CODES)
    for snap in result["series"]:
        assert set(snap["per_symbol_shares"]) == set(ALL_HALO_CODES)
    for e in result["events"]:
        assert "159201" not in e["halo_dca"]
        assert "159201" not in e["dca_trades"]


def test_first_snapshot_is_zero_return_cost_anchor() -> None:
    """The very first snapshot lands on the initial-build trading day (the
    user's 起始日) and its cash-on-cash return is pinned to 0 — the curve
    starts exactly at 0%, never a synthetic negative from same-day fees."""
    nav = _build_minimal_nav()
    result = run_simulation(
        nav_by_code=nav,
        from_month=date(2025, 8, 1),
        to_date=date(2026, 8, 4),
        params=EtfSimulationParams(),
    )
    anchor = result["series"][0]
    # Anchor date = first trading day of from_month (2025-08-01 is a Friday).
    assert anchor["date"] == "2025-08-01"
    assert Decimal(anchor["return_pct"]) == 0
    assert Decimal(anchor["lump_sum_return_pct"]) == 0
    # total_value is the REAL mark-to-market (fees already paid), cost is
    # the invested capital — identical for the anchor by construction.
    assert Decimal(anchor["cost_value"]) == Decimal("100000")
    # The honest fees-only dip appears on the NEXT snapshot, not the start.
    second = result["series"][1]
    assert Decimal(second["return_pct"]) < 0


def test_run_simulation_applies_initial_build_at_target_weights() -> None:
    """The first snapshot is the initial-build DAY (cost anchor, return 0);
    the second snapshot is the first month-end after the first DCA. Both
    reflect the target-weight whole-lot build (spec §2.1/§6)."""
    nav = _build_minimal_nav()
    result = run_simulation(
        nav_by_code=nav,
        from_month=date(2025, 8, 1),
        to_date=date(2026, 8, 4),
        params=EtfSimulationParams(),
    )
    anchor = result["series"][0]
    # Anchor: the day money was deployed — cost = initial_capital only,
    # return pinned to 0, whole-lot shares at the target weights.
    assert Decimal(anchor["cost_value"]) == Decimal("100000")
    assert Decimal(anchor["return_pct"]) == 0
    assert Decimal(anchor["cash_value"]) < Decimal("110")  # < one 100-share lot at ¥1
    for code in ALL_HALO_CODES:
        shares = int(anchor["per_symbol_shares"][code])
        assert shares % 100 == 0, code
        target_lots = float(DEFAULT_TARGET_WEIGHTS[code]) * 100000 / 100.0
        # Whole-lot + greedy under-allocation buying may leave the LAST
        # symbol up to ~3 lots short when cash runs out mid-build (the
        # first monthly DCA tops it up the same month).
        assert abs(shares / 100 - target_lots) <= 3.0, (
            f"{code} shares={shares} far from target {target_lots} lots"
        )
    # First month-end: after the first monthly DCA (cost +5000).
    first_month_end = result["series"][1]
    assert Decimal(first_month_end["cost_value"]) == Decimal("105000")


def test_run_simulation_monthly_dca_increases_invested_capital() -> None:
    """Each calendar month books ``period_amount`` into invested capital;
    cost_value = initial + period_amount × periods elapsed."""
    nav = _build_minimal_nav()
    result = run_simulation(
        nav_by_code=nav,
        from_month=date(2025, 8, 1),
        to_date=date(2026, 8, 4),
        params=EtfSimulationParams(),  # default period_amount=5000
    )
    assert len(result["events"]) == 13
    # 13 months × 5000 + 100000 initial = 165000
    assert Decimal(result["summary"]["final_cost_value"]) == Decimal("165000")
    # Every event records the cash contribution.
    for e in result["events"]:
        assert Decimal(e["dca_cash_added"]) == Decimal("5000")


def test_run_simulation_dca_only_buys_no_sells() -> None:
    """Regular DCA never sells: rebalance_trades stays empty and shares only
    grow between snapshots when no quarter-end rebalance fired."""
    nav = _build_minimal_nav()
    result = run_simulation(
        nav_by_code=nav,
        from_month=date(2025, 8, 1),
        to_date=date(2026, 8, 4),
        params=EtfSimulationParams(),
    )
    for e in result["events"]:
        if e["kind"] == "monthly_dca_only":
            assert e["rebalance_trades"] == {}
            assert e["sell_count"] == 0
        # shares never decrease for any symbol when there was no rebalance
    series = result["series"]
    for code in ALL_HALO_CODES:
        shares = [int(s["per_symbol_shares"][code]) for s in series]
        # monotone non-decreasing
        for prev, nxt in pairwise(shares):
            assert nxt >= prev, f"{code} shares decreased without a rebalance"


def test_run_simulation_dca_prioritises_underallocated() -> None:
    """With a custom target-weight dict that heavily favours one symbol, the
    DCA top-ups flow to that symbol first (欠配优先, spec §4)."""
    nav = _build_minimal_nav()
    weights = dict(DEFAULT_TARGET_WEIGHTS)
    weights["561560"] = Decimal("0.60")  # bulk of the portfolio
    weights["563010"] = Decimal("0.12")
    weights["159930"] = Decimal("0.07")
    weights["512400"] = Decimal("0.07")
    weights["516950"] = Decimal("0.07")
    weights["512660"] = Decimal("0.07")
    params = EtfSimulationParams(target_weights=weights)
    result = run_simulation(
        nav_by_code=nav,
        from_month=date(2025, 8, 1),
        to_date=date(2026, 8, 4),
        params=params,
    )
    # 561560 (60% target) must end up with the largest share count.
    last = result["series"][-1]
    shares_561560 = int(last["per_symbol_shares"]["561560"])
    for code in ALL_HALO_CODES:
        if code == "561560":
            continue
        assert shares_561560 > int(last["per_symbol_shares"][code]) * 2, code


def test_run_simulation_monthly_zero_means_no_dca() -> None:
    """period_amount=0 → only the initial build fires; DCA trades empty;
    invested capital stays at initial_capital."""
    nav = _build_minimal_nav()
    result = run_simulation(
        nav_by_code=nav,
        from_month=date(2025, 8, 1),
        to_date=date(2026, 8, 4),
        params=EtfSimulationParams(period_amount=Decimal("0")),
    )
    for e in result["events"]:
        assert e["dca_trades"] == {}
        assert Decimal(e["dca_cash_added"]) == Decimal("0")
    assert Decimal(result["summary"]["final_cost_value"]) == Decimal("100000")


def test_run_simulation_holds_cash_when_lot_unaffordable() -> None:
    """When the monthly amount can't afford one whole lot, DCA emits no
    trades and the cash rolls to the next period (spec §4.4).

    Price ¥5.0 → one lot costs 500×1.001 + max(500×0.00025, 5) ≈ 505.50.
    With period_amount=50 no month can afford a whole lot, so every DCA
    holds and the cash balance grows monotonically across the window.
    """
    nav = _build_minimal_nav(base=5.0)
    result = run_simulation(
        nav_by_code=nav,
        from_month=date(2025, 8, 1),
        to_date=date(2026, 8, 4),
        params=EtfSimulationParams(period_amount=Decimal("50")),
    )
    events = result["events"]
    for e in events:
        assert e["dca_trades"] == {}, "no whole lot affordable → HOLD"
    cash_values = [Decimal(p["cash_value"]) for p in result["series"]]
    # 周定投一直买不起一手 → 现金滚存;但季末加码(quarterly_topup,2026-08-11
    # 方案 A)会在现金累积够一手时把欠配符号补买至目标权重,部署滚存的现金。
    # 因此现金在加码季末会回落,而非单调递增。
    for e in events:
        if e["kind"] == "quarterly_topup":
            assert e["sell_count"] == 0
            assert e["buy_count"] >= 1
            assert all(Decimal(str(v)) > 0 for v in e["rebalance_trades"].values())
    assert cash_values[-1] >= Decimal("0")


def test_run_simulation_rebalances_at_quarter_end_when_drift_exceeds_bandwidth() -> None:
    """Divergent prices push weights outside their per-symbol bandwidth and
    the quarter-end review fires: sells happen BEFORE buys, and the event
    records per-symbol rationale."""
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
        "561560": gen("561560", "SH", 0.10),
        "159930": gen("159930", "SZ", -0.05),
        "512400": gen("512400", "SH", 0.15),
        "516950": gen("516950", "SH", 0.0),
        "512660": gen("512660", "SH", -0.10),
        "563010": gen("563010", "SH", 0.05),
    }
    result = run_simulation(
        nav_by_code=nav,
        from_month=date(2025, 8, 1),
        to_date=date(2026, 8, 4),
        params=EtfSimulationParams(),
    )
    assert result["summary"]["rebalance_count"] >= 1
    rebalances = [e for e in result["events"] if e["kind"] == "quarterly_rebalance"]
    assert rebalances
    # With band-corridor DCA the first trigger is often a deficit-corridor
    # top-up (only buys); a divergent market must also produce a sell-side
    # rebalance somewhere in the window — 512400 growing +15%/month pushes
    # it past the upper band, triggering a sell of the overweight ETF.
    assert any(e["sell_count"] >= 1 for e in rebalances), (
        "a divergent rally must eventually trip a sell-side rebalance"
    )
    sell_rebalance = next(e for e in rebalances if e["sell_count"] >= 1)
    e = sell_rebalance
    assert Decimal(e["friction_cost"]) > Decimal("0")
    rationale = e["trade_rationale"]
    # Sells are recorded before buys in the rationale insertion order.
    sides = [info["side"] for info in rationale.values()]
    if "sell" in sides and "buy" in sides:
        last_sell = max(i for i, s in enumerate(sides) if s == "sell")
        first_buy = sides.index("buy")
        assert last_sell < first_buy
    # Drift_pct = |target − current| per symbol.
    for _, info in rationale.items():
        assert abs(float(info["drift_pct"]) - abs(
            float(info["target_weight"]) - float(info["current_weight"])
        )) < 0.001


def test_run_simulation_flat_market_never_sells() -> None:
    """Flat prices → no symbol ever crosses the UPPER band, so quarter-end
    reviews never sell (spec §5.4). Band-corridor DCA may still top up a
    deficit-corridor drift (rolled cash dilutes weights), but the review
    must never emit a sell."""
    nav = _build_minimal_nav()
    result = run_simulation(
        nav_by_code=nav,
        from_month=date(2025, 8, 1),
        to_date=date(2026, 8, 4),
        params=EtfSimulationParams(),
    )
    kinds = {e["kind"] for e in result["events"]}
    assert kinds <= {"monthly_dca_only", "no_trigger", "quarterly_rebalance", "quarterly_topup"}
    for e in result["events"]:
        if e["kind"] in ("quarterly_rebalance", "quarterly_topup"):
            assert e["sell_count"] == 0, "flat market must never sell"
        if e["kind"] == "quarterly_topup":
            # 季末加码 (2026-08-11 方案 A): 纯买入,欠配符号补买至目标权重。
            assert e["buy_count"] >= 1
            assert all(Decimal(str(v)) > 0 for v in e["rebalance_trades"].values())
        elif e["kind"] == "no_trigger":
            assert e["sell_count"] == 0
            assert e["rebalance_trades"] == {}


def test_run_simulation_offset_shifts_rebalance_to_next_month() -> None:
    """With rebalance_offset_days=5 the December quarter-end review fires in
    January (≈5 trading days after the 12-31 DCA) — 当日或随后 1–2 交易日
    per spec §5.6, we support up to 5 via the input."""
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
        "561560": gen("561560", "SH", 0.10),
        "159930": gen("159930", "SZ", -0.05),
        "512400": gen("512400", "SH", 0.15),
        "516950": gen("516950", "SH", 0.0),
        "512660": gen("512660", "SH", -0.10),
        "563010": gen("563010", "SH", 0.05),
    }
    result = run_simulation(
        nav_by_code=nav,
        from_month=date(2025, 8, 1),
        to_date=date(2026, 8, 4),
        params=EtfSimulationParams(rebalance_offset_days=5),
    )
    dec_events = [e for e in result["events"] if str(e["dca_date"]).startswith("2025-12")]
    assert dec_events
    dec = dec_events[0]
    # The December DCA's bandwidth review lands in January 2026.
    assert str(dec["date"]).startswith("2026-01"), dec["date"]
    assert dec["rebalance_offset_days"] == 5
    # offset=0 keeps the review on the DCA day.
    r0 = run_simulation(
        nav_by_code=nav,
        from_month=date(2025, 8, 1),
        to_date=date(2026, 8, 4),
        params=EtfSimulationParams(rebalance_offset_days=0),
    )
    for e in r0["events"]:
        assert e["date"] == e["dca_date"]


# --- Return convention ---------------------------------------------------


def test_return_pct_is_cash_on_cash_on_invested_capital() -> None:
    """return_pct = (total_value − invested) / invested. The initial-build
    DAY is the cost anchor: its return is pinned to exactly 0 (reference
    origin). The FIRST MONTH-END then shows the honest fees-only drag
    (slightly negative with flat prices)."""
    nav = _build_minimal_nav()
    result = run_simulation(
        nav_by_code=nav,
        from_month=date(2025, 8, 1),
        to_date=date(2026, 8, 4),
        params=EtfSimulationParams(),
    )
    anchor = result["series"][0]
    assert Decimal(anchor["return_pct"]) == 0
    assert Decimal(anchor["lump_sum_return_pct"]) == 0
    # First month-end: invested = 105000, value = 105000 − fees → small dip.
    first_month_end = result["series"][1]
    assert Decimal(first_month_end["return_pct"]) < 0
    assert Decimal(first_month_end["return_pct"]) > Decimal("-0.005")  # fees-only drag
    # Check the identity: return_pct ≈ (total − cost) / cost (quantised to
    # 0.0001, so allow ±0.0001 for the 4-decimal rounding) on a non-anchor
    # snapshot.
    snap = result["series"][-1]
    expected = (Decimal(snap["total_value"]) - Decimal(snap["cost_value"])) / Decimal(
        snap["cost_value"]
    )
    assert abs(Decimal(snap["return_pct"]) - expected) < Decimal("0.0001")


def test_return_pct_negative_when_price_drops() -> None:
    """A 5%/month price drop drives the cash-on-cash return clearly
    negative as the market value falls behind invested capital."""
    def gen(code: str, market: str, drift: float) -> NavSeries:
        pts = []
        d = date(2025, 8, 1)
        end = date(2026, 8, 4)
        price = 1.0
        while d <= end:
            if d.weekday() < 5:
                if d.day == 1 or (d.day < 8 and len(pts) == 0):
                    price *= 1 + drift
                pts.append((d, price))
            d += timedelta(days=1)
        return _build_nav(code, market, pts)

    nav = {c: gen(c, "SH" if c.startswith(("5", "6")) else "SZ", -0.05)
           for c in ALL_HALO_CODES}
    result = run_simulation(
        nav_by_code=nav,
        from_month=date(2025, 8, 1),
        to_date=date(2026, 8, 4),
        params=EtfSimulationParams(),
    )
    assert Decimal(result["series"][-1]["return_pct"]) < Decimal("-0.05")


# --- Buy-and-hold benchmark ----------------------------------------------


def test_lump_sum_benchmark_present() -> None:
    nav = _build_minimal_nav()
    result = run_simulation(
        nav_by_code=nav,
        from_month=date(2025, 8, 1),
        to_date=date(2026, 8, 4),
        params=EtfSimulationParams(),
    )
    series = result["series"]
    assert series
    for snap in series:
        assert "lump_sum_value" in snap
        assert "lump_sum_return_pct" in snap
    assert float(series[-1]["lump_sum_value"]) > 0


def test_summary_includes_final_cash_and_lump_sum_vs_dca() -> None:
    nav = _build_minimal_nav()
    result = run_simulation(
        nav_by_code=nav,
        from_month=date(2025, 8, 1),
        to_date=date(2026, 8, 4),
        params=EtfSimulationParams(),
    )
    s = result["summary"]
    assert "final_cash_value" in s
    assert "lump_sum_vs_dca_pct" in s
    assert Decimal(s["final_cash_value"]) >= 0
    # Cash-on-cash total return identity on the summary too.
    expected = (Decimal(s["final_total_value"]) - Decimal(s["final_cost_value"])) / Decimal(
        s["final_cost_value"]
    )
    assert abs(Decimal(s["total_return_pct"]) - expected) < Decimal("0.00001")


# --- Validation -----------------------------------------------------------


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
    del nav["561560"]
    with pytest.raises(ValueError, match="missing NAV for HALO"):
        run_simulation(
            nav_by_code=nav,
            from_month=date(2025, 8, 1),
            to_date=date(2026, 8, 4),
            params=EtfSimulationParams(),
        )


def test_run_simulation_rejects_weights_not_summing_to_one() -> None:
    nav = _build_minimal_nav()
    weights = dict(DEFAULT_TARGET_WEIGHTS)
    weights["561560"] = Decimal("0.30")
    with pytest.raises(ValueError, match="sum to 1"):
        run_simulation(
            nav_by_code=nav,
            from_month=date(2025, 8, 1),
            to_date=date(2026, 8, 4),
            params=EtfSimulationParams(target_weights=weights),
        )


def test_run_simulation_rejects_unknown_target_weight_codes() -> None:
    nav = _build_minimal_nav()
    with pytest.raises(ValueError, match="unknown target-weight codes"):
        run_simulation(
            nav_by_code=nav,
            from_month=date(2025, 8, 1),
            to_date=date(2026, 8, 4),
            params=EtfSimulationParams(
                target_weights={"999999": Decimal("1.0")}
            ),
        )


def test_run_simulation_rejects_bad_params_through_schema() -> None:
    # Negative monthly amount, zero initial capital, out-of-range offset.
    with pytest.raises(ValueError):
        EtfSimulationParams(period_amount=Decimal("-1"))
    with pytest.raises(ValueError):
        EtfSimulationParams(initial_capital=Decimal("0"))
    with pytest.raises(ValueError):
        EtfSimulationParams(rebalance_offset_days=6)
    with pytest.raises(ValueError):
        EtfSimulationParams(rebalance_offset_days=-1)


def test_run_simulation_returns_empty_envelope_when_all_series_empty() -> None:
    nav_by_code = {
        c: NavSeries(code=c, market="SH", points=[], name=None)
        for c in ALL_HALO_CODES
    }
    result = run_simulation(
        nav_by_code=nav_by_code,
        from_month=date(2025, 1, 1),
        to_date=date(2026, 8, 4),
        params=EtfSimulationParams(),
    )
    assert result["series"] == []
    assert result["events"] == []
    assert result["months"] == []
    assert result["meta"]["coverage_start"] == "2025-01-01"
    assert result["meta"]["coverage_end"] == "2026-08-04"
    assert result["meta"]["source_status"] == "unavailable"
    assert result["meta"]["halos_listing_start"] is None
    assert result["summary"]["months_simulated"] == 0
    assert float(result["summary"]["final_total_value"]) == 0.0


def test_run_simulation_meta_halos_listing_start_with_staggered_data() -> None:
    """halos_listing_start = MAX of all HALO symbols' earliest data point."""
    def gen(code: str, market: str, start_offset_days: int) -> NavSeries:
        pts = []
        d0 = date(2025, 1, 1) + timedelta(days=start_offset_days)
        d = d0
        end = date(2025, 6, 1)
        while d <= end:
            if d.weekday() < 5:
                pts.append((d, 1.0))
            d += timedelta(days=1)
        return _build_nav(code, market, pts)

    nav = {
        "561560": gen("561560", "SH", 0),
        "159930": gen("159930", "SZ", 60),
        "512400": gen("512400", "SH", 60),
        "516950": gen("516950", "SH", 60),
        "512660": gen("512660", "SH", 60),
        "563010": gen("563010", "SH", 60),
    }
    result = run_simulation(
        nav_by_code=nav,
        from_month=date(2025, 1, 1),
        to_date=date(2025, 6, 1),
        params=EtfSimulationParams(),
    )
    assert result["meta"]["halos_listing_start"] == "2025-03-03"


def test_halos_listing_start_is_first_day_all_symbols_present() -> None:
    """halos_listing_start = the FIRST trading day present in ALL six
    series — NOT the max of each symbol's first date. When a symbol's
    history has a gap after its listing day, the max of first-dates lands
    on a day where that symbol is missing, under-shooting the real start."""
    def gen_all(code: str, market: str) -> NavSeries:
        # Every symbol trades from 2025-01-03 onward (weekdays).
        pts = []
        d = date(2025, 1, 3)
        end = date(2025, 3, 1)
        while d <= end:
            if d.weekday() < 5:
                pts.append((d, 1.0))
            d += timedelta(days=1)
        return _build_nav(code, market, pts)

    # 561560 lists EARLIEST (01-01/01-02) but then has a gap 01-03..01-09,
    # resuming 01-10 (the day every symbol finally has data).
    pts_561560 = [
        (date(2025, 1, 1), 1.0),
        (date(2025, 1, 2), 1.0),
    ]
    d = date(2025, 1, 10)
    while d <= date(2025, 3, 1):
        if d.weekday() < 5:
            pts_561560.append((d, 1.0))
        d += timedelta(days=1)

    nav = {
        "561560": _build_nav("561560", "SH", pts_561560),
        "159930": gen_all("159930", "SZ"),
        "512400": gen_all("512400", "SH"),
        "516950": gen_all("516950", "SH"),
        "512660": gen_all("512660", "SH"),
        "563010": gen_all("563010", "SH"),
    }
    result = run_simulation(
        nav_by_code=nav,
        from_month=date(2025, 1, 1),
        to_date=date(2025, 3, 1),
        params=EtfSimulationParams(),
    )
    # max(first-date) would be 2025-01-03 (the other five symbols' first
    # day), but 561560 has no bar that day → the true all-present day is
    # 2025-01-10 (when 561560 resumes and every symbol has data).
    assert result["meta"]["halos_listing_start"] == "2025-01-10"


def test_run_simulation_decimal_end_to_end() -> None:
    nav = _build_minimal_nav()
    result = run_simulation(
        nav_by_code=nav,
        from_month=date(2025, 8, 1),
        to_date=date(2026, 8, 4),
        params=EtfSimulationParams(),
    )
    for s in result["series"]:
        Decimal(s["total_value"])
        Decimal(s["cost_value"])
        Decimal(s["cash_value"])
    for e in result["events"]:
        Decimal(e["dca_cash_added"])
        for _, v in e["dca_trades"].items():
            Decimal(v)
        for _, v in e["rebalance_trades"].items():
            Decimal(v)


# --- Weekly DCA frequency (说明书 §2.2 / 表0) ----------------------------


def test_funding_dates_weekly_last_trading_day_of_each_week() -> None:
    """Weekly funding = the last trading day of every calendar week whose
    week-end falls inside the month; a week spilling into the next month
    is counted in the next month's iteration."""
    from app.services.ashare_etf_simulation import _funding_dates_in_month

    cal = {
        d: None
        for d in [
            date(2026, 3, 2), date(2026, 3, 6), date(2026, 3, 13),
            date(2026, 3, 20), date(2026, 3, 27), date(2026, 3, 31),
        ]
    }
    weekly = _funding_dates_in_month(date(2026, 3, 1), date(2026, 3, 31), cal, "week")
    assert weekly == [
        date(2026, 3, 6),
        date(2026, 3, 13),
        date(2026, 3, 20),
        date(2026, 3, 27),
        date(2026, 3, 31),  # Mar 30–Apr 5 week spills → month-end is the last one inside
    ]
    # Monthly frequency collapses to the single month-end trading day.
    monthly = _funding_dates_in_month(date(2026, 3, 1), date(2026, 3, 31), cal, "month")
    assert monthly == [date(2026, 3, 31)]


def test_weekly_frequency_books_one_amount_per_week() -> None:
    """frequency='week' books ``period_amount`` on every weekly funding date
    (last trading day of each week), while 'month' books it once per month.
    With flat prices the invested capital grows by period_amount × #weeks."""
    nav = _build_minimal_nav()
    r_week = run_simulation(
        nav_by_code=nav,
        from_month=date(2025, 8, 1),
        to_date=date(2026, 8, 4),
        params=EtfSimulationParams(frequency="week"),
    )
    r_month = run_simulation(
        nav_by_code=nav,
        from_month=date(2025, 8, 1),
        to_date=date(2026, 8, 4),
        params=EtfSimulationParams(frequency="month"),
    )
    # Monthly: 100000 + 13 × 5000 = 165000.
    assert Decimal(r_month["summary"]["final_cost_value"]) == Decimal("165000")
    # Weekly: strictly more funding events → strictly more invested capital.
    n_week = sum(1 for e in r_week["events"] if e["kind"] == "weekly_dca")
    n_month = sum(1 for e in r_month["events"] if e["kind"] == "monthly_dca_only")
    assert n_week > n_month
    assert Decimal(r_week["summary"]["final_cost_value"]) > Decimal(
        r_month["summary"]["final_cost_value"]
    )
    # Every weekly event carries one period_amount.
    for e in r_week["events"]:
        if e["kind"] == "weekly_dca":
            assert Decimal(e["dca_cash_added"]) == Decimal("5000")


def test_weekly_frequency_quarter_end_review_runs_once() -> None:
    """Even with several weekly fundings per month, the quarter-end
    bandwidth review runs exactly once — on the LAST funding date of the
    quarter-end month (attached to its event)."""
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

    # Aggressive divergence: two rockets vs four droppers. Weekly DCA
    # self-corrects more than monthly, so we need a stronger seed to push
    # 561560 past its 5.00pp bandwidth.
    nav = {
        "561560": gen("561560", "SH", 0.20),
        "159930": gen("159930", "SZ", -0.10),
        "512400": gen("512400", "SH", 0.30),
        "516950": gen("516950", "SH", -0.10),
        "512660": gen("512660", "SH", -0.10),
        "563010": gen("563010", "SH", -0.10),
    }
    result = run_simulation(
        nav_by_code=nav,
        from_month=date(2025, 8, 1),
        to_date=date(2026, 8, 4),
        params=EtfSimulationParams(frequency="week"),
    )
    rebalances = [e for e in result["events"] if e["kind"] == "quarterly_rebalance"]
    assert 1 <= len(rebalances) <= 4
    # Each review is attached to the LAST weekly funding date of its month.
    # The last funding's event is merged INTO the review event (spec §5:
    # 季末调仓与当期定投合并计算), so its kind becomes quarterly_rebalance
    # while dca_date still records the funding day.
    from collections import defaultdict

    by_month: dict[str, list[str]] = defaultdict(list)
    for e in result["events"]:
        if e["dca_date"]:
            by_month[str(e["dca_date"])[:7]].append(str(e["dca_date"]))
    for e in rebalances:
        dca_month = str(e["dca_date"])[:7]
        assert dca_month in by_month
        assert str(e["dca_date"]) == max(by_month[dca_month]), (
            f"review must attach to the last funding date; got {e['dca_date']} "
            f"vs {sorted(set(by_month[dca_month]))}"
        )


# --- Band-corridor DCA (2026-08-07 regression) -----------------------------
# The monthly DCA used to re-target every symbol to its exact target weight,
# which erased intra-quarter price drift before the quarter-end review ran —
# over 39 real months only 1 rebalance fired. The DCA now tops up only to the
# band's lower edge (target − band), so drift inside the corridor survives to
# the review and the bandwidth mechanism does real work.


def test_target_shares_with_band_lowers_target_to_corridor_edge() -> None:
    """_target_shares(..., band=X) must target target−X, never the full
    target — the corridor edge, not the centre."""
    params = EtfSimulationParams()
    portfolio = Decimal("200000")
    code = "512400"  # target 0.1059, band 0.025
    price = 1.0
    band = _bandwidth_for(code, params)
    at_target = _target_shares(code, portfolio, price, params)
    at_edge = _target_shares(code, portfolio, price, params, band=band)
    assert at_edge < at_target, "band must lower the buy target"
    # Both targets round to whole lots: lots = value / 100 quantised with
    # ROUND_HALF_UP (matches _target_shares' rounding), then × 100.
    from decimal import ROUND_HALF_UP

    def whole_lots(value: Decimal) -> int:
        return int((value / 100).quantize(Decimal("0"), rounding=ROUND_HALF_UP)) * 100

    assert at_target == whole_lots(portfolio * params.target_weights[code])
    assert at_edge == whole_lots(portfolio * (params.target_weights[code] - band))


def test_band_dca_buys_only_to_corridor_edge_not_target() -> None:
    """The monthly DCA (respect_band=True) must stop at the band's lower
    edge: a symbol under-allocated within the corridor is NOT topped up to
    the exact target, so the drift survives to the quarter-end review."""
    nav = _build_minimal_nav()
    params = EtfSimulationParams()
    code = "512400"
    band = _bandwidth_for(code, params)
    price = 1.0
    portfolio = Decimal("200000")
    edge_shares = _target_shares(code, portfolio, price, params, band=band)

    # Give 512400 a moderate under-allocation: well inside the corridor
    # (deficit vs band edge = a few lots), with plenty of cash.
    state = _SimStateProxy(portfolio, edge_shares - 3 * params.lot_size)
    lots, _ = _buy_underallocated(
        state, nav, date(2025, 8, 1), params, respect_band=True
    )
    # The top-up is bounded by the corridor edge — never the full target.
    assert state.shares[code] <= edge_shares, (
        "band DCA must not buy past the corridor edge"
    )
    target_shares = _target_shares(code, portfolio, price, params)
    assert state.shares[code] < target_shares, (
        "band DCA must leave the symbol below the exact target"
    )


class _SimStateProxy:
    """Minimal _SimState stand-in for the _buy_underallocated helper test.

    Constructs a portfolio whose TOTAL market value equals ``portfolio``
    (price 1.0): half of it is cash, half is deployed at the target weights,
    with the target symbol sitting below its corridor edge. _buy_underallocated
    recomputes the portfolio value from cash + shares × price, so the shares
    must be sized so that cash + Σ shares == ``portfolio``.
    """

    def __init__(self, portfolio: Decimal, deficit_start: Decimal) -> None:
        from decimal import ROUND_HALF_UP

        params = EtfSimulationParams()
        self.portfolio = portfolio
        self.shares: dict[str, int] = {}
        deployed = Decimal("0")
        for c in ALL_HALO_CODES:
            if c == "512400":
                continue
            # Half the portfolio deployed at target weights (price 1.0).
            value = (portfolio / 2) * params.target_weights[c]
            lots = (value / 100).quantize(Decimal("0"), rounding=ROUND_HALF_UP)
            self.shares[c] = int(lots) * 100
            deployed += value.quantize(Decimal("0.01"))
        self.shares["512400"] = int(deficit_start)
        deployed += Decimal(str(deficit_start))
        # The remaining half is cash, so cash + Σ shares × 1.0 == portfolio.
        self.cash = (portfolio - deployed).quantize(Decimal("0.01"))
        # Cashflow sleeve is empty for these helper tests — the engine's
        # mark-to-market now reads these two attributes (2026-08-07).
        self.cashflow_shares = 0
        self.cashflow_cash = Decimal("0")


@pytest.mark.asyncio
async def test_real_cache_quarter_end_rebalances_fire_multiple_times() -> None:
    """Regression for the 2026-08-07 report: 39 real months (2023-07 →
    2026-08) produced only ONE rebalance because the monthly DCA re-targeted
    every symbol monthly, starving the bandwidth review. With corridor
    DCA the review must fire several times on the real historical data.

    Gated on the local history cache (the six fund_history JSON files) —
    the test reads them read-only and skips when they're absent.
    """
    from pathlib import Path

    from app.services.ashare_etf_history import EtfHistoryService

    cache_dir = Path("runtime/cache/fund_history")
    missing = [c for c in ALL_HALO_CODES if not (cache_dir / f"{c}.json").exists()]
    if missing:
        pytest.skip(f"fund history cache missing: {missing}")

    service = EtfHistoryService()
    nav = {}
    for code in ALL_HALO_CODES:
        snap = await service.get_snapshot(
            code, from_date=date(2023, 7, 1), to_date=date(2026, 8, 7), fetch=False
        )
        if not snap.points:
            pytest.skip(f"no cached history for {code}")
        nav[code] = NavSeries(
            code=snap.code,
            market=snap.market,
            points=[(p.trade_date, p.close) for p in snap.points],
            name=snap.name,
        )
    result = run_simulation(
        nav_by_code=nav,
        from_month=date(2023, 7, 1),
        to_date=date(2026, 8, 7),
        params=EtfSimulationParams(),
    )
    # 2026-08-07: 调仓必须卖出超配资产(纯欠配补买是每周定投的职责)。带
    # band 走廊的周定投持续把欠配补到下沿,真实数据上组合很少超配超带宽;
    # 断言修正为:任何标为调仓的事件都必须含卖出,且调仓次数是诚实计数。
    for e in result["events"]:
        if e["kind"] == "quarterly_rebalance":
            assert e["sell_count"] >= 1, (
                f"{e['date']}: quarterly_rebalance must contain a sell, "
                f"got sell_count={e['sell_count']}"
            )


# --- Full strategy: HALO weekly DCA + quarterly rebalance + cashflow ETF ---
# (2026-08-07) The complete ETF strategy is HALO 六只周定投+季末带宽调仓
# PLUS the cashflow ETF (159201) weekly DCA — buy-only, never rebalanced,
# never sold — with every period's cash split HALO:cashflow = 6:1.


def _build_minimal_nav_with_cashflow(
    base: float = 1.0,
    end: date = date(2026, 8, 4),
    start: date = date(2025, 8, 1),
) -> dict[str, NavSeries]:
    """6 HALO symbols + the cashflow ETF (159201) at flat daily NAV."""
    nav = _build_minimal_nav(base=base, end=end, start=start)
    pts = []
    d = start
    while d <= end:
        if d.weekday() < 5:
            pts.append((d, base))
        d += timedelta(days=1)
    nav["159201"] = _build_nav("159201", "SZ", pts)
    return nav


def test_split_period_cash_is_six_to_one() -> None:
    """6:1 split: cashflow leg = period/7 (rounded), HALO leg = remainder,
    both always sum to the original period amount."""
    from app.services.ashare_etf_simulation import _split_period_cash

    halo, cf = _split_period_cash(Decimal("5000"), Decimal("6"))
    assert cf == Decimal("714.29")  # 5000/7 = 714.285… → 714.29
    assert halo == Decimal("4285.71")
    assert halo + cf == Decimal("5000")

    halo2, cf2 = _split_period_cash(Decimal("1000"), Decimal("6"))
    assert cf2 == Decimal("142.86")
    assert halo2 == Decimal("857.14")
    assert halo2 + cf2 == Decimal("1000")


def test_cashflow_leg_carves_dedicated_pool_and_buys_whole_lots() -> None:
    """Each period carves period/7 into the cashflow pool and buys whole
    lots of 159201 from it; the HALO legs never see that cash."""
    nav = _build_minimal_nav_with_cashflow()
    result = run_simulation(
        nav_by_code=nav,
        from_month=date(2025, 8, 1),
        to_date=date(2026, 8, 4),
        params=EtfSimulationParams(),
    )
    # Every DCA event books the cashflow share and the pool accumulates.
    cf_cash_seen = Decimal("0")
    for e in result["events"]:
        assert Decimal(e["cashflow_cash_added"]) == Decimal("714.29")
        cf_cash_seen += Decimal(e["cashflow_cash_added"])
        assert e["cashflow_shares_added"] % 100 == 0  # whole lots
        # The cashflow ETF never appears in the HALO DCA trades.
        assert "159201" not in e["halo_dca"]
        assert "159201" not in e["dca_trades"]
    # Final cashflow sleeve: shares at flat ¥1 + the unspent pool remainder
    # must roughly equal the cumulative cashflow contributions (minus fees).
    last = result["series"][-1]
    assert Decimal(last["cashflow_value"]) > 0
    assert Decimal(last["cashflow_cash_value"]) >= 0
    sleeve_total = Decimal(last["cashflow_value"]) + Decimal(last["cashflow_cash_value"])
    assert sleeve_total <= cf_cash_seen, (
        f"cashflow sleeve {sleeve_total} cannot exceed contributed {cf_cash_seen}"
    )


def test_cashflow_leg_never_sells_or_rebalances() -> None:
    """Quarter-end bandwidth reviews rebalance ONLY the HALO basket; the
    cashflow shares must stay monotone non-decreasing across the window."""
    nav = _build_minimal_nav_with_cashflow()
    result = run_simulation(
        nav_by_code=nav,
        from_month=date(2025, 8, 1),
        to_date=date(2026, 8, 4),
        params=EtfSimulationParams(),
    )
    for e in result["events"]:
        if e["kind"] == "quarterly_rebalance":
            assert "159201" not in e["rebalance_trades"], (
                "cashflow ETF must never be sold or rebalanced"
            )
    cf_shares = [int(s["cashflow_shares"]) for s in result["series"]]
    for prev, nxt in pairwise(cf_shares):
        assert nxt >= prev, "cashflow shares decreased — sleeve must be buy-only"


def test_cashflow_leg_inactive_when_nav_missing() -> None:
    """When 159201 has no cached NAV at all (series absent), the cashflow
    leg never activates (2026-08-07): every period's budget goes to the
    HALO basket instead of sitting idle in a pool that can never buy."""
    nav = _build_minimal_nav()  # 6 HALO symbols only, no 159201
    result = run_simulation(
        nav_by_code=nav,
        from_month=date(2025, 8, 1),
        to_date=date(2026, 8, 4),
        params=EtfSimulationParams(),
    )
    for e in result["events"]:
        assert Decimal(e["cashflow_cash_added"]) == 0
        assert int(e["cashflow_shares_added"]) == 0
    last = result["series"][-1]
    assert int(last["cashflow_shares"]) == 0
    assert Decimal(last["cashflow_cash_value"]) == 0
    assert Decimal(last["cashflow_value"]) == 0
    # The whole weekly budget reached the HALO basket (cost counts every
    # period; nothing was parked).
    assert Decimal(last["cost_value"]) > Decimal("100000")


def test_pre_listing_budget_goes_to_halo_then_split_after_listing() -> None:
    """159201 listed 2025-08-01 (synthetic; real listing 2025-02-27):
    DCA periods BEFORE the listing must NOT carve the 1/7 cashflow leg —
    the whole budget buys HALO. From the listing week on, the 6:1 split
    applies."""
    # HALO series run from 2025-03; 159201 only from 2025-08 (staggered
    # listing) — emulating the real pre-listing window.
    halo_start = date(2025, 3, 1)
    nav = _build_minimal_nav(end=date(2025, 12, 31), start=halo_start)
    listing = date(2025, 8, 1)
    nav["159201"] = _build_nav(
        "159201", "SZ",
        [(d, 1.0) for d, _ in nav["561560"].points if d >= listing],
    )
    result = run_simulation(
        nav_by_code=nav,
        from_month=date(2025, 3, 1),
        to_date=date(2025, 12, 31),
        params=EtfSimulationParams(),
    )
    pre = [e for e in result["events"] if date.fromisoformat(e["date"]) < listing]
    post = [e for e in result["events"] if date.fromisoformat(e["date"]) >= listing]
    assert pre, "expected DCA events before the cashflow listing"
    assert post, "expected DCA events after the cashflow listing"
    for e in pre:
        assert Decimal(e["cashflow_cash_added"]) == 0, (
            "pre-listing periods must not carve a cashflow leg"
        )
    for e in post:
        assert Decimal(e["cashflow_cash_added"]) == Decimal("714.29"), (
            "post-listing periods must carve 1/7 (6:1 split)"
        )
        assert int(e["cashflow_shares_added"]) > 0
    # No cashflow pool accumulated before the listing.
    pre_last = [s for s in result["series"] if date.fromisoformat(s["date"]) < listing]
    assert pre_last
    assert Decimal(pre_last[-1]["cashflow_cash_value"]) == 0


def test_full_strategy_weekly_dca_cashflow_in_summary() -> None:
    """Weekly frequency + cashflow sleeve: summary exposes the cashflow
    market value / shares / pool, and cost_value counts every weekly
    contribution."""
    nav = _build_minimal_nav_with_cashflow()
    result = run_simulation(
        nav_by_code=nav,
        from_month=date(2025, 8, 1),
        to_date=date(2026, 8, 4),
        params=EtfSimulationParams(frequency="week"),
    )
    summary = result["summary"]
    # 平市(所有 NAV 恒 1.0)+ band-DCA 每周补欠配 → 组合从不超配 → 无真调仓
    # (2026-08-07: 调仓必须卖出超配资产,纯欠配补买是定投的职责)。
    assert summary["rebalance_count"] == 0, (
        "flat market never produces an overweight symbol → no rebalance"
    )
    # 所有"调仓"事件(若有)必须含卖出;纯买入事件不得标为 quarterly_rebalance。
    for e in result["events"]:
        if e["kind"] == "quarterly_rebalance":
            assert e["sell_count"] >= 1, "rebalance must sell, never pure-buy"
    assert Decimal(summary["final_cashflow_value"]) > 0
    assert int(summary["final_cashflow_shares"]) > 0
    assert Decimal(summary["final_cashflow_cash"]) >= 0
    # cost_value = initial + every weekly contribution. Every event is a
    # funding date (quarter-end rebalances just overwrite the kind — they
    # still book the period's DCA cash).
    funding_events = [e for e in result["events"] if Decimal(e["dca_cash_added"]) > 0]
    assert len(funding_events) >= 40, f"expected ~weekly funding dates, got {len(funding_events)}"
    assert Decimal(summary["final_cost_value"]) == Decimal(
        "100000"
    ) + Decimal("5000") * Decimal(len(funding_events))
    # Lump-sum benchmark includes the cashflow sleeve (1/7 of the total).
    assert Decimal(summary["lump_sum_final_value"]) > 0


def test_engine_is_deterministic_across_runs() -> None:
    """Same inputs → byte-identical output (2026-08-07 user report: 'same
    history + same strategy produced different rebalance counts'). The engine
    is a pure function of (nav, from_month, to_date, params); the ONLY field
    that changes between runs is the ``fetched_at`` timestamp. Rebalance
    counts, events, snapshots and the summary must be identical."""
    nav = _build_minimal_nav_with_cashflow()
    params = EtfSimulationParams(
        initial_capital=Decimal("10000"),
        period_amount=Decimal("1000"),
        frequency="week",
        cashflow_ratio=Decimal("6"),
    )
    r1 = run_simulation(
        nav_by_code=nav,
        from_month=date(2025, 8, 1),
        to_date=date(2026, 8, 4),
        params=params,
    )
    r2 = run_simulation(
        nav_by_code=nav,
        from_month=date(2025, 8, 1),
        to_date=date(2026, 8, 4),
        params=params,
    )
    # Strip the only legitimately-varying field (per-run timestamp).
    r1["meta"]["fetched_at"] = None
    r2["meta"]["fetched_at"] = None
    assert r1 == r2, "simulation must be deterministic for identical inputs"


def test_weekly_series_emitted_with_iso_week_dedup() -> None:
    """The weekly mark-to-market trail (``weekly_series``) is emitted
    alongside ``series`` so the frontend can render the equity curve at
    weekly x-axis granularity. Contract:

    - exactly one entry per ISO week (Mon-Sun) — verified by dedup;
    - dates align 1:1 with ``weeks``;
    - each entry is a pure mark-to-market snapshot (no new trading
      activity) using the state AFTER the latest funding date of that
      ISO week;
    - the trail is present even when ``frequency="month"`` — the mark
      is taken on the month's funding date, contributing one snapshot
      per month (≈ 4 per ISO week, deduped);
    - the trail is empty when there are no funding dates.
    """
    nav = _build_minimal_nav()
    result = run_simulation(
        nav_by_code=nav,
        from_month=date(2025, 8, 1),
        to_date=date(2026, 8, 4),
        params=EtfSimulationParams(frequency="month"),
    )

    weekly_series = result["weekly_series"]
    weeks = result["weeks"]

    # Monthly DCA → ~13 monthly funding dates → ~13 ISO weeks → ~13 weekly snaps
    assert isinstance(weekly_series, list)
    assert isinstance(weeks, list)
    assert len(weekly_series) == len(weeks), (
        "weekly_series and weeks must be 1:1 aligned"
    )
    assert len(weekly_series) >= 12, (
        f"expected ~13 weekly snapshots for 13 monthly funding dates, "
        f"got {len(weekly_series)}"
    )

    # One entry per ISO week — verify dedup
    seen_weeks: set[str] = set()
    for w in weeks:
        d = date.fromisoformat(w) if isinstance(w, str) else w
        iso_year, iso_week, _ = d.isocalendar()
        key = f"{iso_year:04d}-W{iso_week:02d}"
        assert key not in seen_weeks, f"duplicate ISO week key {key}"
        seen_weeks.add(key)

    # Each weekly snapshot is a valid EtfSimulationPoint with the same
    # field shape as the monthly series.
    if weekly_series:
        first = weekly_series[0]
        for required in ("date", "total_value", "cost_value", "lump_sum_value",
                         "return_pct", "lump_sum_return_pct"):
            assert required in first, f"weekly snapshot missing {required}"

    # Empty-input envelope must still produce empty (not absent) weekly lists
    # so the frontend never has to special-case None vs [].
    empty_nav: dict[str, NavSeries] = {
        code: NavSeries(code=code, market="SH", points=[]) for code in (
            "561560", "159930", "512400", "516950", "512660", "563010"
        )
    }
    empty = run_simulation(
        nav_by_code=empty_nav,
        from_month=date(2025, 8, 1),
        to_date=date(2026, 8, 4),
        params=EtfSimulationParams(),
    )
    assert empty["weekly_series"] == []
    assert empty["weeks"] == []


def test_lump_sum_is_current_total_principal_front_loaded() -> None:
    """一次性投入基准 = 把"当前累计投入总额"(初始 + 全部定投期数 × 每期)
    在期初一次性买入的权益曲线(2026-08-07)。期初点 = 总额(而非期初已投入),
    且每周定投 +period 后总额递增 → 曲线整体按新总额重算:起点 169000 →
    下一周 170000。平市(¥1 恒价)下增益恒 ≈1,故整条一次性曲线 ≈ 总额恒定。"""
    nav = _build_minimal_nav_with_cashflow()  # flat ¥1 prices → gain ≈ 1
    result = run_simulation(
        nav_by_code=nav,
        from_month=date(2025, 8, 1),
        to_date=date(2026, 8, 4),
        params=EtfSimulationParams(),
    )
    series = result["series"]
    anchor = series[0]
    # 期初一次性投入 = 累计投入总额(初始 + 全部期数 × 每期),而非期初已投入 100000。
    funding_events = [e for e in result["events"] if Decimal(e["dca_cash_added"]) > 0]
    total_cash = Decimal("100000") + Decimal("5000") * Decimal(len(funding_events))
    assert Decimal(anchor["lump_sum_value"]) == pytest.approx(
        total_cash, abs=Decimal("0.005") * total_cash
    ), f"anchor lump_sum {anchor['lump_sum_value']} must ≈ total principal {total_cash}"
    # 平市:增益恒 ≈1 → 一次性曲线 ≈ 总额恒定(不随已投入增长)。
    for snap in series:
        assert Decimal(snap["lump_sum_value"]) == pytest.approx(
            total_cash, abs=Decimal("0.03") * total_cash
        ), f"{snap['date']}: lump_sum {snap['lump_sum_value']} must stay ≈ total in flat market"
    # 期初收益锚 = 0(一次性曲线从本金开始,与策略曲线同起点语义)。
    assert Decimal(anchor["lump_sum_return_pct"]) == 0
    # return_pct 口径不变: 策略现金回报。
    assert Decimal(anchor["return_pct"]) == 0


def test_empty_window_lump_sum_no_divide_by_zero() -> None:
    """Discovery/empty window (first_td has no NAV → gain0 = 0) must not
    raise 0/0 DivisionUndefined (2026-08-07 regression: the page's first
    wide discovery call with from_month far before any data crashed the
    endpoint with decimal.InvalidOperation)."""
    from app.services.ashare_etf_simulation import _lump_sum_value

    assert _lump_sum_value(Decimal("10000"), Decimal("1.0"), Decimal("0")) == Decimal("0")
    assert _lump_sum_value(Decimal("169000"), Decimal("1.2921"), Decimal("0")) == Decimal("0")
    # Normal case still scales: 169000 × 1.2921 / 0.999 = 218563.…
    v = _lump_sum_value(Decimal("169000"), Decimal("1.2921"), Decimal("0.999"))
    assert Decimal("218500") < v < Decimal("218600")


def test_rebalance_fires_only_when_overweight_beyond_band_and_sells() -> None:
    """调仓必须卖出超配资产(2026-08-07)。单只暴涨 → 其权重超目标+带宽 →
    季末触发调仓:先卖出该超配符号、再买入欠配符号。纯欠配补买不算调仓。"""
    end = date(2026, 2, 2)
    start = date(2025, 8, 1)
    nav = _build_minimal_nav_with_cashflow(end=end, start=start)
    # 561560(目标25%,带宽5%)在 2025-11-01 后价格翻倍 → 权重大幅超配。
    boosted = []
    for d, p in nav["561560"].points:
        boosted.append((d, p * 2.0 if d >= date(2025, 11, 1) else p))
    nav["561560"] = _build_nav("561560", "SH", boosted)

    result = run_simulation(
        nav_by_code=nav,
        from_month=date(2025, 8, 1),
        to_date=end,
        params=EtfSimulationParams(),
    )
    rebs = [e for e in result["events"] if e["kind"] == "quarterly_rebalance"]
    assert rebs, "a symbol that doubled past its band must trigger a rebalance"
    for e in rebs:
        assert e["sell_count"] >= 1, (
            f"{e['date']}: rebalance must contain a sell, got {e['rebalance_trades']}"
        )
        # 561560 是超配方,必须被卖出。
        assert Decimal(str(e["rebalance_trades"].get("561560", 0))) < 0, (
            f"{e['date']}: overweight 561560 must be sold"
        )
    # 纯欠配补买的事件不得标为调仓。
    for e in result["events"]:
        if e["kind"] != "quarterly_rebalance":
            assert e["sell_count"] == 0


def test_quarterly_topup_deploys_accumulated_cash_not_rebalance() -> None:
    """季末加码(方案 A, 2026-08-11): 无超配超带宽时,季末把欠配符号补买至
    目标权重(纯买入、无卖出),部署 band 走廊外累计的现金。独立标签
    quarterly_topup,不计入 rebalance_count(必须含卖出的调仓)。"""
    nav = _build_minimal_nav_with_cashflow()  # flat ¥1 prices → 从不超配
    result = run_simulation(
        nav_by_code=nav,
        from_month=date(2025, 8, 1),
        to_date=date(2026, 8, 4),
        params=EtfSimulationParams(),
    )
    summary = result["summary"]
    # 平市从不超配 → 真调仓 0;但季末加码发生(每周定投只补到走廊下沿,
    # 现金在季末累积够一手后被部署)。
    assert summary["rebalance_count"] == 0
    topups = [e for e in result["events"] if e["kind"] == "quarterly_topup"]
    assert summary["quarterly_topup_count"] == len(topups) >= 1
    for e in topups:
        assert e["sell_count"] == 0
        assert e["buy_count"] >= 1
        assert all(Decimal(str(v)) > 0 for v in e["rebalance_trades"].values())
        # 加码买入的符号是欠配的(权重 < 目标)。
        for code in e["rebalance_trades"]:
            assert "159201" != code, "现金流ETF 永不参与季末加码"
    # 期末未部署现金明显低于"无加码"基线(现金被部署进组合)。
    last = result["series"][-1]
    assert Decimal(last["cash_value"]) < Decimal("10000")
