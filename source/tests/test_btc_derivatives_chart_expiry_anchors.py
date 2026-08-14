"""Regression tests for the wall-migration chart's standard-expiry overlay.

The '关键行权价迁移' chart (key_levels_history) currently shows 4
historical series (Spot / Call Wall / Put Wall / Max Pain). Users want
each row of the '标准到期日期限矩阵' (maturity_ladder) to also appear as
a vertical expiry marker on the same chart — so the table's 6 expiry
columns and the chart's historical lines can be read against each
other in a single view.

We assert the renderer source exposes:
  1. An expiry-anchor plugin/function (drawing dots + vertical lines).
  2. The plugin reads `maturity_ladder` rows from the dashboard payload.
  3. The chart config for `key_levels_history` includes the overlay.
"""
from __future__ import annotations

from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
BTCD = ROOT / "app" / "static" / "pages" / "btc_derivatives.js"
CHARTS = ROOT / "app" / "static" / "ui" / "charts.js"


def _read(p: Path) -> str:
    return p.read_text(encoding="utf-8")


def test_expiry_anchor_plugin_defined() -> None:
    """The expiry-anchor plugin must exist in either btc_derivatives.js
    or charts.js — both files are acceptable since either side can own
    the canvas annotation."""
    src = _read(BTCD) + _read(CHARTS)
    assert "expiryAnchors" in src or "renderExpiryAnchors" in src, (
        "an expiry-anchor plugin/function must exist for the wall-migration "
        "chart to overlay standard expiry markers"
    )


def test_plugin_reads_maturity_ladder() -> None:
    """The plugin must read from `maturity_ladder` rows."""
    src = _read(BTCD)
    assert "maturity_ladder" in src, (
        "btc_derivatives.js must reference dashboard.options.maturity_ladder "
        "to drive the wall-migration overlay"
    )


def test_wall_migration_chart_config_uses_overlay() -> None:
    """The key_levels_history chart config must wire the overlay in
    (either via plugin registration or by passing anchors into the
    chart config)."""
    src = _read(BTCD) + _read(CHARTS)
    # either by inline plugin registration next to the chart config,
    # or by passing anchors via chart.options.plugins.expiryAnchors
    found = (
        "expiryAnchors" in src
        and ("key_levels_history" in src or "wall-migration" in src or "wallMigration" in src)
    )
    assert found, (
        "key_levels_history chart config must include expiryAnchors "
        "(either as a registered plugin or via chart options)"
    )