"""Tests for V1.7.5 EV-based risk_reward_score."""

from app.services.strategy_signal.risk_reward import risk_reward_score_ev


def test_risk_reward_score_ev_no_ceiling():
    """rr=5 with p=0.5 → 250 capped at 100 (no longer the rr=90 ceiling)."""
    assert risk_reward_score_ev(rr=5.0, p_win=0.5) == 100


def test_risk_reward_score_ev_high_p_high_rr():
    """rr=3 with p=0.8 → 240 capped at 100."""
    assert risk_reward_score_ev(rr=3.0, p_win=0.8) == 100


def test_risk_reward_score_ev_low_rr_p():
    """rr=1.5 with p=0.4 → 60 (below trigger threshold 72 typically)."""
    assert risk_reward_score_ev(rr=1.5, p_win=0.4) == 60


def test_risk_reward_score_ev_no_rr():
    """rr=None → 0"""
    assert risk_reward_score_ev(rr=None, p_win=0.5) == 0


def test_risk_reward_score_ev_default_p():
    """Default p_win=0.5"""
    assert risk_reward_score_ev(rr=2.0) == 100  # 0.5 * 2.0 * 100 = 100
    assert risk_reward_score_ev(rr=1.0) == 50  # 0.5 * 1.0 * 100 = 50


def test_risk_reward_score_ev_clamp_at_zero():
    """rr=0 → 0 (not negative)."""
    assert risk_reward_score_ev(rr=0, p_win=0.5) == 0
    assert risk_reward_score_ev(rr=-1, p_win=0.5) == 0