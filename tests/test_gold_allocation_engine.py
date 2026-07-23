from __future__ import annotations

# ruff: noqa: E501
import pytest

from app.services.gold_allocation_engine import build_gold_allocation_plan


def _portfolio(**overrides):
    payload = {
        "total_portfolio_value": 200_000,
        "current_gold_value": 8_000,
        "monthly_new_cash": 10_000,
        "current_gold_cost": 7_500,
        "is_quarterly_rebalance_month": False,
        "crypto_weight": 0.22,
        "us_equity_weight": 0.18,
        "a_share_weight": 0.16,
        "halo_etf_weight": 0.28,
        "cashflow_etf_weight": 0.20,
    }
    payload.update(overrides)
    return payload


def _macro(**overrides):
    payload = {
        "inflation_yoy": 0.031,
        "real_yield_10y_delta_4w": -0.002,
        "dxy_change_4w": -0.012,
        "global_m2_delta_13w": 0.015,
        "fed_balance_sheet_delta_13w": -0.004,
        "vix_level": 22.0,
        "liquidity_credit_score": 56,
        "cross_asset_score": 54,
    }
    payload.update(overrides)
    return payload


def _goldhub(**overrides):
    payload = {
        "central_bank_net_purchase_tonnes_12m": 920,
        "central_bank_net_purchase_tonnes_3m": 210,
        "gold_etf_flow_tonnes_1m": 34,
        "mine_production_yoy": 0.012,
        "aisc_yoy": 0.08,
        "recycling_yoy": 0.025,
        "supply_demand_balance_tonnes": -80,
        "futures_oi_change_4w": 0.02,
        "futures_volume_zscore": 0.8,
        "cot_net_spec_percentile": 0.55,
    }
    payload.update(overrides)
    return payload


def _market(**overrides):
    payload = {
        "xaut_symbol": "XAUT_USDT",
        "price": 4552,
        "ret_1d": -0.012,
        "ret_7d": -0.02,
        "ret_30d": 0.048,
        "drawdown_60d": -0.055,
        "natr_14": 0.024,
        "volume_zscore": 1.2,
        "above_ma50": True,
        "above_ma200": True,
        "daily_window": {
            "trend": "above_ma50",
            "ret_30d": 0.048,
            "drawdown": -0.055,
            "logic": "日线仍处于均线支撑上方，但波动偏高，适合分批执行。",
        },
        "weekly_window": {
            "trend": "above_ma200",
            "ret_12w": 0.082,
            "drawdown": -0.04,
            "logic": "周线仍维持长期上行结构，配置目标区间不因短线波动下调。",
        },
        "updated_at": "2026-06-05 15:00",
    }
    payload.update(overrides)
    return payload


def test_underweight_supportive_inputs_return_actionable_add_guidance() -> None:
    plan = build_gold_allocation_plan(
        _portfolio(current_gold_value=6_000),
        macro=_macro(),
        goldhub=_goldhub(),
        market=_market(),
    ).to_dict()

    assert plan["allocation_state"] == "underweight"
    assert plan["target_range"]["min"] >= 0.08
    assert plan["current_weight"] < plan["target_range"]["min"]
    assert plan["primary_instruction"]
    assert plan["decision_summary"]
    assert plan["suggested_this_month"] > 0
    assert plan["suggested_this_month"] <= 6000
    assert plan["module_cards"]
    assert any(card["key"] == "official_reserve_demand" for card in plan["module_cards"])
    assert any("官方储备" in step or "央行" in step for step in plan["reasoning_steps"])


def test_underweight_liquidity_selloff_forces_tranches_not_full_gap() -> None:
    plan = build_gold_allocation_plan(
        _portfolio(current_gold_value=5_000, monthly_new_cash=20_000),
        macro=_macro(),
        goldhub=_goldhub(),
        market=_market(
            ret_7d=-0.07,
            btc_ret_7d=-0.11,
            eth_ret_7d=-0.10,
            nasdaq_ret_7d=-0.05,
            dxy_ret_7d=0.02,
            vix_change_7d=0.24,
            volume_zscore=2.1,
            gold_risk_corr_20d=0.45,
        ),
    ).to_dict()

    assert plan["allocation_state"] == "underweight"
    assert plan["execution_style"] == "split_2_to_3_tranches"
    assert plan["suggested_this_month"] < plan["gap_to_target_min"]
    assert any(card["key"] == "liquidity_selloff_rebound" for card in plan["module_cards"])
    assert "一次性" not in plan["primary_instruction"]


def test_overweight_non_quarter_pauses_adding_without_reduce_amount() -> None:
    plan = build_gold_allocation_plan(
        _portfolio(current_gold_value=45_000, is_quarterly_rebalance_month=False),
        macro=_macro(),
        goldhub=_goldhub(),
        market=_market(),
    ).to_dict()

    assert plan["allocation_state"] == "overweight"
    assert plan["execution_style"] == "pause_add"
    assert plan["suggested_this_month"] == 0
    assert plan["gap_above_target_max"] > 0
    assert "暂停" in plan["primary_instruction"]


