"""Static guards for the shared button hierarchy and page-guide interaction."""

from pathlib import Path


ROOT = Path(__file__).resolve().parents[1]
EDITORIAL = (ROOT / "app" / "static" / "editorial.css").read_text(encoding="utf-8")
GUIDE = (ROOT / "app" / "static" / "ui" / "pageGuideFab.js").read_text(encoding="utf-8")


def test_shared_button_typography_has_one_action_scale() -> None:
    assert ":where(button, .btn, .primary-button" in EDITORIAL
    assert "font-size: 14px;" in EDITORIAL
    assert "font-weight: 600;" in EDITORIAL
    assert ".primary-button.compact" in EDITORIAL
    assert "min-height: 38px;" in EDITORIAL


def test_top_level_refresh_actions_use_the_compact_primary_variant() -> None:
    expected = {
        "analysis.js": "analysis-refresh\" class=\"primary-button compact",
        "btc_derivatives.js": "class=\"primary-button compact\" id=\"btc-refresh",
        "structure.js": "structure-refresh\" class=\"primary-button compact",
        "market_events.js": "events-refresh\" class=\"primary-button compact",
        "macro_calendar.js": "macro-sync-button\" class=\"primary-button compact",
        "gold_v5.js": "class=\"primary-button compact\" id=\"gold-refresh",
        "ashare_etf.js": "class=\"primary-button compact\" id=\"etf-refresh-button",
    }
    for filename, marker in expected.items():
        source = (ROOT / "app" / "static" / "pages" / filename).read_text(encoding="utf-8")
        assert marker in source

    strategy = (ROOT / "app" / "static" / "pages" / "strategy" / "index.js").read_text(encoding="utf-8")
    assert 'class="primary-button compact" id="strategy-scan-refresh"' in strategy


def test_page_guide_has_fixed_header_and_outside_dismissal() -> None:
    assert "page-guide-panel-head" in GUIDE
    assert "page-guide-scroll-body" in GUIDE
    assert "page-guide-close" not in GUIDE
    assert 'document.addEventListener("pointerdown", handleOutsidePointer, true)' in GUIDE
    assert 'document.addEventListener("keydown", handleKeydown)' in GUIDE
    assert 'event.key === "Escape"' in GUIDE
    assert "grid-template-rows: auto minmax(0, 1fr)" in EDITORIAL
    assert ".page-guide-scroll-body" in EDITORIAL
    assert "overflow-y: auto" in EDITORIAL
