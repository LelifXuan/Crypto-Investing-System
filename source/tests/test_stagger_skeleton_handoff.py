from __future__ import annotations

from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
STATIC = ROOT / "app" / "static"
DOM = (STATIC / "core" / "dom.js").read_text(encoding="utf-8")
MAIN = (STATIC / "main.js").read_text(encoding="utf-8")
STYLES = (STATIC / "styles.css").read_text(encoding="utf-8")
EDITORIAL = (STATIC / "editorial.css").read_text(encoding="utf-8")
ANALYSIS = (STATIC / "pages" / "analysis.js").read_text(encoding="utf-8")
STRUCTURE = (STATIC / "pages" / "structure.js").read_text(encoding="utf-8")
EVENTS = (STATIC / "pages" / "market_events.js").read_text(encoding="utf-8")
BTC_DERIVATIVES = (STATIC / "pages" / "btc_derivatives.js").read_text(encoding="utf-8")
ETF = (STATIC / "pages" / "ashare_etf.js").read_text(encoding="utf-8")
GOLD = (STATIC / "pages" / "gold_v5.js").read_text(encoding="utf-8")


def test_reveal_stagger_is_bounded_and_cleans_repeated_runs() -> None:
    assert "const revealStates = new WeakMap();" in DOM
    assert "stepMs = 28" in DOM
    assert "maxPhases = 6" in DOM
    assert "durationMs = 180" in DOM
    assert "clearRevealState(container);" in DOM
    assert 'item.removeAttribute("data-stagger-item")' in DOM
    assert 'item.style.removeProperty("--stagger-delay")' in DOM
    assert "Math.min(index, lastPhase) * stepMs" in DOM


def test_route_handoff_never_starts_from_a_blank_frame() -> None:
    assert "revealStagger(pageRoot);" in MAIN
    assert "--dur-route-enter: 160ms" in STYLES
    assert "from { opacity: 0.55; transform: translateY(3px); }" in STYLES
    assert "from { opacity: 0; transform: translateY(4px); }" not in STYLES


def test_skeletons_join_a_document_wide_negative_phase() -> None:
    assert "export function skeletonPhaseStyle" in DOM
    assert "performance.now()" in DOM
    assert "--skeleton-delay: -${Math.round(elapsed)}ms" in DOM
    assert "skeletonPhaseStyle(-i, { periodMs: 2400, stepMs: 70 })" in DOM
    assert "animation-delay: var(--skeleton-delay, 0ms)" in STYLES
    assert "--candle-index" not in STYLES


def test_key_pages_reveal_only_when_async_content_lands() -> None:
    assert 'revealStagger(document.getElementById("analysis-signal-cards"))' in ANALYSIS
    assert 'revealStagger(canvas.closest(".chart-wrap"))' in ANALYSIS

    network_render = STRUCTURE.index("renderFromBundle(bundle);")
    chart_reveal = STRUCTURE.index(
        'revealStagger(document.getElementById("structure-chart-panel"))'
    )
    assert network_render < chart_reveal
    assert "renderFromBundle(state.bundle);\n        revealStagger" not in STRUCTURE

    assert EVENTS.count('revealStagger(document.getElementById("events-feed")') == 2
    assert "calc(var(--event-row) * 28ms)" in EDITORIAL
    assert "calc(var(--event-row) * 35ms)" not in EDITORIAL

    load_dashboard = BTC_DERIVATIVES.index("async function loadDashboard")
    chart_render = BTC_DERIVATIVES.index("  renderCharts();", load_dashboard)
    dashboard_reveal = BTC_DERIVATIVES.index("  revealInitialDashboard();")
    assert chart_render < dashboard_reveal
    assert "let initialDashboardRevealPlayed = false;" in BTC_DERIVATIVES
    assert "initialDashboardRevealPlayed = true;" in BTC_DERIVATIVES

    load_quotes = ETF.index("async function loadQuotes")
    plan_ready = ETF.index("    await planRebalance();", load_quotes)
    content_reveal = ETF.index("  revealInitialEtfContent();", load_quotes)
    assert plan_ready < content_reveal
    assert 'selector: ":scope > section:not(#etf-equity-curve)"' in ETF
    assert "initialEquityRevealPlayed = true;" in ETF

    gold_chart_render = GOLD.index("      await renderGoldCharts(data, signal);")
    gold_reveal = GOLD.index("      revealStagger(root);")
    assert gold_chart_render < gold_reveal
    assert "setRoot(renderGoldLoading());" in GOLD
    assert "正在接入黄金配置数据" in GOLD
    assert "phaseGoldLoadingSkeleton();" in GOLD


def test_reduced_motion_uses_stable_end_states() -> None:
    reduced = STYLES[STYLES.index("@media (prefers-reduced-motion: reduce)") :]
    assert ".loading-pulse" in reduced
    assert "[data-stagger-item]" in reduced
    assert "animation: none !important" in reduced
    assert "opacity: 1 !important" in reduced
    assert "transform: none !important" in reduced
