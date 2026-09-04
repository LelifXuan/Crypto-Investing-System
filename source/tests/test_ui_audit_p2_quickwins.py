"""Static guards for the P2 quick-wins batch (ui-audit 2026-09-04).

P2#6 monitoring 52px stacked spacing, P2#8 dropdown white background,
P2#9 tertiary contrast, P2#11 canvas accessibility, P2#13 macro empty
table, P2#3 handbook contradictions.
"""

import re
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
STYLES = (ROOT / "app/static/styles.css").read_text(encoding="utf-8")
EDITORIAL = (ROOT / "app/static/editorial.css").read_text(encoding="utf-8")
MACRO = (ROOT / "app/static/pages/macro_calendar.js").read_text(encoding="utf-8")
GUIDE = (ROOT.parent / "docs/design-guidelines.md").read_text(encoding="utf-8")
PAGES = ROOT / "app/static/pages"


def _lum(hex_color: str) -> float:
    hex_color = hex_color.lstrip("#")
    vals = [int(hex_color[i:i + 2], 16) / 255 for i in (0, 2, 4)]
    def f(c):
        return c / 12.92 if c <= 0.03928 else ((c + 0.055) / 1.055) ** 2.4
    return 0.2126 * f(vals[0]) + 0.7152 * f(vals[1]) + 0.0722 * f(vals[2])


def _ratio(fg: str, bg: str) -> float:
    a, b = _lum(fg), _lum(bg)
    if a < b:
        a, b = b, a
    return (a + 0.05) / (b + 0.05)


def test_monitoring_topbar_no_stacked_margin() -> None:
    idx = STYLES.index("#monitoring-topbar + .monitoring-summary-surface")
    block = STYLES[idx:STYLES.index("}", idx)]
    assert "margin-top: 0" in block or "margin-top: 28px" not in block


def test_supply_calendar_dropdown_uses_shared_surface() -> None:
    idx = EDITORIAL.index(".supply-calendar-filter {")
    block = EDITORIAL[idx:EDITORIAL.index("}", idx)]
    assert "background: var(--surface)" in block
    assert "var(--white)" not in block


def test_tertiary_text_meets_aa_on_both_surfaces() -> None:
    m = re.search(r"--text-tertiary:\s*(#[0-9a-fA-F]{6})", EDITORIAL)
    assert m, "tertiary token missing"
    color = m.group(1)
    assert _ratio(color, "#fcfbf8") >= 4.5, f"on surface-elevated: {_ratio(color, '#fcfbf8'):.2f}"
    assert _ratio(color, "#f7f5f1") >= 4.5, f"on surface: {_ratio(color, '#f7f5f1'):.2f}"


def test_macro_empty_table_shows_reason_and_sync_time() -> None:
    assert "macro-table-empty" in MACRO
    assert "macro-empty-state" in MACRO
    assert "当前没有可展示的宏观事件" in MACRO
    assert "macroLastSyncedAt" in MACRO


def test_all_chart_canvases_have_accessible_names() -> None:
    missing = []
    for js in sorted(PAGES.rglob("*.js")):
        text = js.read_text(encoding="utf-8")
        # strip line comments so prose like "no longer rendered as a
        # <canvas>" is not mistaken for markup
        code = re.sub(r"//[^\n]*", "", text)
        for m in re.finditer(r"<canvas\b[^>]*>", code):
            tag = m.group(0)
            if "aria-label" not in tag and "aria-labelledby" not in tag:
                missing.append(f"{js.name}: {tag[:50]}")
    # The dynamic restore path in analysis.js maps every id to a label,
    # and btc/gold templates label through variables — those literals
    # contain aria-label, so any remaining bare tags are regressions.
    assert not missing, f"canvases without accessible names: {missing}"


def test_handbook_sidebar_breakpoint_matches_code() -> None:
    # code truth: editorial.css collapses the sidebar at 1180px
    assert "@media (max-width: 1180px)" in EDITORIAL
    # handbook must not claim the stale 1279px as the current rule
    assert "1279px 及以下切换为离屏抽屉" not in GUIDE
    assert "1180px 及以下切换为离屏抽屉" in GUIDE
