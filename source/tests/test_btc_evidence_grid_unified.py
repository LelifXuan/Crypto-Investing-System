"""Regression tests for the BTC evidence two-row unified grid.

The BTC derivatives page used to render '衍生品状态' (4 short tiles)
and '推理' (4 dense tiles) as two separate grids. With the second row
being much taller than the first, the page showed a large empty band
between the two sections. The fix unifies both into a single
`.btc-evidence-grid` (4 columns × 2 rows, equal height).
"""

from __future__ import annotations

from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
PAGE = ROOT / "app" / "static" / "pages" / "btc_derivatives.js"
STYLES = ROOT / "app" / "static" / "styles.css"


def _read(path: Path) -> str:
    return path.read_text(encoding="utf-8")


def test_workbench_removes_persistent_indicator_rail_and_keeps_inference_audit_grid() -> None:
    source = _read(PAGE)
    shell_start = source.index('<div class="btc-derivatives-page">')
    shell = source[shell_start : shell_start + 1800]
    assert "renderWorkbenchEvidenceRail()" not in shell
    assert 'id="btc-open-summary-evidence"' in source
    assert 'firstChartInspection("leverage_pressure_timeline")' in source

    # The supporting audit section remains below and keeps the inference
    # blocks for users who need the full audit trail.
    grid_start = source.index('class="btc-evidence-grid"')
    grid_block = source[grid_start : grid_start + 600]
    assert "inferenceTiles" in grid_block, "the supporting audit grid must retain inference blocks"
    assert "indicatorTiles" not in grid_block
    inference_src = source[
        source.index("const inferenceTiles") : source.index("const inferenceTiles") + 400
    ]
    assert "blocks" in inference_src and "map" in inference_src, (
        "inferenceTiles must be populated from the inference blocks array"
    )
    # And the upstream `blocks` must come from analysis.inference_blocks.
    upstream = source[source.index("const blocks") : source.index("const blocks") + 100]
    assert "inference_blocks" in upstream, (
        "the blocks local var must be sourced from analysis.inference_blocks"
    )


def test_indicator_judgement_rail_and_internal_fields_are_not_rendered() -> None:
    source = _read(PAGE)
    assert "function renderIndicatorJudgements" not in source
    assert "function renderWorkbenchEvidenceRail" not in source
    assert "btc-evidence-source-detail" not in source
    assert "<dt>指标键</dt>" not in source


def test_unified_grid_is_equal_height() -> None:
    styles = _read(STYLES)
    assert ".btc-evidence-grid" in styles, "styles.css must define .btc-evidence-grid"
    block = styles[styles.index(".btc-evidence-grid") : styles.index(".btc-evidence-grid") + 800]
    assert "grid-auto-rows: 1fr" in block, (
        ".btc-evidence-grid must use grid-auto-rows: 1fr so all 8 tiles "
        "in the two rows are equal height and the empty band disappears"
    )
    assert "repeat(4" in block, (
        ".btc-evidence-grid must be a fixed 4-col grid (not auto-fit) so "
        "row 1 lines up with row 2 visually"
    )


def test_unified_tile_style_defined() -> None:
    styles = _read(STYLES)
    assert ".btc-evidence-tile" in styles, (
        "styles.css must define the shared .btc-evidence-tile used by "
        "both indicator and inference sub-cards"
    )
