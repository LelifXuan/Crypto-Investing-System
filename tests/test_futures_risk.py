"""Acceptance tests for T06: ATR x leverage futures margin pressure.

The audit found that the strategy generator had no futures-risk gate. The
snapshot now carries one risk bundle per side (long / short) with:
  - atr_pct, leverage, stop_distance_pct
  - one_atr_margin_impact_pct = atr_pct * leverage
  - stop_margin_impact_pct   = stop_distance_pct * leverage
  - liquidation_buffer_pct   = 100 / leverage - stop_distance_pct
  - futures_margin_pressure  in {ok, downsize, small, block}

The pressure is mapped to a GateDiagnostic in the strategy generator and
to a one-line bullet in the terminal summary risk row.
"""

from __future__ import annotations

from app.services.strategy_signal.snapshot_builder import (
    _classify_margin_pressure,
    _compute_futures_risk,
)
from app.services.strategy_signal.strategy_generator import StrategyGenerator
from app.services.terminal_summary_engine import (
    TerminalSummaryEngine,
    _decision_extract_futures_pressure,
    _decision_format_futures_pressure,
)

# ruff: noqa: I001


THRESHOLDS = {"downsize": 20, "small": 40, "block": 70}


def test_classify_margin_pressure_ok() -> None:
    assert _classify_margin_pressure(15.0, THRESHOLDS) == "ok"
    assert _classify_margin_pressure(0.0, THRESHOLDS) == "ok"


def test_classify_margin_pressure_downsize() -> None:
    assert _classify_margin_pressure(20.0, THRESHOLDS) == "downsize"
    assert _classify_margin_pressure(39.9, THRESHOLDS) == "downsize"


def test_classify_margin_pressure_small() -> None:
    assert _classify_margin_pressure(40.0, THRESHOLDS) == "small"
    assert _classify_margin_pressure(69.9, THRESHOLDS) == "small"


def test_classify_margin_pressure_block() -> None:
    assert _classify_margin_pressure(70.0, THRESHOLDS) == "block"
    assert _classify_margin_pressure(150.0, THRESHOLDS) == "block"


def test_classify_margin_pressure_uses_absolute_value() -> None:
    """Short side impact is negative; the classifier folds to absolute value."""
    assert _classify_margin_pressure(-80.0, THRESHOLDS) == "block"
    assert _classify_margin_pressure(-30.0, THRESHOLDS) == "downsize"


def test_compute_futures_risk_atr_3pct_at_10x_is_downsize() -> None:
    risk = _compute_futures_risk(
        atr_pct=3.0,
        entry=100.0,
        stop=96.0,
        leverage=10.0,
        thresholds=THRESHOLDS,
        liq_warn_pct=3.0,
        liq_block_pct=1.5,
    )
    # one-ATR impact = 3.0 * 10 = 30% -> downsize
    assert risk["one_atr_margin_impact_pct"] == 30.0
    assert risk["futures_margin_pressure"] == "downsize"
    assert risk["leverage"] == 10.0
    assert risk["stop_distance_pct"] == 4.0
    assert risk["stop_margin_impact_pct"] == 40.0
    # liq buffer = 100/10 - 4 = 6.0
    assert risk["liquidation_buffer_pct"] == 6.0
    assert risk["futures_risk_blocked"] is False


def test_compute_futures_risk_atr_8pct_at_10x_is_block() -> None:
    risk = _compute_futures_risk(
        atr_pct=8.0,
        entry=100.0,
        stop=92.0,
        leverage=10.0,
        thresholds=THRESHOLDS,
        liq_warn_pct=3.0,
        liq_block_pct=1.5,
    )
    # one-ATR impact = 8.0 * 10 = 80% -> block
    assert risk["one_atr_margin_impact_pct"] == 80.0
    assert risk["futures_margin_pressure"] == "block"
    assert risk["futures_risk_blocked"] is True


def test_compute_futures_risk_low_leverage_caps_buffer() -> None:
    """5x leverage has a larger liq buffer; lower impact -> ok."""
    risk = _compute_futures_risk(
        atr_pct=2.0,
        entry=100.0,
        stop=97.0,
        leverage=5.0,
        thresholds=THRESHOLDS,
        liq_warn_pct=3.0,
        liq_block_pct=1.5,
    )
    # one-ATR impact = 2.0 * 5 = 10% -> ok
    assert risk["one_atr_margin_impact_pct"] == 10.0
    assert risk["futures_margin_pressure"] == "ok"
    # liq buffer = 100/5 - 3 = 17.0
    assert risk["liquidation_buffer_pct"] == 17.0


