"""ETF strategy simulation engine.

Implements the 资金投入 strategy from 《ETF Rolling-252 Cov 策略与资金投入
说明书》(定稿 2026-08-06). The strategy is a cash-flow rebalancing rule, NOT
a rolling-252 ERC solver — research only outputs the final target weights
(表1), and the engine replays those weights with the execution rules:

- 初始建仓一次: on the first trading day of ``from_month``, deploy the whole
  ``initial_capital`` towards the confirmed target weights, buying the most
  under-allocated ETF one whole lot at a time until cash can't afford
  another lot.
- 常规定投只买不卖: on every DCA funding date (weekly or monthly per
  ``frequency`` — 表0: 周定投与月定投只是资金到账频率的区别) the account
  receives ``period_amount``; only ETFs below their target weight are
  bought (largest deficit first). Never sells. If no whole lot is
  affordable the cash rolls to the next period (HOLD).
- 季末调仓: after the quarter-end DCA is booked, per-symbol bandwidth
  ``max(target_weight × bandwidth_pct, bandwidth_floor_pp)`` is reviewed;
  when any symbol drifts beyond its band, overweight ETFs are sold down to
  a target whole-lot share FIRST, then underweight ETFs are bought. No
  trigger → no sell.
- 整手、费用与现金: all orders are whole ``lot_size`` (100-share) lots;
  commissions ``max(notional × commission_rate, min_commission)`` and
  slippage (buy at ask, sell at bid) are deducted from cash; cash never
  drops below ``min_cash_reserve``.

The engine is pure (no I/O). It walks the ACTUAL historical NAV series day
by day, applying the rules as if the strategy had been running in real
time — no look-ahead, no prediction. ``cost_value`` tracks the cumulative
capital deployed (initial_capital + Σ period_amount), so the yield chart
reads a cash-on-cash return on invested capital: ``return_pct =
(total_value − cost_value) / cost_value``.
"""

from __future__ import annotations

import logging
from dataclasses import dataclass
from datetime import date, datetime, timedelta, timezone
from decimal import ROUND_HALF_UP, Decimal

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

# The strategy universe is FIXED at 6 ETFs (spec 表1) + 1 cashflow ETF.
# The cashflow ETF (159201) receives its own weekly DCA leg and is NEVER
# rebalanced or sold — it is a separate "defensive cashflow" sleeve funded
# at HALO:cashflow = cashflow_ratio:1 (default 6:1).
HALO_SYMBOLS: tuple[tuple[str, str], ...] = (
    ("561560", "电力"),
    ("159930", "能源"),
    ("512400", "有色金属"),
    ("516950", "基建"),
    ("512660", "军工"),
    ("563010", "电信主题"),
)

ALL_HALO_CODES: tuple[str, ...] = tuple(c for c, _ in HALO_SYMBOLS)

CASHFLOW_CODE = "159201"
CASHFLOW_NAME = "现金流ETF"

# Every code the simulation can trade: the 6 HALO symbols + the cashflow ETF.
SIM_CODES: tuple[str, ...] = ALL_HALO_CODES + (CASHFLOW_CODE,)


def _split_period_cash(
    period_amount: Decimal,
    cashflow_ratio: Decimal,
) -> tuple[Decimal, Decimal]:
    """Split one DCA period's cash into (halo_amount, cashflow_amount).

    HALO:cashflow = cashflow_ratio:1. The cashflow share is
    ``period_amount / (ratio + 1)`` rounded to the cent (half-up); the HALO
    share is the remainder, so both legs always sum to ``period_amount``.
    """
    cashflow_amount = (period_amount / (cashflow_ratio + 1)).quantize(
        Decimal("0.01"), rounding=ROUND_HALF_UP
    )
    halo_amount = (period_amount - cashflow_amount).quantize(Decimal("0.01"))
    return halo_amount, cashflow_amount


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
# Execution primitives (whole-lot trading, fees, slippage)
# ---------------------------------------------------------------------------


@dataclass(slots=True)
class _SimState:
    """Portfolio state: whole-lot HALO share counts + cashflow sleeve + cash."""

    shares: dict[str, int]
    cash: Decimal
    invested: Decimal
    # Cashflow-ETF sleeve: whole-lot shares of 159201 + the dedicated cash
    # pool that funds it. The sleeve is funded by its own share of every
    # DCA period (cashflow_ratio:1); its cash NEVER feeds the HALO legs
    # and its shares are never sold or rebalanced.
    cashflow_shares: int = 0
    cashflow_cash: Decimal = Decimal("0")


def _bandwidth_for(code: str, params: EtfSimulationParams) -> Decimal:
    """Per-symbol effective bandwidth = max(target × pct, floor_pp).

    Spec §3: 有效带宽 = max(目标权重×20%, 2.5个百分点). Computed per symbol
    so 有色/电信 (small weights) land on the 2.5pp floor while 电力 (25%)
    gets 5.00pp.
    """
    target = params.target_weights.get(code, Decimal("0"))
    return max(target * params.bandwidth_pct, params.bandwidth_floor_pp).quantize(
        Decimal("0.0001")
    )


def _order_cost(price: float, lots: int, params: EtfSimulationParams) -> Decimal:
    """Cash needed for a BUY of ``lots`` whole lots at ``price``.

    Buy price pays slippage (ask = price × (1+slip)); commission is
    ``max(notional × rate, min_commission)`` on the pre-slippage notional.
    """
    notional = Decimal(str(price)) * Decimal(str(lots * params.lot_size))
    gross = notional * (Decimal("1") + params.slippage_rate)
    commission = max(notional * params.commission_rate, params.min_commission)
    return (gross + commission).quantize(Decimal("0.01"))


def _sell_proceeds(price: float, lots: int, params: EtfSimulationParams) -> Decimal:
    """Cash proceeds of SELLING ``lots`` whole lots at ``price``.

    Sell price absorbs slippage (bid = price × (1−slip)); commission is
    deducted. Never negative (defensive against absurd price inputs).
    """
    notional = Decimal(str(price)) * Decimal(str(lots * params.lot_size))
    net = notional * (Decimal("1") - params.slippage_rate)
    commission = max(notional * params.commission_rate, params.min_commission)
    return max(net - commission, Decimal("0")).quantize(Decimal("0.01"))


