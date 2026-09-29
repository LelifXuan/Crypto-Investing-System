"""Static guards for the strategy detail drawer (ui-audit 2026-09-04 P1#2).

Audit findings being pinned:
- Drawer top:0 sat under the 64px global topbar — the "返回扫描" button
  was invisible (guideline §5.2 topbar avoidance).
- aria-modal="true" but no focus containment (§10 dialog lifecycle).
- Internal scrollWidth (2482px) exceeded clientWidth (1918px) — long
  trigger sentences and audit tables spilled horizontally (§11).
"""

from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
STYLES = (ROOT / "app/static/styles.css").read_text(encoding="utf-8")
PANEL = (ROOT / "app/static/pages/strategy/renderDetailPanel.js").read_text(encoding="utf-8")


def test_drawer_starts_below_topbar() -> None:
    idx = STYLES.index(".strategy-detail-panel {")
    block = STYLES[idx : STYLES.index("}", idx)]
    assert "top: var(--topbar-height, 64px)" in block
    assert "calc(100vh - var(--topbar-height, 64px))" in STYLES[idx : idx + 600]


def test_drawer_body_clips_horizontal_overflow() -> None:
    idx = STYLES.index(".strategy-detail-body {")
    tail = STYLES[idx : idx + 900]
    assert "overflow-x: clip" in tail
    assert "overflow-wrap: anywhere" in tail


def test_dialog_implements_focus_lifecycle() -> None:
    assert 'panel.setAttribute("aria-modal", "true")' in PANEL
    assert "(backBtn || panel).focus({ preventScroll: true })" in PANEL
    assert 'if (e.key !== "Tab") return' in PANEL
    assert 'document.removeEventListener("keydown", tabHandler)' in PANEL
    assert "focusOrigin?.isConnected" in PANEL


def test_drawer_leads_with_independent_period_execution() -> None:
    """The selected cell owns the decision and its lower-period execution."""
    assert "timeframe_stack" in PANEL
    assert "cellNode" in PANEL
    assert PANEL.index("renderPeriodOpportunity(opportunity, model, helpers)") < PANEL.index(
        "renderTimeframeFocus(model, timeframe, helpers)"
    )
    assert "renderOverview(model, helpers)" not in PANEL
    focus = (ROOT / "app/static/pages/strategy/renderTimeframeFocus.js").read_text(encoding="utf-8")
    assert "item?.timeframe === timeframe" in focus
    assert "node.direction" in focus
    assert "node.key_support" in focus and "node.key_resistance" in focus
    assert "执行价位来自下一交易级别" in focus
