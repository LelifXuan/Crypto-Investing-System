from __future__ import annotations

from app.schemas.btc_derivatives import HedgePlanRequest, HedgePlanResponse

NEAR_BOUNDARY_RATIO = 0.05


def _premium(request: HedgePlanRequest, ratio: float) -> float:
    return round(max(request.net_notional_usd, 0) * ratio, 2)


def _response(
    request: HedgePlanRequest,
    *,
    action: str,
    label: str,
    explanation: str,
    protection_zone: str | None = None,
    premium_ratio: float | None = None,
    legs: list[dict] | None = None,
    warnings: list[str] | None = None,
) -> HedgePlanResponse:
    premium = _premium(request, premium_ratio) if premium_ratio is not None else None
    budget_ok = (
        premium <= request.hedge_budget_usd
        if premium is not None and request.hedge_budget_usd > 0
        else None
    )
    return HedgePlanResponse(
        action=action,
        label=label,
        candidate_legs=legs or [],
        protection_zone=protection_zone,
        estimated_premium_usd=premium,
        budget_ok=budget_ok,
        liquidity_status=request.liquidity_state,
        warnings=warnings or [],
        explanation=explanation,
    )


def build_hedge_plan(request: HedgePlanRequest) -> HedgePlanResponse:
    if request.liquidity_state == "poor":
        return _response(
            request,
            action="wait_due_to_poor_liquidity",
            label="期权流动性不足",
            explanation="候选合约缺少有效双边报价或价差过宽，暂不使用期权硬做保护。",
            warnings=["可先降低网格风险敞口，或等待流动性改善。"],
        )

    if request.portfolio_type == "short_grid":
        if request.grid_upper is None:
            return _response(
                request,
                action="data_insufficient",
                label="缺少空网格上沿",
                explanation="无法定义上破保护区。",
            )
        if request.spot_price > request.grid_upper:
            return _response(
                request,
                action="reduce_grid",
                label="优先降低空网格敞口",
                protection_zone=f"{request.grid_upper:g} 上方",
                explanation="价格已经突破网格上沿，先处理失效网格，再评估期权辅助保护。",
                warnings=["期权不能替代网格边界失效后的直接风险处理。"],
            )
        distance = (request.grid_upper - request.spot_price) / request.grid_upper
        if distance > NEAR_BOUNDARY_RATIO:
            return _response(
                request,
                action="no_hedge_needed",
                label="暂未接近空网格上沿",
                explanation="当前价格距离上沿仍有缓冲，继续监控 Call skew、OI 与保护成本。",
            )
        use_spread = request.iv_state == "iv_high" and request.allow_debit_spread
        action = "call_debit_spread" if use_spread else "buy_call"
        legs = [{"side": "buy", "option_type": "call", "strike_hint": request.grid_upper}]
        if use_spread:
            legs.append(
                {
                    "side": "sell",
                    "option_type": "call",
                    "strike_hint": round(request.grid_upper * 1.15, 2),
                    "covered_by_long_leg": True,
                }
            )
        return _response(
            request,
            action=action,
            label="Call Debit Spread 保护空网格上破" if use_spread else "买入 Call 保护空网格上破",
            protection_zone=f"{request.grid_upper:g} 上方",
            premium_ratio=0.012 if use_spread else 0.02,
            legs=legs,
            explanation="使用最大损失明确的买入期权或借记价差覆盖上破尾部风险。",
            warnings=["不使用裸卖 Call，也不把比例价差描述为安全对冲。"],
        )

    if request.portfolio_type in {"long_grid", "spot_only"}:
        boundary = request.grid_lower
        if request.portfolio_type == "long_grid" and boundary is None:
            return _response(
                request,
                action="data_insufficient",
                label="缺少多网格下沿",
                explanation="无法定义下破保护区。",
            )
        if boundary is not None and request.spot_price < boundary:
            return _response(
                request,
                action="reduce_grid",
                label="优先降低多网格敞口",
                protection_zone=f"{boundary:g} 下方",
                explanation="价格已经跌破网格下沿，先处理失效网格，再评估期权辅助保护。",
                warnings=["期权不能替代网格边界失效后的直接风险处理。"],
            )
        strike = boundary or request.spot_price * 0.9
        if boundary is not None:
            distance = (request.spot_price - boundary) / boundary
            if distance > NEAR_BOUNDARY_RATIO:
                return _response(
                    request,
                    action="no_hedge_needed",
                    label="暂未接近多网格下沿",
                    explanation="当前价格距离下沿仍有缓冲，继续监控 Put skew、OI 与保护成本。",
                )
        use_spread = request.iv_state == "iv_high" and request.allow_debit_spread
        action = "put_debit_spread" if use_spread else "buy_put"
        legs = [{"side": "buy", "option_type": "put", "strike_hint": strike}]
        if use_spread:
            legs.append(
                {
                    "side": "sell",
                    "option_type": "put",
                    "strike_hint": round(strike * 0.85, 2),
                    "covered_by_long_leg": True,
                }
            )
        return _response(
            request,
            action=action,
            label="Put Debit Spread 保护下破" if use_spread else "买入 Put 保护下破",
            protection_zone=f"{strike:g} 下方",
            premium_ratio=0.012 if use_spread else 0.02,
            legs=legs,
            explanation="使用最大损失明确的买入期权或借记价差覆盖下破尾部风险。",
            warnings=["不使用裸卖 Put，也不把比例价差描述为安全对冲。"],
        )

    return _response(
        request,
        action="no_hedge_needed",
        label="中性网格暂不增加方向保护",
        explanation="当前输入未显示单边边界风险，继续监控衍生品证据与网格距离。",
    )
