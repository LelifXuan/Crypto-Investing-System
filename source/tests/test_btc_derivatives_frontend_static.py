from __future__ import annotations

from pathlib import Path

ROOT = Path(__file__).resolve().parents[2]
PAGE = ROOT / "source/app/static/pages/btc_derivatives.js"
API = ROOT / "source/app/static/core/api.js"
MAIN = ROOT / "source/app/static/main.js"
TEMPLATE = ROOT / "source/app/templates/page.html"
WEB_ROUTER = ROOT / "source/app/web/router.py"
STYLES = ROOT / "source/app/static/styles.css"


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
    api = Path(ROOT / "source/app/static/core/api.js").read_text(encoding="utf-8")

    assert "waitForRefreshJob" in source
    assert "getRefreshJob" in source
    assert "requestJson(`/refresh-jobs/${jobId}`" in api
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
    assert 'dashboard?.data_quality?.mode || "fixture"' not in source


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
        assert chart_id in source, f"chart_id {chart_id!r} is missing from the page JS"

    assert "dashboard?.chart_layout?.sections" in source
    assert "dashboard?.chart_layout?.cards" in source
    assert "btc-card-span-${span}" in source
    assert "btc-chart-density-${escapeHtml(density)}" in source
    assert "OVERVIEW_CHARTS" not in source
    assert "CHART_CANVAS_IDS" not in source
    assert "renderDecisionCards" in source
    assert "renderHedgePlanner" in source
    assert "renderGovernanceGroup" in source
    assert "renderFuturesTable" in source, "the per-venue crowding table renderer must be present"
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
    assert 'class="btc-table-wrap btc-maturity-table-wrap"' in source
    maturity_wrap_rule = styles[styles.index(".btc-table-wrap.btc-maturity-table-wrap") :]
    maturity_wrap_rule = maturity_wrap_rule[: maturity_wrap_rule.index("}")]
    assert "max-height: none" in maturity_wrap_rule
    assert "overflow-y: hidden" in maturity_wrap_rule
    assert "非标准到期日" not in source


def test_option_chain_and_raw_tables_are_in_closed_details_panel() -> None:
    # 2026-08-19: 原始市场明细已删除，此测试不再适用
    # 保留空函数以避免测试收集器告警
    pass


def test_data_source_footer_matches_gold_governance_ledger() -> None:
    """2026-08-27 §13.2 #3: btc-derivatives no longer inlines the
    governance section template — it delegates to renderGovernanceLedger(
    {variant: "btc"}). The label set (期权行情 / 永续合约 / 接口覆盖 / 快照时间)
    still comes from the page, so we assert those plus the renderer
    delegation."""
    source = PAGE.read_text(encoding="utf-8")
    styles = STYLES.read_text(encoding="utf-8")
    editorial = Path(ROOT / "source/app/static/editorial.css").read_text(encoding="utf-8")

    # Page must import + delegate to the shared renderer.
    assert "renderGovernanceLedger" in source
    assert 'variant: "btc"' in source
    # The 4-item label set is still authored by the page.
    for label in ("期权行情", "永续合约", "接口覆盖", "快照时间"):
        assert label in source
    # Legacy inline section template must NOT be reintroduced.
    assert 'class="card governance-ledger btc-governance"' not in source
    assert 'class="governance-ledger__grid btc-governance-grid"' not in source
    # styles.css no longer carries the body[data-page="btc-derivatives"] legacy block.
    assert 'body[data-page="btc-derivatives"] .governance-ledger' not in styles
    # The variant now lives in editorial.css as .governance-ledger--btc.
    assert ".governance-ledger--btc" in editorial
    assert '<details class="btc-source-details">' not in source
    assert '<details class="btc-quality-details">' not in source
    assert "btc-provider-card" not in source
    assert "btc-provider-error" not in source
    for leak in ("last_error", "Client error", "HTTPStatus", "Mozilla"):
        assert leak not in source


def test_filter_request_abort_is_not_reported_as_page_error() -> None:
    source = PAGE.read_text(encoding="utf-8")

    assert "function handleLoadError(error)" in source
    handler = source[
        source.index("function handleLoadError(error)") : source.index("function showError(error)")
    ]
    assert 'error?.name !== "AbortError"' in handler
    assert ".catch(handleLoadError)" in source


def test_chart_styles_and_risk_series_are_split_into_two_charts() -> None:
    source = PAGE.read_text(encoding="utf-8")

    assert "...(dataset.style || {})" in source
    assert "const RISK_CHART_VIEWS" in source
    assert 'title: "期权情绪"' in source
    assert 'title: "保护成本"' in source
    assert 'data-risk-chart-view="${escapeHtml(riskView)}"' in source
    assert "datasetVisibleInRiskView" in source
    assert "axesForRiskView" in source
    assert "annotationsForRiskView" in source
    assert 'item.type === "horizontalLine"' in source
    assert "data-risk-chart-mode" not in source
    assert "riskChartMode" not in source


