from __future__ import annotations

from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
BANNED_COPY = ["策略降级", "降级策略信号", "只能降级参考", "结论已做降级处理"]
KEY_FILES = [
    "app/services/strategy_signal/service.py",
    "app/services/strategy_signal/strategy_generator.py",
    "app/services/chip_structure.py",
    "app/services/alerts_bundle.py",
    "app/services/confidence_engine.py",
    "app/services/final_decision.py",
    "app/static/pages/strategy.js",
]


def test_no_user_visible_degradation_copy_v9():
    violations = []
    for rel in KEY_FILES:
        path = ROOT / rel
        if not path.exists():
            continue
        text = path.read_text(encoding="utf-8", errors="replace")
        for phrase in BANNED_COPY:
            if phrase in text:
                violations.append((rel, phrase))
    assert violations == [], f"Degradation copy found: {violations}"
