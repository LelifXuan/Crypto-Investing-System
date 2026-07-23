from __future__ import annotations

from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]


def test_strategy_navigation_and_page_registration():
    page = (ROOT / "app/templates/page.html").read_text(encoding="utf-8")
    main = (ROOT / "app/static/main.js").read_text(encoding="utf-8")
    router = (ROOT / "app/web/router.py").read_text(encoding="utf-8")

    assert page.rfind('data-page-link="ai-strategy"') > page.rfind(
        'data-page-link="knowledge-base"'
    )
    assert '"ai-strategy": () => loadPageModule("./pages/strategy.js?v=trade-4h-v1")' in main
    assert "/strategy-page" in router
    assert '"ai-strategy"' in router


def test_strategy_entry_does_not_expose_mojibake():
    source = (ROOT / "app/static/pages/strategy/index.js").read_text(encoding="utf-8")

    assert "缁熶竴绛栫暐" not in source
    assert "统一策略快照尚未就绪，后台预热中" in source


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
        "app/static/pages/strategy/renderHorizonStack.js",
        "app/static/pages/strategy/renderTradePlans.js",
        "app/static/pages/strategy/renderRiskPanel.js",
        "app/static/pages/strategy/renderEventWatch.js",
        "app/static/pages/strategy/renderEvidenceTrace.js",
        "app/static/pages/strategy/renderNarrative.js",
        "app/static/pages/strategy/renderExecutionPlan.js",
        "app/static/pages/strategy/renderEvidenceStack.js",
    ]:
        assert (ROOT / rel).exists(), rel
    index = (ROOT / "app/static/pages/strategy/index.js").read_text(encoding="utf-8")
    assert "renderHorizonGovernance" not in index
    assert "renderEventWatch" in index
    assert "strategy-review" in index
    assert "avg_entry_price" not in strategy
    assert "liquidation_price" not in strategy
    assert "notional" not in strategy
    assert 'requestJson("/strategy/bundle"' in api
    assert 'requestJson("/strategy/signals"' in api


def test_strategy_page_does_not_show_position_management_actions():
    strategy = (ROOT / "app/static/pages/strategy.js").read_text(encoding="utf-8")

    forbidden = ["ADD_LONG", "REDUCE_LONG", "CLOSE_LONG", "HOLD_LONG", "TAKE_PROFIT"]
    assert not any(item in strategy for item in forbidden)


def test_strategy_work_groups_are_wrapped_in_card_containers():
    modules = {
        "renderMarketOperation.js": "strategy-market-operation card",
        "renderExecutionPlan.js": "strategy-execution-plan card",
        "renderEvidenceStack.js": "strategy-evidence-stack card",
        "renderRiskPanel.js": "strategy-risk-layout card",
        "renderEventWatch.js": "strategy-event-watch strategy-collapsible card",
    }
    base = ROOT / "app/static/pages/strategy"
    for filename, class_fragment in modules.items():
        source = (base / filename).read_text(encoding="utf-8")
        assert class_fragment in source


def test_strategy_horizon_governance_renders_trade_decision_text():
    source = (ROOT / "app/static/pages/strategy/renderHorizonGovernance.js").read_text(
        encoding="utf-8"
    )

    assert "higherDecisionText" in source
    assert "lowerDecisionText" in source
    assert "key_resistance" in source
    assert "key_support" in source
    assert "invalidation" in source
    assert "higher.rule" not in source
    assert "lower.rule" not in source
    assert "鍐冲畾鎴樼暐杈圭晫" not in source


def test_strategy_data_access_state_renders_at_page_end():
    source = (ROOT / "app/static/pages/strategy/index.js").read_text(encoding="utf-8")
    render_block = source.split("content.innerHTML = `", 1)[1].split("`;", 1)[0]
    assert render_block.rfind("${buildDataDegradedCard(model)}") > render_block.rfind(
        "${renderEvidenceStack(model, helpers)}"
    )
    assert "renderDataAccessState" not in source


def test_strategy_horizon_governance_summary_is_merged_into_overview():
    index = (ROOT / "app/static/pages/strategy/index.js").read_text(encoding="utf-8")
    source = (ROOT / "app/static/pages/strategy/renderOverview.js").read_text(encoding="utf-8")

    assert "renderHorizonGovernance" not in index
    assert "strategy-horizon-governance" not in index
    assert "model.horizon_governance" not in source
    assert "position_cap" not in source
    assert "recommended_leverage" in source


