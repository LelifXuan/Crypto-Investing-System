"""BOLL candles use blue/plum with fill-density direction encoding."""

from pathlib import Path


ROOT = Path(__file__).resolve().parents[1]
SOURCE = (ROOT / "app" / "static" / "pages" / "analysis.js").read_text(encoding="utf-8")


def test_boll_candles_do_not_use_red_green_direction_colors() -> None:
    start = SOURCE.index('["analysis-boll"')
    end = SOURCE.index("options:", SOURCE.index("options:", start) + 1) if SOURCE.count("options:", start) > 1 else start + 3000
    block = SOURCE[start:end]
    assert 'themeColor("--info", "#3e6f9f")' in block
    assert 'themeColor("--accent", "#66548e")' in block
    assert 'themeColor("--bullish"' not in block
    assert 'themeColor("--bearish"' not in block
    assert 'upColor: "rgba(230, 238, 246, 0.38)"' in block
    assert 'downColor: "rgba(102, 84, 142, 0.42)"' in block
