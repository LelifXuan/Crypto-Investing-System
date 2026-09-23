"""Regression tests for referenceLines x-resolution and label collision avoidance.

Two defects in the shared ``referenceLines`` chart plugin (app/static/ui/charts.js):

1. Every vertical annotation anchored its label at ``chartArea.top + 12``, so
   two walls on nearby strikes printed on top of each other. On the
   btc-derivatives 行权价表面 (strike_surface) chart Max Pain ($79k) and Call
   Wall ($80k) measured x∈[391,435] and x∈[412,454] at the same baseline — 23px
   of overlap, rendering as one unreadable string.

2. An annotation whose value was not exactly equal to an x label was silently
   dropped. The strike grid is "62000.0", "64000.0", … while spot is 86010.14,
   so the "Spot" line never rendered at all; the walls did only because walls
   are reported at strikes by definition.

Both helpers are pure (fake ctx / fake scale in, pixel or baseline out), so
these tests execute the real shipped implementation under node instead of
asserting against a copy of it.
"""
from __future__ import annotations

import json
import shutil
import subprocess
from pathlib import Path

import pytest

ROOT = Path(__file__).resolve().parents[1]
CHARTS = ROOT / "app" / "static" / "ui" / "charts.js"

# Both helpers sit between these two markers in charts.js.
_HELPERS_START = "function resolveReferenceLineX"
_HELPERS_END = "const referenceLines"

# A strike grid shaped like the live one: ".0"-suffixed prices, irregular gaps,
# and the real wall values (75000 / 79000 / 80000) plus the strikes that
# bracket spot (86000 / 88000).
STRIKE_LABELS = [
    "62000.0", "64000.0", "66000.0", "70000.0", "72000.0", "74000.0",
    "75000.0", "76000.0", "78000.0", "79000.0", "80000.0", "82000.0",
    "84000.0", "86000.0", "88000.0", "90000.0", "92000.0", "94000.0",
    "96000.0", "98000.0", "100000.0", "102000.0", "104000.0", "106000.0",
    "108000.0", "110000.0",
]


def _read() -> str:
    return CHARTS.read_text(encoding="utf-8")


def _helpers_source() -> str:
    src = _read()
    start = src.index(_HELPERS_START)
    end = src.index(_HELPERS_END, start)
    assert start < end, "the referenceLines helpers must precede the plugin"
    return src[start:end]


@pytest.fixture(scope="module")
def node_available() -> None:
    """Skip rather than fail where node is unavailable — these assertions
    execute the shipped helpers."""
    if shutil.which("node") is None:
        pytest.skip("node not available; cannot execute the chart helpers")


def _run_node(body: str) -> object:
    result = subprocess.run(
        ["node", "-e", _helpers_source() + body],
        capture_output=True,
        text=True,
        timeout=30,
        check=False,
    )
    assert result.returncode == 0, f"node failed: {result.stderr}"
    return json.loads(result.stdout.strip())


def _run_layout(cases: list[tuple[str, int, int]]) -> list[int]:
    """Place each (text, left, baseY) in order, returning the baselines drawn."""
    return _run_node(
        """
const ctx = { measureText: (t) => ({ width: String(t).length * 6 }) };
const placed = [];
const cases = %s;
console.log(JSON.stringify(cases.map(([text, left, baseY]) =>
  reserveReferenceLabelY(ctx, text, left, baseY, placed))));
"""
        % json.dumps(cases)
    )


def _run_resolver(values: list[object], labels: list[str] | None = None) -> list[object]:
    """Resolve each annotation value against STRIKE_LABELS via a stub scale
    where index i maps to pixel 100 + 10i."""
    return _run_node(
        """
const labels = %s;
const chart = { data: { labels } };
const xScale = { getPixelForValue: (i) => 100 + i * 10 };
const values = %s;
console.log(JSON.stringify(values.map((v) => resolveReferenceLineX(chart, xScale, v))));
"""
        % (json.dumps(labels if labels is not None else STRIKE_LABELS), json.dumps(values))
    )