def test_strategy_merged_evidence_summary_sits_near_page_top():
    source = (ROOT / "app/static/pages/strategy/index.js").read_text(encoding="utf-8")
    render_block = source.split("content.innerHTML = `", 1)[1].split("`;", 1)[0]

    assert render_block.find("${renderOverview(model, helpers)}") < render_block.find(
        "${renderEvidenceStack(model, helpers)}"
    )
    assert render_block.find("${renderEvidenceStack(model, helpers)}") < render_block.find(
        "${renderMarketOperation(model, helpers)}"
    )


def test_strategy_decision_evidence_and_trade_plans_sit_before_detail_modules():
    source = (ROOT / "app/static/pages/strategy/index.js").read_text(encoding="utf-8")
    render_block = source.split("content.innerHTML = `", 1)[1].split("`;", 1)[0]

    evidence = render_block.find("${renderEvidenceStack(model, helpers)}")
    plans = render_block.find("${renderExecutionPlan(model, helpers)}")
    market = render_block.find("${renderMarketOperation(model, helpers)}")

    assert render_block.find("${renderOverview(model, helpers)}") < plans < evidence
    assert evidence < market
    for old_renderer in (
        "renderTradeDecision",
        "renderTradePlans",
        "renderEvidenceTrace",
        "renderNarrative",
        "renderHorizonStack",
    ):
        assert old_renderer not in render_block


def test_strategy_data_access_state_is_single_and_collapsed_by_default():
    source = (ROOT / "app/static/pages/strategy/index.js").read_text(encoding="utf-8")
    adapter = (ROOT / "app/static/pages/strategy/adapter.js").read_text(encoding="utf-8")
    styles = (ROOT / "app/static/styles.css").read_text(encoding="utf-8")
    assert "renderDataAccessState" not in source
    assert source.count("buildDataDegradedCard(model)") == 1
    assert "strategy-degraded-footer strategy-collapsible card" in adapter
    assert 'class="strategy-collapse-control"' in adapter
    assert "strategy-data-state-toggle" not in adapter
    assert ".strategy-collapsible[open] .strategy-collapse-control::before" in styles


def test_strategy_degraded_data_access_footer_is_collapsed_by_default():
    source = (ROOT / "app/static/pages/strategy/adapter.js").read_text(encoding="utf-8")
    fn_block = source.split("function buildDataDegradedFooter(model)", 1)[1].split(
        "\nfunction ",
        1,
    )[0]

    assert "strategy-degraded-footer strategy-collapsible card" in fn_block
    assert 'hasFailures ? "open" : ""' in fn_block
    assert "strategy-degraded-summary strategy-collapsible-summary" in fn_block
    assert "strategy-degraded-grid" in fn_block


def test_strategy_evidence_trace_renders_compact_summary():
    source = (ROOT / "app/static/pages/strategy/renderEvidenceTrace.js").read_text(encoding="utf-8")

    assert "buildEvidenceSummary" in source
    assert "strategy-evidence-summary" in source
    assert "strategy-evidence-summary-item" in source
    assert "方向依据" in source
    assert "风险与缺口" in source

    # Payload internals stay available upstream, but this module must not render
    # diagnostic grids full of source modules, timeframes, or calculation keys.
    for internal_field in [
        "calculation_rule",
        "input_features",
        "source_modules",
        "source_timeframes",
        "strategy-evidence-meta",
        "conclusionKey",
        "鏆傛棤瑙ｉ噴鏂囨湰",
    ]:
        assert internal_field not in source


def test_strategy_narrative_hides_internal_layers_and_keeps_next_check():
    source = (ROOT / "app/static/pages/strategy/renderNarrative.js").read_text(encoding="utf-8")

    assert "narrative.watchlist" in source
    assert "strategy-narrative-watch" in source
    assert "下一检查项" in source
    assert "narrative.summary" not in source
    for internal_token in [
        "narrative.layers",
        "strategy-narrative-layer",
        "basis",
        "required_signal",
        "direction_label",
        "joinTimeframes",
    ]:
        assert internal_token not in source


