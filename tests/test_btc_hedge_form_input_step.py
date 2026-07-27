"""Regression tests for the hedge-planner form numeric inputs.

The '现价 USD' input is auto-populated from `hedge_context.spot_price`,
which is a float (e.g. 65226.17). HTML5 `<input type="number">` defaults
to step=1, so any fractional value triggered Chrome's
'请输入有效值。两个最接近的有效值分别为 N 和 M' validation message
even though the value is logically valid. The fix sets step='any' on
the spot_price input so the system-imported value passes HTML5
validation without the user having to manually align it to an integer.

The other numeric inputs (grid_lower / grid_upper / net_notional_usd /
hedge_budget_usd) default to integer literals in the markup, so they
do not need step='any'. This guard pins only the field that we know
needs the fix.
"""
from __future__ import annotations

from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
BTC_DERIVATIVES = ROOT / "app" / "static" / "pages" / "btc_derivatives.js"


def _read() -> str:
    return BTC_DERIVATIVES.read_text(encoding="utf-8")


def test_spot_price_input_has_step_any() -> None:
    source = _read()
    # Pull just the spot_price input line so the assertion does not get
    # confused by grid_lower / grid_upper.
    idx = source.index('name="spot_price"')
    line = source[idx : idx + 400]
    assert 'step="any"' in line, (
        "spot_price input must declare step='any' so an auto-imported "
        "float value (e.g. 65226.17) passes HTML5 validation without "
        "showing '请输入有效值。两个最接近的有效值分别为 ...' to the user"
    )