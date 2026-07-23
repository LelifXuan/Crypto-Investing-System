"""Tests that the user-facing time labels no longer carry '北京时间'.

The dashboard's default time zone is Beijing time (CST / Asia/Shanghai),
so the explicit suffix '北京时间' is redundant noise — it duplicates
information the user already knows. After the cleanup:

* `formatDateTime(...)` (app/static/core/dom.js)
* `formatStrategyDateTime(...)` (app/static/pages/strategy/formatHelpers.js)
* chart axis time formatters (app/static/ui/charts.js)

must produce 'YYYY/MM/DD hh:mm' and 'YYYY-MM-DD hh:mm' strings **without**
the '北京时间' suffix. The change is cosmetic but matters: a Chinese
trader reading '14:55' on a dashboard titled "BTC 衍生品" already knows
it's Beijing time; the suffix is noise.

The reverse direction — making the suffix mandatory when the default
zone ever stops being Beijing — is left for the future. For now we only
lock down the strip.
"""

from __future__ import annotations

from pathlib import Path

import pytest

REPO = Path(__file__).resolve().parents[1]


def _read(path: Path) -> str:
    return path.read_text(encoding="utf-8")


SOURCE_FILES = [
    REPO / "app" / "static" / "core" / "dom.js",
    REPO / "app" / "static" / "pages" / "strategy" / "formatHelpers.js",
    REPO / "app" / "static" / "ui" / "charts.js",
]


@pytest.mark.parametrize("path", SOURCE_FILES, ids=lambda p: p.name)
def test_source_files_do_not_emit_beijing_time_suffix(path: Path) -> None:
    """None of the user-facing time formatters may emit the literal string
    '北京时间'. The literal suffix was deliberately dropped because the
    dashboard's default zone is already Beijing time."""
    content = _read(path)
    assert "北京时间" not in content, (
        f"{path.name} still emits the redundant '北京时间' suffix. The "
        f"dashboard's default zone is already Beijing time, so the suffix "
        f"is noise. Remove the ' 北京时间' tail from the template string."
    )


def test_formatDateTime_renders_without_beijing_time_suffix() -> None:
    """formatDateTime is the canonical user-facing timestamp formatter used
    across the dashboard. After the cleanup it returns 'YYYY/MM/DD hh:mm'
    with no suffix."""
    import json
    import subprocess

    result = subprocess.run(
        ["node", "--input-type=module", "-e",
         "import { formatDateTime } from 'file:///E:/Personal/Research/Crypto "
         "Investing System/app/static/core/dom.js';"
         # jsdom-free: feed a valid ISO string and a Date.
         "const s = formatDateTime('2026-07-23T14:55:00+08:00'); "
         "console.log(JSON.stringify({ s }));"],
        check=True, capture_output=True, text=True, encoding="utf-8",
    )
    payload = json.loads(result.stdout)
    assert "北京时间" not in payload["s"], (
        f"formatDateTime now returns {payload['s']!r}; the '北京时间' suffix "
        "must be stripped"
    )
    # Format must still be correct so callers downstream still parse it.
    assert payload["s"].startswith("2026/"), (
        f"formatDateTime should still render 'YYYY/MM/DD hh:mm'; got {payload['s']!r}"
    )


def test_strategy_formatIsoShort_renders_without_beijing_time_suffix() -> None:
    """strategy/formatHelpers.js#formatIsoShort is the strategy-page
    formatter. It must drop '北京时间' too."""
    import json
    import subprocess

    result = subprocess.run(
        ["node", "--input-type=module", "-e",
         "import { formatIsoShort } from 'file:///E:/Personal/Research/Crypto "
         "Investing System/app/static/pages/strategy/formatHelpers.js';"
         "const s = formatIsoShort('2026-07-23T14:55:00+08:00'); "
         "console.log(JSON.stringify({ s }));"],
        check=True, capture_output=True, text=True, encoding="utf-8",
    )
    payload = json.loads(result.stdout)
    assert "北京时间" not in payload["s"], (
        f"formatIsoShort now returns {payload['s']!r}; the '北京时间' suffix "
        "must be stripped"
    )
    assert payload["s"].startswith("2026-"), (
        f"formatIsoShort should still render 'YYYY-MM-DD hh:mm'; got {payload['s']!r}"
    )


def test_charts_time_axis_renders_without_beijing_time_suffix() -> None:
    """app/static/ui/charts.js uses `北京时间` inside a chart axis time
    callback. The callback should keep the same data shape but drop the
    suffix so chart axes stay consistent with the rest of the UI."""
    content = _read(REPO / "app" / "static" / "ui" / "charts.js")
    assert "北京时间" not in content, (
        "charts.js time-axis callback still emits ' 北京时间'; the suffix "
        "should be stripped so chart axes match the rest of the UI"
    )