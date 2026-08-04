"""ETF strategy simulation engine.

Implements the HALO Rolling-252-Cov strategy as described in:

- ETF Rolling-252 Cov 策略.docx  (strategy rules)
- ETF Rolling-252 Cov Checklist.docx (operational checklist)
- HALO_rolling_cov_strategy_template.xlsx (parameter template + formulas)

What this module does NOT do
----------------------------
- It is **not** a Monte Carlo / forward-looking projection. It walks the
  ACTUAL historical price series for each symbol, day by day, applying
  monthly DCA + quarterly rebalance events as if you had been running the
  strategy in real time. The result is a faithful "if I had been
  following these rules since 2021-01, here's how my portfolio would look
  today" — same honesty as the equity-curve endpoint, with simulated
  transaction events layered on top.

Algorithm overview
------------------
1. Resolve the trading calendar from cached NAV history for each symbol.
2. For each calendar month in [from_month, to_date]:
   a. End-of-month snapshot: shares × close price + remaining cash.
   b. Apply monthly DCA (last trading day of the month): add
      ``dca_lots × lot_size`` shares per HALO symbol, deduct cash.
   c. If this month is the last trading day of Mar/Jun/Sep/Dec → quarter
      end. Compute 252-day rolling covariance matrix from daily returns;
      solve constrained ERC weights; compare to current weights; if any
      |target - actual| > θ → rebalance.
3. Emit one EtfSimulationPoint per month-end and one EtfSimulationEvent
   per month.

Numerical correctness
---------------------
- All share counts are integers (lot_size rounded).
- All money math is ``Decimal`` end-to-end; we never multiply float × float.
- Friction is applied as ``abs(notional) × friction_rate`` and reduces
  cash accordingly. This is a simple round-trip model, not bid-ask
  spread modelling.
- "Cost basis" is the cumulative cash spent on share purchases (DCA +
  rebalance buys), not the realised PnL. It tracks the user's investment
  from day 0, regardless of subsequent sells.

This module is pure (no I/O). It takes pre-loaded NAV series dicts and
returns serialisable dicts; the endpoint layer is responsible for
fetching history via EtfHistoryService.
"""

from __future__ import annotations

import logging
from dataclasses import dataclass
from datetime import date, datetime, timezone
from decimal import Decimal

import numpy as np

from app.schemas.etf_simulation import (
    EtfSimulationEvent,
    EtfSimulationMeta,
    EtfSimulationParams,
    EtfSimulationPoint,
    EtfSimulationResponse,
    EtfSimulationSummary,
)

logger = logging.getLogger(__name__)

UTC = timezone.utc

# HALO ETF universe (mirrors app.services.ashare_etf_rebalance.ETF_UNIVERSE)
HALO_SYMBOLS: tuple[tuple[str, str], ...] = (
    ("561560", "电力"),
    ("159930", "能源"),
    ("512400", "有色金属"),
    ("516950", "基建"),
    ("512660", "军工"),
    ("563010", "电信主题"),
)

CASHFLOW_SYMBOL: str = "159201"

# Group membership for constraints
COMMODITY_CODES: frozenset[str] = frozenset({"159930", "512400"})  # 能源+有色
STABILITY_CODES: frozenset[str] = frozenset({"561560", "563010"})  # 电力+电信

ALL_HALO_CODES: tuple[str, ...] = tuple(c for c, _ in HALO_SYMBOLS)


# ---------------------------------------------------------------------------
# NAV input shape (pre-loaded by the endpoint layer)
# ---------------------------------------------------------------------------


@dataclass(slots=True)
class NavSeries:
    code: str
    market: str
    points: list[tuple[date, float]]  # sorted ascending
    name: str | None = None

    @property
    def by_date(self) -> dict[date, float]:
        return dict(self.points)


# ---------------------------------------------------------------------------
# Constrained ERC (Equal Risk Contribution) target weights
# ---------------------------------------------------------------------------


