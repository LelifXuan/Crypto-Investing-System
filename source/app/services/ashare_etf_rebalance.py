from __future__ import annotations

import math
from dataclasses import dataclass
from enum import Enum
from typing import Any, Literal


class PlanMode(str, Enum):
    MONTHLY_DCA = "monthly_dca"
    QUARTERLY_REBALANCE = "quarterly_rebalance"


class Side(str, Enum):
    BUY = "BUY"
    SELL = "SELL"
    HOLD = "HOLD"


class EtfState(str, Enum):
    """组合管理状态,不是多空判断。

    - 状态色由 state 决定,不绑定涨跌正负。
    - after_deviation < 0 表示低配,after_deviation > 0 表示超配。
    """

    ON_TARGET = "ON_TARGET"
    UNDERWEIGHT = "UNDERWEIGHT"
    OVERWEIGHT = "OVERWEIGHT"
    BUY_PLANNED = "BUY_PLANNED"
    SELL_PLANNED = "SELL_PLANNED"
    NO_ADD = "NO_ADD"
    LOT_BLOCKED = "LOT_BLOCKED"
    CASH_LEFT = "CASH_LEFT"
    DATA_STALE = "DATA_STALE"
    INPUT_MISSING = "INPUT_MISSING"


def classify_etf_state(
    *,
    current_weight: float | None,
    target_weight: float | None,
    after_weight: float | None,
    after_deviation: float | None,
    planned_side: str = "NONE",
    planned_shares: int = 0,
    tolerance_pct: float = 0.02,
    is_data_stale: bool = False,
) -> EtfState:
    """Return the single dominant portfolio-management state for one ETF row.

    优先级(高→低):INPUT_MISSING → DATA_STALE → SELL_PLANNED → BUY_PLANNED
    → LOT_BLOCKED → ON_TARGET → UNDERWEIGHT → OVERWEIGHT → NO_ADD
    """
    if any(
        value is None
        for value in (current_weight, target_weight, after_weight, after_deviation)
    ):
        return EtfState.INPUT_MISSING
    if is_data_stale:
        return EtfState.DATA_STALE

    side = str(planned_side or "NONE").upper()
    shares = int(planned_shares or 0)
    if side == "SELL" and shares > 0:
        return EtfState.SELL_PLANNED
    if side == "BUY" and shares > 0:
        return EtfState.BUY_PLANNED

    deviation = float(after_deviation)
    tolerance = abs(float(tolerance_pct))
    if abs(deviation) <= tolerance:
        return EtfState.ON_TARGET
    if deviation < -tolerance:
        return EtfState.UNDERWEIGHT
    if deviation > tolerance:
        return EtfState.OVERWEIGHT
    return EtfState.NO_ADD


@dataclass(frozen=True)
class ETFDefinition:
    symbol: str
    code: str
    name: str
    bucket: Literal["HALO", "CASHFLOW"]
    role: str
    target_weight: float


ETF_UNIVERSE: tuple[ETFDefinition, ...] = (
    ETFDefinition("563010.SH", "563010", "电信ETF", "HALO", "防御红利 / 数字基础设施", 0.105),
    ETFDefinition("512660.SH", "512660", "军工ETF", "HALO", "事件驱动 / 高弹性进攻", 0.084),
    ETFDefinition("516950.SH", "516950", "基建ETF", "HALO", "稳增长 / 政策驱动", 0.105),
    ETFDefinition("512400.SH", "512400", "有色金属ETF", "HALO", "资源周期 / 高波动进攻", 0.084),
    ETFDefinition("159930.SZ", "159930", "能源ETF", "HALO", "资源周期 / 红利周期", 0.112),
    ETFDefinition("561560.SH", "561560", "电力ETF", "HALO", "公用事业 / 稳定现金流", 0.120),
    ETFDefinition("159201.SZ", "159201", "现金流ETF", "CASHFLOW", "防御底仓 / 现金流因子", 0.390),
)