def test_overweight_quarterly_material_excess_reduces_to_upper_band() -> None:
    plan = build_gold_allocation_plan(
        _portfolio(current_gold_value=45_000, is_quarterly_rebalance_month=True),
        macro=_macro(real_yield_10y_delta_4w=0.003, dxy_change_4w=0.025, global_m2_delta_13w=-0.02),
        goldhub=_goldhub(),
        market=_market(),
        options={"allow_quarterly_sell": True},
    ).to_dict()

    assert plan["allocation_state"] == "overweight"
    assert plan["execution_style"] == "quarterly_reduce_to_upper_band"
    assert plan["suggested_this_month"] < 0


def test_missing_macro_is_explicit_in_cards_warnings_and_reasoning() -> None:
    plan = build_gold_allocation_plan(
        _portfolio(),
        macro={},
        goldhub=_goldhub(),
        market=_market(),
    ).to_dict()

    macro_card = next(
        card for card in plan["module_cards"] if card["key"] == "macro_monetary_environment"
    )
    assert macro_card["data_quality"] in {"missing", "partial"}
    assert macro_card["warnings"]
    assert any("宏观" in warning or "实际利率" in warning for warning in plan["warnings"])
    assert any("数据缺失" in step or "置信度" in step for step in plan["reasoning_steps"])


def test_derivative_crowding_splits_execution_without_overriding_band() -> None:
    plan = build_gold_allocation_plan(
        _portfolio(current_gold_value=8_000),
        macro=_macro(),
        goldhub=_goldhub(
            futures_oi_change_4w=0.12,
            futures_volume_zscore=1.8,
            cot_net_spec_percentile=0.78,
        ),
        market=_market(ret_30d=0.07),
    ).to_dict()

    assert plan["target_range"]["min"] >= 0.08
    assert plan["execution_style"] == "split_2_to_3_tranches"
    derivatives = next(
        card for card in plan["module_cards"] if card["key"] == "derivatives_pressure"
    )
    assert derivatives["allocation_effect"] == "split_add"
    assert "拥挤" in derivatives["headline"] or "分批" in derivatives["interpretation"]


def test_tight_supply_and_reserve_demand_are_long_term_support_reasons() -> None:
    plan = build_gold_allocation_plan(
        _portfolio(current_gold_value=10_000),
        macro=_macro(),
        goldhub=_goldhub(),
        market=_market(),
    ).to_dict()

    joined = " ".join(plan["reasoning_steps"]) + plan["decision_summary"]
    assert "官方储备" in joined or "央行" in joined
    assert "供给" in joined


def test_market_windows_and_cross_asset_hedge_need_are_visible() -> None:
    plan = build_gold_allocation_plan(
        _portfolio(),
        macro=_macro(),
        goldhub=_goldhub(),
        market=_market(),
    ).to_dict()

    xaut = next(card for card in plan["module_cards"] if card["key"] == "xaut_price_state")
    hedge = next(card for card in plan["module_cards"] if card["key"] == "portfolio_hedging_need")
    assert any("日线" in fact for fact in xaut["facts"])
    assert any("周线" in fact for fact in xaut["facts"])
    assert any("Crypto" in fact for fact in hedge["facts"])
    assert any("美股" in fact for fact in hedge["facts"])
    assert any("A股" in fact for fact in hedge["facts"])


def test_macro_overview_layers_are_used_as_gold_macro_evidence() -> None:
    macro_overview = {
        "total_score": 46,
        "data_completeness": {"effective_count": 12, "total_count": 18, "ratio": 0.67},
        "layer_contributions": {
            "rates_policy": -3.2,
            "inflation": -1.1,
            "liquidity_credit": -2.4,
            "cross_asset_confirmation": 1.5,
        },
        "layers": [
            {
                "layer_key": "rates_policy",
                "label_cn": "利率与政策",
                "score": 38,
                "bias": "偏紧",
                "effective_count": 3,
                "total_count": 4,
                "indicators": [
                    {
                        "indicator_key": "real_yield_10y",
                        "display_label": "美国10年实际利率",
                        "value_num": 2.1,
                        "unit": "%",
                        "is_scored": True,
                    },
                    {
                        "indicator_key": "us10y_yield",
                        "display_label": "美国10年国债收益率",
                        "value_num": 4.6,
                        "unit": "%",
                        "is_scored": True,
                    },
                ],
            },
            {
                "layer_key": "inflation",
                "label_cn": "通胀与价格",
                "score": 42,
                "bias": "偏紧",
                "effective_count": 2,
                "total_count": 3,
                "indicators": [
                    {
                        "indicator_key": "core_cpi_yoy",
                        "display_label": "核心CPI同比",
                        "value_num": 3.4,
                        "unit": "%",
                        "is_scored": True,
                    },
                ],
            },
            {
                "layer_key": "cross_asset_confirmation",
                "label_cn": "跨资产确认",
                "score": 58,
                "bias": "中性",
                "effective_count": 2,
                "total_count": 3,
                "indicators": [
                    {
                        "indicator_key": "dxy",
                        "display_label": "美元指数DXY",
                        "value_num": 104.3,
                        "unit": "index",
                        "is_scored": True,
                    },
                ],
            },
        ],
    }
    plan = build_gold_allocation_plan(
        _portfolio(),
        macro=macro_overview,
        goldhub=_goldhub(),
        market=_market(),
    ).to_dict()

    macro_card = next(
        card for card in plan["module_cards"] if card["key"] == "macro_monetary_environment"
    )
    assert macro_card["data_quality"] != "missing"
    assert any("利率" in fact or "通胀" in fact or "美元" in fact for fact in macro_card["facts"])