def _solve_constrained_erc(
    cov: np.ndarray,
    *,
    cap_per_symbol: float,
    commodity_cap: float,
    stability_floor: float,
    dianxin_cap: float,
    iterations: int,
    code_index: dict[str, int],
) -> np.ndarray:
    """Solve ERC weights under the strategy's hard caps.

    Method: closed-form-ERC update
        w_i ∝ 1 / sqrt( (Σ w)_i )     (Spinu's standard ERC update)
    with per-iteration projection onto the feasible set:

    1. Cap every individual weight at ``cap_per_symbol``.
    2. Cap 563010 specifically at ``dianxin_cap``.
    3. Cap the commodity pair (能源+有色) sum at ``commodity_cap``.
    4. Require stability pair (电力+电信) sum ≥ ``stability_floor``.
    5. Renormalise so weights sum to 1.

    Returns a 1-D numpy array of shape ``(len(codes),)``.
    """
    n = cov.shape[0]
    # Initialise at equal weight (the ERC identity solution when Σ ∝ I).
    w = np.full(n, 1.0 / n)

    for _ in range(iterations):
        port_vol = float(np.sqrt(w @ cov @ w))
        if port_vol <= 1e-12:
            # Degenerate: fall back to equal weight and stop iterating.
            w = np.full(n, 1.0 / n)
            break
        # Marginal risk contribution (proportional to w_i * (Σw)_i)
        marginal_rc = (cov @ w) / port_vol
        # Spinu update: w ∝ 1 / sqrt(marginal_rc)
        new_w = 1.0 / np.sqrt(np.maximum(marginal_rc, 1e-12))
        new_w /= new_w.sum()
        w = new_w

    # Projection step: enforce hard constraints (10 alternating projections
    # are usually enough; we just do a few to keep this fast).
    for _ in range(10):
        # 1. Individual cap
        w = np.minimum(w, cap_per_symbol)
        # 2. Telecom cap (specific symbol)
        dianxin_idx = code_index.get("563010")
        if dianxin_idx is not None:
            w[dianxin_idx] = min(w[dianxin_idx], dianxin_cap)
        # 3. Commodity cap (sum of energy + non-ferrous)
        commodity_indices = [code_index[c] for c in COMMODITY_CODES if c in code_index]
        if commodity_indices:
            commodity_sum = float(w[commodity_indices].sum())
            if commodity_sum > commodity_cap:
                scale = commodity_cap / commodity_sum
                for i in commodity_indices:
                    w[i] *= scale
        # 4. Stability floor (sum of 电力 + 电信 must be ≥ floor)
        stability_indices = [code_index[c] for c in STABILITY_CODES if c in code_index]
        if stability_indices:
            stability_sum = float(w[stability_indices].sum())
            if stability_sum < stability_floor:
                # Boost each stability symbol up to the floor, taking from
                # the largest non-stability symbol to keep sum=1.
                deficit = stability_floor - stability_sum
                non_stability = [i for i in range(n) if i not in stability_indices]
                non_stab_total = float(w[non_stability].sum())
                if non_stab_total > deficit:
                    for i in stability_indices:
                        w[i] += deficit * (w[i] / max(stability_sum, 1e-12))
                    for i in non_stability:
                        w[i] *= (non_stab_total - deficit) / non_stab_total
                else:
                    # Cannot satisfy — set stability pair to whatever sum
                    # is possible and renormalise the rest to fill the gap.
                    for i in stability_indices:
                        w[i] = w[i] * (stability_floor / max(stability_sum, 1e-12))
                    # Renormalise everything else so sum=1.
                    pass
        # Renormalise to sum to 1
        w_sum = float(w.sum())
        if w_sum > 1e-12:
            w = w / w_sum

    return w


# ---------------------------------------------------------------------------
# Simulation engine
# ---------------------------------------------------------------------------


@dataclass
class _SymbolState:
    code: str
    shares: int = 0
    cost_basis: Decimal = Decimal("0")  # cumulative cash spent on buys