def test_compute_futures_risk_liquidation_buffer_can_force_block() -> None:
    """Stop too close to liq triggers block even if one-ATR impact is ok."""
    risk = _compute_futures_risk(
        atr_pct=0.5,  # 5% at 10x
        entry=100.0,
        stop=91.0,  # 9% from entry, almost at 10x liq
        leverage=10.0,
        thresholds=THRESHOLDS,
        liq_warn_pct=3.0,
        liq_block_pct=1.5,
    )
    assert risk["one_atr_margin_impact_pct"] == 5.0
    assert risk["futures_margin_pressure"] == "ok"
    # liq buffer = 100/10 - 9 = 1.0, below the 1.5 block threshold
    assert risk["liquidation_buffer_pct"] == 1.0
    assert risk["futures_risk_blocked"] is True
    assert risk["liquidation_buffer_warning"] == "block"


def test_compute_futures_risk_zero_entry_is_safe() -> None:
    """Zero or missing entry must not divide-by-zero."""
    risk = _compute_futures_risk(
        atr_pct=0.0,
        entry=0.0,
        stop=0.0,
        leverage=10.0,
        thresholds=THRESHOLDS,
        liq_warn_pct=3.0,
        liq_block_pct=1.5,
    )
    assert risk["stop_distance_pct"] == 0.0
    assert risk["one_atr_margin_impact_pct"] == 0.0
    assert risk["futures_margin_pressure"] == "ok"


def test_compute_futures_risk_handles_subunit_leverage() -> None:
    """Leverage 1x or below should still produce sane numbers."""
    risk = _compute_futures_risk(
        atr_pct=5.0,
        entry=100.0,
        stop=95.0,
        leverage=1.0,
        thresholds=THRESHOLDS,
        liq_warn_pct=3.0,
        liq_block_pct=1.5,
    )
    assert risk["leverage"] == 1.0
    assert risk["one_atr_margin_impact_pct"] == 5.0
    assert risk["futures_margin_pressure"] == "ok"


def test_strategy_generator_emits_block_gate_when_futures_blocked() -> None:
    config = {
        "thresholds": {
            "spread_hard_limit_bps": 25,
            "slippage_hard_limit_bps": 40,
            "min_depth_score": 25,
        }
    }
    gen = StrategyGenerator(config)
    snapshot = {
        "spread_bps": 0,
        "slippage_bps": 0,
        "depth_score": 100,
        "strategy_bias": "long",
        "futures_risk": {
            "long": {
                "futures_margin_pressure": "block",
                "one_atr_margin_impact_pct": 80.0,
                "thresholds": THRESHOLDS,
            },
            "short": {
                "futures_margin_pressure": "ok",
                "one_atr_margin_impact_pct": 10.0,
                "thresholds": THRESHOLDS,
            },
        },
    }
    gates = gen._gates(snapshot, _DummyScores(data_quality=80))  # noqa: SLF001
    codes = [g["code"] for g in gates]
    assert "FUTURES_MARGIN_BLOCK" in codes
    block = next(g for g in gates if g["code"] == "FUTURES_MARGIN_BLOCK")
    assert block["severity"] == "block"
    assert block["status"] == "fail"
    assert block["required"] == 70
    assert "80" in block["message"]


def test_strategy_generator_emits_small_warning_when_futures_small() -> None:
    config = {
        "thresholds": {
            "spread_hard_limit_bps": 25,
            "slippage_hard_limit_bps": 40,
            "min_depth_score": 25,
        }
    }
    gen = StrategyGenerator(config)
    snapshot = {
        "spread_bps": 0,
        "slippage_bps": 0,
        "depth_score": 100,
        "strategy_bias": "short",
        "futures_risk": {
            "long": {
                "futures_margin_pressure": "ok",
                "one_atr_margin_impact_pct": 10.0,
                "thresholds": THRESHOLDS,
            },
            "short": {
                "futures_margin_pressure": "small",
                "one_atr_margin_impact_pct": 50.0,
                "thresholds": THRESHOLDS,
            },
        },
    }
    gates = gen._gates(snapshot, _DummyScores(data_quality=80))  # noqa: SLF001
    codes = [g["code"] for g in gates]
    assert "FUTURES_MARGIN_SMALL" in codes
    warn = next(g for g in gates if g["code"] == "FUTURES_MARGIN_SMALL")
    assert warn["severity"] == "warning"


def test_strategy_generator_no_futures_gate_when_pressure_ok() -> None:
    config = {
        "thresholds": {
            "spread_hard_limit_bps": 25,
            "slippage_hard_limit_bps": 40,
            "min_depth_score": 25,
        }
    }
    gen = StrategyGenerator(config)
    snapshot = {
        "spread_bps": 0,
        "slippage_bps": 0,
        "depth_score": 100,
        "strategy_bias": "long",
        "futures_risk": {
            "long": {
                "futures_margin_pressure": "ok",
                "one_atr_margin_impact_pct": 5.0,
                "thresholds": THRESHOLDS,
            },
            "short": {
                "futures_margin_pressure": "ok",
                "one_atr_margin_impact_pct": 5.0,
                "thresholds": THRESHOLDS,
            },
        },
    }
    gates = gen._gates(snapshot, _DummyScores(data_quality=80))  # noqa: SLF001
    codes = [g["code"] for g in gates]
    assert not any(c.startswith("FUTURES_MARGIN") for c in codes)