def test_funding_z_uses_solid_positive_and_dashed_negative_segments() -> None:
    source = PAGE.read_text(encoding="utf-8")

    assert "export function expandFundingZeroCrossings" in source
    assert "export function splitFundingZSeries" in source
    assert 'dataset.label === "Funding Z"' in source
    assert "borderDash: [6, 4]" in source
    assert "fundingZLegendDuplicate" in source
    assert ".filter((dataset) => datasetVisibleInRiskView(dataset.label, riskView))" in source
    assert ".flatMap((dataset, index)" in source
    assert "fundingZSegmentBorderDash" not in source


def test_single_point_history_charts_show_centered_markers() -> None:
    source = PAGE.read_text(encoding="utf-8")

    assert "function finiteSeriesPointCount(values)" in source
    assert "finiteSeriesPointCount(dataset.data) === 1" in source
    assert "extra.pointRadius = Math.max(Number(extra.pointRadius) || 0, 4)" in source
    assert "extra.pointHoverRadius = Math.max(Number(extra.pointHoverRadius) || 0, 6)" in source
    assert "expanded.labels.length === 1" in source
    assert "{ x: { offset: true } }" in source


def test_method_notes_section_is_removed() -> None:
    source = PAGE.read_text(encoding="utf-8")

    assert "btc-method-notes" not in source
    assert "renderMethodNotes" not in source
    for fragment in (
        "风险提示与方法边界",
        "最大痛点用于观察持仓分布迁移",
        "不推荐裸卖期权",
        "也不把比例价差描述为安全对冲",
    ):
        assert fragment not in source
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
    styles = Path(ROOT / "source/app/static/styles.css").read_text(encoding="utf-8")
    judgement = Path(ROOT / "source/app/static/core/judgement.js").read_text(encoding="utf-8")

    assert 'hasData ? chartInsight(chartId, riskView) : "数据不足"' in source
    assert '${hasData ? "" : " is-empty"}' in source
    assert ".btc-chart-card.is-empty .btc-chart-wrap" in styles
    assert "height: 120px" in styles
    assert 'STABLE: "持仓稳定"' in judgement
    assert 'stateKey === "NEUTRAL" && judgement.axis === "crowding"' in judgement
    assert ".btc-indicator-semantics .btc-decision-card" in styles


def test_chart_x_axis_keeps_date_only_labels_as_dates_without_fake_time() -> None:
    charts = Path(ROOT / "source/app/static/ui/charts.js").read_text(encoding="utf-8")

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
    assert "RISK_CHART_VIEWS[riskView]?.insight" in chart_insight
    assert 'title: "保护成本"' in source


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
    editorial = Path(ROOT / "source/app/static/editorial.css").read_text(encoding="utf-8")
    shared = Path(ROOT / "source/app/static/ui/governanceLedger.js").read_text(encoding="utf-8")

    assert "btc-bottom-group" in source
    assert "btc-protection-group" in source
    assert "btc-audit-group" in source
    # The .btc-governance class hook moved into the shared
    # governanceLedger.js (GOVERNANCE_VARIANTS.btc.extraClass) — the
    # btc_derivatives.js page no longer carries that literal.
    assert "btc-governance" in shared
    assert ".btc-bottom-group" in styles
    assert ".btc-bottom-group-body" in styles
    # The .governance-ledger__* classes moved to editorial.css during
    # the §13.2 #3 cleanup (the shared base lives there now).
    assert ".governance-ledger__head" in editorial
    assert ".governance-ledger__item" in editorial


def test_protection_planner_is_collapsed_by_default_and_toggle_hides_its_body() -> None:
    source = PAGE.read_text(encoding="utf-8")
    styles = STYLES.read_text(encoding="utf-8")

    assert "let isHedgePlannerCollapsed = true;" in source
    assert "body.hidden = isHedgePlannerCollapsed" in source
    assert "setHedgePlannerCollapsed(!isHedgePlannerCollapsed)" in source
    assert ".btc-bottom-group .btc-bottom-group-body[hidden]" in styles
    assert "display: none !important;" in styles


def test_audit_details_are_collapsed_by_default_and_toggle_hides_the_body() -> None:
    source = PAGE.read_text(encoding="utf-8")
    styles = STYLES.read_text(encoding="utf-8")

    assert "let isAuditGroupCollapsed = true;" in source
    assert "body.hidden = isAuditGroupCollapsed" in source
    assert "setAuditGroupCollapsed(!isAuditGroupCollapsed)" in source
    assert ".btc-bottom-group .btc-bottom-group-body[hidden]" in styles
    assert "指标信号与多空推断，供复核和追溯使用。" not in source


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
    assert "function scheduleAutoRefresh" in source, "page must define scheduleAutoRefresh()"
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
    assert "destroyChartsForPage" in unmount_block, "unmount() must still destroy chart instances"

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


