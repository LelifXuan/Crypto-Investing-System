from __future__ import annotations

from pathlib import Path

PAGE = Path("app/static/pages/btc_derivatives.js")
API = Path("app/static/core/api.js")
MAIN = Path("app/static/main.js")
TEMPLATE = Path("app/templates/page.html")
WEB_ROUTER = Path("app/web/router.py")
STYLES = Path("app/static/styles.css")


def test_btc_derivatives_page_is_registered_across_spa_and_web_router() -> None:
    main = MAIN.read_text(encoding="utf-8")
    template = TEMPLATE.read_text(encoding="utf-8")
    router = WEB_ROUTER.read_text(encoding="utf-8")
    assert '"btc-derivatives": () => loadPageModule("./pages/btc_derivatives.js")' in main
    assert 'pageId === "btc-derivatives"' in main
    assert 'data-page-link="btc-derivatives"' in template
    assert 'href="/btc-derivatives-page"' in template
    assert '@web_router.get("/btc-derivatives-page")' in router


def test_btc_derivatives_refresh_uses_job_polling_instead_of_long_request() -> None:
    source = PAGE.read_text(encoding="utf-8")
    api = Path("app/static/core/api.js").read_text(encoding="utf-8")

    assert "waitForRefreshJob" in source
    assert "getRefreshJob" in source
    assert 'requestJson(`/refresh-jobs/${jobId}`' in api
    assert "getBtcDerivativesDashboard" in api
    assert "refreshBtcDerivativesDashboard" in api
    assert "planBtcDerivativeHedge" in api


def test_refresh_freshness_copy_sits_under_refresh_button_not_status_banner() -> None:
    source = PAGE.read_text(encoding="utf-8")
    styles = STYLES.read_text(encoding="utf-8")

    assert "btc-refresh-freshness" in source
    assert "btc-refresh-freshness" in styles
    assert 'statusBanner("衍生品快照已刷新"' not in source


def test_internal_snapshot_state_codes_are_mapped_to_chinese_copy() -> None:
    source = PAGE.read_text(encoding="utf-8")

    assert 'data_insufficient: "数据不足"' in source
    assert 'stale: "最近真实缓存"' in source
    assert 'failed: "不可用"' in source
    assert ">${escapeHtml(snapshotState)}</span>" not in source
    assert "dashboard?.data_quality?.mode || \"fixture\"" not in source


def test_page_renders_six_chart_layout_from_backend_metadata() -> None:
    source = PAGE.read_text(encoding="utf-8")

    for chart_id in {
        "leverage_pressure_timeline",
        "exchange_crowding_snapshot",
        "term_structure",
        "strike_surface",
        "key_levels_history",
        "options_risk_premium_history",
    }:
        assert chart_id in source

    assert "dashboard?.chart_layout?.sections" in source
    assert "dashboard?.chart_layout?.cards" in source
    assert "btc-card-span-${span}" in source
    assert "btc-chart-density-${escapeHtml(density)}" in source
    assert "OVERVIEW_CHARTS" not in source
    assert "CHART_CANVAS_IDS" not in source
    assert "renderDecisionCards" in source
    assert "renderHedgePlanner" in source
    assert "renderDataQuality" in source
    assert "destroyChartsForPage" in source


def test_page_exposes_expiry_switching_and_hedge_fields() -> None:
    source = PAGE.read_text(encoding="utf-8")

    for field in {
        "portfolio_type",
        "grid_lower",
        "grid_upper",
        "net_notional_usd",
        "hedge_budget_usd",
        "preferred_expiry_bucket",
    }:
        assert f'name="{field}"' in source
    assert 'name="selected_expiry"' in source
    assert "api.planBtcDerivativeHedge" in source
    assert "api.refreshBtcDerivativesDashboard" in source


def test_page_exposes_window_maturity_and_strike_controls() -> None:
    source = PAGE.read_text(encoding="utf-8")
    api = API.read_text(encoding="utf-8")

    for field in {
        "window",
        "expiry_mode",
        "maturity_bucket",
        "selected_expiry",
        "strike_range_pct",
    }:
        assert f'name="{field}"' in source
    assert "dashboardQuery()" in source
    assert "expiryMode" in api
    assert "maturityBucket" in api
    assert "strikeRangePct" in api


def test_option_chain_and_raw_tables_are_in_closed_details_panel() -> None:
    source = PAGE.read_text(encoding="utf-8")

    assert '<details class="btc-details-drawer">' in source
    assert '<details class="btc-details-drawer" open>' not in source
    details = source[source.index('<details class="btc-details-drawer">') :]
    assert "renderOptionChain()" in details
    assert "renderFuturesTable()" in details


