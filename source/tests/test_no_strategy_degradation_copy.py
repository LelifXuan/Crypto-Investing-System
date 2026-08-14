from __future__ import annotations

from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
BANNED_COPY = ["降级策略信号", "策略只能降级参考", "底层快照不完整", "降级分析模式", "降级数据"]


def test_no_strategy_degradation_copy():
    violations = []
    for rel in [
        "app/services/strategy_signal/service.py",
        "app/services/chip_structure.py",
        "app/services/alerts_bundle.py",
        "app/static/pages/strategy.js",
    ]:
        text = (ROOT / rel).read_text(encoding="utf-8", errors="replace")
        for phrase in BANNED_COPY:
            if phrase in text:
                violations.append((rel, phrase))
    assert violations == [], f"Degradation copy found: {violations}"