def test_strategy_market_operation_shows_source_and_hides_internal_codes():
    source = (ROOT / "app/static/pages/strategy/renderMarketOperation.js").read_text(
        encoding="utf-8"
    )

    # V1.7 contract: render decision-useful natural language only.
    # Raw source_page / data_status / missing_inputs remain payload diagnostics,
    # not visible labels for the trading decision card.
    assert "source_page" not in source
    assert "strategy_impact" in source
    assert "human_explanation" in source
    assert "数据状态：" in source
    assert "STATUS_LABELS" in source
    assert "INTERNAL_TEXT_PATTERNS" in source
    # Internal codes must NOT appear in the rendered UI.
    for token in [
        "missing_inputs",
        "operation_bias",
        "regime_key",
        "RISK_APPETITE_SUPPORTIVE",
        "鏉ユ簮",
        "鐘舵€?${status}",
        "鎴樼暐鏍?",
        "鎴樻湳鏍?",
    ]:
        assert token not in source


def test_strategy_frontend_prefers_direction_resolution_cards():
    adapter = (ROOT / "app/static/pages/strategy/adapter.js").read_text(encoding="utf-8")
    operation = (ROOT / "app/static/pages/strategy/renderMarketOperation.js").read_text(
        encoding="utf-8"
    )
    overview = (ROOT / "app/static/pages/strategy/renderOverview.js").read_text(encoding="utf-8")

    assert "direction_resolution" in adapter
    assert "operation_cards" in adapter
    assert "governance_cards" in adapter
    assert "renderResolutionOperationCard" in operation
    assert "trading_meaning" in operation
    assert "permission_effect" in operation
    assert "position_effect" in operation
    assert "next_check" in operation
    assert "model.horizon_governance" not in overview
    assert "tradeDecision.recommended_leverage" in overview


def test_strategy_compact_merges_and_hides_internal_ui_codes():
    index = (ROOT / "app/static/pages/strategy/index.js").read_text(encoding="utf-8")
    execution = (ROOT / "app/static/pages/strategy/renderExecutionPlan.js").read_text(
        encoding="utf-8"
    )
    evidence = (ROOT / "app/static/pages/strategy/renderEvidenceStack.js").read_text(
        encoding="utf-8"
    )
    adapter = (ROOT / "app/static/pages/strategy/adapter.js").read_text(encoding="utf-8")

    assert "renderExecutionPlan" in index
    assert "renderEvidenceStack" in index
    assert "recommended_leverage" in execution
    assert "max_leverage" in execution
    # The primary plan no longer renders a redundant "计划" column for the
    # main row (it shows on the dedicated primary-plan card instead), so the
    # planLabel helper is no longer called for primary rows. The secondary
    # table still uses planLabel for non-primary plans.
    assert "planLabel" in execution
    assert "timeframe_stack" in evidence
    assert "evidence_trace" in evidence
    assert "narrative" in evidence
    for token in ("SHORT_BIAS", "LONG_BIAS", "OBSERVE"):
        assert token not in execution
        assert token not in evidence
    assert 'SHORT_BIAS: "下跌结构"' in adapter
    assert 'OBSERVE: "等待确认"' in adapter


def test_strategy_empty_sections_collapse_and_share_visual_contract():
    index = (ROOT / "app/static/pages/strategy/index.js").read_text(encoding="utf-8")
    event = (ROOT / "app/static/pages/strategy/renderEventWatch.js").read_text(encoding="utf-8")
    styles = (ROOT / "app/static/styles.css").read_text(encoding="utf-8")

    assert 'isEmpty ? "" : "open"' in event
    assert 'isEmpty ? "" : "open"' in index
    assert "暂无高影响事件" in event
    assert "暂无战术复盘记录" in index
    compact_styles = styles.split("/* Strategy compact information architecture */", 1)[1]
    assert "strategy-collapsible-summary" in compact_styles
    assert "min-height: 64px" in compact_styles
    assert "transition: all" not in compact_styles
    assert "font-variant-numeric: tabular-nums" in compact_styles


def test_strategy_collapsibles_use_one_arrow_control() -> None:
    root = ROOT / "app/static/pages/strategy"
    sources = [
        (root / "adapter.js").read_text(encoding="utf-8"),
        (root / "renderEventWatch.js").read_text(encoding="utf-8"),
        (root / "renderExecutionPlan.js").read_text(encoding="utf-8"),
        (root / "index.js").read_text(encoding="utf-8"),
    ]
    styles = (ROOT / "app/static/styles.css").read_text(encoding="utf-8")

    assert all("strategy-data-state-toggle" not in source for source in sources)
    assert sum(source.count('class="strategy-collapse-control"') for source in sources) >= 4
    assert "strategy-data-state-toggle" not in styles
    assert 'content: "展开"' not in styles
    assert 'content: "收起"' not in styles
    assert "width: 44px" in styles
    assert "height: 44px" in styles
    assert "border-radius: 12px" in styles