# Scope separation: HALO sleeve drives the rotation optimizer; Cashflow ETF
# is monthly DCA display-only and must never enter the optimizer. The legacy
# ETF_UNIVERSE alias is kept for callers that still need the 7-symbol quote
# catalog.
HALO_ROTATION_UNIVERSE: tuple[ETFDefinition, ...] = tuple(
    item for item in ETF_UNIVERSE if item.bucket == "HALO"
)
CASHFLOW_ETF: ETFDefinition = next(
    item for item in ETF_UNIVERSE if item.bucket == "CASHFLOW"
)
QUOTE_UNIVERSE: tuple[ETFDefinition, ...] = ETF_UNIVERSE

ETF_BY_SYMBOL = {item.symbol: item for item in QUOTE_UNIVERSE}
ETF_BY_CODE = {item.code: item for item in QUOTE_UNIVERSE}
TARGET_WEIGHTS = {item.symbol: item.target_weight for item in QUOTE_UNIVERSE}

CASHFLOW_SYMBOL: str = CASHFLOW_ETF.symbol
HALO_SYMBOLS: frozenset[str] = frozenset(item.symbol for item in HALO_ROTATION_UNIVERSE)
HALO_DEFINITION_BY_SYMBOL: dict[str, ETFDefinition] = {
    item.symbol: item for item in HALO_ROTATION_UNIVERSE
}

# HALO-internal target weights normalized to sum 1.0 within the six HALO ETFs.
# These are the legacy ETF_UNIVERSE target weights for the HALO symbols
# re-expressed as a HALO-sleeve share, NOT a global portfolio share.
_HALO_TARGET_WEIGHTS_RAW: dict[str, float] = {
    item.symbol: item.target_weight for item in HALO_ROTATION_UNIVERSE
}
_HALO_TARGET_WEIGHTS_TOTAL: float = sum(_HALO_TARGET_WEIGHTS_RAW.values())
HALO_TARGET_WEIGHTS: dict[str, float] = {
    symbol: weight / _HALO_TARGET_WEIGHTS_TOTAL
    for symbol, weight in _HALO_TARGET_WEIGHTS_RAW.items()
}
HALO_TARGET_WEIGHTS_DEFAULT: dict[str, float] = dict(HALO_TARGET_WEIGHTS)


@dataclass(frozen=True)
class ETFPosition:
    symbol: str
    shares: int
    cost_price: float
    current_price: float

    @property
    def definition(self) -> ETFDefinition:
        return ETF_BY_SYMBOL[self.symbol]

    @property
    def market_value(self) -> float:
        return self.shares * self.current_price

    @property
    def cost_value(self) -> float:
        return self.shares * self.cost_price

    @property
    def pnl_amount(self) -> float:
        return self.market_value - self.cost_value

    @property
    def pnl_pct(self) -> float | None:
        if self.cost_price <= 0:
            return None
        return self.current_price / self.cost_price - 1.0


@dataclass(frozen=True)
class RebalanceConfig:
    mode: PlanMode
    cash_to_invest: float
    lot_size: int = 100
    tolerance_pct: float = 0.02
    hard_tolerance_pct: float = 0.05
    min_trade_amount: float = 0.0
    fee_rate: float = 0.0
    min_fee: float = 0.0
    turnover_penalty: float = 0.01
    trade_count_penalty: float = 0.0002
    cash_deviation_penalty: float = 0.35
    max_iterations: int = 500
    max_target_window_lots: int = 3
    avoid_loss_sell_inside_hard_band: bool = True


@dataclass(frozen=True)
class CandidateAction:
    side: Side
    position: ETFPosition
    shares: int
    cash_delta: float
    fee: float


