from __future__ import annotations

import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))


def test_strategy_js_no_generic_trigger_copy():
    source = (Path(__file__).resolve().parents[1] / "app" / "static" / "pages" / "strategy.js").read_text(encoding="utf-8", errors="replace")
    assert "但触发条件未齐" not in source, "Generic trigger copy still present in strategy.js"


def test_strategy_js_has_trigger_board():
    root = Path(__file__).resolve().parents[1]
    source = (root / "app" / "static" / "pages" / "strategy" / "renderTradePlans.js").read_text(encoding="utf-8")
    assert "entry_logic" in source, "V2 trade plans must expose entry logic"
    assert "invalidation" in source, "V2 trade plans must expose invalidation logic"
    assert "position_rule" in source, "V2 trade plans must expose position rules"


def test_strategy_js_trigger_diagnostics_visible():
    root = Path(__file__).resolve().parents[1]
    source = (root / "app" / "static" / "pages" / "strategy" / "renderRiskPanel.js").read_text(encoding="utf-8")
    assert "RISK GATES" in source
    assert "is-hidden" not in source, "V2 risk gates should be visible by default"


def test_strategy_js_plan_conditions_expanded():
    root = Path(__file__).resolve().parents[1]
    source = (root / "app" / "static" / "pages" / "strategy" / "renderTradePlans.js").read_text(encoding="utf-8")
    assert "<details>" not in source, "Plan summary still using details wrapper"


def test_strategy_generator_returns_blocking_gates():
    from app.services.strategy_signal.strategy_generator import StrategyGenerator
    config = {
            "thresholds": {
                "dominant_gap": 18,
                "bias_score": 58,
                "setup_score": 66,
                "trigger_score": 72,
                "min_rr_trade": 1.5,
                "event_wait": 75,
                "data_quality_min_decision": 40,
                "spread_hard_limit_bps": 25,
                "slippage_hard_limit_bps": 40,
                "depth_hard_limit_score": 25,
                "min_depth_score": 50,
                "conflict_both_high": 70,
                "conflict_gap": 15,
                "no_edge_score": 30,
            },
            "state_permissions": {},
        }
    gen = StrategyGenerator(config)
    # Test with a snapshot that produces BIAS state
    snapshot = {
        "current_price": 100000,
        "atr_14": 2000,
        "event_risk_score": 30,
        "execution_quality": 65,
        "long_setup_ready": False,
        "long_trigger_ready": False,
    }
    from app.services.strategy_signal.scoring_engine import DirectionScores
    scores = DirectionScores(long_score=62, short_score=40, neutral_score=60, confidence=75, data_quality_score=80, conflict_score=10, rr_long=2.0, rr_short=1.0, long_penalty=0, short_penalty=0)
    decision = gen.build_decision(snapshot, scores)
    assert "blocking_gates" in decision, "decision missing blocking_gates"
    assert "next_trigger" in decision, "decision missing next_trigger"
