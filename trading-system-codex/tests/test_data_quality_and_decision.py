from __future__ import annotations

from dataclasses import dataclass
from datetime import UTC, datetime, timedelta
from decimal import Decimal

from app.services.data_quality import DataQualityMonitor
from app.services.decision.multi_timeframe import MultiTimeframeDecisionEngine, TimeframeSignal
from app.services.decision.scenario import ScenarioEngine
from app.services.execution.liquidity import ExecutionLiquidityEngine
from app.services.portfolio.rotation import PortfolioRotationEngine
from app.services.risk import RiskEngine, RiskInput


@dataclass
class CandleStub:
    ts_open: datetime
    high: Decimal
    low: Decimal
    close: Decimal
    volume: Decimal


def test_data_quality_monitor_degrades_sparse_and_stale_data() -> None:
    start = datetime(2026, 1, 1, tzinfo=UTC)
    candles = [
        CandleStub(
            ts_open=start + timedelta(hours=index * 2),
            high=Decimal("100"),
            low=Decimal("100") if index % 3 == 0 else Decimal("99"),
            close=Decimal("99.5"),
            volume=Decimal("0") if index % 2 == 0 else Decimal("10"),
        )
        for index in range(12)
    ]
    assessment = DataQualityMonitor().assess_candles(
        candles,
        expected_min_points=20,
        stale_after_seconds=3600,
        now=start + timedelta(days=2),
    )
    assert assessment.status in {"degraded", "bad"}
    assert assessment.can_alert is False
    assert assessment.issues


def test_multi_timeframe_engine_outputs_actionable_mode() -> None:
    result = MultiTimeframeDecisionEngine().decide(
        [
            TimeframeSignal("1d", "bullish", 0.74),
            TimeframeSignal("4h", "bullish", 0.61),
            TimeframeSignal("1h", "bearish", 0.58),
        ]
    )
    assert result.mode == "wait_pullback_long"
    assert result.confirmation
    assert result.invalidation
    assert result.suggested_action


def test_scenario_engine_builds_structured_context() -> None:
    result = ScenarioEngine().build(
        primary_scenario="breakout_watch",
        evidence_for=["4h 突破高点", "成交量同步扩张"],
        evidence_against=["1d 仍在震荡边缘"],
        confirmation="等待 1d 收盘确认。",
        invalidation="重新跌回突破位下方。",
        suggested_action="先观察，确认后再跟进。",
        alternative_scenarios=["range_only"],
        risk_notes=["高位追价风险偏高"],
    )
    assert result.primary_scenario == "breakout_watch"
    assert result.evidence_for
    assert result.evidence_against
    assert result.confirmation
    assert result.invalidation
    assert result.suggested_action


def test_rotation_liquidity_and_risk_engine_form_risk_off_hint() -> None:
    rotation = PortfolioRotationEngine().assess(
        relative_strength=-0.3,
        beta_hint=1.2,
        sector_leadership="lagging",
        volatility_adjusted_momentum=-0.2,
        correlation=0.84,
    )
    liquidity = ExecutionLiquidityEngine().assess(
        bid_ask_spread=Decimal("0.002"),
        depth=Decimal("5000"),
        slippage=Decimal("0.004"),
        min_depth=Decimal("8000"),
        funding_cost=Decimal("0.0018"),
        requested_size=Decimal("12000"),
    )
    assessment = RiskEngine().assess(
        RiskInput(
            entry_price=Decimal("100"),
            equity=Decimal("10000"),
            requested_notional=Decimal("2000"),
            leverage=Decimal("4"),
            highs=[Decimal("101"), Decimal("103"), Decimal("102"), Decimal("104")] * 5,
            lows=[Decimal("99"), Decimal("100"), Decimal("99.5"), Decimal("101")] * 5,
            closes=[Decimal("100"), Decimal("102"), Decimal("101"), Decimal("103")] * 5,
            data_quality_ok=False,
            rotation_assessment=rotation,
            liquidity_assessment=liquidity,
        )
    )
    assert assessment.pause_trading is True
    assert assessment.allowed_to_trade is False
    assert assessment.reasons
