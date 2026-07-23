"""Static-source tests for the AI strategy stale-plan helpers.

`app/static/pages/strategy/formatHelpers.js` exposes
``formatEntryDistance(source)`` and ``staleToneFor(source)`` which the
``triggerText`` path consults once the backend fills
``plan_distance_pct`` / ``plan_stale_score`` / ``plan_stale_reason``.

We don't run JS in pytest, so this test asserts the source contains
the contract: the stale-tile label, the warning / stale styling
hooks, and the trigger row that surfaces the distance string.
"""

from __future__ import annotations

import re
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
FORMAT_HELPERS = ROOT / "app" / "static" / "pages" / "strategy" / "formatHelpers.js"
EXECUTION_PLAN = ROOT / "app" / "static" / "pages" / "strategy" / "renderExecutionPlan.js"
HERO = ROOT / "app" / "static" / "pages" / "strategy" / "renderOverview.js"
STYLES = ROOT / "app" / "static" / "styles.css"


def _read(path: Path) -> str:
    return path.read_text(encoding="utf-8")


def test_format_helpers_exposes_distance_and_stale_helpers():
    text = _read(FORMAT_HELPERS)
    assert "export function formatEntryDistance" in text
    assert "export function staleToneFor" in text
    # The warning / stale thresholds must match the backend buckets.
    assert "pct >= 3" in text
    assert "1.5" in text


def test_trigger_row_includes_distance_after_validity_text():
    """The trigger row needs to weave the distance string into the
    activation / validity / next-check narrative. The user-visible
    order is the array literal in the return statement:
    ``[conditions, validText, distanceText, nextText]``.
    """
    text = _read(EXECUTION_PLAN)
    # All three helpers must be invoked.
    for helper in ("formatValidUntil", "formatEntryDistance", "formatNextCheck"):
        assert helper in text, f"missing helper call: {helper}"
    # Find the return-array literal and check ordering inside it.
    array = re.search(r"return\s*\[\.\.\.conditions,\s*(\w+),\s*(\w+),\s*(\w+)\]", text)
    assert array is not None, "trigger return literal not found"
    a, b, c = array.groups()
    assert (a, b, c) == ("validText", "distanceText", "nextText"), (a, b, c)


def test_hero_pill_replaces_leverage_when_plan_is_stale():
    text = _read(HERO)
    # When order_type is CONDITIONAL_LIMIT and distance_pct > 0 the
    # 建议杠杆 tile is swapped for a stale-plan tile.
    assert 'order_type === "CONDITIONAL_LIMIT"' in text
    assert "showStaleChip" in text
    assert '策略-v2-metric-stale' in text or "strategy-v2-metric-stale" in text


def test_styles_add_warning_and_stale_tones_for_stale_tile():
    text = _read(STYLES)
    # Warning tone = amber (1.5%–3% drift).
    assert ".strategy-v2-metric-stale[data-tone=\"warning\"]" in text
    # Stale tone = red (≥ 3% drift).
    assert ".strategy-v2-metric-stale[data-tone=\"stale\"]" in text