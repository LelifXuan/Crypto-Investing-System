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


def test_strategy_page_no_longer_renders_divergence_risk_card() -> None:
    """V1.7 SPA 重构后，divergence risk card 已从 strategy 页面移除。

    卡片功能仍在 alerts 页面保留（见 ``app/static/pages/alerts.js``），
    但 strategy 页应专注于"X+Y+Z 全栈推演"，不再嵌入告警卡片。
    """
    strategy_legacy = (ROOT / "app/static/pages/strategy.js").read_text(encoding="utf-8")
    strategy_index = (ROOT / "app/static/pages/strategy/index.js").read_text(encoding="utf-8")

    # 新 strategy 页是 re-export，不应再渲染 divergence risk card
    assert "renderDivergenceRiskCard" not in strategy_legacy
    assert "renderDivergenceRiskCard" not in strategy_index
    # 与 alert center 相关的内部分类/状态码不应暴露
    assert "technical_risk" not in strategy_index
