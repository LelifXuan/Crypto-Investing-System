# tests/test_opportunity_scanner.py
import pytest
from app.services.strategy_unified.opportunity_scanner import (
    compute_opportunity_score,
)


class TestComputeOpportunityScore:
    def test_perfect_long_signal(self):
        """全票做多: confidence=80, rr=3.0, consistency=100, 1w frame"""
        score = compute_opportunity_score(
            confidence=80,
            risk_reward=3.0,
            direction="LONG",
            modules_direction_tally={"bullish": 4, "bearish": 0, "neutral": 0},
            timeframe="1w",
        )
        # confidence 80*0.40=32, rr 3/5*100*0.25=15, consistency=100*0.20=20, timeframe=100*0.15=15
        assert score == pytest.approx(82.0)

    def test_mixed_signal_low_consistency(self):
        """分歧信号: 2个偏多 2个偏空"""
        score = compute_opportunity_score(
            confidence=55,
            risk_reward=1.2,
            direction="LONG",
            modules_direction_tally={"bullish": 2, "bearish": 2, "neutral": 0},
            timeframe="4h",
        )
        # consistency=0 (矛盾), timeframe=40*0.15=6
        assert score == pytest.approx(34.0)

    def test_wait_direction_returns_zero(self):
        """WAIT 方向不应参与排序，score 返回 0"""
        score = compute_opportunity_score(
            confidence=50,
            risk_reward=1.0,
            direction="WAIT",
            modules_direction_tally={"bullish": 0, "bearish": 0, "neutral": 4},
            timeframe="1d",
        )
        assert score == 0.0

    def test_risk_reward_capped(self):
        """盈亏比 > 5 时归一化到 1.0"""
        score_5x = compute_opportunity_score(
            confidence=70, risk_reward=5.0, direction="LONG",
            modules_direction_tally={"bullish": 3, "bearish": 0, "neutral": 1},
            timeframe="1d",
        )
        score_10x = compute_opportunity_score(
            confidence=70, risk_reward=10.0, direction="LONG",
            modules_direction_tally={"bullish": 3, "bearish": 0, "neutral": 1},
            timeframe="1d",
        )
        assert score_5x == score_10x  # both capped at rr_norm=1.0
