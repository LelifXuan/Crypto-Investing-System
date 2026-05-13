from __future__ import annotations

from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]


def test_strategy_navigation_and_page_registration():
    page = (ROOT / "app/templates/page.html").read_text(encoding="utf-8")
    main = (ROOT / "app/static/main.js").read_text(encoding="utf-8")
    router = (ROOT / "app/web/router.py").read_text(encoding="utf-8")

    assert page.rfind("AI策略") > page.rfind("知识百科")
    assert '"ai-strategy": () => loadPageModule("./pages/strategy.js")' in main
    assert "/strategy-page" in router
    assert '"AI策略"' in router


def test_strategy_page_uses_v16_market_signal_api_and_clean_chinese():
    strategy = (ROOT / "app/static/pages/strategy.js").read_text(encoding="utf-8")
    api = (ROOT / "app/static/core/api.js").read_text(encoding="utf-8")

    assert "api.getStrategyBundle" in strategy
    assert "api.saveStrategySnapshot" in strategy
    assert "市场多空策略信号" in strategy
    assert "strategy_bias" in strategy
    assert "primary_strategy" in strategy
    assert "entry_checklist" in strategy
    assert "avg_entry_price" not in strategy
    assert "liquidation_price" not in strategy
    assert "notional" not in strategy
    assert "锟" not in strategy
    assert "脙" not in strategy
    assert 'requestJson("/strategy/bundle"' in api
    assert 'requestJson("/strategy/signals"' in api


def test_strategy_page_does_not_show_position_management_actions():
    strategy = (ROOT / "app/static/pages/strategy.js").read_text(encoding="utf-8")

    forbidden = ["ADD_LONG", "REDUCE_LONG", "CLOSE_LONG", "HOLD_LONG", "TAKE_PROFIT"]
    assert not any(item in strategy for item in forbidden)