def test_terminal_extract_futures_pressure_uses_active_side() -> None:
    decision = {
        "strategy_bias": "long",
        "futures_risk": {
            "long": {
                "futures_margin_pressure": "block",
                "one_atr_margin_impact_pct": 80.0,
                "leverage": 10.0,
                "atr_pct": 8.0,
                "stop_margin_impact_pct": 30.0,
                "liquidation_buffer_pct": 1.0,
            },
            "short": {
                "futures_margin_pressure": "ok",
                "one_atr_margin_impact_pct": 5.0,
            },
        },
    }
    out = _decision_extract_futures_pressure(decision)
    assert out is not None
    assert out["side"] == "long"
    assert out["level"] == "block"
    assert out["impact_pct"] == 80.0


def test_terminal_extract_futures_pressure_returns_none_when_missing() -> None:
    out = _decision_extract_futures_pressure({"strategy_bias": "long"})
    assert out is None


def test_terminal_format_futures_pressure_block() -> None:
    line = _decision_format_futures_pressure(
        {
            "side": "long",
            "level": "block",
            "impact_pct": 80.0,
            "liquidation_buffer_pct": 1.0,
            "leverage": 10.0,
        }
    )
    assert "block" in line
    assert "做多" in line
    assert "80" in line


def test_terminal_format_futures_pressure_ok_returns_empty() -> None:
    """Pass cases should not be rendered in the risk row."""
    assert _decision_format_futures_pressure({"side": "long", "level": "ok"}) == ""


def test_decision_brief_surfaces_futures_pressure_in_risk_row() -> None:
    """T10: futures pressure is shown on the overview only when the
    strategy is actually entering a position. ``LONG_TRIGGERED`` is
    actionable, so the block-level pressure surfaces in the key_risk
    row. ``WAIT_TRIGGER`` and ``OBSERVE`` are gated out (covered by
    the test_decision_brief_hides_futures_pressure_when_observe
    test below).
    """
    engine = TerminalSummaryEngine()
    decision = {
        "strategy_state": "LONG_TRIGGERED",
        "strategy_bias": "long",
        "strategy_permission": "allow",
        "next_trigger": "已触发，按计划执行",
        "primary_strategy": {},
        "gates": [],
        "futures_risk": {
            "long": {
                "futures_margin_pressure": "block",
                "one_atr_margin_impact_pct": 80.0,
                "leverage": 10.0,
                "atr_pct": 8.0,
                "stop_margin_impact_pct": 40.0,
                "liquidation_buffer_pct": 1.0,
                "futures_risk_blocked": True,
            },
            "short": {
                "futures_margin_pressure": "ok",
                "one_atr_margin_impact_pct": 5.0,
            },
        },
    }
    brief = engine._build_decision_brief(  # noqa: SLF001
        base_summary={"watch_points": []},
        alerts_bundle={},
        strategy_bundle=decision,
        timeframe_snapshots={},
        structure={},
    )
    risk_row = next(row for row in brief["rows"] if row["key"] == "key_risk")
    text = "\n".join(risk_row["bullets"])
    assert "合约保证金压力" in text
    assert "block" in text


def test_decision_brief_hides_futures_pressure_when_observe() -> None:
    """T10: when the strategy is OBSERVE, the overview does NOT
    surface the futures pressure. The user observed this contradiction
    in the live page (OBSERVE state + 建议减半仓位); the gate closes
    that loophole.
    """
    engine = TerminalSummaryEngine()
    decision = {
        "strategy_state": "OBSERVE",
        "strategy_bias": "neutral",
        "strategy_permission": "observe_only",
        "next_trigger": "等待更清晰信号",
        "primary_strategy": {},
        "gates": [],
        "futures_risk": {
            "long": {
                "futures_margin_pressure": "downsize",
                "one_atr_margin_impact_pct": 30.8,
                "leverage": 10.0,
                "stop_margin_impact_pct": 40.0,
                "liquidation_buffer_pct": 6.0,
            },
            "short": {
                "futures_margin_pressure": "ok",
                "one_atr_margin_impact_pct": 5.0,
            },
        },
    }
    brief = engine._build_decision_brief(  # noqa: SLF001
        base_summary={"watch_points": []},
        alerts_bundle={},
        strategy_bundle=decision,
        timeframe_snapshots={},
        structure={},
    )
    risk_row = next(row for row in brief["rows"] if row["key"] == "key_risk")
    text = "\n".join(risk_row["bullets"])
    assert "合约保证金压力" not in text
    assert "减半仓位" not in text
    assert "30.8" not in text


class _DummyScores:
    def __init__(self, data_quality: float = 80.0) -> None:
        self.data_quality_score = data_quality
        self.long_score = 50.0
        self.short_score = 50.0
        self.conflict_score = 0.0
        self.rr_long = 0.0
        self.rr_short = 0.0
        self.confidence = 0.0