def _order_friction(price: float, lots: int, params: EtfSimulationParams) -> Decimal:
    """Total friction (slippage + commission) of an order for accounting."""
    notional = Decimal(str(price)) * Decimal(str(lots * params.lot_size))
    slippage = notional * params.slippage_rate
    commission = max(notional * params.commission_rate, params.min_commission)
    return (slippage + commission).quantize(Decimal("0.01"))


def _max_affordable_lots(
    cash: Decimal, price: float, params: EtfSimulationParams
) -> int:
    """Largest whole-lot count one order can afford without breaching the reserve.

    Commission grows with notional so ``_order_cost`` is monotonic in lots —
    doubling search then binary search keeps this O(log N).
    """
    budget = cash - params.min_cash_reserve
    if budget <= 0:
        return 0
    n = 1
    while _order_cost(price, n, params) <= budget:
        n *= 2
    lo, hi = n // 2, n
    while lo + 1 < hi:
        mid = (lo + hi) // 2
        if _order_cost(price, mid, params) <= budget:
            lo = mid
        else:
            hi = mid
    return lo


def _target_shares(
    code: str,
    portfolio_value: Decimal,
    price: float,
    params: EtfSimulationParams,
    *,
    band: Decimal | None = None,
) -> int:
    """Whole-lot share count closest to ``code``'s target weight.

    Rounds to the NEAREST whole lot (half-up) so rebalance sells stop "near
    the target", and DCA/buy loops never overshoot a symbol's fair share by
    a whole lot.

    When ``band`` is given (the per-symbol bandwidth), the target is
    lowered to the corridor's lower edge ``target − band``. The regular
    monthly DCA uses this so it only tops up symbols that drifted BELOW the
    band — the band corridor then has real meaning for the quarter-end
    review (drift accumulates inside the corridor instead of being erased
    by monthly re-targeting). Initial build and the post-review correction
    buys keep ``band=None`` (deploy to the exact target).
    """
    raw_weight = params.target_weights.get(code, Decimal("0"))
    if band is not None:
        raw_weight = max(raw_weight - band, Decimal("0"))
    target_value = (portfolio_value * raw_weight).quantize(
        Decimal("0.01")
    )
    if price is None or price <= 0:
        return 0
    lots = int(
        (target_value / (Decimal(str(price)) * Decimal(params.lot_size))).quantize(
            Decimal("0"), rounding=ROUND_HALF_UP
        )
    )
    return lots * params.lot_size


def _last_price_on_or_before(
    nav: NavSeries | None, asof: date
) -> float | None:
    """Last known close on-or-before ``asof`` (binary search; points ascending).

    Used ONLY for mark-to-market valuation of the cashflow sleeve: when a
    holding's cached NAV lags the HALO calendar (e.g. 159201 data ends a
    couple of days before the HALO symbols), the sleeve is valued at its
    last known NAV instead of being written down to 0. Execution (buying)
    still requires a same-day price — this helper never fabricates a price
    for a trade.
    """
    if nav is None or not nav.points:
        return None
    lo, hi = 0, len(nav.points) - 1
    best: float | None = None
    while lo <= hi:
        mid = (lo + hi) // 2
        d, close = nav.points[mid]
        if d <= asof:
            best = close
            lo = mid + 1
        else:
            hi = mid - 1
    return best


def _portfolio_value(
    state: _SimState,
    nav_by_code: dict[str, NavSeries],
    asof: date,
) -> Decimal:
    """Mark-to-market total = cash + Σ HALO shares × close + cashflow sleeve."""
    total = state.cash
    for code in ALL_HALO_CODES:
        price = nav_by_code[code].by_date.get(asof)
        if price is None or price <= 0:
            continue
        total += Decimal(state.shares[code]) * Decimal(str(price))
    cf = nav_by_code.get(CASHFLOW_CODE)
    cf_price = _last_price_on_or_before(cf, asof)
    if cf_price is not None and cf_price > 0:
        total += Decimal(state.cashflow_shares) * Decimal(str(cf_price))
    total += state.cashflow_cash
    return total.quantize(Decimal("0.01"))


def _cashflow_listing_date(
    nav_by_code: dict[str, NavSeries],
) -> date | None:
    """First trading day the cashflow ETF (159201) has a cached NAV.

    159201 listed on 2025-02-27; any DCA period BEFORE that date cannot buy
    it, so the whole period's cash goes to the HALO basket instead (the
    weekly budget is never left idle — 上市前全部改投 HALO,2026-08-07).
    Returns ``None`` when the cashflow series is absent entirely (then the
    cashflow leg never activates).
    """
    cf = nav_by_code.get(CASHFLOW_CODE)
    if cf is not None and cf.points:
        return cf.points[0][0]
    return None


def _buy_cashflow(
    state: _SimState,
    nav_by_code: dict[str, NavSeries],
    asof: date,
    params: EtfSimulationParams,
) -> tuple[int, Decimal]:
    """Buy whole lots of the cashflow ETF from its dedicated cash pool.

    Only-buys, never rebalances, never sells. Buys the most whole lots the
    pool can afford (commission + slippage included); the unused remainder
    stays in the cashflow pool and rolls to the next period. Returns
    ``(lots_bought, friction)`` and mutates ``state``. A missing NAV (the
    ETF wasn't listed yet, or a data gap) is a silent HOLD — the cash rolls.
    """
    cf = nav_by_code.get(CASHFLOW_CODE)
    price = cf.by_date.get(asof) if cf is not None else None
    if price is None or price <= 0:
        return 0, Decimal("0")
    affordable = _max_affordable_lots(state.cashflow_cash, price, params)
    if affordable <= 0:
        return 0, Decimal("0")
    cost = _order_cost(price, affordable, params)
    state.cashflow_cash -= cost
    state.cashflow_shares += affordable * params.lot_size
    return affordable, _order_friction(price, affordable, params)


