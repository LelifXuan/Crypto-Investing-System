"""Acceptance tests for T10: hide futures margin pressure on the
overview when the strategy has no actionable plan.

The audit found the overview rendering
``合约保证金压力=block: long 侧 one-ATR 影响 80%，合约开仓被拒绝``
while the strategy state was ``OBSERVE``. The contradiction is
resolved by gating the pressure bullet behind an actionable plan
state (TRIGGERED / *_BIAS / SETUP_DETECTED). The strategy page
still owns the gate rendering, so the user keeps the signal — it
just does not leak into the overview as advice for a position that
does not exist.
"""

from __future__ import annotations

import pytest

from app.services.terminal_summary_engine import (
    TerminalSummaryEngine,
    _decision_should_show_futures_pressure,
)

# ruff: noqa: I001


# ---------------------------------------------------------------------------
# _decision_should_show_futures_pressure unit tests
# ---------------------------------------------------------------------------


@pytest.mark.parametrize(
    "state",
    [
        "LONG_TRIGGERED",
        "SHORT_TRIGGERED",
        "TREND_FOLLOW_TRIGGERED",
        "BREAKOUT_TRIGGERED",
        "BREAKDOWN_TRIGGERED",
        "LONG_BIAS",
        "SHORT_BIAS",
        "SETUP_DETECTED",
    ],
)
def test_should_show_futures_pressure_for_actionable_state(state: str) -> None:
    assert _decision_should_show_futures_pressure({"strategy_state": state}) is True


@pytest.mark.parametrize(
    "state",
    [
        "OBSERVE",
        "NO_EDGE",
        "CONFLICTED_NO_TRADE",
        "EVENT_WAIT",
        "RISK_OFF",
        "INVALID_PLAN_LEVELS",
        "WAIT_LOWER_TF_CONFIRMATION",
        "WAIT_LONG_CONFIRMATION",
        "WAIT_SHORT_CONFIRMATION",
        "WAIT_PULLBACK_CONFIRMATION",
        "WAIT_RETEST_AFTER_MISSED_MOVE",
        "TP1_HIT",
        "TP2_HIT",
        "STOP_HIT",
        "SETUP_EXPIRED",
        "SETUP_INVALIDATED",
        "MOVE_MISSED",
        "blocked",  # legacy
    ],
)
def test_should_hide_futures_pressure_for_non_actionable_state(state: str) -> None:
    assert _decision_should_show_futures_pressure({"strategy_state": state}) is False


def test_should_hide_futures_pressure_when_decision_empty() -> None:
    assert _decision_should_show_futures_pressure({}) is False
    assert _decision_should_show_futures_pressure(None) is False  # type: ignore[arg-type]


def test_should_hide_futures_pressure_when_state_missing() -> None:
    assert _decision_should_show_futures_pressure({"strategy_bias": "long"}) is False


# ---------------------------------------------------------------------------
# End-to-end: the overview no longer surfaces the pressure for OBSERVE
# ---------------------------------------------------------------------------


def _decision_brief(decision: dict) -> dict:
    engine = TerminalSummaryEngine()
    return engine._build_decision_brief(  # noqa: SLF001
        base_summary={"watch_points": []},
        alerts_bundle={},
        strategy_bundle=decision,
        timeframe_snapshots={},
        structure={},
    )


def test_overview_hides_futures_pressure_for_observe_state() -> None:
    decision = {
        "strategy_state": "OBSERVE",
        "strategy_bias": "neutral",
        "next_trigger": "等待更清晰信号",
        "futures_risk": {
            "long": {
                "futures_margin_pressure": "downsize",
                "one_atr_margin_impact_pct": 30.8,
                "leverage": 10.0,
            },
            "short": {
                "futures_margin_pressure": "ok",
                "one_atr_margin_impact_pct": 5.0,
            },
        },
    }
    brief = _decision_brief(decision)
    key_risk = next(row for row in brief["rows"] if row["key"] == "key_risk")
    text = "\n".join(key_risk["bullets"])
    assert "合约保证金压力" not in text
    assert "30.8" not in text
    assert "减半仓位" not in text


def test_overview_hides_futures_pressure_for_wait_states() -> None:
    for state in (
        "WAIT_LOWER_TF_CONFIRMATION",
        "WAIT_LONG_CONFIRMATION",
        "WAIT_SHORT_CONFIRMATION",
        "NO_EDGE",
        "RISK_OFF",
    ):
        decision = {
            "strategy_state": state,
            "strategy_bias": "long",
            "futures_risk": {
                "long": {
                    "futures_margin_pressure": "block",
                    "one_atr_margin_impact_pct": 80.0,
                }
            },
        }
        brief = _decision_brief(decision)
        key_risk = next(row for row in brief["rows"] if row["key"] == "key_risk")
        text = "\n".join(key_risk["bullets"])
        assert "合约保证金压力" not in text, f"leaked for state={state}"


def test_overview_shows_futures_pressure_for_triggered_state() -> None:
    decision = {
        "strategy_state": "LONG_TRIGGERED",
        "strategy_bias": "long",
        "next_trigger": "已触发，按计划执行",
        "futures_risk": {
            "long": {
                "futures_margin_pressure": "small",
                "one_atr_margin_impact_pct": 50.0,
                "leverage": 10.0,
            }
        },
    }
    brief = _decision_brief(decision)
    key_risk = next(row for row in brief["rows"] if row["key"] == "key_risk")
    text = "\n".join(key_risk["bullets"])
    assert "合约保证金压力" in text


def test_overview_shows_futures_pressure_for_bias_state() -> None:
    """LONG_BIAS is actionable (the user may consider a position) so
    the pressure bullet surfaces. This gives the user a heads-up
    about margin requirements before a trigger fires.
    """
    decision = {
        "strategy_state": "LONG_BIAS",
        "strategy_bias": "long",
        "next_trigger": "等待 setup 结构完整形成",
        "futures_risk": {
            "long": {
                "futures_margin_pressure": "downsize",
                "one_atr_margin_impact_pct": 30.8,
                "leverage": 10.0,
            }
        },
    }
    brief = _decision_brief(decision)
    key_risk = next(row for row in brief["rows"] if row["key"] == "key_risk")
    text = "\n".join(key_risk["bullets"])
    assert "合约保证金压力" in text


def test_overview_hides_futures_pressure_for_terminal_states() -> None:
    """TP1_HIT / TP2_HIT / STOP_HIT / SETUP_EXPIRED / MOVE_MISSED are
    terminal — the position lifecycle is over. The pressure bullet
    should not surface as advice for a position that has already
    closed.
    """
    for state in ("TP1_HIT", "TP2_HIT", "STOP_HIT", "MOVE_MISSED", "SETUP_EXPIRED"):
        decision = {
            "strategy_state": state,
            "strategy_bias": "long",
            "futures_risk": {
                "long": {
                    "futures_margin_pressure": "block",
                    "one_atr_margin_impact_pct": 80.0,
                }
            },
        }
        brief = _decision_brief(decision)
        key_risk = next(row for row in brief["rows"] if row["key"] == "key_risk")
        text = "\n".join(key_risk["bullets"])
        assert "合约保证金压力" not in text, f"leaked for state={state}"
