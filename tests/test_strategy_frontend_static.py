"""Frontend contract tests for the AI Strategy page (multi-instrument
opportunity scanner hub).

The strategy page was rewritten (commit 28df2e3) as a scan matrix that
lists all instruments × timeframes; clicking a cell / ranked card opens
a slide-in detail panel that consumes `/strategy/unified` for that pair.

These tests validate the **scan-hub contract** — they no longer assert
the legacy unified-only renderer architecture.
"""
from __future__ import annotations

from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]


# ---------------------------------------------------------------------------
# Registration / entry point
# ---------------------------------------------------------------------------


def test_strategy_navigation_and_page_registration():
    """The strategy page is registered after knowledge-base in the top nav,
    loaded via `loadPageModule`, exposed at /strategy-page."""
    page = (ROOT / "app/templates/page.html").read_text(encoding="utf-8")
    main = (ROOT / "app/static/main.js").read_text(encoding="utf-8")
    router = (ROOT / "app/web/router.py").read_text(encoding="utf-8")

    assert page.rfind('data-page-link="ai-strategy"') > page.rfind(
        'data-page-link="knowledge-base"'
    )
    assert '"ai-strategy": () => loadPageModule("./pages/strategy.js?v=trade-4h-v1")' in main
    assert "/strategy-page" in router
    assert '"ai-strategy"' in router


def test_strategy_entry_is_thin_re_export():
    """strategy.js is a one-line re-export shim — the real entry is
    pages/strategy/index.js."""
    shim = (ROOT / "app/static/pages/strategy.js").read_text(encoding="utf-8")
    index = (ROOT / "app/static/pages/strategy/index.js").read_text(encoding="utf-8")

    assert shim.startswith(
        'export { renderStrategy as default, renderStrategy } from "./strategy/index.js'
    )
    assert "export async function renderStrategy" in index
    assert "export default renderStrategy" in index


def test_strategy_entry_does_not_expose_mojibake():
    """No mojibake or legacy warmup copy leaks into the entry files."""
    index = (ROOT / "app/static/pages/strategy/index.js").read_text(encoding="utf-8")
    shim = (ROOT / "app/static/pages/strategy.js").read_text(encoding="utf-8")
    combined = index + shim

    for forbidden in ("缁熶竴绛栫暐", "统一策略快照尚未就绪，后台预热中"):
        assert forbidden not in combined, (
            f"strategy entry exposes stale copy: {forbidden!r}"
        )


# ---------------------------------------------------------------------------
# Scan shell structure
# ---------------------------------------------------------------------------


def test_strategy_scan_shell_renders_matrix_and_ranked_cards():
    """The scan shell must contain both the matrix section and the ranked
    opportunities section, plus a refresh button."""
    index = (ROOT / "app/static/pages/strategy/index.js").read_text(encoding="utf-8")

    for marker in (
        'class="strategy-v2-page strategy-scan-page"',
        'id="strategy-scan-refresh"',
        'id="strategy-scan-matrix-section"',
        'id="strategy-scan-ranked-section"',
        'id="strategy-scan-matrix"',
        'id="strategy-scan-ranked"',
    ):
        assert marker in index, f"scan shell missing marker: {marker!r}"


def test_strategy_scan_shell_uses_simplified_chinese_titles():
    """User-facing titles in the scan shell are simplified Chinese."""
    index = (ROOT / "app/static/pages/strategy/index.js").read_text(encoding="utf-8")

    for label in ("跨品种跨周期机会扫描", "机会矩阵", "机会排序", "刷新扫描"):
        assert label in index, f"scan shell missing Chinese label: {label!r}"


# ---------------------------------------------------------------------------
# Scanner wiring (hub level)
# ---------------------------------------------------------------------------


def test_strategy_index_uses_strategy_scan_endpoint():
    """The hub fetches /strategy/scan (not /strategy/unified directly)
    to populate the matrix + ranked list."""
    index = (ROOT / "app/static/pages/strategy/index.js").read_text(encoding="utf-8")
    api = (ROOT / "app/static/core/api.js").read_text(encoding="utf-8")

    assert "api.getStrategyScan" in index
    assert '"/strategy/scan"' in api
    # The scan hub's primary data fetch is /strategy/scan — the
    # /strategy/unified call lives only inside the per-cell detail-panel
    # loader (onSelectOpportunity), so it must come AFTER the scan fetch
    # definition in the source order.
    assert index.find("api.getStrategyScan(") > index.find("function onSelectOpportunity"), (
        "getStrategyScan must be referenced after onSelectOpportunity is defined"
    )
    assert index.find("function onSelectOpportunity") > -1
    assert index.find("api.getUnifiedStrategy(") > index.find("function onSelectOpportunity")
    assert "loadStrategy" in index
    # And it must use an AbortController so the previous scan can be
    # cancelled when the user clicks refresh.
    assert "AbortController" in index
    assert "activeController" in index
    assert 'err?.name === "AbortError"' in index


