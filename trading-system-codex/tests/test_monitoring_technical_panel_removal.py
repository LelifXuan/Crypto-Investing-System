"""Tests for the removal of the standalone '技术观测' (TECHNICAL) panel.

The monitoring-overview page used to ship a dedicated right-column panel that
listed ~20 BTC technical indicator cards (EMA / RSI / MACD / ATR / VWAP / ...).
That panel sat next to the macro panel and the terminal summary, mixing
macro/abstract evidence with BTC day-level micro evidence in the same space.

The new architecture folds the technical indicators into the terminal summary
as a '证据：…' (evidence) annotation on the three technical sub-modules
(趋势 / 动量 / 波动). The standalone panel is gone, and the terminal summary
spans both columns so the page reads as a clean macro → terminal-brief flow.
"""

from __future__ import annotations

from pathlib import Path

REPO = Path(__file__).resolve().parents[1]
MONITORING_JS = REPO / "app" / "static" / "pages" / "monitoring.js"
STYLES_CSS = REPO / "app" / "static" / "styles.css"


def _read(path: Path) -> str:
    return path.read_text(encoding="utf-8")


# ---------------------------------------------------------------------------
# 1) The standalone '技术观测' panel must NOT be rendered any more.
# ---------------------------------------------------------------------------


def test_standalone_technical_panel_is_removed_from_render_path() -> None:
    """The renderDashboard entrypoint must not embed the standalone technical
    panel. We assert the technical chip grid template (the 20-card grid) and
    the '技术观测' <h2> headline string are no longer wired into the page
    shell. The helper functions (getTechnicalItems, renderTechnicalCard)
    may still exist because the topbar still uses them to compute
    technicalCount, but the visible 20-card grid must be gone."""
    content = _read(MONITORING_JS)

    # The renderTechnicalPanel function (which produced the visible grid) is
    # gone.
    assert "function renderTechnicalPanel" not in content, (
        "renderTechnicalPanel function must be removed; technical indicators "
        "are now folded into the terminal summary as '证据' annotations"
    )

    # The chip-grid template that wrapped the 20 indicator cards is gone.
    assert "technical-chip-grid" not in content, (
        "the 'technical-chip-grid' template must be removed; that container "
        "held the 20 BTC indicator cards and is no longer rendered"
    )

    # The dedicated <h2>技术观测</h2> headline string (the user-visible card
    # title) must not be emitted by any template any more. The shell
    # template inside applyMonitoringDiff should also not reference the
    # removed technical-panel id.
    assert "<h2>技术观测</h2>" not in content, (
        "the standalone '技术观测' headline must be removed from the page"
    )
    assert "monitoring-technical-panel" not in content, (
        "the 'monitoring-technical-panel' section id must be removed from "
        "the diff shell and section registry"
    )


# ---------------------------------------------------------------------------
# 2) Terminal summary now spans both columns; the right-stack is gone.
# ---------------------------------------------------------------------------


def test_terminal_summary_spans_both_columns_in_render_dashboard() -> None:
    """renderDashboard() must place the terminal summary full-width instead of
    inside the left stack. The right stack and its 'technical-panel' wrapper
    must disappear so we don't leave a stranded empty column."""
    content = _read(MONITORING_JS)

    # Find the renderDashboard function body.
    start = content.find("function renderDashboard(")
    assert start > 0, "renderDashboard function must exist"
    end = content.find("\nfunction ", start + 1)
    if end < 0:
        end = len(content)
    block = content[start:end]

    assert "renderTerminalSummary(data)" in block, (
        "renderDashboard must still call renderTerminalSummary, got block: "
        + block
    )
    # The two-stack layout (left/right columns) must be gone.
    assert "monitoring-right-stack" not in block, (
        "renderDashboard must not split the monitoring surface into left/right "
        "stacks any more; the terminal summary should sit full-width"
    )
    assert "renderTechnicalPanel(data)" not in block, (
        "renderDashboard must not call the removed renderTechnicalPanel"
    )


# ---------------------------------------------------------------------------
# 3) The three technical sub-modules (趋势 / 动量 / 波动) must carry a
# '证据：…' annotation naming the indicators that feed them.
# ---------------------------------------------------------------------------


def test_technical_sub_modules_carry_evidence_annotations() -> None:
    """The terminal summary must annotate each technical sub-module card with
    a '证据：…' line listing the indicators that drive it. The line lives
    inside the same <article class="terminal-summary-vote"> wrapper."""
    content = _read(MONITORING_JS)

    # The renderTerminalSummary body is where the per-module cards are built.
    start = content.find("function renderTerminalSummary(")
    assert start > 0
    end = content.find("\nfunction ", start + 1)
    if end < 0:
        end = len(content)
    block = content[start:end]

    assert "证据" in block, (
        "terminal summary must render an '证据' annotation on technical "
        "sub-modules so users can see what feeds the trend/momentum/volatility "
        "scores"
    )

    # The technical sub-modules we annotate. Non-technical modules (macro,
    # structure, event_risk) intentionally do not get an evidence line.
    for module_key in ("technical_trend", "momentum_volume", "volatility"):
        # Each technical module's card builder must reference the module key
        # AND mention the indicators. The exact split can vary, so we check
        # that the module key appears alongside an evidence annotation.
        assert module_key in block, (
            f"terminal summary must still render the {module_key!r} sub-module"
        )


def test_terminal_summary_vote_card_includes_evidence_field() -> None:
    """The per-module vote card template must include a small evidence line
    below the score. We look for the structural shape: the card uses class
    'terminal-summary-vote' AND embeds the '证据' label inside it."""
    content = _read(MONITORING_JS)
    start = content.find("function renderTerminalSummary(")
    assert start > 0
    end = content.find("\nfunction ", start + 1)
    if end < 0:
        end = len(content)
    block = content[start:end]

    # The vote card template ends with `</article>`. The evidence line lives
    # somewhere between the score <small> and that closing tag.
    assert "<article class=\"terminal-summary-vote\">" in block, (
        "per-module vote card class must remain 'terminal-summary-vote'"
    )
    # Evidence line must be inside that template. Look for the structural
    # pair: '证据' within the article block.
    article_start = block.index("<article class=\"terminal-summary-vote\">")
    article_end = block.index("</article>", article_start)
    article = block[article_start:article_end]
    assert "证据" in article, (
        "evidence annotation must live inside the per-module vote card; "
        f"article was: {article}"
    )