def _buy_underallocated(
    state: _SimState,
    nav_by_code: dict[str, NavSeries],
    asof: date,
    params: EtfSimulationParams,
    *,
    respect_band: bool = False,
) -> tuple[dict[str, int], Decimal]:
    """Buy whole lots of the most under-allocated ETF until cash is spent.

    Spec §4: 新增资金和可用现金优先买入低于目标权重的ETF，不主动卖出。
    §6: 资金不足时先缩放基础买入，再逐手分配剩余现金给最欠配资产。

    Each iteration picks the symbol with the largest share deficit vs its
    target share and places ONE order for as many lots as it can absorb up
    to its target (batched, so the per-order minimum commission is charged
    once per symbol per period, not per lot). When cash can't fill the
    full top-up the order scales down (缩放), and the loop keeps handing
    the remaining cash to the most under-allocated symbol. When no whole
    lot is affordable the loop breaks and cash rolls to the next period
    (HOLD). Returns (lots per code, friction) and mutates ``state``.

    ``respect_band=True`` (the regular monthly DCA) lowers each symbol's
    buy target to the corridor lower edge ``target − band``, so the DCA
    tops up only genuinely under-allocated positions and lets intra-quarter
    price drift accumulate — giving the quarter-end bandwidth review real
    work instead of erasing drift every month (see _target_shares).
    Initial build and the post-review correction buys stay at the exact
    target (``respect_band=False``).
    """
    lots_bought: dict[str, int] = {}
    friction = Decimal("0")
    portfolio_value = _portfolio_value(state, nav_by_code, asof)
    while True:
        best_code: str | None = None
        best_deficit = 0
        for code in ALL_HALO_CODES:
            price = nav_by_code[code].by_date.get(asof)
            if price is None or price <= 0:
                continue
            band = _bandwidth_for(code, params) if respect_band else None
            target_sh = _target_shares(
                code, portfolio_value, price, params, band=band
            )
            deficit_lots = (target_sh - state.shares[code]) // params.lot_size
            if deficit_lots > best_deficit:
                best_deficit = deficit_lots
                best_code = code
        if best_code is None or best_deficit <= 0:
            break  # every symbol at/above target — HOLD
        price = nav_by_code[best_code].by_date[asof]
        affordable = _max_affordable_lots(state.cash, price, params)
        if affordable <= 0:
            break  # no whole lot affordable — roll cash to next period
        buy_lots = min(best_deficit, affordable)
        cost = _order_cost(price, buy_lots, params)
        state.cash -= cost
        state.shares[best_code] += buy_lots * params.lot_size
        lots_bought[best_code] = lots_bought.get(best_code, 0) + buy_lots
        friction += _order_friction(price, buy_lots, params)
    return lots_bought, friction


# ---------------------------------------------------------------------------
# Simulation engine
# ---------------------------------------------------------------------------


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


def _first_trading_day(
    month_first: date,
    nav_by_date: dict[date, float],
) -> date | None:
    """Return the first trading day on-or-after ``month_first`` with NAV.

    Symmetric counterpart of ``_month_end_trading_day``: walks forward
    up to 35 days (covers any month-long data gap) from the 1st of the
    month. Returns ``None`` if no trading day is found.
    """
    if not nav_by_date:
        return None
    cursor = month_first
    for _ in range(35):
        if cursor in nav_by_date:
            return cursor
        cursor = date.fromordinal(cursor.toordinal() + 1)
    return None


def _advance_month(d: date) -> date:
    if d.month == 12:
        return date(d.year + 1, 1, 1)
    return date(d.year, d.month + 1, 1)


def _iso_week_key(d: date) -> str:
    """ISO-8601 week label ``YYYY-Www`` aligned with the existing
    Mon-Sun funding-week convention used by ``_funding_dates_in_month``
    (Python's ``isocalendar`` returns the same Mon-Sun week index).

    The key is used to dedupe weekly mark-to-market snapshots: at most
    one snapshot per ISO week is recorded, taken on the latest funding
    date within that week.
    """
    iso_year, iso_week, _ = d.isocalendar()
    return f"{iso_year:04d}-W{iso_week:02d}"