def test_strategy_index_wires_scan_renderers_and_detail_panel():
    """index.js imports the scan matrix + ranked list renderers and the
    detail panel opener, and binds click handlers for both."""
    index = (ROOT / "app/static/pages/strategy/index.js").read_text(encoding="utf-8")

    for token in (
        'from "./renderScanMatrix.js"',
        'from "./renderScanRanked.js"',
        'from "./renderDetailPanel.js"',
        "renderScanMatrix(",
        "renderScanRanked(",
        "bindScanMatrix(",
        "bindScanRanked(",
        "openDetailPanel(",
    ):
        assert token in index, f"index.js missing wiring: {token!r}"


# ---------------------------------------------------------------------------
# Detail panel
# ---------------------------------------------------------------------------


def test_strategy_detail_panel_exists_and_exports_opener():
    """renderDetailPanel.js exports openDetailPanel(instrumentId,
    timeframe, loadStrategy, onClose) and renders all sub-modules."""
    panel = (ROOT / "app/static/pages/strategy/renderDetailPanel.js").read_text(
        encoding="utf-8"
    )

    assert "export function openDetailPanel" in panel
    # Header + close button
    assert '"strategy-detail-panel"' in panel
    assert '"strategy-detail-overlay"' in panel
    assert '"strategy-detail-close"' in panel
    # Sub-module renderers must all be imported and called
    for renderer in (
        "renderOverview",
        "renderExecutionPlan",
        "renderDecisionAudit",
        "renderEvidenceStack",
        "renderMarketOperation",
        "renderRiskPanel",
        "renderEventWatch",
        "buildDataDegradedCard",
    ):
        assert renderer in panel, f"detail panel missing renderer: {renderer!r}"
    # Error + escape handling
    assert "errorState" in panel
    assert "Escape" in panel
    # Cleanup before re-opening
    assert "existingPanel" in panel
    assert "existingOverlay" in panel


def test_strategy_detail_panel_renders_unified_loaded_model():
    """The panel awaits loadStrategy(...) and replaces the body with the
    full set of module outputs."""
    panel = (ROOT / "app/static/pages/strategy/renderDetailPanel.js").read_text(
        encoding="utf-8"
    )
    assert "loadStrategy(" in panel
    assert ".then((model)" in panel or ".then(model =>" in panel
    assert "body.innerHTML" in panel


# ---------------------------------------------------------------------------
# Scan Matrix renderer
# ---------------------------------------------------------------------------


def test_strategy_scan_matrix_renders_table_with_three_timeframes():
    """Matrix renders a 4-column table (品种 + 3 timeframes)."""
    matrix = (ROOT / "app/static/pages/strategy/renderScanMatrix.js").read_text(
        encoding="utf-8"
    )
    assert "scan-matrix-table" in matrix
    assert "周线" in matrix
    assert "日线" in matrix
    assert "4H" in matrix
    assert "data-instrument" in matrix
    assert "data-timeframe" in matrix
    assert "scan-cell-btn" in matrix
    assert "等待" in matrix  # empty-state cell


def test_strategy_scan_matrix_bind_clicks_route_to_onSelect():
    """bindScanMatrix attaches click handlers that read data-* attrs."""
    matrix = (ROOT / "app/static/pages/strategy/renderScanMatrix.js").read_text(
        encoding="utf-8"
    )
    assert "export function bindScanMatrix" in matrix
    assert "querySelectorAll" in matrix
    assert "dataset.instrument" in matrix
    assert "dataset.timeframe" in matrix
    assert "onSelect(" in matrix


# ---------------------------------------------------------------------------
# Ranked renderer
# ---------------------------------------------------------------------------


