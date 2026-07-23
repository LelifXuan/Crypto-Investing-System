"""Tests for gold V3 Pydantic schemas."""
import pytest
from pydantic import ValidationError


class TestGoldV3SignalLight:
    def test_signal_light_valid(self):
        from app.schemas.gold_v3 import GoldSignalLight
        light = GoldSignalLight(
            key="real_yield_10y",
            label="实际利率",
            code="TIPS 10Y",
            value=2.03,
            unit="%",
            bias="bearish",
            bias_label="偏空",
            bias_reason="利率偏高，债券吸引力上升，压制黄金",
            source="fred_public_csv",
        )
        assert light.key == "real_yield_10y"
        assert light.value == 2.03
        assert light.bias == "bearish"

    def test_signal_light_missing_bias(self):
        from app.schemas.gold_v3 import GoldSignalLight
        light = GoldSignalLight(
            key="dxy",
            label="美元指数",
            code="DXY",
            value=None,
            unit="index",
            bias="missing",
            bias_label="数据不足",
            bias_reason="数据不足",
            source="",
        )
        assert light.value is None
        assert light.bias == "missing"


class TestGoldV3AllocationResponse:
    def test_allocation_response_minimal(self):
        from app.schemas.gold_v3 import (
            GoldV3AllocationResponse,
            GoldSignalLight,
            GoldSpotDca,
            GoldContractRef,
        )
        resp = GoldV3AllocationResponse(
            signals=[
                GoldSignalLight(
                    key="real_yield_10y", label="实际利率", code="TIPS 10Y",
                    value=2.03, unit="%", bias="bearish", bias_label="偏空",
                    bias_reason="利率偏高", source="fred_public_csv",
                ),
                GoldSignalLight(
                    key="dxy", label="美元指数", code="DXY",
                    value=120.4, unit="index", bias="bearish", bias_label="偏空",
                    bias_reason="美元走强", source="fred_public_csv",
                ),
                GoldSignalLight(
                    key="vix", label="波动率", code="VIX",
                    value=18.8, unit="index", bias="neutral", bias_label="中性",
                    bias_reason="VIX 中性", source="fred_public_csv",
                ),
            ],
            spot_summary="⚠ 偏谨慎",
            liquidity_shock_detected=False,
            spot=GoldSpotDca(
                current_weight=0.05,
                target_min=0.05,
                target_max=0.08,
                weight_state="at_min",
                base_amount=500.0,
                dip_multiplier=2.0,
                macro_gate_passed=True,
                macro_gate_reason="利率<2.8% AND DXY<108",
                drawdown_triggered=True,
                drawdown_60d=-0.12,
                drawdown_threshold=0.08,
                indicator_confirmations=[
                    {"label": "RSI(14)", "value": 38.0, "display": "38", "condition": "≤40", "passed": True},
                    {"label": "布林位置", "value": 0.18, "display": "0.18", "condition": "≤0.2", "passed": True},
                    {"label": "距EMA20", "value": -0.021, "display": "-2.1%", "condition": "≤-2%", "passed": True},
                    {"label": "CCI(20)", "value": -85.0, "display": "-85", "condition": "≤-80", "passed": True},
                    {"label": "成交量", "value": -1.2, "display": "Z=-1.2", "condition": "Z≥1.5", "passed": False},
                ],
                confirmations_passed=4,
                confirmations_required=3,
                recommended_amount=1500.0,
                recommendation_reason="基础定投 + 加仓（回撤触发 + 指标确认 4/5）",
            ),
            contract=GoldContractRef(
                price=4091.9,
                above_ma50=False,
                ma50_value=4350.0,
                above_ma200=False,
                ma200_value=4680.0,
                drawdown_60d=-0.12,
                natr_14=0.017,
                volume_zscore=-1.2,
                oi_change_4w=None,
                funding_rate=None,
                cot_net_spec_percentile=None,
                derivatives_note="OI/资金费率数据积累中",
                updated_at="2026-07-22T10:00:00",
            ),
        )
        assert len(resp.signals) == 3
        assert resp.spot.macro_gate_passed is True
        assert resp.spot.recommended_amount == 1500.0
        assert resp.contract.drawdown_60d == -0.12

    def test_allocation_response_serializes_to_json(self):
        import json
        from app.schemas.gold_v3 import (
            GoldV3AllocationResponse, GoldSignalLight,
            GoldSpotDca, GoldContractRef,
        )
        resp = GoldV3AllocationResponse(
            signals=[
                GoldSignalLight(
                    key="real_yield_10y", label="实际利率", code="TIPS 10Y",
                    value=2.03, unit="%", bias="bearish", bias_label="偏空",
                    bias_reason="利率偏高", source="fred_public_csv",
                ),
                GoldSignalLight(
                    key="dxy", label="美元指数", code="DXY",
                    value=None, unit="index", bias="missing", bias_label="数据不足",
                    bias_reason="数据不足", source="",
                ),
                GoldSignalLight(
                    key="vix", label="波动率", code="VIX",
                    value=18.8, unit="index", bias="neutral", bias_label="中性",
                    bias_reason="VIX 中性", source="fred_public_csv",
                ),
            ],
            spot_summary="中性",
            liquidity_shock_detected=False,
            spot=GoldSpotDca(
                current_weight=0.05, target_min=0.05, target_max=0.08,
                weight_state="at_min",
                base_amount=500.0, dip_multiplier=2.0,
                macro_gate_passed=True, macro_gate_reason="ok",
                drawdown_triggered=False, drawdown_60d=-0.05, drawdown_threshold=0.08,
                indicator_confirmations=[],
                confirmations_passed=0, confirmations_required=3,
                recommended_amount=500.0,
                recommendation_reason="基础定投（回撤未触发）",
            ),
            contract=GoldContractRef(
                price=4091.9, above_ma50=False, ma50_value=4350.0,
                above_ma200=False, ma200_value=4680.0,
                drawdown_60d=-0.12, natr_14=0.017, volume_zscore=-1.2,
                oi_change_4w=None, funding_rate=None, cot_net_spec_percentile=None,
                derivatives_note="数据积累中", updated_at="2026-07-22T10:00:00",
            ),
        )
        d = json.loads(resp.model_dump_json())
        assert d["liquidity_shock_detected"] is False
        assert len(d["signals"]) == 3
        assert d["spot"]["recommended_amount"] == 500.0