def test_strategy_execution_plan_consumes_backend_order_contract() -> None:
    adapter = (ROOT / "app/static/pages/strategy/adapter.js").read_text(encoding="utf-8")
    execution = (
        ROOT / "app/static/pages/strategy/renderExecutionPlan.js"
    ).read_text(encoding="utf-8")

    for field in (
        "order_type",
        "order_status",
        "execution_price",
        "limit_price",
        "planned_leverage",
        "activation_conditions",
        "price_protection",
    ):
        assert field in adapter
        assert field in execution
    assert "市价执行计划" in execution
    assert "条件限价计划" in execution
    assert "等待价格进入区域" in execution
    assert "等待小周期反转确认" in execution
    assert "触发条件" in execution


# ---------------------------------------------------------------------------
# Frontend restructuring: top strip is reduced to 3 KPI cards (方向 / 执行状态
# / 主要原因) and the primary-plan table is compressed to 6 detail columns
# (执行价 / 止损 / 止盈 / 盈亏比 / 触发条件 / 状态) so that fields shown in
# the top strip never appear again inside the table. "其他计划" stays on the
# legacy 11-column table because it shows row-specific copy across plans.
# ---------------------------------------------------------------------------


def test_execution_plan_top_strip_uses_three_kpi_cards_only() -> None:
    """The top strip must surface exactly: 方向 / 执行状态 / 主要原因.

    订单类型, 杠杆 were removed because the same information already lives
    in the table (or below it as the leverage_reason summary line)."""
    execution = (
        ROOT / "app/static/pages/strategy/renderExecutionPlan.js"
    ).read_text(encoding="utf-8")
    # The strip block now contains exactly 3 KPI <div>s, then the closing
    # </div> for the strip wrapper. We grab from the wrapper opening tag up
    # to the wrapper closing tag by counting nested divs.
    strip_open = '<div class="strategy-decision-strip">'
    assert strip_open in execution, (
        "top strip must still be marked with class 'strategy-decision-strip'"
    )
    start = execution.index(strip_open)
    # Walk forward, counting div opens/closes until depth returns to 0.
    depth = 0
    cursor = start
    end = -1
    while cursor < len(execution):
        next_open = execution.find("<div", cursor)
        next_close = execution.find("</div>", cursor)
        if next_close == -1:
            break
        if next_open != -1 and next_open < next_close:
            depth += 1
            cursor = next_open + 4
        else:
            depth -= 1
            cursor = next_close + len("</div>")
            if depth == 0:
                end = cursor
                break
    assert end > start, "could not locate the closing </div> of the strip wrapper"
    strip_block = execution[start:end]

    # The three KPI labels we expect to keep.
    for label in ("方向", "执行状态", "主要原因"):
        assert f"<span>{label}</span>" in strip_block, (
            f"top strip must keep KPI label {label!r}, got section: {strip_block}"
        )

    # The four KPI labels we explicitly removed.
    for removed in ("订单类型", "杠杆"):
        assert f"<span>{removed}</span>" not in strip_block, (
            f"top strip must NOT carry KPI label {removed!r} any more (it is "
            f"duplicated in the table); got section: {strip_block}"
        )


