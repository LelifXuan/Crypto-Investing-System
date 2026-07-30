"""Guard: no native <select markup remaining in page JS modules."""
from pathlib import Path

import pytest

TARGET_FILES = [
    "app/static/pages/analysis.js",
    "app/static/pages/ashare_etf.js",
    "app/static/pages/btc_derivatives.js",
    "app/static/pages/knowledge.js",
    "app/static/pages/market_events.js",
    "app/static/pages/structure.js",
]


@pytest.mark.parametrize("rel_path", TARGET_FILES)
def test_no_native_select_markup(rel_path):
    p = Path(rel_path)
    assert p.exists(), f"missing page module: {rel_path}"
    src = p.read_text(encoding="utf-8")
    # strip JS line comments (// ...) to avoid false positives in commented-out code
    cleaned = "\n".join(
        ln for ln in src.splitlines() if not ln.lstrip().startswith("//")
    )
    assert "<select " not in cleaned and "<select>" not in cleaned, (
        f"{rel_path} still uses native <select>; replace with "
        '<button class="dropdown"> + mountDropdown'
    )


@pytest.mark.parametrize("rel_path", TARGET_FILES)
def test_each_page_calls_mount_dropdown(rel_path):
    p = Path(rel_path)
    assert p.exists(), f"missing page module: {rel_path}"
    src = p.read_text(encoding="utf-8")
    assert "mountDropdown" in src, f"{rel_path} must import and call mountDropdown"