class TestReferenceLabelCollision:
    def test_overlapping_labels_get_distinct_baselines(self, node_available):
        """The live strike_surface geometry: Call Wall and Max Pain overlap by
        23px, Put Wall is clear. Only the colliding one may move."""
        baselines = _run_layout(
            [
                ("Call Wall", 412, 50),
                ("Put Wall", 308, 50),
                ("Max Pain", 391, 50),
            ]
        )
        call_wall, put_wall, max_pain = baselines
        assert call_wall == 50, "the first label keeps the base row"
        assert put_wall == 50, "a non-overlapping label must not be displaced"
        assert max_pain != call_wall, (
            "Max Pain overlaps Call Wall horizontally and must be staggered"
        )
        assert max_pain - call_wall >= 12, (
            "the stagger must clear a whole 10px text line, not nudge by a few px"
        )

    def test_clear_labels_are_left_alone(self, node_available):
        """Widely spaced walls keep every label on the base row."""
        baselines = _run_layout(
            [
                ("Spot", 100, 50),
                ("Put Wall", 300, 50),
                ("Call Wall", 600, 50),
            ]
        )
        assert baselines == [50, 50, 50]

    def test_rows_are_capped_so_labels_stay_in_the_plot(self, node_available):
        """Six mutually overlapping labels must not march off the chart: the
        row cap bounds how far the baseline can drift."""
        baselines = _run_layout([("Wall", 400, 50)] * 6)
        assert baselines[0] == 50
        assert max(baselines) <= 50 + 12 * 4, (
            "baseline drift must stay within the row cap"
        )
        assert baselines == sorted(baselines), "labels fill rows top-down in order"


class TestReferenceLineXResolution:
    def test_literal_label_match_wins(self, node_available):
        """Date-labelled axes resolve by exact string equality (the original
        NaN===NaN fix must not regress)."""
        dates = ["2026-09-15T16:48:28+00:00", "2026-09-16T16:48:28+00:00"]
        pixels = _run_resolver([dates[1], "2026-09-15T16:48:28+00:00"], labels=dates)
        assert pixels == [110, 100]

    def test_wall_price_on_a_strike_resolves_to_that_strike(self, node_available):
        """Walls are reported at strikes, so they must keep landing exactly on
        their label (75000 is index 6, 80000 is index 10)."""
        assert _run_resolver([75000, 80000, 79000]) == [160, 200, 190]

    def test_off_grid_value_interpolates_between_bracketing_strikes(self, node_available):
        """The reported bug: spot 86010.14 sits between the 86000 (index 13) and
        88000 (index 14) strikes and used to be dropped entirely."""
        (pixel,) = _run_resolver([86010.14])
        low, high = 100 + 13 * 10, 100 + 14 * 10
        assert low < pixel < high, (
            f"spot must fall between the bracket strikes, got {pixel}"
        )
        assert pixel == pytest.approx(100 + (13 + 10.14 / 2000) * 10, abs=0.01)

    def test_value_outside_the_labelled_range_is_dropped(self, node_available):
        """Clamping to an edge would draw a level that does not exist."""
        assert _run_resolver([115000, 61000]) == [None, None]

    def test_unparseable_value_is_dropped(self, node_available):
        assert _run_resolver(["2026-09-15", None]) == [None, None]


class TestReferenceLinesWiring:
    def test_plugin_resolves_vertical_x_through_the_resolver(self):
        src = _read()
        plugin = src[src.index("const referenceLines"):src.index("const expiryAnchors")]
        assert "resolveReferenceLineX(chart, xScale, annotation.x)" in plugin, (
            "vertical annotations must go through resolveReferenceLineX"
        )

    def test_plugin_routes_labels_through_the_reservation_helper(self):
        """A refactor that drops the helper would silently restore the overlap."""
        src = _read()
        plugin = src[src.index("const referenceLines"):src.index("const expiryAnchors")]
        assert "reserveReferenceLabelY(" in plugin, (
            "referenceLines must place its labels via reserveReferenceLabelY"
        )

    def test_occupied_boxes_are_reset_per_draw(self):
        """Hoisting `placed` to module scope would leak occupied rows across
        every redraw and every chart on the page, pushing labels steadily down."""
        src = _read()
        plugin = src[src.index("const referenceLines"):src.index("const expiryAnchors")]
        body = plugin[: plugin.index("config.annotations")]
        assert "const placedLabels = []" in body, (
            "the occupied-box list must be allocated inside afterDatasetsDraw"
        )

    def test_measurement_font_matches_the_draw_font(self):
        """Collision uses ctx.measureText, so the font set before measuring
        must be the same constant future edits change."""
        src = _read()
        plugin = src[src.index("const referenceLines"):src.index("const expiryAnchors")]
        assert "ctx.font = REFERENCE_LABEL_FONT" in plugin, (
            "referenceLines must set ctx.font from REFERENCE_LABEL_FONT before "
            "measuring, otherwise the measured widths do not match the drawn text"
        )
        assert "600 10px IBM Plex Sans" not in plugin, (
            "the label font must have a single source of truth, not a second literal"
        )
