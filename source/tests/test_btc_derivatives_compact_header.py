from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
PAGE_JS = ROOT / "app" / "static" / "pages" / "btc_derivatives.js"
EDITORIAL_CSS = ROOT / "app" / "static" / "editorial.css"


def test_derivatives_header_groups_summary_decisions_and_controls() -> None:
    # 2026-09-04 (V2.3 workbench): the old cockpit-header wrapper is gone.
    # The summary chart is the primary content. Evidence opens on demand,
    # then the shared chart toolbar follows.
    source = PAGE_JS.read_text(encoding="utf-8")
    # isolate the page shell template (its literal markup anchor) so these
    # are CALL positions, not function definitions
    shell_start = source.index('<div class="btc-derivatives-page">')
    shell = source[shell_start:shell_start + 2500]
    assert shell.index("renderSummarySection()") < shell.index("renderChartToolbar()")
    assert shell.index("renderChartToolbar()") < shell.index("renderMaturityLadder()")
    assert "renderWorkbenchEvidenceRail()" not in shell
    assert 'id="btc-open-summary-evidence"' in source


def test_derivatives_header_removes_stacked_card_weight() -> None:
    css = EDITORIAL_CSS.read_text(encoding="utf-8")

    assert 'body[data-page="btc-derivatives"] .btc-cockpit-header' in css
    assert "min-height: 0;" in css
    assert "padding: 13px 18px 12px;" in css
    assert "padding: 11px 18px 12px;" in css
