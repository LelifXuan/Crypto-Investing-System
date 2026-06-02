from __future__ import annotations

import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))


def test_strategy_js_no_generic_trigger_copy():
    source = (Path(__file__).resolve().parents[1] / "app" / "static" / "pages" / "strategy.js").read_text(encoding="utf-8", errors="replace")
    assert "但触发条件未齐" not in source, "Generic trigger copy still present in strategy.js"


def test_strategy_js_has_trigger_board():
    source = (Path(__file__).resolve().parents[1] / "app" / "static" / "pages" / "strategy.js").read_text(encoding="utf-8", errors="replace")
    assert "renderTriggerBoard" in source, "renderTriggerBoard function missing"
    assert "strategy-trigger-board" in source, "trigger-board CSS class missing in template"


def test_strategy_js_trigger_diagnostics_visible():
    source = (Path(__file__).resolve().parents[1] / "app" / "static" / "pages" / "strategy.js").read_text(encoding="utf-8", errors="replace")
    # The trigger diagnostics section should NOT be inside is-hidden
    idx = source.find("触发门禁诊断")
    if idx > 0:
        surrounding = source[max(0, idx - 200):idx + 200]
        assert "is-hidden" not in surrounding, "Trigger diagnostics still hidden"


def test_strategy_js_plan_conditions_expanded():
    source = (Path(__file__).resolve().parents[1] / "app" / "static" / "pages" / "strategy.js").read_text(encoding="utf-8", errors="replace")
    # Verify plan summary no longer uses <details> wrapper
    idx = source.find("renderPlanSummary")
    end = source.find("function normalizeCheck", idx)
    plan_section = source[idx:end] if idx > 0 and end > idx else ""
    assert "<details>" not in plan_section, "Plan summary still using details wrapper"


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