def test_btc_derivatives_expiry_mode_is_a_locked_context_value() -> None:
    # Only one supported UI value must not masquerade as an interactive dropdown.
    # The backend still accepts both Literal values for backward compatibility.
    source = PAGE.read_text(encoding="utf-8")

    assert 'class="dropdown btc-locked-control"' in source
    assert 'aria-label="到期模式：固定到期日"' in source
    assert '<input type="hidden" name="expiry_mode" value="fixed"' in source
    assert 'id: "btc-expiry-mode"' not in source
    assert 'field: "expiry_mode"' not in source
    assert 'const expiryMode = "fixed"' in source
    import re

    api = Path(ROOT / "source/app/api/v1/endpoints/btc_derivatives.py").read_text(encoding="utf-8")
    assert re.search(
        r"expiry_mode:\s*Literal\[[\"']fixed[\"'],\s*[\"']constant_maturity[\"']\]",
        api,
    ), "backend should still accept both expiry_mode values for backward compat"


def test_chart_toolbar_uses_equal_fifth_columns() -> None:
    # 2026-08-19: the previous weighted template (`1.4fr 0.7fr 1fr 1.4fr 1fr`)
    # gave the locked `到期模式` badge a visibly narrower cell than its
    # neighbours, and stretched `标准到期日` to a different rhythm from
    # `期限桶` / `行权价范围`. On a 2560×1600 viewport the five controls
    # read as having uneven horizontal spacing even though the gaps were
    # identical. Switched back to equal fifths so all 5 controls share the
    # same width and the row reads as visually consistent.
    import re

    css = STYLES.read_text(encoding="utf-8")
    toolbar_block = css[css.index(".btc-chart-toolbar {") :]
    toolbar_block = toolbar_block[: toolbar_block.index("}") + 1]
    # Extract only the CSS declarations (lines that start with a property
    # name like `display:`, `grid-template-columns:`). This strips out the
    # multi-line `/* ... */` comment block above the property — the
    # comment intentionally references the old weights to document why
    # the change was made.
    declarations = " ".join(
        match.group(0)
        for match in re.finditer(
            r"^\s*[a-z-]+\s*:[^;]+;",
            toolbar_block,
            flags=re.MULTILINE,
        )
    )
    # Old weighted tracks must be gone from the declarations
    for fr in ("1.4fr", "0.7fr", "1.0fr"):
        assert fr not in declarations, (
            f"chart toolbar must not use weighted tracks ({fr}); use equal fifths"
        )
    # New equal-fifths pattern must be present (one repeat() with 5 tracks)
    assert "repeat(5, minmax(0, 1fr))" in declarations, (
        "chart toolbar must use equal fifths: repeat(5, minmax(0, 1fr))"
    )


def test_chart_toolbar_dropdowns_fill_their_equal_columns() -> None:
    """The shared dropdown max-width must not make four controls look shorter."""
    css = STYLES.read_text(encoding="utf-8")
    selector = 'body[data-page="btc-derivatives"] .btc-chart-toolbar .dropdown {'
    block = css[css.index(selector) :]
    block = block[: block.index("}") + 1]

    assert "width: 100%;" in block
    assert "--dropdown-max-width: none;" in block
    assert "min-width: 0;" in block
    assert "max-width: none;" in block
    assert "box-sizing: border-box;" in block


def test_table_wraps_are_capped_for_2560x1600_viewport() -> None:
    # 2026-08-18: dev / target viewport is 2560x1600 (16:10). A bare 60vh
    # grows to 960px on this viewport — within design tolerance, but if the
    # cap ever silently drifts above 1000px the BTC maturity ladder would
    # take over the viewport. We require an explicit ceiling to make the
    # cap auditable.
    css = STYLES.read_text(encoding="utf-8")

    def block(selector: str) -> str:
        start = css.index(selector + " {")
        end = css.index("}", start)
        return css[start:end]

    assert "min(60vh, 960px)" in block(".table-wrap"), (
        ".table-wrap must cap at min(60vh, 960px) for the 2560x1600 dev viewport"
    )
    assert "min(60vh, 960px)" in block(".btc-table-wrap"), (
        ".btc-table-wrap must cap at min(60vh, 960px) for the 2560x1600 dev viewport"
    )


def test_btc_chart_dropdowns_bind_to_camel_case_filter_state() -> None:
    source = PAGE.read_text(encoding="utf-8")
    chart_dropdown_block = source[
        source.index("function mountBtcChartDropdowns") : source.index(
            "function mountBtcHedgeDropdowns"
        )
    ]
    for key in ("window", "maturityBucket", "selectedExpiry", "strikeRangePct"):
        assert f'filterKey: "{key}"' in source
    assert "filters[cfg.filterKey]" in source
    assert "filters[cfg.field]" not in source
    assert 'placeholder: "请选择"' not in chart_dropdown_block
    assert "filters.selectedExpiry" in source


def test_option_wall_table_distinguishes_effective_wall_from_raw_max_oi() -> None:
    source = PAGE.read_text(encoding="utf-8")

    assert "renderMaturityWall" in source
    assert "有效 Put Wall" in source
    assert "有效 Call Wall" in source
    assert "未形成有效墙" in source
    assert "原始最大 OI" in source
    assert "期限 OI" in source


def test_empty_chart_sections_do_not_leave_orphan_titles() -> None:
    source = PAGE.read_text(encoding="utf-8")

    assert 'if (!auxParts && !chartParts) return "";' in source
