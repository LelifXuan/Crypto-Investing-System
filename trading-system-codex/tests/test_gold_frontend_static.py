from __future__ import annotations

from pathlib import Path

PAGE = Path("app/static/pages/gold_allocation.js")
API = Path("app/static/core/api.js")
MAIN = Path("app/static/main.js")
TEMPLATE = Path("app/templates/page.html")


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