def _funding_dates_in_month(
    month_first: date,
    month_end: date,
    calendar: dict[date, float],
    frequency: str,
) -> list[date]:
    """DCA funding dates within the calendar month [``month_first``, ``month_end``].

    - month frequency: exactly the month-end trading day (one funding per
      calendar month).
    - week frequency: the last trading day of every calendar week (Mon–Sun)
      whose week-end falls inside the month — the "每周既定日期" of spec
      表0. A week that spills into the next month (e.g. Dec 29–Jan 4) is
      counted in the NEXT month's iteration, so each funding date is
      generated exactly once.
    """
    if frequency == "month":
        return [month_end]
    out: list[date] = []
    # Monday of the week containing ``month_first`` (may be in the previous
    # month — its funding, if any, falls before month_first and is skipped).
    week_start = month_first - timedelta(days=month_first.weekday())
    while week_start <= month_end:
        sunday = week_start + timedelta(days=6)
        funding: date | None = None
        cursor = sunday
        for _ in range(7):
            if cursor in calendar:
                funding = cursor
                break
            cursor = date.fromordinal(cursor.toordinal() - 1)
        if funding is not None and funding >= month_first and funding <= month_end:
            out.append(funding)
        week_start = date.fromordinal(week_start.toordinal() + 7)
    return out


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
    ascending points. Must include every HALO code (the 6-ETF universe).
    Caller is responsible for fetching from EtfHistoryService.
    """
    now = now or datetime.now(tz=UTC)
    today = now.date()

    if to_date is None:
        to_date = today
    if from_month > to_date:
        raise ValueError(f"from_month {from_month} must be <= to_date {to_date}")

    # Validate inputs. The 6 HALO symbols are mandatory; the cashflow ETF
    # is optional (it may not be listed yet for early from_month windows —
    # its cash leg then rolls in the dedicated pool until a NAV appears).
    missing = [c for c in ALL_HALO_CODES if c not in nav_by_code]
    if missing:
        raise ValueError(f"missing NAV for HALO symbols: {missing}")
    unknown_weights = sorted(set(params.target_weights) - set(ALL_HALO_CODES))
    if unknown_weights:
        raise ValueError(f"unknown target-weight codes: {unknown_weights}")
    weight_sum = sum(params.target_weights.values())
    if abs(weight_sum - Decimal("1")) > Decimal("0.0001"):
        raise ValueError(f"target_weights must sum to 1.0, got {weight_sum}")

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

    # The first trading day on which EVERY HALO symbol has a NAV close —
    # the natural default for the simulation's from_month (so the user
    # starts at the first day the full 6-ETF basket is trading, not before
    # the last ETF listed). This is computed as the FIRST date present in
    # ALL six series (the "six-all-present day"), NOT the max of each
    # symbol's first date: the max can land on a day where another symbol
    # is still missing (staggered listings / data gaps), under-shooting
    # the real start.
    per_symbol_dates: list[set[date]] = []
    for code in ALL_HALO_CODES:
        series = nav_by_code.get(code)
        if series and series.points:
            per_symbol_dates.append({d for d, _ in series.points})
    halos_listing_start: date | None = None
    if len(per_symbol_dates) == len(ALL_HALO_CODES):
        common_days = sorted(set.intersection(*per_symbol_dates))
        if common_days:
            halos_listing_start = common_days[0]

    # Merged trading calendar (union of every symbol's NAV dates) — the
    # single calendar that drives month-end / DCA / rebalance scheduling.
    merged_dates: set[date] = set()
    for s in nav_by_code.values():
        merged_dates.update(d for d, _ in s.points)
    merged_calendar: dict[date, float] = {d: None for d in merged_dates}

    state = _SimState(
        shares={c: 0 for c in ALL_HALO_CODES},
        cash=Decimal("0"),
        cashflow_shares=0,
        cashflow_cash=Decimal("0"),
        invested=Decimal("0"),
    )

    # Weekly mark-to-market trail: emitted alongside the existing
    # monthly / event-time ``points`` so the frontend can render the
    # equity curve at weekly x-axis granularity. Each entry is a pure
    # valuation snapshot (no extra trading activity) taken on the latest
    # funding date of an ISO week — at most one entry per ISO week.
    weekly_snapshots: list[EtfSimulationPoint] = []
    weekly_seen: set[str] = set()

    # ------------------------------------------------------------------
    # 一次性投入基准 (当前总额期初全投, 2026-08-07)。
    # 用户语义: 一次性投入 = 把"截至最新一次周度定投的累计投入总额"
    # (initial_capital + 全部定投期数 × period_amount = 169000)在图表期初
    # 按目标配置一次性买入并持有的权益曲线 —— 期初点 = 169000,下一周定投
    # 后总额变 170000,曲线整体按 170000 重算。C_total 是窗口内全部 funding
    # 期数 × period_amount + initial(期数用与主循环相同的 funding 日历)。
    # ------------------------------------------------------------------
    cursor_month = date(from_month.year, from_month.month, 1)
    first_td = _first_trading_day(cursor_month, merged_calendar)
    lump_unit: dict | None = None
    lump_total_cash = Decimal("0")
    lump_gain0 = Decimal("0")
    if first_td is not None:
        lump_unit = _build_lump_unit(
            nav_by_code, first_td, _cashflow_listing_date(nav_by_code), params
        )
        lump_gain0 = _lump_unit_gain(lump_unit, nav_by_code, first_td)
        # 累计投入总额 = initial + 窗口内全部 funding 期数 × period_amount
        # (与主循环同源:同一 funding 日历,不含未来/窗口外)。
        lump_cursor = cursor_month
        lump_periods = 0
        while lump_cursor <= to_date:
            lump_me = _month_end_trading_day(lump_cursor, merged_calendar)
            if lump_me is None or lump_me > to_date or lump_me > coverage_end:
                break
            lump_periods += len(
                _funding_dates_in_month(
                    lump_cursor, lump_me, merged_calendar, params.frequency
                )
            )
            lump_cursor = _advance_month(lump_cursor)
        lump_total_cash = params.initial_capital + params.period_amount * Decimal(
            lump_periods
        )

    # ------------------------------------------------------------------
    # Initial build: deploy initial_capital once, on the first trading day,
    # at the target weights (spec §2.1). Unspent remainder stays as cash.
    # ------------------------------------------------------------------
    cumulative_friction = Decimal("0")
    points: list[EtfSimulationPoint] = []
    events: list[EtfSimulationEvent] = []
    warnings: list[str] = []
    if first_td is not None:
        state.cash += params.initial_capital
        state.invested += params.initial_capital
        _, build_friction = _buy_underallocated(state, nav_by_code, first_td, params)
        cumulative_friction += build_friction
        # Cost anchor: the very first snapshot is the initial-build day with
        # total_value == invested capital, so the yield view starts at
        # exactly 0% — the user "sees" 0 return at the moment of investing,
        # not a synthetic negative dip caused by same-day fees/slippage.
        # The mark-to-market total_value stays REAL (fees already paid);
        # only the anchor's return is pinned to 0 as the reference origin.
        # Subsequent snapshots then show the honest drift (e.g. a small
        # fees-only dip at the first month-end, then the market move).
        anchor = _snapshot(state, nav_by_code, first_td)
        anchor_gain = _lump_unit_gain(lump_unit, nav_by_code, first_td)
        anchor.lump_sum_value = _lump_sum_value(
            lump_total_cash, anchor_gain, lump_gain0
        )
        anchor.return_pct = Decimal("0")
        anchor.lump_sum_return_pct = Decimal("0")
        points.append(anchor)
        # 周级曲线从初始建仓日开始(2026-08-07):让"一次性投入"曲线在横坐标
        # 初始日就从 当前累计投入总额(169000)开始,而非等第一个 funding 周。
        week_key = _iso_week_key(first_td)
        if week_key not in weekly_seen:
            weekly_seen.add(week_key)
            weekly_snapshots.append(anchor)

    # 159201 上市日:上市前的定投周没有现金流 ETF 可买,整笔预算全部投入
    # HALO 六只(2026-08-07,资金不闲置);上市日(含)当周起按 6:1 拆分。
    cashflow_listing_date = _cashflow_listing_date(nav_by_code)

    while cursor_month <= to_date:
        month_end = _month_end_trading_day(cursor_month, merged_calendar)
        if month_end is None or month_end > to_date:
            cursor_month = _advance_month(cursor_month)
            continue
        if month_end > coverage_end:
            # We've passed the data window.
            warnings.append(f"simulation_truncated_at:{month_end}:coverage_end={coverage_end}")
            break

        # 1. Fund every DCA period inside this calendar month (one for
        #    monthly, one per week for weekly — spec 表0), then deploy the
        #    cash via only-buys DCA (spec §4) on each funding date.
        funding_dates = _funding_dates_in_month(
            cursor_month, month_end, merged_calendar, params.frequency
        )
        for fd in funding_dates:
            state.cash += params.period_amount
            state.invested += params.period_amount

            # Split this period's cash into the HALO leg and the cashflow
            # leg (HALO:cashflow = cashflow_ratio:1) — but ONLY from the
            # day the cashflow ETF is listed. Before that every period's
            # cash goes to the HALO basket (the weekly budget is never left
            # idle). The HALO leg stays in ``state.cash`` so
            # _buy_underallocated can deploy it or HOLD-roll it.
            cashflow_amount = Decimal("0")
            if cashflow_listing_date is not None and fd >= cashflow_listing_date:
                _, cashflow_amount = _split_period_cash(
                    params.period_amount, params.cashflow_ratio
                )
                state.cash -= cashflow_amount
                state.cashflow_cash += cashflow_amount

            # HALO DCA respects the band corridor (target − band): it tops
            # up only symbols that drifted below their band, so intra-quarter
            # price drift survives to the quarter-end review. The initial
            # build and the review's correction buys still go to the exact
            # target (see _buy_underallocated / _target_shares).
            dca_lots, dca_friction = _buy_underallocated(
                state, nav_by_code, fd, params, respect_band=True
            )
            cumulative_friction += dca_friction

            # Cashflow ETF: buy-only, whole lots from its dedicated pool.
            # Never rebalances, never sells. A missing NAV (not listed yet)
            # is a silent HOLD — the cash rolls in the pool.
            cf_lots, cf_friction = _buy_cashflow(state, nav_by_code, fd, params)
            cumulative_friction += cf_friction

            event = EtfSimulationEvent(
                date=fd,
                dca_date=fd,
                kind="weekly_dca" if params.frequency == "week" else "monthly_dca_only",
                dca_cash_added=params.period_amount,
                halo_dca={code: lots * params.lot_size for code, lots in dca_lots.items()},
                cashflow_cash_added=cashflow_amount,
                cashflow_shares_added=cf_lots * params.lot_size,
                dca_trades={},
                friction_cost=dca_friction + cf_friction,
            )
            for code, lots in dca_lots.items():
                price = nav_by_code[code].by_date.get(fd)
                if price is not None and price > 0:
                    event.dca_trades[code] = (
                        Decimal(lots * params.lot_size) * Decimal(str(price))
                    ).quantize(Decimal("0.01"))
            cf_price = nav_by_code.get(CASHFLOW_CODE)
            cf_p = cf_price.by_date.get(fd) if cf_price is not None else None
            if cf_p is not None and cf_p > 0:
                event.cashflow_notional = (
                    Decimal(cf_lots * params.lot_size) * Decimal(str(cf_p))
                ).quantize(Decimal("0.01"))

            # 2. Quarter-end bandwidth review (spec §5): usually on the same
            #    trading day as the DCA (offset=0); optionally 1–5 trading
            #    days later so the review "sees" the post-DCA drift. The
            #    review runs once per quarter-end month, attached to the
            #    LAST funding date of the month.
            is_quarter_end = month_end.month in (3, 6, 9, 12)
            is_last_funding = fd == funding_dates[-1]
            if is_quarter_end and is_last_funding:
                offset = params.rebalance_offset_days
                rb = (
                    _advance_trading_days(month_end, offset, merged_calendar)
                    if offset > 0
                    else month_end
                )
                if rb is not None and rb <= to_date and rb <= coverage_end:
                    rebalance_date = rb
                else:
                    rebalance_date = None
            else:
                rebalance_date = None

            if rebalance_date is not None and rebalance_date != fd:
                # Post-DCA, pre-rebalance snapshot at the funding date.
                snap = _snapshot(state, nav_by_code, fd)
                snap_gain = _lump_unit_gain(lump_unit, nav_by_code, fd)
                snap.lump_sum_value = _lump_sum_value(
                    lump_total_cash, snap_gain, lump_gain0
                )
                _populate_return_pcts(snap, snap_gain, lump_gain0)
                points.append(snap)

            if rebalance_date is not None:
                trigger = _quarterly_rebalance(
                    state, nav_by_code, rebalance_date, params, event
                )
                if trigger is not None:
                    cumulative_friction += trigger[1]
                event.date = rebalance_date
                event.rebalance_date = rebalance_date
                event.rebalance_offset_days = params.rebalance_offset_days

            # 3. Snapshot at the end of this funding period (after the DCA
            #    and, when the review happens the same day, after it).
            snap_date = rebalance_date if rebalance_date is not None else fd
            snap = _snapshot(state, nav_by_code, snap_date)
            snap_gain = _lump_unit_gain(lump_unit, nav_by_code, snap_date)
            snap.lump_sum_value = _lump_sum_value(
                lump_total_cash, snap_gain, lump_gain0
            )
            _populate_return_pcts(snap, snap_gain, lump_gain0)
            points.append(snap)

            # 4. Emit one weekly valuation snapshot per ISO week. This is a
            #    pure mark-to-market using the state AFTER this funding
            #    period's trades — no new trading activity, just the
            #    strategy portfolio valued on the snap date. Dedupe by
            #    ISO week key so weekly frequency contributes exactly one
            #    snapshot per week, and monthly frequency contributes one
            #    snapshot per month (≈ 4 per ISO week).
            week_key = _iso_week_key(snap_date)
            if week_key not in weekly_seen:
                weekly_seen.add(week_key)
                weekly_snap = _snapshot(state, nav_by_code, snap_date)
                weekly_snap.lump_sum_value = snap.lump_sum_value
                # Reuse the lump_sum_value + return_pcts already computed
                # for the monthly snap (same date, same valuation).
                weekly_snap.return_pct = snap.return_pct
                weekly_snap.lump_sum_return_pct = snap.lump_sum_return_pct
                weekly_snapshots.append(weekly_snap)

            events.append(event)

        cursor_month = _advance_month(cursor_month)

    # Summary
    rebalance_count = sum(1 for e in events if e.kind == "quarterly_rebalance")
    topup_count = sum(1 for e in events if e.kind == "quarterly_topup")
    summary = _summarize(points, cumulative_friction, rebalance_count, topup_count)

    # Source status: ok if all HALO symbols had any data
    symbols_with_data = sorted({
        s.code for s in series_with_data if s.code in ALL_HALO_CODES
    })
    halo_missing = [c for c in ALL_HALO_CODES if c not in symbols_with_data]
    if not series_with_data:
        source_status = "unavailable"
    elif halo_missing:
        source_status = "partial"
    else:
        source_status = "ok"
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
        # Weekly mark-to-market trail: one valuation snapshot per ISO
        # week (deduped). Populated alongside ``series`` so the frontend
        # can render the equity curve at weekly x-axis granularity
        # without losing the monthly view. ``weeks`` carries the dates
        # the frontend uses to derive ISO-week labels for chart x-axis
        # ticks.
        weeks=[p.date for p in weekly_snapshots],
        weekly_series=weekly_snapshots,
    ).model_dump(mode="json")


def _build_lump_unit(
    nav_by_code: dict[str, NavSeries],
    first_td: date,
    listing: date | None,
    params: EtfSimulationParams,
) -> dict:
    """1 元本金期初按目标配置的分数份额基准(无整手/最低佣金,费用按比例)。

    - HALO 6/7: 按表1 目标权重分配。某个符号在 ``first_td`` 尚未上市
      (如 563010 于 2023-07-14 上市,而窗口从 2023-07-03 开始)时,该
      符号的资金份额作为现金保留,在其首个有价日按目标权重买入 —— 与
      策略侧"符号无价时资金留现金、有价后补买"同源。
    - 现金流 1/7: 159201 上市前以现金持有,上市首日一次性买入。
    返回 {"halo": {code: {"notional", "shares", "buy_date"}}, "cf": {...}}。
    """
    unit: dict = {
        "halo": {},
        "cf": {"notional": Decimal("0"), "shares": Decimal("0"), "buy_date": None},
    }
    halo_cash = (Decimal("6") / Decimal("7")).quantize(Decimal("0.000001"))
    cf_cash = (Decimal("1") / Decimal("7")).quantize(Decimal("0.000001"))
    unit["cf"]["notional"] = cf_cash
    for code in ALL_HALO_CODES:
        series = nav_by_code.get(code)
        w = params.target_weights.get(code, Decimal("0"))
        notional = (halo_cash * w).quantize(Decimal("0.000001"))
        if series is None or not series.points or w <= 0:
            unit["halo"][code] = {"notional": notional, "shares": Decimal("0"), "buy_date": None}
            continue
        # 该符号首个 ≥ first_td 的有价交易日。
        buy_date = next(
            (d for d, _ in series.points if d >= first_td), None
        )
        if buy_date is None:
            unit["halo"][code] = {"notional": notional, "shares": Decimal("0"), "buy_date": None}
            continue
        buy_price = Decimal(str(series.by_date[buy_date])) * (Decimal("1") + params.slippage_rate)
        shares = (notional * (Decimal("1") - params.commission_rate)) / buy_price
        unit["halo"][code] = {"notional": notional, "shares": shares, "buy_date": buy_date}
    if listing is not None:
        cf = nav_by_code.get(CASHFLOW_CODE)
        p = cf.by_date.get(listing) if cf is not None else None
        if p is not None and p > 0:
            buy_price = Decimal(str(p)) * (Decimal("1") + params.slippage_rate)
            unit["cf"]["shares"] = (
                cf_cash * (Decimal("1") - params.commission_rate)
            ) / buy_price
            unit["cf"]["buy_date"] = listing
    return unit


def _lump_unit_gain(
    unit: dict | None,
    nav_by_code: dict[str, NavSeries],
    asof: date,
) -> Decimal:
    """1 元一次性投入基准在 ``asof`` 的市值(=单位增益 G(t))。

    未上市符号/159201 上市前: 对应资金份额按现金持有(市值=notional);
    上市日买入后: 按其份额以最后已知 NAV 估值。基准是分数份额、无整手
    约束,所以 1 元本金可以精确按目标配置。
    """
    if unit is None:
        return Decimal("0")
    total = Decimal("0")
    for code, leg in unit["halo"].items():
        if asof < leg["buy_date"] if leg["buy_date"] is not None else False:
            total += leg["notional"]
            continue
        if leg["shares"] <= 0:
            total += leg["notional"] if leg["buy_date"] is None else Decimal("0")
            continue
        series = nav_by_code.get(code)
        price = _last_price_on_or_before(series, asof)
        if price is not None and price > 0:
            total += leg["shares"] * Decimal(str(price))
    cf = unit["cf"]
    if cf["buy_date"] is not None and asof >= cf["buy_date"]:
        cfs = nav_by_code.get(CASHFLOW_CODE)
        p = _last_price_on_or_before(cfs, asof)
        if p is not None and p > 0:
            total += cf["shares"] * Decimal(str(p))
        else:
            total += cf["notional"]
    else:
        total += cf["notional"]
    return total.quantize(Decimal("0.000001"))


def _lump_sum_value(
    total_cash: Decimal,
    gain: Decimal,
    gain0: Decimal,
) -> Decimal:
    """一次性投入基准市值 = 当前累计投入总额 × (gain / gain0)。

    ``gain0`` 是期初单位增益;当窗口在期初没有任何可投标的(discovery 空
    窗口下 first_td 无 NAV)时 gain0 = 0,此时基准无定义,返回 0(曲线该
    段不画一次性投入),避免 0/0 除零。
    """
    if gain0 <= 0:
        return Decimal("0")
    return (total_cash * gain / gain0).quantize(Decimal("0.01"))


def _populate_return_pcts(
    snapshot: EtfSimulationPoint,
    lump_gain: Decimal,
    lump_gain0: Decimal,
) -> None:
    """Fill ``snapshot.return_pct`` and ``snapshot.lump_sum_return_pct``.

    - ``return_pct`` = (total_value − cost_value)/cost_value, cash-on-cash
      return on the cumulative invested capital.
    - ``lump_sum_return_pct`` = gain/gain0 − 1: the buy-and-hold benchmark
      is ``C_total × gain / gain0`` (当前累计投入总额期初全投), so its
      return is the unit gain normalised to the period-start (= 0 at the
      anchor). Both are quantised to 4 decimal places (0.01% precision).
    """
    if snapshot.cost_value > 0:
        snapshot.return_pct = (
            (snapshot.total_value - snapshot.cost_value) / snapshot.cost_value
        ).quantize(Decimal("0.0001"))
    if lump_gain0 > 0:
        snapshot.lump_sum_return_pct = (
            (lump_gain / lump_gain0) - Decimal("1")
        ).quantize(Decimal("0.0001"))


def _snapshot(
    state: _SimState,
    nav_by_code: dict[str, NavSeries],
    asof: date,
) -> EtfSimulationPoint:
    """Compute a mark-to-market snapshot.

    ``cash_value`` is the real uninvested HALO cash (initial build remainder
    + HOLD rollover); the cashflow sleeve's cash pool is NOT included in
    ``cash_value`` (it is a dedicated sleeve, tracked via
    ``per_symbol_shares``/``per_symbol_value`` for 159201 and
    ``cashflow_cash_value``). ``cost_value`` is the cumulative capital
    deployed.
    """
    total = state.cash
    per_symbol_shares: dict[str, int] = {}
    per_symbol_value: dict[str, Decimal] = {}
    for code in ALL_HALO_CODES:
        price = nav_by_code[code].by_date.get(asof)
        per_symbol_shares[code] = state.shares[code]
        if price is None or price <= 0:
            per_symbol_value[code] = Decimal("0")
            continue
        v = (Decimal(state.shares[code]) * Decimal(str(price))).quantize(Decimal("0.01"))
        per_symbol_value[code] = v
        total += v
    cf = nav_by_code.get(CASHFLOW_CODE)
    cf_price = _last_price_on_or_before(cf, asof)
    cf_value = Decimal("0")
    if cf_price is not None and cf_price > 0:
        per_symbol_shares[CASHFLOW_CODE] = state.cashflow_shares
        cf_value = (
            Decimal(state.cashflow_shares) * Decimal(str(cf_price))
        ).quantize(Decimal("0.01"))
        per_symbol_value[CASHFLOW_CODE] = cf_value
        total += cf_value
    total += state.cashflow_cash
    return EtfSimulationPoint(
        date=asof,
        total_value=total.quantize(Decimal("0.01")),
        cost_value=state.invested.quantize(Decimal("0.01")),
        cash_value=state.cash.quantize(Decimal("0.01")),
        per_symbol_shares=per_symbol_shares,
        per_symbol_value=per_symbol_value,
        cashflow_value=cf_value,
        cashflow_shares=state.cashflow_shares,
        cashflow_cash_value=state.cashflow_cash.quantize(Decimal("0.01")),
    )


def _quarterly_rebalance(
    state: _SimState,
    nav_by_code: dict[str, NavSeries],
    asof: date,
    params: EtfSimulationParams,
    event: EtfSimulationEvent,
) -> tuple[dict[str, Decimal], Decimal] | None:
    """Quarter-end bandwidth review. Returns (trades, friction) or None.

    Spec §5: 触发时把明显超配资产卖至接近目标整手份额，卖出成交后再买入。
    Sells execute BEFORE buys, most-overweight first. When nothing drifts
    beyond its band the event records ``no_trigger`` and no sell happens.
    Mutates ``state`` in place and fills ``event``.
    """
    total_value = _portfolio_value(state, nav_by_code, asof)
    if total_value <= 0:
        event.kind = "no_trigger"
        event.notes = "no holdings"
        return None

    current_w: dict[str, float] = {}
    for code in ALL_HALO_CODES:
        price = nav_by_code[code].by_date.get(asof)
        v = (
            Decimal(state.shares[code]) * Decimal(str(price))
            if price is not None and price > 0
            else Decimal("0")
        )
        current_w[code] = float((v / total_value).quantize(Decimal("0.000001")))
    target_w = {
        code: float(params.target_weights.get(code, Decimal("0"))) for code in ALL_HALO_CODES
    }
    bandwidth = {code: float(_bandwidth_for(code, params)) for code in ALL_HALO_CODES}
    drift = {code: abs(current_w[code] - target_w[code]) for code in ALL_HALO_CODES}
    # 2026-08-07: 调仓必须"卖出超配资产"才成立。触发条件只看超配方向
    # (current − target > bandwidth):纯欠配(所有符号都低于带宽下沿)是
    # 每周定投补仓的职责,把它标成"调仓"会在调仓记录里出现纯买入事件。
    # 只有存在超配超带宽的符号才触发(先卖超配 → 再买欠配,恢复目标权重)。
    triggered = any(
        current_w[code] - target_w[code] > bandwidth[code] + 1e-9
        for code in ALL_HALO_CODES
    )
    if not triggered:
        # 2026-08-11 (方案 A): 无超配超带宽时,季末把欠配符号补买至目标权重
        # (不卖超配,带宽内超配不动)。这是"季末加码"—— 独立的资金部署动作,
        # 与调仓(必须有卖出)语义分离,让每周定投 band 走廊外累计的现金在
        # 季末部署进组合,而非长期闲置。
        underweight = any(
            target_w[code] - current_w[code] > 1e-9 for code in ALL_HALO_CODES
        )
        if not underweight:
            event.kind = "no_trigger"
            event.notes = "all drifts within per-symbol bandwidth"
            return None
        buy_lots, buy_friction = _buy_underallocated(state, nav_by_code, asof, params)
        if not buy_lots:
            event.kind = "no_trigger"
            event.notes = "underweight but no whole lot affordable"
            return None
        trades: dict[str, Decimal] = {}
        for code, lots in buy_lots.items():
            price = nav_by_code[code].by_date[asof]
            notional = (Decimal(lots * params.lot_size) * Decimal(str(price))).quantize(
                Decimal("0.01")
            )
            trades[code] = notional
        event.kind = "quarterly_topup"
        event.rebalance_trades = trades
        event.friction_cost = buy_friction.quantize(Decimal("0.01"))
        event.trade_rationale = _build_trade_rationale(trades, target_w, current_w, drift)
        event.sell_count = 0
        event.buy_count = len(trades)
        event.notes = "季末加码:欠配符号补买至目标权重(无卖出)"
        return (trades, buy_friction)

    # 1. Sells first: overweight symbols beyond their band, down to the
    #    target whole-lot share, most overweight first.
    sells: list[tuple[str, int, Decimal]] = []  # (code, lots, excess value)
    for code in ALL_HALO_CODES:
        if current_w[code] - target_w[code] > bandwidth[code] + 1e-9:
            price = nav_by_code[code].by_date.get(asof)
            if price is None or price <= 0:
                continue
            target_sh = _target_shares(code, total_value, price, params)
            excess_lots = (state.shares[code] - target_sh) // params.lot_size
            if excess_lots > 0:
                excess_value = Decimal(excess_lots * params.lot_size) * Decimal(
                    str(price)
                )
                sells.append((code, excess_lots, excess_value))
    sells.sort(key=lambda x: -x[2])  # most-overweight first

    trades: dict[str, Decimal] = {}
    friction = Decimal("0")
    for code, lots, _ in sells:
        price = nav_by_code[code].by_date[asof]
        proceeds = _sell_proceeds(price, lots, params)
        state.cash += proceeds
        state.shares[code] -= lots * params.lot_size
        notional = (Decimal(lots * params.lot_size) * Decimal(str(price))).quantize(
            Decimal("0.01")
        )
        trades[code] = -notional
        friction += _order_friction(price, lots, params)

    # 2. Buys after sells: under-allocated ETFs, most deficient first.
    buy_lots, buy_friction = _buy_underallocated(state, nav_by_code, asof, params)
    friction += buy_friction
    for code, lots in buy_lots.items():
        price = nav_by_code[code].by_date[asof]
        notional = (Decimal(lots * params.lot_size) * Decimal(str(price))).quantize(
            Decimal("0.01")
        )
        trades[code] = notional

    event.kind = "quarterly_rebalance"
    event.rebalance_trades = trades
    event.friction_cost = friction.quantize(Decimal("0.01"))
    event.trade_rationale = _build_trade_rationale(trades, target_w, current_w, drift)
    event.sell_count = sum(1 for v in trades.values() if v < 0)
    event.buy_count = sum(1 for v in trades.values() if v > 0)
    event.notes = "triggered (drift beyond per-symbol bandwidth)"
    return (trades, friction)


def _build_trade_rationale(
    trades: dict[str, Decimal],
    target_w: dict[str, float],
    current_w: dict[str, float],
    drift: dict[str, float],
) -> dict[str, dict[str, str]]:
    """Annotate every traded ETF with side + target/current/drift + notional.

    Insertion order matches the engine's execution order: sells first
    (most-overweight first), then buys (most-underweight first). Symbols
    with zero notional (no trade) are excluded.
    """
    traded = [(c, v) for c, v in trades.items() if v != 0]
    sells = sorted([(c, v) for c, v in traded if v < 0], key=lambda x: x[1])
    buys = sorted([(c, v) for c, v in traded if v > 0], key=lambda x: -x[1])
    rationale: dict[str, dict[str, str]] = {}
    for code, notional in sells + buys:
        rationale[code] = {
            "side": "sell" if notional < 0 else "buy",
            "target_weight": f"{target_w.get(code, 0.0):.4f}",
            "current_weight": f"{current_w.get(code, 0.0):.4f}",
            "drift_pct": f"{drift.get(code, 0.0):.4f}",
            "notional": str(notional),
        }
    return rationale


def _summarize(
    points: list[EtfSimulationPoint],
    cumulative_friction: Decimal,
    rebalance_count: int,
    quarterly_topup_count: int = 0,
) -> EtfSimulationSummary:
    if not points:
        zero = Decimal("0")
        return EtfSimulationSummary(
            final_total_value=zero,
            final_cost_value=zero,
            final_cash_value=zero,
            final_cashflow_value=zero,
            final_cashflow_shares=0,
            final_cashflow_cash=zero,
            peak_total_value=zero,
            trough_total_value=zero,
            max_drawdown_pct=zero,
            total_return_pct=zero,
            rebalance_count=rebalance_count,
            quarterly_topup_count=quarterly_topup_count,
            cumulative_friction=cumulative_friction,
            months_simulated=0,
            lump_sum_final_value=zero,
            lump_sum_vs_dca_pct=zero,
        )
    series = [p.total_value for p in points]
    cost_series = [p.cost_value for p in points]
    final = series[-1]
    # Cash-on-cash return at to_date = (final − invested) / invested.
    starting = cost_series[-1] if cost_series else Decimal("0")
    peak = max(series)
    trough = min(series)
    # Max drawdown on the money series: running-peak drawdown, skipping
    # zero-valued snapshots (pre-build) so they can't trip a phantom -100%.
    running_peak = Decimal("0")
    max_dd = Decimal("0")
    for v in series:
        if v <= 0:
            continue
        if v > running_peak:
            running_peak = v
        if running_peak > 0:
            dd = (v - running_peak) / running_peak
            if dd < max_dd:
                max_dd = dd
    total_return = (final - starting) / starting if starting > 0 else Decimal("0")
    # Lump-sum benchmark: same total cash outlay, opened on from_month's
    # first trading day, no rebalancing. ``lump_sum_vs_dca_pct`` is the
    # DCA outperformance vs buy-and-hold; positive means DCA won.
    lump_series = [p.lump_sum_value for p in points]
    lump_final = lump_series[-1] if lump_series else Decimal("0")
    if lump_final > 0:
        vs_dca = (final - lump_final) / lump_final
    else:
        vs_dca = Decimal("0")
    return EtfSimulationSummary(
        final_total_value=final.quantize(Decimal("0.01")),
        final_cost_value=cost_series[-1].quantize(Decimal("0.01")),
        final_cash_value=points[-1].cash_value.quantize(Decimal("0.01")),
        final_cashflow_value=points[-1].cashflow_value.quantize(Decimal("0.01")),
        final_cashflow_shares=points[-1].cashflow_shares,
        final_cashflow_cash=points[-1].cashflow_cash_value.quantize(Decimal("0.01")),
        peak_total_value=peak.quantize(Decimal("0.01")),
        trough_total_value=trough.quantize(Decimal("0.01")),
        max_drawdown_pct=max_dd,
        total_return_pct=total_return,
        rebalance_count=rebalance_count,
        quarterly_topup_count=quarterly_topup_count,
        cumulative_friction=cumulative_friction,
        months_simulated=len(points),
        lump_sum_final_value=lump_final.quantize(Decimal("0.01")),
        lump_sum_vs_dca_pct=vs_dca,
    )


__all__ = [
    "ALL_HALO_CODES",
    "CASHFLOW_CODE",
    "CASHFLOW_NAME",
    "HALO_SYMBOLS",
    "NavSeries",
    "SIM_CODES",
    "run_simulation",
]
