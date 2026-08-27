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


def test_analysis_uses_tracked_background_refresh_instead_of_browser_live_pipeline():
    source = (Path(__file__).resolve().parents[1] / "app" / "static" / "pages" / "analysis.js").read_text(encoding="utf-8", errors="replace")
    assert "waitForPrecomputeTask" in source
    assert 'candidates: ["analysis"]' in source
    assert "api.getCandles(" not in source
    assert "api.refreshTechnical(" not in source
    assert "api.refreshAnalysisBundle(" not in source
    assert "scheduleBundleRetry" not in source


def test_analysis_switch_mounts_full_skeleton_before_debounced_request():
    source = (Path(__file__).resolve().parents[1] / "app" / "static" / "pages" / "analysis.js").read_text(encoding="utf-8", errors="replace")
    debounce = source[source.index("function debouncedLoadAll"):source.index("function bindEventHandlers")]
    assert debounce.index("beginAnalysisTransition") < debounce.index("window.setTimeout")
    assert "analysis-mark-price" in source
    assert "analysis-signal-cards" in source
    assert "chartSkeleton()" in source
    assert "await renderChartBatch" in source


def test_analysis_idle_warmup_covers_five_by_five_default_matrix_only():
    source = (Path(__file__).resolve().parents[1] / "app" / "static" / "core" / "precompute.js").read_text(encoding="utf-8", errors="replace")
    assert "buildAnalysisWarmupPairs" in source
    assert '["1h", "4h", "1d", "1w", "30d"]' in source
    assert ".slice(0, 5)" in source
    assert 'view_window: "default"' in source
    assert 'candidates: ["analysis"]' in source
