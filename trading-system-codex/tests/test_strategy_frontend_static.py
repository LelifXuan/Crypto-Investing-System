from __future__ import annotations

from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]


def test_strategy_navigation_and_page_registration():
    page = (ROOT / "app/templates/page.html").read_text(encoding="utf-8")
    main = (ROOT / "app/static/main.js").read_text(encoding="utf-8")
    router = (ROOT / "app/web/router.py").read_text(encoding="utf-8")

    assert page.rfind("AI策略") > page.rfind("知识百科")
    assert '"ai-strategy": () => loadPageModule("./pages/strategy.js?v=narrative-layers")' in main
    assert "/strategy-page" in router
    assert '"AI策略"' in router


def test_strategy_page_uses_v16_market_signal_api_and_clean_chinese():
    strategy = (ROOT / "app/static/pages/strategy.js").read_text(encoding="utf-8")
    api = (ROOT / "app/static/core/api.js").read_text(encoding="utf-8")

    assert 'from "./strategy/index.js' in strategy
    assert "export { renderStrategy as default, renderStrategy }" in strategy
    assert "strategy-timeframe" not in strategy
    assert "TIMEFRAMES" not in strategy
    assert "getUnifiedStrategy(" in api
    assert 'requestJson("/strategy/unified"' in api
    for rel in [
        "app/static/pages/strategy/index.js",
        "app/static/pages/strategy/adapter.js",
        "app/static/pages/strategy/renderOverview.js",
        "app/static/pages/strategy/renderMarketOperation.js",
        "app/static/pages/strategy/renderHorizonGovernance.js",
        "app/static/pages/strategy/renderHorizonStack.js",
        "app/static/pages/strategy/renderTradePlans.js",
        "app/static/pages/strategy/renderRiskPanel.js",
        "app/static/pages/strategy/renderEventWatch.js",
        "app/static/pages/strategy/renderEvidenceTrace.js",
        "app/static/pages/strategy/renderNarrative.js",
    ]:
        assert (ROOT / rel).exists(), rel
    index = (ROOT / "app/static/pages/strategy/index.js").read_text(encoding="utf-8")
    assert "renderHorizonGovernance" in index
    assert "renderEventWatch" in index
    assert "1d 战术快照与复盘辅助" in index
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


def test_strategy_work_groups_are_wrapped_in_card_containers():
    modules = {
        "renderMarketOperation.js": "strategy-market-operation card",
        "renderHorizonGovernance.js": "strategy-horizon-governance card",
        "renderHorizonStack.js": "strategy-horizon-stack card",
        "renderTradePlans.js": "strategy-trade-plans card",
        "renderRiskPanel.js": "strategy-risk-layout card",
        "renderEventWatch.js": "strategy-event-watch card",
        "renderEvidenceTrace.js": "strategy-evidence-trace card",
        "renderNarrative.js": "strategy-narrative card",
    }
    base = ROOT / "app/static/pages/strategy"
    for filename, class_fragment in modules.items():
        source = (base / filename).read_text(encoding="utf-8")
        assert class_fragment in source


def test_strategy_data_access_state_renders_at_page_end():
    source = (ROOT / "app/static/pages/strategy/index.js").read_text(encoding="utf-8")
    render_block = source.split("content.innerHTML = `", 1)[1].split("`;", 1)[0]
    assert render_block.rfind("${renderDataAccessState(model)}") > render_block.rfind(
        "${renderNarrative(model, helpers)}"
    )


def test_strategy_evidence_trace_renders_unified_contract_fields():
    source = (ROOT / "app/static/pages/strategy/renderEvidenceTrace.js").read_text(encoding="utf-8")

    # V1.7 unified contract: only render natural-language fields as UI text.
    # `calculation_rule` / `input_features` / `source_modules` / `source_timeframes`
    # are kept in the payload (for API consumers) but no longer rendered as UI text.
    for field in [
        "conclusion_key",
        "conclusion",
        "human_explanation",
        "source_modules",
        "source_timeframes",
        "freshness",
        "confidence",
    ]:
        assert field in source

    # Internal calculation fields must NOT be rendered as UI text in V1.7.
    for internal_field in ["calculation_rule", "input_features"]:
        assert internal_field not in source

    assert "strategy-evidence-meta" in source
    assert "暂无解释文本" in source


def test_strategy_narrative_renders_layers_and_watchlist_without_summary_duplication():
    source = (ROOT / "app/static/pages/strategy/renderNarrative.js").read_text(encoding="utf-8")

    assert "narrative.layers" in source
    assert "narrative.watchlist" in source
    assert "strategy-narrative-layer" in source
    assert "strategy-narrative-watch" in source
    assert "等待信号" in source
    assert "下一检查项" in source
    assert "narrative.summary" not in source


def test_strategy_market_operation_shows_source_and_hides_internal_codes():
    source = (ROOT / "app/static/pages/strategy/renderMarketOperation.js").read_text(
        encoding="utf-8"
    )

    # V1.7 contract: render source_page + strategy_impact + data_status;
    # `missing_inputs` is no longer rendered as a UI label (kept in payload only).
    assert "source_page" in source
    assert "strategy_impact" in source
    assert "human_explanation" in source
    assert "来源" in source
    assert "状态" in source
    # Internal codes must NOT appear in the rendered UI.
    assert "missing_inputs" not in source
    for token in ["DATA_MISSING", "operation_bias", "regime_key", "RISK_APPETITE_SUPPORTIVE"]:
        assert token not in source
