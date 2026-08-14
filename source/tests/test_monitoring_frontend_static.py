from __future__ import annotations

from pathlib import Path

REPO = Path(__file__).resolve().parents[1]
MONITORING_JS = REPO / "app" / "static" / "pages" / "monitoring.js"
STYLES_CSS = REPO / "app" / "static" / "styles.css"

OLD_PRIMARY_LABELS = (
    "交易指引",
    "风险点 / 失效条件",
)


def _read(path: Path) -> str:
    return path.read_text(encoding="utf-8")


def test_monitoring_js_omits_duplicate_decision_rows_from_main_canvas() -> None:
    content = _read(MONITORING_JS)
    assert "renderTerminalSummary" in content
    assert "function getTerminalDecisionRows" not in content
    assert "function renderTerminalDecisionRow" not in content
    assert "terminal-summary-brief" not in content


def test_monitoring_js_old_card_titles_not_used_as_primary() -> None:
    """The old 主要矛盾 / 策略含义 / 观察条件 cards must be gone from the
    active render path. The test confirms the renderTerminalSummary() block
    does not embed these strings as primary labels.
    """

    content = _read(MONITORING_JS)
    start = content.find("function renderTerminalSummary")
    assert start > 0
    end = content.find("\nfunction ", start + 1)
    if end < 0:
        end = len(content)
    block = content[start:end]
    for label in OLD_PRIMARY_LABELS:
        assert label not in block, (
            f"Old label {label!r} still appears as primary card title in "
            "renderTerminalSummary()."
        )


def test_monitoring_css_removes_terminal_brief_classes() -> None:
    content = _read(STYLES_CSS)
    for cls in (
        ".terminal-summary-brief",
        ".terminal-brief-row",
        ".terminal-brief-row-head",
        ".terminal-brief-bullets",
        ".terminal-brief-sources",
        ".terminal-brief-tone-bullish",
        ".terminal-brief-tone-bearish",
        ".terminal-brief-tone-neutral",
        ".terminal-brief-tone-warning",
    ):
        assert cls not in content, f"Obsolete CSS class remains: {cls}"


def test_monitoring_surfaces_have_clear_vertical_separation() -> None:
    content = _read(STYLES_CSS)

    full_render_selector = 'body[data-page="monitoring-overview"] .monitoring-surface + .monitoring-surface'
    diff_shell_selector = 'body[data-page="monitoring-overview"] #monitoring-topbar + .monitoring-summary-surface'
    assert full_render_selector in content
    assert diff_shell_selector in content
    assert "margin-top: 28px;" in content


def test_monitoring_js_does_not_render_decision_brief_in_main_canvas() -> None:
    """V1.5.2 row set is sourced exclusively from the backend
    decision_brief.rows payload; no synthetic fallback rows are
    rendered for missing fields. The function only normalises the
    shape returned by the backend.
    """

    content = _read(MONITORING_JS)
    fn_idx = content.find("function getTerminalDecisionRows")
    assert fn_idx == -1


def test_monitoring_summary_keeps_votes_without_duplicate_brief_wrapper() -> None:
    content = _read(MONITORING_JS)
    start = content.find("function renderTerminalSummary")
    end = content.find("\nfunction ", start + 1)
    block = content[start:end]
    assert "terminal-summary-votes" in block
    assert "terminal-summary-brief" not in block
    assert "renderTerminalDecisionRow" not in block


def test_monitoring_terminal_summary_localizes_module_vote_chips() -> None:
    content = _read(MONITORING_JS)
    start = content.find("function renderTerminalSummary")
    end = content.find("\nfunction renderMacroIndicatorCard", start)
    block = content[start:end]

    assert "impactLabel(" in block
    assert 'readableText(item.impact, "neutral")' not in block
    assert ">neutral<" not in block
    assert ">mild_bearish<" not in block
    assert ">low_confidence<" not in block
    assert ">pending<" not in block


def test_monitoring_source_ref_renderer_is_removed_with_duplicate_rows() -> None:
    content = _read(MONITORING_JS)
    start = content.find("function renderTerminalDecisionRow")

    assert start == -1
    assert "sourcePageHref(" not in content


def test_monitoring_load_dashboard_renders_dashboard_before_macro_enhancement() -> None:
    content = _read(MONITORING_JS)
    start = content.find("async function loadDashboard")
    end = content.find("\nexport async function renderMonitoring", start)
    block = content[start:end]

    assert "Promise.all" not in block
    assert "const macroPromise" in block
    assert "applyMonitoringDiff(bundle)" in block
    assert "macroPromise.then" in block
    assert "mergeMacroIntoBundle(lastRenderedBundle, macro)" in block
    assert "lastRenderedBundle = enhancedBundle" in block
    assert "rememberMonitoringBundle(enhancedBundle, instrumentId, timeframe)" in block


def test_monitoring_macro_enhancement_replaces_stale_dashboard_macro() -> None:
    content = _read(MONITORING_JS)
    start = content.find("function mergeMacroIntoBundle")
    end = content.find("\nfunction readStoredMonitoringBundle", start)
    block = content[start:end]

    assert "macro_overview: macro" in block
    assert "bundle || {}" in block
    assert "!bundle?.macro_overview" not in block


def test_monitoring_load_dashboard_preserves_rendered_page_on_abort_or_failure() -> None:
    content = _read(MONITORING_JS)
    start = content.find("async function loadDashboard")
    end = content.find("\nexport async function renderMonitoring", start)
    block = content[start:end]

    assert "let lastRenderedBundle" in content
    assert 'setRoot(renderShellFallback("正在读取监控快照"))' not in block
    assert 'setRoot(renderShellFallback("监控快照读取失败' not in block
    assert "hasRenderedMonitoringShell()" in block
    assert "showMonitoringBanner(" in block


def test_monitoring_load_dashboard_can_seed_shell_from_recent_browser_snapshot() -> None:
    content = _read(MONITORING_JS)
    start = content.find("async function loadDashboard")
    end = content.find("\nexport async function renderMonitoring", start)
    block = content[start:end]

    assert "MONITORING_SNAPSHOT_STORAGE_KEY" in content
    assert "readStoredMonitoringBundle(instrumentId, timeframe)" in block
    assert "applyMonitoringDiff(storedBundle)" in block
    assert "rememberMonitoringBundle(bundle, instrumentId, timeframe)" in block
