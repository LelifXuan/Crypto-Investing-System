from __future__ import annotations

from pathlib import Path

PAGE = Path("app/static/pages/gold_allocation.js")
API = Path("app/static/core/api.js")
MAIN = Path("app/static/main.js")
TEMPLATE = Path("app/templates/page.html")
STYLES = Path("app/static/styles.css")


def _source() -> str:
    return PAGE.read_text(encoding="utf-8")


def test_gold_page_uses_algebraic_execution_workbench() -> None:
    source = _source()

    for text in {
        "基础定投 x",
        "黄金坑 n × x",
        "今日合计",
        "核心指标",
        "派生指标",
        "刷新 XAUT",
        "系统诊断",
    }:
        assert text in source

    assert "基础定投</span><b>${money" not in source
    assert "黄金坑加仓</span><b>${money" not in source


def test_gold_page_uses_execution_plan_api_and_local_state() -> None:
    source = _source()
    api = API.read_text(encoding="utf-8")

    assert "api.planGoldExecution" in source
    assert "localStorage" in source
    assert "/gold/execution-plan" in api
    assert "planGoldExecution" in api
    assert "dipMultiplier" in source


def test_gold_page_auto_persists_triggered_dip_state() -> None:
    source = _source()

    assert "persistTriggeredDipState" in source
    assert 'dip.status !== "triggered"' in source
    assert "lastDipAddDate" in source
    assert "lastDipCycleId" in source
    assert "dip.cycle_id" in source
    assert "writeState(nextState)" in source


def test_gold_page_renders_indicator_cards_without_raw_keys() -> None:
    source = _source()

    assert "renderIndicatorSection" in source
    assert "core_indicator_cards" in source
    assert "derived_indicator_cards" in source

    source_without_contract_keys = (
        source.replace('"rsi_14"', "")
        .replace('"ema_20"', "")
        .replace('"return_7d"', "")
    )
    for raw in {"rsi_14", "ema_20", "return_7d"}:
        assert raw not in source_without_contract_keys


def test_gold_page_keeps_page_registration() -> None:
    main = MAIN.read_text(encoding="utf-8")
    template = TEMPLATE.read_text(encoding="utf-8")

    assert '"gold-allocation": "黄金配置"' in main
    assert 'page_id == "gold-allocation"' in template
    assert "Gold Allocation / 黄金配置" in template


def test_gold_page_hides_mojibake_and_forbidden_trading_copy() -> None:
    source = _source()

    forbidden = {
        "榛",
        "鎶",
        "鍏",
        "姣",
        "鍊",
        "鐎",
        "缁",
        "闁",
        "做多",
        "做空",
        "开仓",
        "止损",
        "止盈",
        "追突破",
        "减仓",
        "卖出",
        "马丁格尔",
        "倍增加仓",
    }
    for token in forbidden:
        assert token not in source

    assert 'statusBanner("success"' not in source
    assert "diagnostics.reused_indicators.join" not in source
    assert "diagnostics.computed_derived_indicators.join" not in source


def test_gold_v2_macro_strip_renders() -> None:
    """验证 4 个宏观卡相关 CSS 类已声明。"""
    css = STYLES.read_text(encoding="utf-8")
    assert ".gold-macro-strip" in css
    assert ".gold-macro-card" in css
    assert css.count("gold-bias-chip") >= 1


def test_gold_v2_decision_grid_class_exists() -> None:
    """验证决策带相关 CSS 类。"""
    css = STYLES.read_text(encoding="utf-8")
    assert ".gold-decision-grid" in css
    assert ".gold-decision-card" in css


def test_gold_v2_bottom_group_container() -> None:
    """验证二级容器存在。"""
    css = STYLES.read_text(encoding="utf-8")
    assert ".gold-bottom-group" in css
    assert "border-radius: 18px" in css


def test_gold_v2_liquidity_shock_banner() -> None:
    """验证流动性冲击警告类。"""
    css = STYLES.read_text(encoding="utf-8")
    assert ".gold-liquidity-shock-banner" in css


def test_gold_js_macro_strip_function() -> None:
    """验证 4 宏观卡组件函数已定义。"""
    js = _source()
    assert "function renderMacroStrip" in js
    assert "function renderMacroCard" in js
    assert "real_yield_10y" in js
    assert "gold_macro_snapshot" in js


def test_gold_js_9_segments() -> None:
    """验证 9 段渲染函数都已定义。"""
    js = _source()
    for fn in [
        "renderShell",
        "renderDecisionGrid",
        "renderMacroStrip",
        "renderModuleSection",
        "renderModuleCard",
        "renderChartSection",
        "renderMarketPanel",
        "renderStrategyPanel",
        "renderSettingsCard",
        "renderDiagnostics",
        "renderIndicatorSection",
        "renderGovernanceSection",
    ]:
        assert f"function {fn}" in js, f"missing function {fn}"


def test_gold_js_bias_label_function() -> None:
    """验证 5 档多空标签映射函数。"""
    js = _source()
    assert "function biasLabel" in js
    assert "强势看多" in js
    assert "看多" in js
    assert "看空" in js
    assert "强势看空" in js
