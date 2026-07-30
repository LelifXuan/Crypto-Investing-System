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


def test_page_renders_current_chart_layout_from_backend_metadata() -> None:
    # 2026-07-23: the per-venue cross-section chart was replaced by a
    # per-venue HTML table + a standalone 90D aggregate-OI line chart.
    # The term-structure chart was later removed from the page. Keep the
    # remaining chart ids and the aggregate-OI auxiliary renderer locked.
    source = PAGE.read_text(encoding="utf-8")

    for chart_id in {
        "leverage_pressure_timeline",
        "aggregate_oi_90d",
        "strike_surface",
        "key_levels_history",
        "options_risk_premium_history",
    }:
        assert chart_id in source, (
            f"chart_id {chart_id!r} is missing from the page JS"
        )

    assert "dashboard?.chart_layout?.sections" in source
    assert "dashboard?.chart_layout?.cards" in source
    assert "btc-card-span-${span}" in source
    assert "btc-chart-density-${escapeHtml(density)}" in source
    assert "OVERVIEW_CHARTS" not in source
    assert "CHART_CANVAS_IDS" not in source
    assert "renderDecisionCards" in source
    assert "renderHedgePlanner" in source
    assert "renderDataQuality" in source
    assert "renderFuturesTable" in source, (
        "the per-venue crowding table renderer must be present"
    )
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


def test_page_renders_standard_expiry_matrix_and_disables_fixed_selector_in_constant_mode() -> None:
    source = PAGE.read_text(encoding="utf-8")
    styles = STYLES.read_text(encoding="utf-8")

    assert "function renderMaturityLadder()" in source
    assert "标准到期日期限矩阵" in source
    assert "standard_expiries" in source
    assert 'filters.expiryMode === "fixed" ? "" : "disabled"' in source
    assert "optionDirectionLabel" in source
    assert ".btc-maturity-table" in styles
    assert "非标准到期日" not in source


def test_option_chain_and_raw_tables_are_in_closed_details_panel() -> None:
    source = PAGE.read_text(encoding="utf-8")

    assert '<details class="btc-details-drawer">' in source
    assert '<details class="btc-details-drawer" open>' not in source
    details = source[source.index('<details class="btc-details-drawer">') :]
    assert "renderOptionChain()" in details
    assert "renderFuturesTable()" in details


def test_live_source_provider_cards_are_collapsed_by_default() -> None:
    source = PAGE.read_text(encoding="utf-8")

    assert '<details class="btc-source-details">' in source
    assert '<details class="btc-source-details" open>' not in source
    details = source[source.index('<details class="btc-source-details">') :]
    assert "btc-provider-grid" in details
    assert "btc-quality-details" in details
    assert "一键探测数据源" in source[: source.index('<details class="btc-source-details">')]


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


def test_funding_z_uses_solid_positive_and_dashed_negative_segments() -> None:
    source = PAGE.read_text(encoding="utf-8")

    assert "export function expandFundingZeroCrossings" in source
    assert "export function splitFundingZSeries" in source
    assert 'dataset.label === "Funding Z"' in source
    assert "borderDash: [6, 4]" in source
    assert "fundingZLegendDuplicate" in source
    assert "expanded.datasets.flatMap((dataset, index)" in source
    assert "fundingZSegmentBorderDash" not in source


def test_single_point_history_charts_show_centered_markers() -> None:
    source = PAGE.read_text(encoding="utf-8")

    assert "function finiteSeriesPointCount(values)" in source
    assert 'finiteSeriesPointCount(dataset.data) === 1' in source
    assert "extra.pointRadius = Math.max(Number(extra.pointRadius) || 0, 4)" in source
    assert "extra.pointHoverRadius = Math.max(Number(extra.pointHoverRadius) || 0, 6)" in source
    assert "expanded.labels.length === 1" in source
    assert "{ x: { offset: true } }" in source


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


