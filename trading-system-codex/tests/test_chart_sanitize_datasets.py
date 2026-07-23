"""Tests for chart dataset sanitisation.

`app/static/ui/charts.js` exposes a `sanitizeDatasets` helper that runs every
chart dataset through `sanitizeChartSeries` (and the candle normaliser) before
the dataset is handed to Chart.js. The backend writes the per-axis binding
under the field name ``y_axis_id`` (because the JSON schema is snake_case),
but Chart.js reads ``dataset.yAxisID`` at render time. Without the translation
in `sanitizeDatasets`, datasets silently fall back to the default ``y`` scale
and the dual-axis annotation lines end up overlapping the left axis.

These tests pin down the translation so the regression cannot come back.
"""

from __future__ import annotations

import json
import subprocess
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]


def _run_chart_module(script_body: str) -> dict:
    module_path = ROOT / "app/static/ui/charts.js"
    script = f"""
import {{
  sanitizeDatasets,
}} from 'file:///{module_path.as_posix()}';
{script_body}
"""
    result = subprocess.run(
        ["node", "--input-type=module", "-e", script],
        check=True,
        capture_output=True,
        text=True,
        encoding="utf-8",
    )
    return json.loads(result.stdout)


def test_sanitize_datasets_translates_y_axis_id_to_yaxisid() -> None:
    result = _run_chart_module(
        """
const datasets = [
  { label: "25D Skew", data: [0.05, null, 0.07], y_axis_id: "y_skew" },
  { label: "Put/Call OI", data: [1.0, 1.05, 0.98], y_axis_id: "y_ratio" },
];
const out = sanitizeDatasets(datasets);
console.log(JSON.stringify({
  skewYAxisId: out[0].yAxisID,
  skewLegacyField: out[0].y_axis_id,
  ratioYAxisId: out[1].yAxisID,
  ratioLegacyField: out[1].y_axis_id,
}));
"""
    )

    assert result["skewYAxisId"] == "y_skew", (
        f"expected yAxisID='y_skew' so Chart.js binds to the y_skew scale, "
        f"got {result['skewYAxisId']!r}"
    )
    assert result["ratioYAxisId"] == "y_ratio"
    # Keep the legacy snake_case field so any consumer still reading it
    # (e.g. older snapshots, other plugins) continues to work.
    assert result["skewLegacyField"] == "y_skew"
    assert result["ratioLegacyField"] == "y_ratio"


def test_sanitize_datasets_does_not_override_existing_yaxisid() -> None:
    """If a caller already supplied yAxisID, don't clobber it with y_axis_id."""
    result = _run_chart_module(
        """
const datasets = [
  { label: "X", data: [1, 2, 3], yAxisID: "y_right", y_axis_id: "y_left" },
];
const out = sanitizeDatasets(datasets);
console.log(JSON.stringify({ yAxisID: out[0].yAxisID, yAxisId: out[0].y_axis_id }));
"""
    )

    assert result["yAxisID"] == "y_right", (
        "pre-existing yAxisID should win over y_axis_id translation"
    )


def test_sanitize_datasets_passes_through_when_no_axis_id() -> None:
    """Datasets without an axis binding default to the Chart.js 'y' axis."""
    result = _run_chart_module(
        """
const datasets = [
  { label: "Default", data: [1, 2, 3] },
];
const out = sanitizeDatasets(datasets);
console.log(JSON.stringify({ yAxisID: out[0].yAxisID || null }));
"""
    )

    assert result["yAxisID"] is None, (
        f"datasets without axis binding should not have a synthetic yAxisID, "
        f"got {result['yAxisID']!r}"
    )