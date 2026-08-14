from __future__ import annotations

import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))


def test_analysis_js_no_market_impact_dead_code():
    source = (Path(__file__).resolve().parents[1] / "app" / "static" / "pages" / "analysis.js").read_text(encoding="utf-8", errors="replace")
    assert "function marketImpact(" not in source, "marketImpact dead code still present"
    assert "function marketImpactLabel(" not in source, "marketImpactLabel dead code still present"


def test_analysis_js_has_ema_regime():
    source = (Path(__file__).resolve().parents[1] / "app" / "static" / "pages" / "analysis.js").read_text(encoding="utf-8", errors="replace")
    assert "classifyEmaRegime" in source, "classifyEmaRegime missing"
    assert "emaRegime.summary" in source, "emaRegime.summary not used for window-copy"


def test_analysis_js_no_absolute_atr():
    source = (Path(__file__).resolve().parents[1] / "app" / "static" / "pages" / "analysis.js").read_text(encoding="utf-8", errors="replace")
    assert "atrValue >= 2500" not in source, "BTC absolute ATR threshold still present"
    assert "natr" in source.lower(), "NATR-relative thresholds missing"


def test_analysis_js_no_old_ema_copy():
    source = (Path(__file__).resolve().parents[1] / "app" / "static" / "pages" / "analysis.js").read_text(encoding="utf-8", errors="replace")
    assert "图表展示最近" not in source, "Old EMA sample-count copy still present"


def test_analysis_js_signal_cards_use_tone():
    source = (Path(__file__).resolve().parents[1] / "app" / "static" / "pages" / "analysis.js").read_text(encoding="utf-8", errors="replace")
    assert "impactChip(item.tone" in source, "Signal cards not using structured tone"