def test_empty_charts_are_compact_and_do_not_claim_a_direction() -> None:
    source = PAGE.read_text(encoding="utf-8")
    styles = Path("app/static/styles.css").read_text(encoding="utf-8")
    judgement = Path("app/static/core/judgement.js").read_text(encoding="utf-8")

    assert 'hasData ? chartInsight(chartId) : "数据不足"' in source
    assert '${hasData ? "" : " is-empty"}' in source
    assert ".btc-chart-card.is-empty .btc-chart-wrap" in styles
    assert "height: 120px" in styles
    assert 'STABLE: "持仓稳定"' in judgement
    assert 'stateKey === "NEUTRAL" && judgement.axis === "crowding"' in judgement
    assert 'judgement.js?v=semantic-v3' in source
    assert ".btc-indicator-semantics .btc-decision-card" in styles


def test_chart_x_axis_keeps_date_only_labels_as_dates_without_fake_time() -> None:
    charts = Path("app/static/ui/charts.js").read_text(encoding="utf-8")

    assert "isDateOnlyLabel" in charts
    assert "return `${month}-${day}`;" in charts
    date_only_branch = charts[
        charts.index("function formatXAxisTick") : charts.index("const numeric")
    ]
    assert "08:00" not in date_only_branch


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

    assert "function renderWallInterpretation" in source
    assert "wall_matrix" in source
    assert "call_wall" in source
    assert "put_wall" in source
    assert "max_pain" in source
    assert "btc-interp-card" in source
    assert "trade_meaning" in source
    assert "trading_instruction" in source
    assert "synthesis" in source


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
    assert ".btc-hedge-form" in styles
    assert ".btc-hedge-section" in styles
    assert ".btc-details-drawer" in styles
    assert ".btc-chart-insight" in styles
    assert ".btc-level-title .tooltip-icon" in styles
    assert "grid-template-columns: repeat(6, minmax(0, 1fr));" in styles
    assert 'body[data-page="btc-derivatives"]' in styles


def test_btc_derivatives_page_auto_refreshes_via_interval() -> None:
    # 2026-07-25: user complaint — the wall-migration chart on the
    # btc-derivatives page freezes on whatever labels arrived at the
    # first load. The expiry matrix above it never ages because those
    # are forward-dated contract expiries, but the historical chart
    # ages every minute. The fix: a 60s setInterval-driven auto-refresh
    # wired into renderBtcDerivatives mount/unmount/pause/resume, with
    # a document.hidden guard so we don't fire when the tab is in the
    # background.
    source = PAGE.read_text(encoding="utf-8")

    assert "AUTO_REFRESH_MS" in source, (
        "page must export an AUTO_REFRESH_MS constant to drive the loop"
    )
    assert "function scheduleAutoRefresh" in source, (
        "page must define scheduleAutoRefresh()"
    )
    assert "function clearAutoRefresh" in source, (
        "page must define clearAutoRefresh() so pause/unmount can cancel"
    )
    assert "scheduleAutoRefresh()" in source, (
        "renderBtcDerivatives must call scheduleAutoRefresh() after initial load"
    )

    import re

    def _extract_block(label):
        m = re.search(rf"{label}\s*\(\)\s*\{{", source)
        assert m, f"{label} not found"
        start = m.end() - 1
        depth = 1
        i = start + 1
        while i < len(source) and depth > 0:
            ch = source[i]
            if ch == "{":
                depth += 1
            elif ch == "}":
                depth -= 1
            i += 1
        return source[start:i]

    unmount_block = _extract_block("unmount")
    assert "clearAutoRefresh" in unmount_block, (
        "unmount() must call clearAutoRefresh() to avoid a leaked timer"
    )
    assert "requestController?.abort" in unmount_block, (
        "unmount() must still abort the in-flight request controller"
    )
    assert "destroyChartsForPage" in unmount_block, (
        "unmount() must still destroy chart instances"
    )

    pause_block = _extract_block("pause")
    assert "clearAutoRefresh" in pause_block, (
        "pause() must call clearAutoRefresh() so the timer doesn't fire while the "
        "user is on another page"
    )
    resume_block = _extract_block("resume")
    assert "scheduleAutoRefresh" in resume_block, (
        "resume() must restart the loop when navigating back to the page"
    )