def test_execution_plan_primary_table_has_six_detail_columns() -> None:
    """Primary-plan table columns: 执行价/限价区间, 止损, 止盈, 盈亏比,
    触发条件, 状态. No 计划 / 订单类型 / 交易级别 / 方向 / 杠杆 columns —
    those live in the top strip or below the strip.

    The primary plan is rendered into a dedicated ``primaryPlanCard`` shell
    (class ``strategy-primary-plan-card``), so we extract its <dl> grid and
    assert against the dt labels rather than against a <th> row.
    """
    execution = (
        ROOT / "app/static/pages/strategy/renderExecutionPlan.js"
    ).read_text(encoding="utf-8")
    assert "strategy-primary-plan-card" in execution, (
        "primary plan must be rendered into a dedicated shell with class "
        "'strategy-primary-plan-card' so it pops out and the table can shrink"
    )
    card_marker = '<div class="strategy-primary-plan-card">'
    card_block = execution.split(card_marker, 1)[1].split("</dl>", 1)[0]

    # Six dt labels we expect to keep on the primary card.
    for label in (
        "执行价 / 限价区间",
        "止损",
        "止盈",
        "盈亏比",
        "触发条件",
        "状态",
    ):
        assert f"<dt>{label}</dt>" in card_block, (
            f"primary-plan card must keep {label!r}, got: {card_block}"
        )

    # Five columns we removed (redundant with the top strip).
    for removed_label in ("计划", "订单类型", "交易级别", "方向", "杠杆"):
        assert f"<dt>{removed_label}</dt>" not in card_block, (
            f"primary-plan card must NOT carry {removed_label!r} any more "
            f"(redundant with top strip); got: {card_block}"
        )


def test_execution_plan_primary_row_is_marked_with_left_bar() -> None:
    """The primary plan card must carry a visible marker so users can spot
    it inside the now-stripped table. Class name: ``strategy-primary-plan-card``
    on the wrapping div + a dedicated CSS rule to give it a left-edge bar."""
    execution = (
        ROOT / "app/static/pages/strategy/renderExecutionPlan.js"
    ).read_text(encoding="utf-8")
    assert "strategy-primary-plan-card" in execution, (
        "primary plan must be wrapped in a div carrying class "
        "'strategy-primary-plan-card' for the left-edge bar"
    )
    styles = (ROOT / "app/static/styles.css").read_text(encoding="utf-8")
    assert ".strategy-primary-plan-card" in styles, (
        "styles.css must define a rule for .strategy-primary-plan-card so "
        "the primary plan pops out visually"
    )


def test_strategy_overview_uses_single_row_metric_rail_and_4h_trade_level() -> None:
    styles = (ROOT / "app/static/styles.css").read_text(encoding="utf-8")
    adapter = (ROOT / "app/static/pages/strategy/adapter.js").read_text(encoding="utf-8")
    execution = (
        ROOT / "app/static/pages/strategy/renderExecutionPlan.js"
    ).read_text(encoding="utf-8")
    contracts = (
        ROOT / "app/services/strategy_unified/contracts.py"
    ).read_text(encoding="utf-8")

    assert "grid-template-columns: repeat(5, minmax(0, 1fr));" in styles
    assert ".strategy-v2-metric:first-child { border-left: 0; }" in styles
    assert "grid-template-columns: repeat(3, minmax(0, 1fr));" in styles
    assert 'trade_timeframe: safe.trade_timeframe || "4h"' in adapter
    # The legacy "交易级别" column was removed from the table; the trade
    # timeframe is now surfaced as a small "· 4H" annotation next to the
    # primary plan card title. Verify the field is still consumed.
    assert "trade_timeframe" in execution
    assert 'trade_timeframe || "4h"' in execution or 'trade_timeframe || decision.trade_timeframe || "4h"' in execution
    assert "toUpperCase()" in execution
    assert 'EXECUTION_WEIGHTS = {"1h": 0.7, "15m": 0.3}' in contracts
    assert '"4h"' not in contracts.split("EXECUTION_WEIGHTS =", 1)[1].split("\n", 1)[0]


def test_strategy_page_renders_shadow_governance_snapshot_and_signal_coverage() -> None:
    index = (ROOT / "app/static/pages/strategy/index.js").read_text(encoding="utf-8")
    audit = (
        ROOT / "app/static/pages/strategy/renderDecisionAudit.js"
    ).read_text(encoding="utf-8")

    assert "renderDecisionAudit" in index
    assert "新模型仅影子记录，不影响当前主策略" in audit
    assert "market_decision_snapshot" in (
        ROOT / "app/static/pages/strategy/adapter.js"
    ).read_text(encoding="utf-8")
    assert "完整指标覆盖" in audit
    assert "跨模块复核" in audit
    assert "formatDateTime(model.price_as_of)" in audit


def test_strategy_frontend_never_uses_pending_risk_reward_copy() -> None:
    strategy_sources = "\n".join(
        path.read_text(encoding="utf-8")
        for path in (ROOT / "app/static/pages/strategy").glob("*.js")
    )
    assert "待评估" not in strategy_sources
    assert "暂不能评估" not in strategy_sources