def normalize_etf_symbol(value: str | None) -> str:
    raw = str(value or "").strip().upper()
    if not raw:
        raise ValueError("symbol_or_code_required")
    code = raw.split(".", 1)[0]
    if raw in ETF_BY_SYMBOL:
        return raw
    if code in ETF_BY_CODE:
        return ETF_BY_CODE[code].symbol
    raise ValueError(f"unsupported_etf:{raw}")


def _round_money(value: float) -> float:
    return round(float(value) + 1e-12, 2)


def _round_pct(value: float) -> float:
    return round(float(value) + 1e-12, 6)


def _fmt_pct(value: float) -> str:
    return f"{value * 100:.2f}%"


def _fee(gross_amount: float, config: RebalanceConfig) -> float:
    if gross_amount <= 0:
        return 0.0
    fee = gross_amount * config.fee_rate
    return max(fee, config.min_fee) if config.min_fee > 0 else fee


def _buy_cash_cost(shares: int, price: float, config: RebalanceConfig) -> tuple[float, float]:
    gross = shares * price
    fee = _fee(gross, config)
    return gross + fee, fee


def _sell_cash_proceeds(
    shares: int,
    price: float,
    config: RebalanceConfig,
) -> tuple[float, float]:
    gross = shares * price
    fee = _fee(gross, config)
    return gross - fee, fee


def _portfolio_value(
    positions: list[ETFPosition],
    shares_by_symbol: dict[str, int],
    cash: float,
) -> float:
    return cash + sum(shares_by_symbol[p.symbol] * p.current_price for p in positions)


def _target_cash_weight(target_weights: dict[str, float]) -> float:
    return max(0.0, 1.0 - sum(target_weights.values()))


def _weights(
    positions: list[ETFPosition],
    shares_by_symbol: dict[str, int],
    cash: float,
) -> dict[str, float]:
    total = _portfolio_value(positions, shares_by_symbol, cash)
    if total <= 0:
        return {p.symbol: 0.0 for p in positions}
    return {
        p.symbol: shares_by_symbol[p.symbol] * p.current_price / total
        for p in positions
    }


def _deviation_summary(
    positions: list[ETFPosition],
    shares_by_symbol: dict[str, int],
    cash: float,
    target_weights: dict[str, float],
) -> dict[str, float]:
    weights = _weights(positions, shares_by_symbol, cash)
    deviations = [
        weights[position.symbol] - target_weights.get(position.symbol, 0.0)
        for position in positions
    ]
    total = _portfolio_value(positions, shares_by_symbol, cash)
    cash_weight = cash / total if total > 0 else 0.0
    return {
        "total_abs_deviation": sum(abs(item) for item in deviations),
        "max_abs_deviation": max((abs(item) for item in deviations), default=0.0),
        "cash_weight": cash_weight,
        "cash_deviation": cash_weight - _target_cash_weight(target_weights),
    }


def _objective(
    positions: list[ETFPosition],
    shares_by_symbol: dict[str, int],
    cash: float,
    turnover_amount: float,
    trade_count: int,
    config: RebalanceConfig,
    target_weights: dict[str, float],
) -> float:
    summary = _deviation_summary(positions, shares_by_symbol, cash, target_weights)
    total = _portfolio_value(positions, shares_by_symbol, cash)
    turnover_weight = turnover_amount / total if total > 0 else 0.0
    return (
        summary["total_abs_deviation"]
        + 0.55 * summary["max_abs_deviation"]
        + config.cash_deviation_penalty * abs(summary["cash_deviation"])
        + config.turnover_penalty * turnover_weight
        + config.trade_count_penalty * trade_count
    )