def test_funding_z_legend_hide_toggles_both_positive_and_negative_datasets() -> None:
    # 2026-07-25 user feedback: hiding the Funding Z legend entry
    # only hid the positive half of the dashed line — the negative
    # half stayed on the canvas because Chart.js's legend clicks
    # toggle a single dataset at a time. Funding-Z is rendered as two
    # parallel datasets sharing the same label so the positive and
    # negative sides can have different borderDash styles. The fix is
    # to wire a legend.onClick hook that flips both siblings together.
    source = PAGE.read_text(encoding="utf-8")

    assert "_fundingZSibling" in source, (
        "Funding Z datasets must carry _fundingZSibling metadata so the legend hook "
        "can flip them together"
    )
    assert "legend" in source and "onClick" in source, (
        "renderSingleChart must wire a plugins.legend.onClick hook to coordinate the toggle"
    )
    # The hook must call setDatasetVisibility on the sibling dataset.
    assert "setDatasetVisibility" in source, (
        "the legend.onClick hook must use setDatasetVisibility to flip sibling visibility"
    )
    # Make sure we still hit Chart.js's default toggle for non-funding
    # entries by keeping the existing legendFilter path intact.
    assert "legendFilter" in source
    # Confirm the hook applies for the Funding Z sibling case but
    # defaults behavior is preserved for everything else.
    assert "_fundingZSibling" in source and "isDatasetVisible" in source, (
        "legend.onClick must check both isDatasetVisible (default toggle path) and "
        "_fundingZSibling metadata"
    )


def test_btc_derivatives_expiry_mode_dropdown_only_shows_fixed_expiry() -> None:
    # 2026-07-25 user feedback: the 到期模式 dropdown offered two modes
    # ("固定到期日" / "恒定期限") but the user only cares about picking
    # a concrete expiry date. Hide the "恒定期限" entry from the UI;
    # the backend still accepts both Literal values for backward
    # compatibility with stored links / dashboards.
    source = PAGE.read_text(encoding="utf-8")

    select_block_start = source.index('name="expiry_mode"')
    # 2026-07-30: dropdown migration replaced <select> with <button class="dropdown">;
    # the data dropdown config is now in mountBtcChartDropdowns() and includes
    # the visible labels for expiry_mode items. Locate the expiry_mode config block.
    items_block_start = source.index('field: "expiry_mode"', select_block_start)
    # Scan until next config entry to capture the label lambda too.
    next_id = source.find("\n    {", items_block_start + 1)
    items_block_end = next_id if next_id > 0 else len(source)
    items_block = source[items_block_start:items_block_end]
    assert "恒定期限" not in items_block, (
        "到期模式 dropdown must not surface the 恒定期限 entry "
        "(users only pick a fixed expiry date now)"
    )
    assert "固定到期日" in items_block, (
        "到期模式 dropdown must keep the 固定到期日 entry"
    )
    import re
    api = Path("app/api/v1/endpoints/btc_derivatives.py").read_text(encoding="utf-8")
    assert re.search(
        r"expiry_mode:\s*Literal\[[\"']fixed[\"'],\s*[\"']constant_maturity[\"']\]",
        api,
    ), (
        "backend should still accept both expiry_mode values for backward compat"
    )


def test_option_wall_table_distinguishes_effective_wall_from_raw_max_oi() -> None:
    source = PAGE.read_text(encoding="utf-8")

    assert "renderMaturityWall" in source
    assert "有效 Put Wall" in source
    assert "有效 Call Wall" in source
    assert "未形成有效墙" in source
    assert "原始最大 OI" in source
    assert "期限 OI" in source
    assert "8D–45D Delta" in source


def test_empty_chart_sections_do_not_leave_orphan_titles() -> None:
    source = PAGE.read_text(encoding="utf-8")

    assert 'if (!auxParts && !chartParts) return "";' in source