def test_gold_macro_card_uses_5y_tips_as_real_rate_evidence() -> None:
    macro_overview = {
        "total_score": 42,
        "layer_contributions": {
            "cross_asset_confirmation": -4.5,
        },
        "layers": [
            {
                "layer_key": "cross_asset_confirmation",
                "label_cn": "跨资产确认",
                "score": 38,
                "bias": "偏紧",
                "effective_count": 2,
                "total_count": 3,
                "indicators": [
                    {
                        "indicator_key": "real_yield_5y",
                        "display_label": "美国5年期通胀保值国债收益率",
                        "display_code": "US 5Y TIPS",
                        "value_num": 1.83,
                        "unit": "%",
                        "source_provider": "tradingeconomics_web",
                        "observation_ts": "2026-06-08T00:00:00+00:00",
                        "is_scored": True,
                    },
                    {
                        "indicator_key": "real_yield_10y",
                        "display_label": "美国10年实际利率",
                        "value_num": 2.22,
                        "unit": "%",
                        "is_scored": True,
                    },
                ],
            }
        ],
    }
    plan = build_gold_allocation_plan(
        _portfolio(),
        macro=macro_overview,
        goldhub=_goldhub(),
        market=_market(),
    ).to_dict()

    macro_card = next(
        card for card in plan["module_cards"] if card["key"] == "macro_monetary_environment"
    )
    facts_text = "\n".join(macro_card["facts"])

    assert "美国5年期通胀保值国债收益率" in facts_text
    assert "1.83%" in facts_text
    assert "机会成本" in facts_text or "实际利率压力" in facts_text


def test_liquidity_and_derivatives_have_daily_weekly_windows() -> None:
    plan = build_gold_allocation_plan(
        _portfolio(current_gold_value=5_000, monthly_new_cash=20_000),
        macro=_macro(liquidity_credit_score=35, cross_asset_score=42),
        goldhub=_goldhub(
            futures_oi_change_4w=0.12, futures_volume_zscore=None, cot_net_spec_percentile=None
        ),
        market=_market(
            ret_7d=-0.065, natr_14=0.041, volume_zscore=2.2, btc_ret_7d=-0.1, nasdaq_ret_7d=-0.05
        ),
    ).to_dict()

    for key in ("liquidity_selloff_rebound", "derivatives_pressure"):
        card = next(card for card in plan["module_cards"] if card["key"] == key)
        assert card["window_views"]["daily"]["label"] == "日线窗口"
        assert card["window_views"]["weekly"]["label"] == "周线窗口"
        assert card["window_views"]["daily"]["headline"]
        assert card["window_views"]["weekly"]["headline"]

    derivatives = next(
        card for card in plan["module_cards"] if card["key"] == "derivatives_pressure"
    )
    assert derivatives["window_views"]["weekly"]["data_quality"] in {"partial", "proxy"}


def test_invalid_total_value_is_rejected() -> None:
    with pytest.raises(ValueError, match="total"):
        build_gold_allocation_plan(_portfolio(total_portfolio_value=0))


def test_build_gold_allocation_plan_includes_gold_macro_snapshot():
    """验证 AllocationPlan.to_dict() 输出包含 gold_macro_snapshot 字段。"""
    plan_dict = _build_test_plan().to_dict()
    assert "gold_macro_snapshot" in plan_dict
    assert "real_yield_10y" in plan_dict["gold_macro_snapshot"]
    assert "dxy" in plan_dict["gold_macro_snapshot"]
    assert "cpi_yoy" in plan_dict["gold_macro_snapshot"]
    assert "vix" in plan_dict["gold_macro_snapshot"]
    assert "_diagnostics" in plan_dict["gold_macro_snapshot"]


def _build_test_plan():
    """构造最小可用 AllocationPlan 用于测试"""
    from app.services.gold_allocation_engine import AllocationPlan
    return AllocationPlan(
        allocation_state="within_range",
        allocation_score=60.0,
        target_range={"min": 0.05, "max": 0.12},
        current_weight=0.08,
        gap_to_target_min=0.0,
        gap_above_target_max=0.0,
        suggested_this_month=100.0,
        execution_style="maintain",
        primary_instruction="保持当前配置",
        decision_summary="测试场景",
        reasoning_steps=["测试"],
        module_cards=[],
        data_quality={"confidence": 0.8, "missing_modules": [], "partial_modules": [], "proxy_modules": []},
        warnings=[],
        drivers={},
        asset_impact_summary={"gold": "测试"},
        macro_payload={},  # 空 macro 也能正常序列化
    )
