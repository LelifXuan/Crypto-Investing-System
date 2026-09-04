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


def test_workbench_uses_indicator_rail_and_keeps_inference_audit_grid() -> None:
    source = _read(PAGE)
    rail_start = source.index("function renderWorkbenchEvidenceRail")
    rail_block = source[rail_start : rail_start + 700]
    assert "renderIndicatorJudgements()" in rail_block
    assert 'class="btc-workbench-evidence-list"' in rail_block

    # UI 2.0 promotes indicator judgements beside the leverage timeline.
    # The supporting audit section remains below and keeps the inference
    # blocks without duplicating the promoted evidence.
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


def test_indicator_judgement_tile_uses_unified_class() -> None:
    source = _read(PAGE)
    block = source[
        source.index("function renderIndicatorJudgements") : source.index(
            "function renderIndicatorJudgements"
        )
        + 1500
    ]
    assert "btc-evidence-tile" in block, (
        "renderIndicatorJudgements must emit .btc-evidence-tile so the "
        "first row matches the inference row visually"
    )
    assert "btc-decision-card" not in block, (
        "renderIndicatorJudgements must drop the legacy .btc-decision-card wrapper"
    )


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