def _lot_candidates_around_gap(gap_lots: int, max_lots: int, window: int) -> list[int]:
    if max_lots <= 0:
        return []
    candidates: set[int] = {1, max_lots}
    if gap_lots > 0:
        for delta in range(-window, window + 1):
            candidates.add(gap_lots + delta)
        candidates.add(max(1, gap_lots // 2))
        candidates.add(min(max_lots, gap_lots * 2))
    power = 1
    while power <= max_lots:
        candidates.add(power)
        power *= 2
    return sorted(item for item in candidates if 1 <= item <= max_lots)


def _candidate_buy_sizes(
    position: ETFPosition,
    shares: dict[str, int],
    cash: float,
    positions: list[ETFPosition],
    config: RebalanceConfig,
    target_weights: dict[str, float],
) -> list[int]:
    lot_cost, _ = _buy_cash_cost(config.lot_size, position.current_price, config)
    if lot_cost < config.min_trade_amount or cash + 1e-9 < lot_cost:
        return []
    max_lots = int(math.floor((cash + 1e-9) / lot_cost))
    if max_lots <= 0:
        return []
    total = _portfolio_value(positions, shares, cash)
    current_value = shares[position.symbol] * position.current_price
    target_value = target_weights.get(position.symbol, 0.0) * total
    gap_value = max(0.0, target_value - current_value)
    if gap_value <= 0:
        gap_lots = 1
    else:
        gap_lots = int(math.ceil(gap_value / (config.lot_size * position.current_price)))
    lots = _lot_candidates_around_gap(
        gap_lots,
        max_lots,
        config.max_target_window_lots,
    )
    return [item * config.lot_size for item in lots]


def _candidate_sell_sizes(
    position: ETFPosition,
    shares: dict[str, int],
    cash: float,
    positions: list[ETFPosition],
    config: RebalanceConfig,
    target_weights: dict[str, float],
) -> list[int]:
    held = shares[position.symbol]
    max_lots = held // config.lot_size
    if max_lots <= 0:
        return []
    total = _portfolio_value(positions, shares, cash)
    current_value = held * position.current_price
    target_value = target_weights.get(position.symbol, 0.0) * total
    excess_value = max(0.0, current_value - target_value)
    if excess_value <= 0:
        gap_lots = 1
    else:
        gap_lots = int(math.floor(excess_value / (config.lot_size * position.current_price)))
    valid: list[int] = []
    for lots in _lot_candidates_around_gap(gap_lots, max_lots, config.max_target_window_lots):
        size = lots * config.lot_size
        proceeds, _ = _sell_cash_proceeds(size, position.current_price, config)
        if proceeds >= config.min_trade_amount:
            valid.append(size)
    return sorted(set(valid))


def _candidate_actions(
    positions: list[ETFPosition],
    shares: dict[str, int],
    cash: float,
    config: RebalanceConfig,
    target_weights: dict[str, float],
) -> list[CandidateAction]:
    current_weights = _weights(positions, shares, cash)
    candidates: list[CandidateAction] = []
    for position in positions:
        before_dev = current_weights[position.symbol] - target_weights.get(position.symbol, 0.0)

        if before_dev <= config.tolerance_pct:
            for buy_shares in _candidate_buy_sizes(
                position, shares, cash, positions, config, target_weights
            ):
                cost, fee = _buy_cash_cost(buy_shares, position.current_price, config)
                if cash + 1e-9 >= cost:
                    candidates.append(CandidateAction(Side.BUY, position, buy_shares, -cost, fee))

        if config.mode != PlanMode.QUARTERLY_REBALANCE:
            continue
        if before_dev <= config.tolerance_pct:
            continue
        pnl = position.pnl_pct
        if (
            config.avoid_loss_sell_inside_hard_band
            and pnl is not None
            and pnl < 0
            and before_dev < config.hard_tolerance_pct
        ):
            continue
        for sell_shares in _candidate_sell_sizes(
            position, shares, cash, positions, config, target_weights
        ):
            proceeds, fee = _sell_cash_proceeds(sell_shares, position.current_price, config)
            candidates.append(CandidateAction(Side.SELL, position, sell_shares, proceeds, fee))
    return candidates


def _validate_config(config: RebalanceConfig) -> None:
    if config.cash_to_invest < 0:
        raise ValueError("cash_to_invest_negative")
    if config.lot_size <= 0:
        raise ValueError("lot_size_must_be_positive")
    if config.hard_tolerance_pct < config.tolerance_pct:
        raise ValueError("hard_tolerance_must_be_gte_tolerance")
    if config.min_trade_amount < 0 or config.fee_rate < 0 or config.min_fee < 0:
        raise ValueError("trade_costs_negative")


def _validate_halo_position_fields(positions: list[ETFPosition]) -> None:
    if len(positions) != len(set(item.symbol for item in positions)):
        raise ValueError("duplicate_etf_position")
    for position in positions:
        if position.shares < 0:
            raise ValueError(f"{position.symbol}:shares_negative")
        if position.cost_price < 0:
            raise ValueError(f"{position.symbol}:cost_price_negative")
        if position.current_price <= 0:
            raise ValueError(f"{position.symbol}:current_price_required")


def _validate_legacy_positions(positions: list[ETFPosition]) -> None:
    """Legacy 7-ETF validator kept only for callers that still pass 7 positions.

    The optimizer itself no longer accepts this input; the API layer filters
    159201.SZ before reaching the optimizer.
    """
    if len(positions) != len(ETF_UNIVERSE):
        raise ValueError("positions_must_include_fixed_7_etfs")
    symbols = [item.symbol for item in positions]
    if set(symbols) != set(ETF_BY_SYMBOL):
        raise ValueError("positions_must_match_fixed_universe")
    _validate_halo_position_fields(positions)


def validate_halo_positions(positions: list[ETFPosition]) -> list[ETFPosition]:
    """Strict HALO validator.

    Accepts exactly the six HALO symbols (in any order), rejects 159201.SZ
    Cashflow ETF and any other non-HALO symbol.
    """
    symbols = [normalize_etf_symbol(p.symbol) for p in positions]
    if CASHFLOW_SYMBOL in symbols:
        raise ValueError(
            f"{CASHFLOW_SYMBOL}:cashflow_etf_is_monthly_dca_only_not_rebalance_input"
        )
    if set(symbols) != HALO_SYMBOLS:
        missing = HALO_SYMBOLS - set(symbols)
        extra = set(symbols) - HALO_SYMBOLS
        raise ValueError(
            "halo_positions_must_include_exactly_6_etfs"
            f"; missing={','.join(sorted(missing)) or '-'}"
            f"; extra={','.join(sorted(extra)) or '-'}"
        )
    _validate_halo_position_fields(positions)
    index_by_symbol = {item.symbol: idx for idx, item in enumerate(HALO_ROTATION_UNIVERSE)}
    return sorted(
        (
            ETFPosition(
                symbol=normalize_etf_symbol(p.symbol),
                shares=int(p.shares),
                cost_price=float(p.cost_price),
                current_price=float(p.current_price),
            )
            for p in positions
        ),
        key=lambda item: index_by_symbol[item.symbol],
    )


def normalize_halo_target_weights(
    weights: dict[str, float] | None,
) -> dict[str, float]:
    """Normalize HALO-internal target weights to sum to 1.0.

    Rejects 159201.SZ and any non-HALO symbol. Returns a copy of
    HALO_TARGET_WEIGHTS_DEFAULT when input is None.
    """
    if weights is None:
        return dict(HALO_TARGET_WEIGHTS_DEFAULT)
    out: dict[str, float] = {}
    for sym, weight in weights.items():
        symbol = normalize_etf_symbol(sym)
        if symbol == CASHFLOW_SYMBOL:
            raise ValueError("cashflow_etf_not_allowed_in_halo_target_weights")
        if symbol not in HALO_SYMBOLS:
            raise ValueError(f"not_halo_etf:{symbol}")
        if weight < 0:
            raise ValueError(f"negative_target_weight:{symbol}")
        out[symbol] = float(weight)
    missing = HALO_SYMBOLS - set(out)
    if missing:
        raise ValueError(
            f"missing_halo_target_weights:{','.join(sorted(missing))}"
        )
    total = sum(out.values())
    if total <= 0:
        raise ValueError("target_weight_sum_must_be_positive")
    return {symbol: value / total for symbol, value in out.items()}


def _buy_reason(before_dev: float, after_dev: float, _config: RebalanceConfig) -> str:
    return f"执行前偏离 {_fmt_pct(before_dev)}，预计执行后偏离 {_fmt_pct(after_dev)}。"


def _sell_reason(position: ETFPosition, before_dev: float, after_dev: float) -> str:
    pnl = position.pnl_pct
    if pnl is None:
        pnl_text = "成本价缺失，仅按市值权重降低超配风险"
    elif pnl >= 0:
        pnl_text = f"当前浮盈 {_fmt_pct(pnl)}，卖出用于降低超配风险"
    else:
        pnl_text = f"当前浮亏 {_fmt_pct(pnl)}，但超配已超过硬阈值，需要控制组合偏离"
    return (
        "季度再平衡：当前权重高于目标且超过容忍带，"
        f"执行前偏离 {_fmt_pct(before_dev)}，预计执行后偏离 {_fmt_pct(after_dev)}，"
        f"{pnl_text}。"
    )


def _hold_reason(position: ETFPosition, after_dev: float, config: RebalanceConfig) -> str:
    if abs(after_dev) <= config.tolerance_pct:
        return f"执行后偏离 {_fmt_pct(after_dev)} 在容忍带内，不需要操作。"
    if after_dev > config.tolerance_pct:
        pnl = position.pnl_pct
        if config.mode == PlanMode.MONTHLY_DCA:
            return f"当前仍超配 {_fmt_pct(after_dev)}，月度定投阶段不新增、不卖出。"
        if pnl is not None and pnl < 0 and after_dev < config.hard_tolerance_pct:
            return (
                f"当前超配 {_fmt_pct(after_dev)} 但仍在硬阈值内且浮亏，"
                "本次不强制卖出。"
            )
        return (
            f"当前仍超配 {_fmt_pct(after_dev)}，但继续交易不能有效改善偏离"
            "或会造成过度换手。"
        )
    return f"当前低配 {_fmt_pct(after_dev)}，但剩余现金不足一手或买入后不能有效改善偏离。"


def optimize_etf_rebalance(
    positions: list[ETFPosition],
    config: RebalanceConfig,
    target_weights: dict[str, float] | None = None,
) -> dict[str, Any]:
    """Optimize the HALO-sleeve rebalance.

    The optimizer accepts exactly the six HALO ETF positions.  Cashflow ETF
    (159201.SZ) must be filtered out by the API layer before reaching here.
    The ``target_weights`` argument is normalized to sum 1.0 within the HALO
    sleeve; when omitted, ``HALO_TARGET_WEIGHTS_DEFAULT`` is used.
    """
    _validate_config(config)
    halo_positions = validate_halo_positions(positions)
    halo_targets = normalize_halo_target_weights(target_weights)

    items = halo_positions
    initial_shares = {position.symbol: int(position.shares) for position in items}
    shares = dict(initial_shares)
    cash = float(config.cash_to_invest)
    initial_cash = cash
    turnover = 0.0
    trade_count = 0
    before_weights = _weights(items, initial_shares, initial_cash)
    before_summary = _deviation_summary(items, initial_shares, initial_cash, halo_targets)
    current_obj = _objective(
        items, shares, cash, turnover, trade_count, config, halo_targets
    )

    for _ in range(config.max_iterations):
        best: tuple[float, CandidateAction, dict[str, int], float, float, int] | None = None
        for action in _candidate_actions(items, shares, cash, config, halo_targets):
            new_shares = dict(shares)
            new_cash = cash + action.cash_delta
            if new_cash < -1e-7:
                continue
            if action.side == Side.BUY:
                new_shares[action.position.symbol] += action.shares
            elif action.side == Side.SELL:
                if new_shares[action.position.symbol] < action.shares:
                    continue
                new_shares[action.position.symbol] -= action.shares
            else:
                continue

            gross_turnover = action.shares * action.position.current_price
            new_turnover = turnover + gross_turnover
            new_trade_count = trade_count + 1
            new_obj = _objective(
                items,
                new_shares,
                new_cash,
                new_turnover,
                new_trade_count,
                config,
                halo_targets,
            )
            improvement = current_obj - new_obj
            if improvement <= 1e-10:
                continue
            if best is None or improvement > best[0]:
                best = (improvement, action, new_shares, new_cash, new_turnover, new_trade_count)
        if best is None:
            break
        _, _, shares, cash, turnover, trade_count = best
        current_obj = _objective(
            items, shares, cash, turnover, trade_count, config, halo_targets
        )

    after_weights = _weights(items, shares, cash)
    after_summary = _deviation_summary(items, shares, cash, halo_targets)
    orders: list[dict[str, Any]] = []
    rows: list[dict[str, Any]] = []
    for position in items:
        definition = position.definition
        target_w = halo_targets[position.symbol]
        before_w = before_weights[position.symbol]
        after_w = after_weights[position.symbol]
        before_dev = before_w - target_w
        after_dev = after_w - target_w
        share_diff = shares[position.symbol] - initial_shares[position.symbol]
        fee_estimate = 0.0
        if share_diff > 0:
            side = Side.BUY
            trade_shares = share_diff
            estimated_amount, fee_estimate = _buy_cash_cost(
                trade_shares,
                position.current_price,
                config,
            )
            reason = _buy_reason(before_dev, after_dev, config)
        elif share_diff < 0:
            side = Side.SELL
            trade_shares = abs(share_diff)
            estimated_amount, fee_estimate = _sell_cash_proceeds(
                trade_shares,
                position.current_price,
                config,
            )
            reason = _sell_reason(position, before_dev, after_dev)
        else:
            side = Side.HOLD
            trade_shares = 0
            estimated_amount = 0.0
            reason = _hold_reason(position, after_dev, config)

        row = {
            "symbol": definition.symbol,
            "code": definition.code,
            "name": definition.name,
            "bucket": definition.bucket,
            "role": definition.role,
            "current_shares": initial_shares[position.symbol],
            "final_shares": shares[position.symbol],
            "current_price": position.current_price,
            "cost_price": position.cost_price,
            "current_value": _round_money(
                initial_shares[position.symbol] * position.current_price
            ),
            "final_value": _round_money(shares[position.symbol] * position.current_price),
            "pnl_amount": _round_money(position.pnl_amount),
            "pnl_pct": (
                _round_pct(position.pnl_pct) if position.pnl_pct is not None else None
            ),
            "target_weight": _round_pct(target_w),
            "before_weight": _round_pct(before_w),
            "after_weight": _round_pct(after_w),
            "before_deviation": _round_pct(before_dev),
            "after_deviation": _round_pct(after_dev),
            "action": side.value,
            "trade_shares": trade_shares,
            "estimated_trade_amount": _round_money(estimated_amount),
            "fee_estimate": _round_money(fee_estimate),
            "explanation": reason,
            "state": classify_etf_state(
                current_weight=before_w,
                target_weight=target_w,
                after_weight=after_w,
                after_deviation=after_dev,
                planned_side=side.value,
                planned_shares=trade_shares,
                tolerance_pct=config.tolerance_pct,
            ).value,
        }
        rows.append(row)
        if side != Side.HOLD:
            orders.append(
                {
                    "symbol": definition.symbol,
                    "code": definition.code,
                    "name": definition.name,
                    "side": side.value,
                    "shares": trade_shares,
                    "estimated_amount": _round_money(estimated_amount),
                    "price": position.current_price,
                    "fee_estimate": _round_money(fee_estimate),
                    "before_weight": _round_pct(before_w),
                    "after_weight": _round_pct(after_w),
                    "target_weight": _round_pct(target_w),
                    "before_deviation": _round_pct(before_dev),
                    "after_deviation": _round_pct(after_dev),
                    "pnl_pct": (
                        _round_pct(position.pnl_pct)
                        if position.pnl_pct is not None
                        else None
                    ),
                    "reason": reason,
                    "state": classify_etf_state(
                        current_weight=before_w,
                        target_weight=target_w,
                        after_weight=after_w,
                        after_deviation=after_dev,
                        planned_side=side.value,
                        planned_shares=trade_shares,
                        tolerance_pct=config.tolerance_pct,
                    ).value,
                }
            )

    return {
        "scope": "HALO_ONLY",
        "mode": config.mode.value,
        "orders": orders,
        "rows": rows,
        "cash": {
            "initial_cash_to_invest": _round_money(initial_cash),
            "cash_left": _round_money(cash),
            "cash_weight_after": _round_pct(after_summary["cash_weight"]),
            "target_cash_weight": _round_pct(_target_cash_weight(halo_targets)),
        },
        "deviation_summary": {
            "before_total_abs_deviation": _round_pct(
                before_summary["total_abs_deviation"]
            ),
            "before_max_abs_deviation": _round_pct(before_summary["max_abs_deviation"]),
            "after_total_abs_deviation": _round_pct(after_summary["total_abs_deviation"]),
            "after_max_abs_deviation": _round_pct(after_summary["max_abs_deviation"]),
            "improvement_total_abs_deviation": _round_pct(
                before_summary["total_abs_deviation"]
                - after_summary["total_abs_deviation"]
            ),
        },
        "portfolio": {
            "before_total_value": _round_money(
                _portfolio_value(items, initial_shares, initial_cash)
            ),
            "after_total_value": _round_money(_portfolio_value(items, shares, cash)),
            "turnover_amount": _round_money(turnover),
            "trade_count": trade_count,
        },
        "execution_constraints": {
            "lot_size": config.lot_size,
            "min_trade_amount": config.min_trade_amount,
            "fee_rate": config.fee_rate,
            "min_fee": config.min_fee,
            "tolerance_pct": config.tolerance_pct,
            "hard_tolerance_pct": config.hard_tolerance_pct,
            "exact_weight_required": False,
            "rounding_policy": "买入/卖出按可执行份额取整，允许保留剩余现金。",
        },
        "target_weights": {
            symbol: _round_pct(weight) for symbol, weight in halo_targets.items()
        },
        "excluded_etfs": [
            {
                "symbol": CASHFLOW_SYMBOL,
                "name": CASHFLOW_ETF.name,
                "reason": (
                    "现金流ETF仅按月度定投执行，不参与HALO轮动/再平衡优化器。"
                ),
            }
        ],
        "warnings": [],
        "notes": _plan_notes(items, config, cash, after_summary),
    }


def _plan_notes(
    positions: list[ETFPosition],
    config: RebalanceConfig,
    cash_left: float,
    after_summary: dict[str, float],
) -> list[str]:
    notes = [
        "目标权重按策略配置锁定；成本价只用于浮盈亏展示和卖出解释。",
        "A股ETF按一手份额生成可执行指令，不追求精确到每一分钱的目标权重。",
    ]
    cheapest_lot = min(
        _buy_cash_cost(config.lot_size, position.current_price, config)[0]
        for position in positions
    )
    if 0 < cash_left < cheapest_lot:
        notes.append("剩余现金低于当前最便宜 ETF 一手金额，保留到下次执行。")
    if after_summary["max_abs_deviation"] > config.hard_tolerance_pct:
        notes.append("执行后仍有单项偏离超过硬阈值，请检查可投现金规模或季度卖出约束。")
    return notes
