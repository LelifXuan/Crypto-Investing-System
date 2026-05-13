from __future__ import annotations
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
STRUCTURE_JS = ROOT / "app" / "static" / "pages" / "structure.js"


def test_structure_js_uses_nearest_candle_index():
    text = STRUCTURE_JS.read_text(encoding="utf-8", errors="replace")

    assert "nearestCandleIndex" in text, "structure.js must use nearestCandleIndex helper"

    assert "xIndex.get" not in text, "structure.js must not use legacy xIndex.get pattern"
    assert "xIndex.set" not in text, "structure.js must not use legacy xIndex.set pattern"
    assert "xIndex.has" not in text, "structure.js must not use legacy xIndex.has pattern"

    lines = text.splitlines()
    nearest_count = sum(1 for line in lines if "nearestCandleIndex" in line)
    assert nearest_count >= 1, "nearestCandleIndex must be defined and used at least once"