def test_filter_request_abort_is_not_reported_as_page_error() -> None:
    source = PAGE.read_text(encoding="utf-8")

    assert "function handleLoadError(error)" in source
    handler = source[
        source.index("function handleLoadError(error)") :
        source.index("function showError(error)")
    ]
    assert 'error?.name !== "AbortError"' in handler
    assert ".catch(handleLoadError)" in source


def test_chart_styles_and_risk_mode_are_rendered_without_api_reload() -> None:
    source = PAGE.read_text(encoding="utf-8")

    assert "...(dataset.style || {})" in source
    assert 'riskChartMode = "sentiment"' in source
    assert 'data-risk-chart-mode="sentiment"' in source
    assert 'data-risk-chart-mode="hedge_cost"' in source
    mode_handler = source[
        source.index('document.querySelectorAll("[data-risk-chart-mode]"') :
        source.index('document.getElementById("btc-hedge-form")')
    ]
    assert "loadDashboard(" not in mode_handler
    assert 'renderSingleChart("options_risk_premium_history")' in mode_handler
    assert "rendered.modeHidden = rendered.hidden" in source
    assert "!data.datasets[item.datasetIndex]?.modeHidden" in source
    assert "updateRiskChartHeaderInsight" in source


def test_page_safety_copy_is_explicit_and_forbidden_actions_are_absent() -> None:
    source = PAGE.read_text(encoding="utf-8")

    assert '<details class="btc-method-notes">' in source
    assert '<details class="btc-method-notes" open>' not in source
    method_notes = source[source.index('<details class="btc-method-notes">') :]
    assert "最大痛点" in method_notes and "价格预测" in method_notes
    assert "期权墙" in method_notes and "确定支撑或阻力" in method_notes
    assert "不执行下单" in method_notes
    assert "不推荐裸卖期权" in method_notes
    assert "比例价差" in method_notes and "安全对冲" in method_notes
    for forbidden in {"naked_sell", '"sell_call"', '"sell_put"', '"ratio_spread"'}:
        assert forbidden not in source


def test_chart_header_uses_interpretation_not_timestamp_metadata() -> None:
    source = PAGE.read_text(encoding="utf-8")

    assert "function chartInsight" in source
    assert "btc-chart-insight" in source
    assert "metadata.updated_at" not in source
    assert "displayState(metadata.quality)" not in source


def test_chart_header_uses_short_labels_not_evidence_layer_sentences() -> None:
    source = PAGE.read_text(encoding="utf-8")
    chart_insight = source[
        source.index("function chartInsight") : source.index("function chartCard")
    ]

    assert "implication" not in chart_insight
    assert "关键价位迁移与现价存在分歧" not in chart_insight
    assert "墙位迁移" in chart_insight
    assert "保护成本" in chart_insight


def test_hero_uses_market_verdict_not_generic_page_description() -> None:
    source = PAGE.read_text(encoding="utf-8")
    hero_verdict = source[
        source.index("function heroMarketVerdict") : source.index("function renderHero")
    ]

    assert "function heroMarketVerdict" in source
    assert "暂不能形成可靠多空判定" in source
    assert "用真实公开数据观察期货拥挤" not in source
    assert "依据：" not in hero_verdict


def test_page_renders_options_wall_signal_card_from_dashboard_metrics() -> None:
    source = PAGE.read_text(encoding="utf-8")

    assert "function renderOptionsWallSignal" in source
    assert "options_wall_signal" in source
    assert "call_wall" in source
    assert "put_wall" in source
    assert "max_pain" in source
    assert "btc-wall-signal-card" in source
    assert "现价变化" in source
    assert "signal.spot_change_pct" in source
    assert "expiry_context" in source


def test_bottom_sections_are_grouped_into_parent_containers() -> None:
    source = PAGE.read_text(encoding="utf-8")
    styles = STYLES.read_text(encoding="utf-8")

    assert "btc-bottom-group" in source
    assert "btc-protection-group" in source
    assert "btc-audit-group" in source
    assert "btc-governance-group" in source
    assert ".btc-bottom-group" in styles
    assert ".btc-bottom-group-body" in styles


def test_page_has_scoped_responsive_styles() -> None:
    styles = STYLES.read_text(encoding="utf-8")

    assert ".btc-derivatives-page" in styles
    assert ".btc-dashboard-grid" in styles
    for span in {4, 6, 8, 12}:
        assert f".btc-card-span-{span}" in styles
    for density in {"hero", "surface", "standard", "compact"}:
        assert f".btc-chart-density-{density}" in styles
    assert ".btc-hedge-grid" in styles
    assert ".btc-details-drawer" in styles
    assert ".btc-chart-insight" in styles
    assert ".btc-level-title .tooltip-icon" in styles
    assert "grid-template-columns: repeat(6, minmax(0, 1fr));" in styles
    assert 'body[data-page="btc-derivatives"]' in styles
