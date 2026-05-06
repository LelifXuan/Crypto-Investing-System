from __future__ import annotations

from dataclasses import dataclass, field
from decimal import Decimal

from app.core.decimal_utils import DECIMAL_ZERO
from app.quant.indicators import atr_wilder_series
from app.services.execution.liquidity import LiquidityAssessment
from app.services.portfolio.rotation import RotationAssessment


@dataclass(slots=True)
class RiskInput:
    entry_price: Decimal
    equity: Decimal
    leverage: Decimal = Decimal("1")
    requested_notional: Decimal = DECIMAL_ZERO
    max_trade_loss_pct: Decimal = Decimal("0.01")
    max_total_exposure_pct: Decimal = Decimal("0.50")
    max_leverage: Decimal = Decimal("3")
    liquidation_distance_pct: Decimal = Decimal("0.08")
    volatility_scale_threshold_pct: Decimal = Decimal("0.04")
    stop_atr_multiple: Decimal = Decimal("2")
    current_total_exposure: Decimal = DECIMAL_ZERO
    liquidation_price: Decimal | None = None
    data_quality_ok: bool = True
    rotation_assessment: RotationAssessment | None = None
    liquidity_assessment: LiquidityAssessment | None = None
    highs: list[Decimal] = field(default_factory=list)
    lows: list[Decimal] = field(default_factory=list)
    closes: list[Decimal] = field(default_factory=list)


@dataclass(slots=True)
class RiskAssessment:
    recommended_position_notional: Decimal
    recommended_stop_distance: Decimal
    allowed_to_trade: bool
    reasons: list[str]
    reduce_size: bool
    pause_trading: bool


class RiskEngine:
    def assess(self, payload: RiskInput) -> RiskAssessment:
        reasons: list[str] = []
        atr = (
            atr_wilder_series(payload.highs, payload.lows, payload.closes, 14).value
            if payload.closes
            else DECIMAL_ZERO
        )
        stop_distance = (
            atr * payload.stop_atr_multiple if atr else payload.entry_price * Decimal("0.015")
        )
        max_trade_loss = payload.equity * payload.max_trade_loss_pct
        risk_position = (
            (max_trade_loss / stop_distance) * payload.entry_price
            if stop_distance
            else payload.requested_notional
        )
        max_total_exposure = payload.equity * payload.max_total_exposure_pct
        recommended = min(
            value
            for value in (
                payload.requested_notional or risk_position,
                risk_position,
                max(max_total_exposure - payload.current_total_exposure, DECIMAL_ZERO),
            )
            if value is not None
        )

        reduce_size = False
        pause_trading = False

        if payload.leverage > payload.max_leverage:
            reduce_size = True
            reasons.append("当前杠杆超过上限，建议先降低杠杆后再继续参与。")
        if payload.current_total_exposure + recommended > max_total_exposure:
            reduce_size = True
            reasons.append("总敞口接近或超过限制，建议压缩单笔仓位。")
        if (
            atr
            and payload.entry_price
            and (atr / payload.entry_price) >= payload.volatility_scale_threshold_pct
        ):
            reduce_size = True
            recommended *= Decimal("0.75")
            reasons.append("波动率显著抬升，建议主动降低参与规模。")
        if payload.liquidation_price:
            distance = abs(payload.entry_price - payload.liquidation_price) / payload.entry_price
            if distance <= payload.liquidation_distance_pct:
                reduce_size = True
                reasons.append("清算价格距离过近，建议缩小仓位或降低杠杆。")
        if not payload.data_quality_ok:
            pause_trading = True
            reasons.append("数据质量异常，建议暂停交易并等待数据恢复。")
        if payload.rotation_assessment and payload.rotation_assessment.relative_strength < 0:
            reduce_size = True
            reasons.append("相对强弱不足，建议降低该标的优先级和参与仓位。")
        if payload.liquidity_assessment:
            if not payload.liquidity_assessment.min_liquidity_ok:
                pause_trading = True
                reasons.append("流动性不足，建议暂不执行。")
            elif payload.liquidity_assessment.max_executable_size < recommended:
                reduce_size = True
                recommended = payload.liquidity_assessment.max_executable_size
                reasons.append("可执行流动性受限，建议按可成交规模缩减仓位。")

        allowed_to_trade = not pause_trading and recommended > DECIMAL_ZERO
        if not reasons:
            reasons.append("当前风控约束处于允许区间，可按计划参与。")

        return RiskAssessment(
            recommended_position_notional=recommended.quantize(Decimal("0.01"))
            if recommended
            else DECIMAL_ZERO,
            recommended_stop_distance=stop_distance.quantize(Decimal("0.01"))
            if stop_distance
            else DECIMAL_ZERO,
            allowed_to_trade=allowed_to_trade,
            reasons=reasons,
            reduce_size=reduce_size,
            pause_trading=pause_trading,
        )