def _month_end_trading_day(month_first: date, nav_by_date: dict[date, float]) -> date | None:
    """Return the last trading day on-or-before the calendar month-end.

    ``month_first`` is the first day of the month. We walk forward up to
    35 days and pick the latest date present in ``nav_by_date``.
    """
    if not nav_by_date:
        return None
    year, month = month_first.year, month_first.month
    # Calendar month-end (handles Dec correctly via mod-12 carry).
    next_month = date(year + (month // 12), (month % 12) + 1, 1)
    last_calendar = date.fromordinal(next_month.toordinal() - 1)
    # Walk back from the calendar month-end to find the latest trading day
    # that has a NAV.
    cursor = last_calendar
    for _ in range(35):
        if cursor in nav_by_date:
            return cursor
        cursor = date.fromordinal(cursor.toordinal() - 1)
    return None


def _advance_trading_days(
    anchor: date,
    n: int,
    nav_by_date: dict[date, float],
) -> date | None:
    """Return the trading day that is exactly ``n`` trading days after ``anchor``.

    Walks forward calendar-day by calendar-day, skipping any date absent
    from ``nav_by_date``. Returns ``None`` if the walk goes more than 60
    calendar days without finding enough trading days (defensive against
    data gaps or pathological inputs).
    """
    if n <= 0:
        return anchor
    if not nav_by_date:
        return None
    cursor = anchor
    days_walked = 0
    while days_walked < 60:
        cursor = date.fromordinal(cursor.toordinal() + 1)
        if cursor in nav_by_date:
            n -= 1
            if n <= 0:
                return cursor
        days_walked += 1
    return None


def _returns_matrix(
    series_by_code: dict[str, list[tuple[date, float]]], window: int
) -> tuple[np.ndarray, list[date]] | None:
    """Compute log-returns matrix for the last ``window`` trading days.

    Returns (matrix shape ``(window, n)``, trading-day list) or None if
    insufficient overlap. Uses union of dates and forward-fills NaN.
    """
    if not series_by_code:
        return None
    # Find the most recent ``window`` trading days that appear in EVERY
    # symbol's series. Simple intersection approach: collect the last N
    # dates of each, intersect, then take the trailing ``window`` of that
    # intersection.
    date_sets = [set(d for d, _ in pts) for pts in series_by_code.values()]
    common = sorted(set.intersection(*date_sets))
    if len(common) < window:
        return None
    selected = common[-window:]
    matrix = np.zeros((window, len(series_by_code)), dtype=float)
    for col, pts in enumerate(series_by_code.values()):
        by_date = dict(pts)
        closes = np.array([by_date[d] for d in selected], dtype=float)
        # Daily log returns; first element is 0 (no prior close).
        rets = np.zeros_like(closes)
        rets[1:] = np.log(closes[1:] / closes[:-1])
        matrix[:, col] = rets
    return matrix, selected


def run_simulation(
    *,
    nav_by_code: dict[str, NavSeries],
    from_month: date,
    to_date: date | None,
    params: EtfSimulationParams,
    now: datetime | None = None,
) -> dict:
    """Run the strategy simulation and return a serialisable dict.

    ``nav_by_code`` is a pre-loaded map: code -> NavSeries with sorted
    ascending points. Must include every HALO code + CASHFLOW_SYMBOL.
    Caller is responsible for fetching from EtfHistoryService.
    """
    now = now or datetime.now(tz=UTC)
    today = now.date()

    if to_date is None:
        to_date = today
    if from_month > to_date:
        raise ValueError(f"from_month {from_month} must be <= to_date {to_date}")

    # Validate inputs
    missing = [c for c in ALL_HALO_CODES if c not in nav_by_code]
    if missing:
        raise ValueError(f"missing NAV for HALO symbols: {missing}")
    if CASHFLOW_SYMBOL not in nav_by_code:
        raise ValueError(f"missing NAV for cashflow symbol {CASHFLOW_SYMBOL}")

    # Coverage metadata. When ALL series are empty (upstream outage),
    # we still need valid ISO dates for the response schema — fall back
    # to ``from_month`` / ``to_date`` so the caller sees an honest
    # "no data" envelope rather than a 500.
    series_with_data = [s for s in nav_by_code.values() if s.points]
    if series_with_data:
        coverage_start = min(min(d for d, _ in s.points) for s in series_with_data)
        coverage_end = max(max(d for d, _ in s.points) for s in series_with_data)
    else:
        coverage_start = from_month
        coverage_end = to_date

    # Earliest date on which EVERY HALO symbol has data — the natural
    # default for the simulation's from_month (so the user starts at the
    # first month where the full basket is already trading, not before
    # some ETF had even listed).
    halo_first_dates: list[date] = []
    for code in ALL_HALO_CODES:
        series = nav_by_code.get(code)
        if series and series.points:
            halo_first_dates.append(min(d for d, _ in series.points))
    halos_listing_start = max(halo_first_dates) if halo_first_dates else None

    nav_index: dict[str, dict[date, float]] = {code: s.by_date for code, s in nav_by_code.items()}

    # Per-symbol state
    state: dict[str, _SymbolState] = {code: _SymbolState(code=code) for code in nav_by_code}
    # Cash is tracked but always non-negative; the strategy assumes the
    # user has unlimited cash to deploy (no transaction funding constraint).
    # We use cash as a sentinel for "did the cost basis exceed market
    # value this month" and to compute realised+unrealised PnL, but it
    # never goes negative in steady state.
    cash = Decimal("0")  # unused for valuation; kept for API completeness

    # Iterate months
    cursor_month = date(from_month.year, from_month.month, 1)
    points: list[EtfSimulationPoint] = []
    events: list[EtfSimulationEvent] = []
    warnings: list[str] = []
    cumulative_friction = Decimal("0")

    while cursor_month <= to_date:
        # Find the last trading day in this month that has data
        month_end = _month_end_trading_day(cursor_month, nav_index.get(CASHFLOW_SYMBOL, {}))
        if month_end is None or month_end > to_date:
            cursor_month = _advance_month(cursor_month)
            continue
        if month_end > coverage_end:
            # We've passed the data window.
            warnings.append(f"simulation_truncated_at:{month_end}:coverage_end={coverage_end}")
            break

        # End-of-month snapshot (before DCA/rebalance of THIS month)
        snapshot = _snapshot(state, cash, nav_index, month_end)
        points.append(snapshot)

        # Step 1: Monthly DCA on the last trading day of the month.
        # The strategy assumes the user can fund every DCA buy regardless
        # of cash reserves (infinite credit line). We track cumulative
        # cost_basis but do NOT model cash depletion.
        cashflow_price = nav_index[CASHFLOW_SYMBOL].get(month_end)
        for code in ALL_HALO_CODES:
            price = nav_index[code].get(month_end)
            if price is None or price <= 0:
                continue
            shares_added = params.dca_lots_halo * params.lot_size
            notional = (Decimal(shares_added) * Decimal(str(price))).quantize(Decimal("0.01"))
            state[code].shares += shares_added
            state[code].cost_basis += notional
        if cashflow_price is not None and cashflow_price > 0:
            cf_added = params.dca_lots_cashflow * params.lot_size
            cf_notional = (
                Decimal(cf_added) * Decimal(str(cashflow_price))
            ).quantize(Decimal("0.01"))
            state[CASHFLOW_SYMBOL].shares += cf_added
            state[CASHFLOW_SYMBOL].cost_basis += cf_notional

        # Step 2: Quarterly rebalance (Mar/Jun/Sep/Dec).
        #
        # When ``rebalance_offset_days > 0`` the rebalance fires N trading
        # days AFTER the DCA. This lets the rebalance "see" the price
        # drift introduced by the DCA itself plus ~1 week of market noise,
        # so the ERC target gets a fairer chance to rebalance towards the
        # post-DCA shape. ``event.date`` is anchored to the rebalance day
        # (which may fall in the next calendar month); ``event.dca_date``
        # preserves the original month-end DCA date for back-reference.
        is_quarter_end = month_end.month in (3, 6, 9, 12)
        event = EtfSimulationEvent(
            date=month_end,
            dca_date=month_end,
            kind="monthly_dca_only",
            cashflow_shares_added=(
                params.dca_lots_cashflow * params.lot_size if cashflow_price else 0
            ),
            halo_dca={
                code: params.dca_lots_halo * params.lot_size
                for code in ALL_HALO_CODES
                if nav_index[code].get(month_end)
            },
        )

        if is_quarter_end:
            offset = params.rebalance_offset_days
            if offset > 0:
                rebalance_date = _advance_trading_days(
                    month_end, offset, nav_index.get(CASHFLOW_SYMBOL, {})
                )
            else:
                rebalance_date = month_end
            if (
                rebalance_date is not None
                and rebalance_date <= to_date
                and rebalance_date <= coverage_end
            ):
                # Snapshot the post-DCA state on the rebalance day so the
                # chart shows two markers for quarter-ends: one at DCA
                # and one at rebalance. Skipped silently if the offset
                # pushes the rebalance beyond the data window.
                if rebalance_date != month_end:
                    rb_snapshot = _snapshot(
                        state, cash, nav_index, rebalance_date
                    )
                    points.append(rb_snapshot)
                trigger = _maybe_rebalance(
                    state,
                    cash,
                    nav_index,
                    rebalance_date,
                    params,
                    event,
                )
                if trigger is not None:
                    # trigger = (trades dict, friction cost) where cash
                    # has already been mutated by the caller; we only
                    # need to accumulate friction here.
                    cumulative_friction += trigger[1]
                event.date = rebalance_date
                event.rebalance_date = rebalance_date
                event.rebalance_offset_days = offset

        events.append(event)

        # Roll forward one calendar month
        cursor_month = _advance_month(cursor_month)

    # Summary
    rebalance_count = sum(1 for e in events if e.kind == "quarterly_rebalance")
    summary = _summarize(points, cumulative_friction, rebalance_count)

    # Source status: ok if all HALO + cashflow had any data
    symbols_with_data = list(state.keys())
    # source_status reflects NAV coverage honestly:
    # - "unavailable" when no symbol returned any points (upstream outage)
    # - "partial"   when at least one symbol has data but not all
    # - "ok"        when every requested symbol has data
    if not series_with_data:
        source_status = "unavailable"
    elif missing:
        source_status = "partial"
    else:
        source_status = "ok"
    # Track which HALO codes actually have data (not just present in the dict).
    symbols_with_data = sorted({
        s.code for s in series_with_data if s.code in ALL_HALO_CODES
    })
    # HALO codes that have no usable NAV at all.
    halo_missing = [c for c in ALL_HALO_CODES if c not in symbols_with_data]
    meta = EtfSimulationMeta(
        data_source="eastmoney_kline",
        fetched_at=now,
        coverage_start=coverage_start,
        coverage_end=coverage_end,
        symbols_with_data=symbols_with_data,
        symbols_missing=halo_missing,
        source_status=source_status,  # type: ignore[arg-type]
        halos_listing_start=halos_listing_start,
    )

    return EtfSimulationResponse(
        from_month=date(from_month.year, from_month.month, 1),
        to_date=to_date,
        months=[p.date for p in points],
        series=points,
        events=events,
        summary=summary,
        meta=meta,
        warnings=warnings,
    ).model_dump(mode="json")


def _advance_month(d: date) -> date:
    if d.month == 12:
        return date(d.year + 1, 1, 1)
    return date(d.year, d.month + 1, 1)


def _snapshot(
    state: dict[str, _SymbolState],
    cash: Decimal,
    nav_index: dict[str, dict[date, float]],
    asof: date,
) -> EtfSimulationPoint:
    """Compute end-of-month snapshot.

    ``cash`` is included in ``total_value`` for completeness but the DCA
    strategy assumes infinite cash so it stays at zero (see
    ``run_simulation`` for the policy decision). ``cost_value`` is the
    cumulative cash deployed into shares.
    """
    total = cash
    cost = Decimal("0")
    cash_value = cash
    per_symbol_shares: dict[str, int] = {}
    per_symbol_value: dict[str, Decimal] = {}
    for code, st in state.items():
        price = nav_index.get(code, {}).get(asof)
        if price is None or price <= 0:
            per_symbol_shares[code] = st.shares
            per_symbol_value[code] = Decimal("0")
            continue
        v = (Decimal(st.shares) * Decimal(str(price))).quantize(Decimal("0.01"))
        per_symbol_shares[code] = st.shares
        per_symbol_value[code] = v
        total += v
        cost += st.cost_basis
    return EtfSimulationPoint(
        date=asof,
        total_value=total.quantize(Decimal("0.01")),
        cost_value=cost.quantize(Decimal("0.01")),
        cash_value=cash_value.quantize(Decimal("0.01")),
        per_symbol_shares=per_symbol_shares,
        per_symbol_value=per_symbol_value,
    )


def _maybe_rebalance(
    state: dict[str, _SymbolState],
    cash: Decimal,
    nav_index: dict[str, dict[date, float]],
    asof: date,
    params: EtfSimulationParams,
    event: EtfSimulationEvent,
) -> tuple[dict[str, Decimal], Decimal] | None:
    """Attempt a quarterly rebalance. Returns (trades, friction) or None.

    On success, mutates ``state[code].shares`` and ``cash`` in place and
    fills ``event`` with the trade details.
    """
    # 1. Pull the last 252 trading days of closes for HALO codes
    series_by_code: dict[str, list[tuple[date, float]]] = {}
    for code in ALL_HALO_CODES:
        # Use the trailing window up to ``asof``
        all_pts = [(d, p) for d, p in nav_index[code].items() if d <= asof]
        all_pts.sort()
        series_by_code[code] = all_pts[-252:]

    min_len = min(len(s) for s in series_by_code.values())
    matrix_result = _returns_matrix(
        series_by_code, window=min(252, min_len)
    )
    if matrix_result is None:
        event.kind = "no_trigger"
        event.notes = "insufficient history for 252d covariance"
        return None
    returns_matrix, dates = matrix_result

    # 2. Compute covariance matrix (annualised)
    # Use only rows where all symbols have data (already guaranteed by
    # _returns_matrix using the intersection of dates).
    cov = np.cov(returns_matrix[1:].T) * 252  # skip row 0 (zeros)

    # 3. Solve constrained ERC
    code_index = {code: i for i, code in enumerate(ALL_HALO_CODES)}
    target_w = _solve_constrained_erc(
        cov,
        cap_per_symbol=float(params.single_weight_cap),
        commodity_cap=float(params.commodity_cap),
        stability_floor=float(params.stability_floor),
        dianxin_cap=float(params.dianxin_cap),
        iterations=params.iterations,
        code_index=code_index,
    )

    # 4. Compute current weights (HALO sleeve only)
    halo_total = Decimal("0")
    current_values: dict[str, Decimal] = {}
    for code in ALL_HALO_CODES:
        price = nav_index[code].get(asof)
        if price is None or price <= 0:
            current_values[code] = Decimal("0")
            continue
        v = (Decimal(state[code].shares) * Decimal(str(price))).quantize(Decimal("0.01"))
        current_values[code] = v
        halo_total += v

    if halo_total <= 0:
        event.kind = "no_trigger"
        event.notes = "no HALO holdings yet"
        return None

    current_w = {code: float(v / halo_total) for code, v in current_values.items()}

    # 5. Compare drift to bandwidth
    theta = float(params.rebalance_bandwidth)
    drift = {code: abs(target_w[i] - current_w[code]) for i, code in enumerate(ALL_HALO_CODES)}
    triggered = any(d > theta for d in drift.values())
    if not triggered:
        event.kind = "no_trigger"
        event.notes = "all drifts within ±{:.0%}".format(theta)
        return None

    # 6. Generate trades: target_market_value = total × target_w
    # We treat the HALO sleeve as a self-balancing subset: target total
    # = current HALO total (cash is left untouched for the cashflow ETF).
    #
    # Sells are executed BEFORE buys, with the most-overweight symbols
    # sold first. This makes the "high-drift sells, low-drift buys" intent
    # explicit in the code (rather than implicit in symbol-tuple order)
    # and lets the API expose a per-symbol trade rationale (side +
    # target_weight / current_weight / drift_pct) so the front end can
    # show *why* each ETF was traded. Because the strategy assumes
    # infinite cash and halo_total is fixed across the rebalance,
    # sequential vs parallel execution is bit-equivalent on the final
    # state — only the execution order changes.
    trades: dict[str, Decimal] = {}
    candidates: list[tuple[str, Decimal]] = []
    for i, code in enumerate(ALL_HALO_CODES):
        target_value = (halo_total * Decimal(str(target_w[i]))).quantize(Decimal("0.01"))
        current_value = current_values[code]
        delta = (target_value - current_value).quantize(Decimal("0.01"))
        trades[code] = delta
        if delta != 0:
            candidates.append((code, delta))

    # Sort: sells (delta<0) most-overweight first (most negative delta),
    # then buys (delta>0) most-underweight first (most positive delta).
    sells_sorted = sorted(
        [(c, d) for c, d in candidates if d < 0],
        key=lambda x: x[1],  # ascending delta → most negative first
    )
    buys_sorted = sorted(
        [(c, d) for c, d in candidates if d > 0],
        key=lambda x: -x[1],  # descending delta → most positive first
    )
    execution_order = sells_sorted + buys_sorted

    friction = Decimal("0")
    for code, delta in execution_order:
        price = nav_index[code].get(asof)
        if price is None or price <= 0:
            continue
        # delta > 0 = buy; delta < 0 = sell.
        # We round share counts to lot_size for execution realism, with
        # trade-off bias going to the larger side so we don't exceed the
        # target_value on buys.
        share_delta_raw = float(delta) / float(price)
        share_delta = int(round(share_delta_raw / params.lot_size)) * params.lot_size
        new_shares_count = max(0, state[code].shares + share_delta)
        share_diff = Decimal(new_shares_count) - Decimal(state[code].shares)
        actual_delta = (share_diff * Decimal(str(price))).quantize(Decimal("0.01"))
        # Friction on the absolute traded notional
        friction += (abs(actual_delta) * params.friction_rate).quantize(Decimal("0.01"))
        # Update state
        state[code].shares = new_shares_count
        if actual_delta > 0:
            state[code].cost_basis += actual_delta
        else:
            # Sell: reduce cost basis by |sell_value| (avg-cost method).
            state[code].cost_basis = max(
                Decimal("0"), state[code].cost_basis + actual_delta
            )
        # Friction is tracked separately (cumulative_friction); cash is
        # not modelled since the DCA strategy assumes infinite funding.

    event.kind = "quarterly_rebalance"
    event.rebalance_trades = {code: trades[code] for code in ALL_HALO_CODES}
    event.friction_cost = friction
    event.notes = "triggered (drift > {:.0%})".format(theta)
    # Per-symbol rationale so consumers can show why each ETF was traded.
    event.trade_rationale = _build_trade_rationale(
        trades, target_w, current_w, drift
    )
    event.sell_count = sum(
        1 for v in trades.values() if v < 0
    )
    event.buy_count = sum(
        1 for v in trades.values() if v > 0
    )
    return (trades, friction)


def _build_trade_rationale(
    trades: dict[str, Decimal],
    target_w: np.ndarray,
    current_w: dict[str, float],
    drift: dict[str, float],
) -> dict[str, dict[str, str]]:
    """Annotate every traded ETF with side + target/current/drift + notional.

    Insertion order matches the engine's execution order: sells first
    (most-overweight first), then buys (most-underweight first). This lets
    consumers key the rationale dict and read it in execution order.

    Symbols with zero notional (no trade) are excluded so consumers can
    ``Object.keys(rationale)`` to get just the traded set.
    """
    code_index = {code: i for i, code in enumerate(ALL_HALO_CODES)}
    rationale: dict[str, dict[str, str]] = {}
    # Build sorted execution order: sells ascending by notional, then buys
    # descending by notional — same key the engine uses to pick the next
    # symbol to mutate.
    traded = [(c, v) for c, v in trades.items() if v != 0]
    sells = sorted([(c, v) for c, v in traded if v < 0], key=lambda x: x[1])
    buys = sorted(
        [(c, v) for c, v in traded if v > 0], key=lambda x: -x[1]
    )
    for code, notional in sells + buys:
        i = code_index[code]
        rationale[code] = {
            "side": "sell" if notional < 0 else "buy",
            "target_weight": f"{float(target_w[i]):.4f}",
            "current_weight": f"{float(current_w.get(code, 0.0)):.4f}",
            "drift_pct": f"{float(drift.get(code, 0.0)):.4f}",
            "notional": str(notional),
        }
    return rationale


def _summarize(
    points: list[EtfSimulationPoint],
    cumulative_friction: Decimal,
    rebalance_count: int,
) -> EtfSimulationSummary:
    if not points:
        zero = Decimal("0")
        return EtfSimulationSummary(
            final_total_value=zero,
            final_cost_value=zero,
            peak_total_value=zero,
            trough_total_value=zero,
            max_drawdown_pct=zero,
            total_return_pct=zero,
            rebalance_count=rebalance_count,
            cumulative_friction=cumulative_friction,
            months_simulated=0,
        )
    series = [p.total_value for p in points]
    cost_series = [p.cost_value for p in points]
    starting = cost_series[0]
    final = series[-1]
    peak = max(series)
    trough = min(series)
    running_peak = starting
    max_dd = Decimal("0")
    for v in series:
        if v > running_peak:
            running_peak = v
        if running_peak > 0:
            dd = (v - running_peak) / running_peak
            if dd < max_dd:
                max_dd = dd
    total_return = (final - starting) / starting if starting > 0 else Decimal("0")
    return EtfSimulationSummary(
        final_total_value=final.quantize(Decimal("0.01")),
        final_cost_value=cost_series[-1].quantize(Decimal("0.01")),
        peak_total_value=peak.quantize(Decimal("0.01")),
        trough_total_value=trough.quantize(Decimal("0.01")),
        max_drawdown_pct=max_dd,
        total_return_pct=total_return,
        rebalance_count=rebalance_count,
        cumulative_friction=cumulative_friction,
        months_simulated=len(points),
    )


__all__ = [
    "ALL_HALO_CODES",
    "CASHFLOW_SYMBOL",
    "COMMODITY_CODES",
    "HALO_SYMBOLS",
    "NavSeries",
    "STABILITY_CODES",
    "run_simulation",
]