"""Static guards for the mobile strategy scan layout (ui-audit 2026-09-04 P1#1).

Audit findings being pinned:
- 390px two-column flex left matrix cells ~41px wide with "等待确认"
  wrapping character-by-character (guideline §7.8 / §11).
- The empty ranked panel stretched to half the screen height.
"""

from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
EDITORIAL = (ROOT / "app/static/editorial.css").read_text(encoding="utf-8")
AI_BLOCK_START = "Opportunity scanner uses the remaining viewport"
MOBILE_MARKER = "ui-audit P1#1"


def test_strategy_scan_grid_collapses_to_one_column_below_900px() -> None:
    assert MOBILE_MARKER in EDITORIAL, "P1#1 mobile block marker missing"
    block = EDITORIAL[EDITORIAL.index(MOBILE_MARKER) - 200:EDITORIAL.index(MOBILE_MARKER) + 2000]
    assert "@media (max-width: 900px)" in block
    assert "flex-direction: column" in block
    assert ".strategy-scan-grid" in block


def test_matrix_table_keeps_screen_font_and_local_scroll() -> None:
    idx = EDITORIAL.index(MOBILE_MARKER)
    block = EDITORIAL[idx:idx + 2000]
    # readable minimum column budget via min-width; scroll happens in table-wrap
    assert ".scan-matrix-table" in block
    assert "min-width: 560px" in block
    assert "#strategy-scan-matrix .table-wrap" in block
    assert "overflow-x: auto" in block


def test_ranked_panel_uses_content_height_not_half_screen() -> None:
    idx = EDITORIAL.index(MOBILE_MARKER)
    block = EDITORIAL[idx:idx + 2000]
    assert "#strategy-scan-ranked-section" in block
    assert "max-height: 60vh" in block