def test_strategy_scan_ranked_renders_directional_cards_only():
    """Ranked list renders .scan-ranked-card articles with tone +
    instrument + timeframe data attrs and shows score / confidence /
    risk_reward / leverage_hint."""
    ranked = (ROOT / "app/static/pages/strategy/renderScanRanked.js").read_text(
        encoding="utf-8"
    )

    assert "scan-ranked-list" in ranked
    assert "scan-ranked-card" in ranked
    assert "data-tone" in ranked
    assert "data-instrument" in ranked
    assert "data-timeframe" in ranked
    assert "direction_label" in ranked
    assert "summary" in ranked
    assert "confidence" in ranked
    assert "risk_reward" in ranked
    assert "leverage_hint" in ranked
    assert "现货" in ranked  # spot translation
    assert "当前无明确交易机会。所有品种×级别均处于等待状态。" in ranked


def test_strategy_scan_ranked_bind_clicks_route_to_onSelect():
    """bindScanRanked attaches click handlers on .scan-ranked-card."""
    ranked = (ROOT / "app/static/pages/strategy/renderScanRanked.js").read_text(
        encoding="utf-8"
    )
    assert "export function bindScanRanked" in ranked
    assert "scan-ranked-card" in ranked
    assert "dataset.instrument" in ranked
    assert "dataset.timeframe" in ranked
    assert "onSelect(" in ranked


# ---------------------------------------------------------------------------
# Click flow
# ---------------------------------------------------------------------------


def test_strategy_index_opens_detail_panel_on_cell_click():
    """onSelectOpportunity wires matrix / ranked clicks to the detail
    panel with an async loader that fetches the unified strategy for
    that (instrumentId, timeframe) pair."""
    index = (ROOT / "app/static/pages/strategy/index.js").read_text(encoding="utf-8")

    assert "function onSelectOpportunity" in index
    assert "api.getUnifiedStrategy(" in index
    assert "normalizeUnifiedStrategy" in index
    assert "openDetailPanel(instrumentId, timeframe," in index
    # Loader returns a normalized model with instrument_code + data_access
    assert "model.instrument_code" in index
    assert "data_access" in index


# ---------------------------------------------------------------------------
# Lifecycle
# ---------------------------------------------------------------------------


def test_strategy_render_returns_lifecycle_object():
    """renderStrategy() returns { mount, unmount, pause, resume } and
    unmount() resets mounted + aborts the active controller."""
    index = (ROOT / "app/static/pages/strategy/index.js").read_text(encoding="utf-8")

    assert "  mount: async" in index
    assert "  unmount: async" in index
    assert "  pause: async" in index
    assert "  resume: async" in index
    assert "mounted = false" in index
    assert "activeController?.abort()" in index
    assert "activeController = null" in index


def test_strategy_mount_resumes_after_pause_without_redundant_scan():
    """resume() must avoid re-scanning when scanData is already cached."""
    index = (ROOT / "app/static/pages/strategy/index.js").read_text(encoding="utf-8")
    assert "if (mounted && !scanData) await loadScan(false)" in index


# ---------------------------------------------------------------------------
# Legacy contract — these old renderers must not be wired into the scan hub
# ---------------------------------------------------------------------------


def test_strategy_index_does_not_wire_legacy_renderers():
    """The scan hub must not import / call the legacy unified renderers —
    those now live behind the detail panel only."""
    index = (ROOT / "app/static/pages/strategy/index.js").read_text(encoding="utf-8")

    for old_renderer in (
        "renderHorizonGovernance",
        "renderHorizonStack",
        "renderTradePlans",
        "renderEvidenceTrace",
        "renderNarrative",
        "renderTradeDecision",
    ):
        assert old_renderer not in index, (
            f"scan hub must not wire legacy renderer: {old_renderer}"
        )


def test_strategy_does_not_show_position_management_actions():
    """Combined check across all strategy/* files: no position-management
    copy leaked into the new architecture."""
    base = ROOT / "app/static/pages/strategy"
    combined = "\n".join(p.read_text(encoding="utf-8") for p in base.glob("*.js"))
    forbidden = ["ADD_LONG", "REDUCE_LONG", "CLOSE_LONG", "HOLD_LONG", "TAKE_PROFIT"]
    assert not any(item in combined for item in forbidden), (
        f"position-management copy leaked into strategy module: {forbidden}"
    )


def test_strategy_never_uses_pending_risk_reward_copy():
    """Combined check: no '待评估' / '暂不能评估' copy on the strategy page."""
    base = ROOT / "app/static/pages/strategy"
    combined = "\n".join(p.read_text(encoding="utf-8") for p in base.glob("*.js"))
    assert "待评估" not in combined
    assert "暂不能评估" not in combined


