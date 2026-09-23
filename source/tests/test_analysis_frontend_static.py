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


def test_analysis_healthy_load_renders_no_status_banner():
    """A ready load must stay silent; the banner is for non-happy states only.

    The statusbar used to print "数据已就绪" after every successful load, which
    spent a row of attention confirming what the charts, mark price and regime
    badge already show. Degraded / loading / failure messages must survive —
    they carry information the user cannot infer from the data.

    Comments are stripped before scanning so a maintainer may still explain the
    removed banner by name (same rule as the gold_v5 emoji guard).
    """
    import re

    source = (Path(__file__).resolve().parents[1] / "app" / "static" / "pages" / "analysis.js").read_text(encoding="utf-8", errors="replace")
    code = re.sub(r"//[^\n]*", "", source)

    assert '"数据已就绪"' not in code, (
        "the healthy path must not render a data-ready confirmation banner"
    )
    # The ready branch passes an empty message; statusBanner("") renders nothing,
    # so the statusbar keeps only the regime badge.
    ready_call = code[code.index("const degradedSamples = allCandles.length < minCandles;"):]
    ready_call = ready_call[: ready_call.index(");")]
    assert 'degradedSamples ? "样本较少，已使用可用 K 线进行降级分析" : ""' in ready_call, (
        "the healthy branch must pass an empty message to renderAnalysisStatus"
    )
    assert 'degradedSamples ? "warning" : "success"' in ready_call


def test_analysis_status_messages_for_non_happy_states_survive():
    """Dropping the ready banner must not take the diagnostics with it."""
    source = (Path(__file__).resolve().parents[1] / "app" / "static" / "pages" / "analysis.js").read_text(encoding="utf-8", errors="replace")

    assert '"当前快照准备中"' in source
    assert '"正在刷新当前分析快照"' in source
    assert '"刷新失败，保留最近有效分析快照"' in source
    assert '"正在读取缓存"' in source
