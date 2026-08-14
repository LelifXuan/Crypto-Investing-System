"""Regression tests for the maturity-ladder Max Pain cell styling.

The Max Pain column is the most-glanceable single number on the row.
Previously it inherited the table base font (14px), making it hard to
distinguish from the surrounding wall / metric cells. The fix bumps
the font one notch larger (16px / 700 weight) and tints it slightly
darker so the column reads as a primary signal.
"""
from __future__ import annotations

import re
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
BTC_DERIVATIVES = ROOT / "app" / "static" / "pages" / "btc_derivatives.js"
STYLES = ROOT / "app" / "static" / "styles.css"


def _read(path: Path) -> str:
    return path.read_text(encoding="utf-8")


def test_max_pain_cell_uses_dedicated_class() -> None:
    source = _read(BTC_DERIVATIVES)
    assert '<td class="btc-max-pain">' in source, (
        "Max Pain cell must use the dedicated .btc-max-pain class so it "
        "can be styled independently of the rest of the maturity table"
    )


def test_max_pain_cell_font_size_larger_than_base() -> None:
    source = _read(STYLES)
    # Find the .btc-maturity-table td.btc-max-pain rule.
    match = re.search(
        r"\.btc-maturity-table\s+td\.btc-max-pain\s*\{[^}]*font-size:\s*([\d.]+)px",
        source,
    )
    assert match, (
        "styles.css must define a .btc-maturity-table td.btc-max-pain "
        "rule with an explicit font-size"
    )
    max_pain_size = float(match.group(1))
    # Find the table base font-size on .btc-table.
    base_match = re.search(r"\.btc-table\s*\{[^}]*font-size:\s*([\d.]+)px", source)
    assert base_match, ".btc-table base rule must declare a font-size"
    base_size = float(base_match.group(1))
    assert max_pain_size - base_size >= 1.5, (
        f"Max Pain font-size ({max_pain_size}px) must be at least 1.5px "
        f"larger than the table base ({base_size}px) so the column "
        f"visually stands out"
    )