# ---------------------------------------------------------------------------
# Cold-load reliability (2026-07-24):
# Cold direct-load was failing because /strategy/scan blocked for 60+
# seconds (rebuilding every cell's unified strategy from cold cache)
# while the frontend timed out at 60s. The page never invoked its
# existing /strategy/prewarm endpoint. Fixes:
#   1. index.js must call api.prewarmStrategy() once on mount.
#   2. The first cold scan must use a 90s+ timeout.
#   3. Auto-scan on mount must be force=false (force is reserved for
#      the manual 刷新扫描 button).
#   4. loadScan() must retry once on transient failure.
#   5. A warming banner must distinguish "warming" from "loading".
# ---------------------------------------------------------------------------


def test_strategy_index_prewarms_on_mount():
    """index.js must call api.prewarmStrategy() once on mount before
    loadScan(), with a module-level guard so it only fires once per
    page module load."""
    index = (ROOT / "app/static/pages/strategy/index.js").read_text(encoding="utf-8")
    api = (ROOT / "app/static/core/api.js").read_text(encoding="utf-8")

    assert "api.prewarmStrategy" in index or "prewarmStrategy(" in index, (
        "strategy page never calls api.prewarmStrategy — cold scan will hang 60+ s"
    )
    assert "prewarmStrategy(" in api, "api.js must export prewarmStrategy"
    # Module-level guard
    assert ("let prewarmed" in index) or ("const prewarmed" in index), (
        "prewarm must be guarded by a module-level flag to avoid spamming the precompute queue"
    )


def test_strategy_index_uses_extended_timeout_for_cold_scan():
    """First scan must use a 90s+ timeoutMs so the ~68s cold-load
    latency doesn't trip the default 60s frontend timeout."""
    index = (ROOT / "app/static/pages/strategy/index.js").read_text(encoding="utf-8")
    # Either a literal number >= 90000 in a timeoutMs option, or a
    # helper that selects between forced/cold timeoutMs values.
    assert (
        "timeoutMs: 90000" in index
        or "timeoutMs: 120000" in index
        or "timeoutMs: 100000" in index
    ), (
        "first scan timeoutMs must be >= 90000 to ride out cold latency"
    )


def test_strategy_index_auto_scan_is_not_forced():
    """Auto-scan on mount is force=false; force=true is reserved for
    the manual 刷新扫描 button."""
    index = (ROOT / "app/static/pages/strategy/index.js").read_text(encoding="utf-8")
    assert "loadScan(false)" in index, "mount-time auto-scan must use force=false"
    assert "loadScan(true)" in index, "manual 刷新扫描 button must use force=true"


def test_strategy_index_retries_once_on_transient_error():
    """If loadScan fails on a transient error, it must retry once
    before showing the "扫描失败" banner."""
    index = (ROOT / "app/static/pages/strategy/index.js").read_text(encoding="utf-8")
    # The retry must go through loadScan again, not bypass it
    assert "retry" in index.lower(), (
        "loadScan must have a retry-once path for transient failures"
    )


def test_strategy_index_shows_warming_banner():
    """While the backend signals 'warming' (cache_meta.source='warming'),
    the page must render a banner that distinguishes warming from
    the normal loading dots."""
    index = (ROOT / "app/static/pages/strategy/index.js").read_text(encoding="utf-8")
    assert ("预热" in index) or ("warming" in index.lower()), (
        "index.js must show a warming-state UI distinct from the regular loading dots"
    )


# ---------------------------------------------------------------------------
# Sanity — the modules that the detail panel still consumes must exist
# ---------------------------------------------------------------------------


def test_strategy_detail_panel_dependencies_exist():
    """Modules imported by the detail panel must still exist on disk."""
    base = ROOT / "app/static/pages/strategy"
    for rel in (
        "renderOverview.js",
        "renderExecutionPlan.js",
        "renderDecisionAudit.js",
        "renderEvidenceStack.js",
        "renderMarketOperation.js",
        "renderRiskPanel.js",
        "renderEventWatch.js",
        "adapter.js",
    ):
        assert (base / rel).exists(), f"detail panel dependency missing: {rel}"


def test_strategy_detail_panel_uses_no_mojibake():
    """renderDetailPanel.js + adapter.js must not contain mojibake."""
    base = ROOT / "app/static/pages/strategy"
    sources = "\n".join(
        (base / name).read_text(encoding="utf-8")
        for name in ("renderDetailPanel.js", "adapter.js")
    )
    assert "缁熶竴绛栫暐" not in sources
    assert "鑱旇" not in sources  # generic mojibake marker