"""Regression tests for the maturity ladder's wall-cell visual weight.

The '标准到期日期限矩阵' table shows both effective walls (with a
price like '$60,000') and insufficient walls ('未形成有效墙'). Those
two states previously rendered with the same visual weight because
.btc-wall-cell had no styling. The fix introduces distinct sizes /
colors / borders so the user can scan the column and immediately tell
which rows have actionable levels.
"""
from __future__ import annotations

import re
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
STYLES = ROOT / "app" / "static" / "styles.css"


def _read() -> str:
    return STYLES.read_text(encoding="utf-8")


def _block(source: str, selector: str, length: int = 1200) -> str:
    """Return a slice starting at ``selector`` declaration."""
    idx = source.index(selector)
    return source[idx : idx + length]


def _font_size_px(block: str) -> float | None:
    match = re.search(r"font-size:\s*([\d.]+)px", block)
    if not match:
        return None
    return float(match.group(1))


def test_wall_cell_effective_and_insufficient_selectors_exist() -> None:
    source = _read()
    assert ".btc-wall-cell.is-effective" in source, (
        "styles.css must define a distinct .btc-wall-cell.is-effective "
        "block to give confirmed walls higher visual weight"
    )
    assert ".btc-wall-cell.is-insufficient" in source, (
        "styles.css must define a distinct .btc-wall-cell.is-insufficient "
        "block to demote '未形成有效墙' rows"
    )


def test_effective_value_font_size_larger_than_insufficient() -> None:
    """The confirmed-wall price ($60,000) must render with a strictly
    larger font than the '未形成有效墙' headline. Without this the two
    states visually compete and the user can't tell which is the real
    signal."""
    source = _read()
    effective_block = _block(source, ".btc-wall-cell.is-effective")
    insufficient_block = _block(source, ".btc-wall-cell.is-insufficient")
    # The headline value is inside <b>; the insufficient equivalent is
    # also <b>. We pick the first font-size on each selector block to
    # anchor the comparison.
    eff_size = _font_size_px(effective_block)
    ins_size = _font_size_px(insufficient_block)
    assert eff_size is not None and ins_size is not None, (
        f"both wall-cell states must declare a font-size; got "
        f"effective={eff_size}, insufficient={ins_size}"
    )
    assert eff_size - ins_size >= 2.0, (
        f"effective wall font-size ({eff_size}px) must be at least 2px "
        f"larger than insufficient ({ins_size}px) to differentiate the "
        f"two states visually"
    )


def test_insufficient_cell_is_visually_demoted() -> None:
    """The '未形成有效墙' cell must carry a visual demotion signal:
    lower opacity OR muted color OR dashed border. Without one of these
    the cell reads as confidently as the effective wall."""
    source = _read()
    insufficient_block = _block(source, ".btc-wall-cell.is-insufficient")
    has_opacity = re.search(r"opacity:\s*0?\.[0-8]\d", insufficient_block) is not None
    has_dashed = "dashed" in insufficient_block
    has_muted_color = (
        "var(--muted)" in insufficient_block
        or re.search(r"color:\s*#[0-9a-fA-F]{6}", insufficient_block) is not None
    )
    assert has_opacity or has_dashed or has_muted_color, (
        "the insufficient wall cell must carry at least one demotion "
        "signal (opacity < 1, dashed border, or muted color)"
    )