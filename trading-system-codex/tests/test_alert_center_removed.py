from __future__ import annotations

from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]


def test_main_navigation_no_longer_exposes_alert_center_page() -> None:
    template = (ROOT / "app/templates/page.html").read_text(encoding="utf-8")
    main = (ROOT / "app/static/main.js").read_text(encoding="utf-8")

    assert 'data-page-link="alert-center"' not in template
    assert "告警中心" not in template
    assert '"alert-center"' not in main
    assert "pages/alerts.js" not in main


def test_alerts_page_is_routed_to_ai_strategy() -> None:
    router = (ROOT / "app/web/router.py").read_text(encoding="utf-8")

    assert "alerts_page" in router
    assert 'PAGE_TITLES["ai-strategy"]' in router
    assert '"ai-strategy"' in router.split("async def alerts_page", 1)[1].split(
        "async def", 1
    )[0]


def test_strategy_page_renders_divergence_risk_card() -> None:
    strategy = (ROOT / "app/static/pages/strategy.js").read_text(encoding="utf-8")
    styles = (ROOT / "app/static/styles.css").read_text(encoding="utf-8")

    assert "renderDivergenceRiskCard" in strategy
    assert "背离风险提醒" in strategy
    assert "technical_risk" in strategy
    assert "strategy-divergence-risk-card" in styles
    forbidden = ["CVD", "open_interest", "order_book", "depth", "slippage"]
    card_source = strategy.split("renderDivergenceRiskCard", 1)[1].split(
        "function renderBundle", 1
    )[0]
    for token in forbidden:
        assert token not in card_source
