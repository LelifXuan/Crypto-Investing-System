from __future__ import annotations

from app.schemas.btc_derivatives import HedgePlanRequest
from app.services.btc_derivatives.hedge_engine import build_hedge_plan


def _request(**overrides) -> HedgePlanRequest:
    values = {
        "portfolio_type": "short_grid",
        "spot_price": 61_000,
        "grid_lower": 45_000,
        "grid_upper": 62_000,
        "net_notional_usd": 5_000,
        "hedge_budget_usd": 150,
        "preferred_expiry_bucket": "60D",
        "allow_debit_spread": True,
        "iv_state": "iv_neutral",
        "liquidity_state": "usable",
    }
    values.update(overrides)
    return HedgePlanRequest.model_validate(values)


def test_short_grid_near_upper_bound_uses_finite_risk_call_protection() -> None:
    plan = build_hedge_plan(_request())

    assert plan.action == "buy_call"
    assert plan.candidate_legs == [{"side": "buy", "option_type": "call", "strike_hint": 62_000}]
    assert plan.budget_ok is True


def test_grid_boundary_breach_prioritizes_reduction() -> None:
    short_plan = build_hedge_plan(_request(spot_price=63_000))
    long_plan = build_hedge_plan(
        _request(
            portfolio_type="long_grid",
            spot_price=44_000,
            grid_lower=45_000,
            grid_upper=62_000,
        )
    )

    assert short_plan.action == "reduce_grid"
    assert long_plan.action == "reduce_grid"


def test_high_iv_uses_debit_spread_and_poor_liquidity_blocks_option_hedge() -> None:
    high_iv = build_hedge_plan(_request(iv_state="iv_high"))
    poor = build_hedge_plan(_request(liquidity_state="poor"))

    assert high_iv.action == "call_debit_spread"
    assert high_iv.candidate_legs[1]["covered_by_long_leg"] is True
    assert poor.action == "wait_due_to_poor_liquidity"
    assert poor.candidate_legs == []


def test_long_grid_uses_put_protection_and_forbidden_actions_never_appear() -> None:
    plan = build_hedge_plan(
        _request(
            portfolio_type="long_grid",
            spot_price=46_000,
            grid_lower=45_000,
            iv_state="iv_high",
        )
    )
    serialized = str(plan.model_dump()).lower()

    assert plan.action == "put_debit_spread"
    assert "naked_sell" not in serialized
    assert "ratio_spread" not in serialized
    assert "sell_call" not in serialized
    assert "sell_put" not in serialized
