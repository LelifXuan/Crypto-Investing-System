"""Static guard for chart series token coverage (manual §13.2 #4).

Background:
    2026-08-27 §13.2 #4 cleanup: every chart series color must declare its
    value in editorial.css (:root) as a `--series-*` token, and the page
    JS must read it through `getSeriesColor(label)` in ui/charts.js
    instead of writing a literal hex into lineDataset / barDataset.

    This file locks the structural side of that contract:
      1. editorial.css declares every series token with a non-empty value.
      2. charts.js exposes SERIES_FALLBACK / CHART_SERIES / getSeriesColor
         / getPatternFill as the public surface.
      3. The four pages that previously hardcoded series colors
         (analysis / gold_v5 / structure / btc_derivatives) no longer carry
         per-line hex literals inside `lineDataset(...)` / `barDataset(...)`
         calls; they go through `getSeriesColor(label)`.

    Pages that intentionally keep hex literals (e.g. ashare_etf weekly
    contrast fills because the alpha 0.55 doesn't map to any --*-soft
    token) are excluded from the page-side check by file path.

    Audit reference: docs/design-guidelines.md §7.9 (charts) and §13.2 #4.
"""
from __future__ import annotations

import re
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
EDITORIAL = ROOT / "app" / "static" / "editorial.css"
CHARTS_JS = ROOT / "app" / "static" / "ui" / "charts.js"

# 2026-08-27: 21 series tokens declared in editorial.css :root. The
# fallback column mirrors SERIES_FALLBACK in ui/charts.js so a missing
# token falls back to the documented hex (preserves the visual baseline).
EXPECTED_SERIES_TOKENS = {
    "--series-price": "#2c3849",
    "--series-ema-short": "#dcb09a",
    "--series-ema-mid": "#a89569",
    "--series-ema-mid-alt": "#cba071",
    "--series-ema-long": "#6a8fa0",
    "--series-ema-long-deep": "#4d6485",
    "--series-ema-long-deepest": "#3a5170",
    "--series-vwap-light": "#d5c8e0",
    "--series-vwap-mid": "#a594c2",
    "--series-vwap-deep": "#5d4e7e",
    "--series-rsi": "#a896c8",
    "--series-funding": "#8a86b5",
    "--series-iv": "#9686b9",
    "--series-call-wall": "#8eb098",
    "--series-put-wall": "#c2725a",
    "--series-max-pain": "#5a6a7c",
    "--series-xaut": "#1f1b16",
    "--series-classic": "#b8924a",
    "--series-profile": "#9686b9",
    "--series-swing": "#2563eb",
    "--series-swing-live": "#3b82f6",
    "--series-fused": "#6a7587",
    "--series-pattern-neckline": "#e67e22",
    "--series-pattern-resistance": "#e74c3c",
    "--series-pattern-support": "#27ae60",
    "--series-pattern-zone": "#6366f1",
}

EXPECTED_PATTERN_FILL_TOKENS = {
    "--pattern-fill-bullish": "rgba(39, 174, 96, 0.12)",
    "--pattern-fill-bearish": "rgba(231, 76, 60, 0.12)",
    "--pattern-fill-neutral": "rgba(99, 102, 241, 0.12)",
    "--pattern-fill-mixed": "rgba(230, 126, 34, 0.12)",
}

# Pages that MUST go through getSeriesColor for series strokes.
PAGES_WITH_SERIES = [
    ROOT / "app" / "static" / "pages" / "analysis.js",
    ROOT / "app" / "static" / "pages" / "gold_v5.js",
    ROOT / "app" / "static" / "pages" / "structure.js",
    ROOT / "app" / "static" / "pages" / "btc_derivatives.js",
]


def _read(path: Path) -> str:
    return path.read_text(encoding="utf-8", errors="replace")


def _root_block(source: str) -> str:
    match = re.search(r":root\s*\{", source)
    assert match, ":root block missing in editorial.css"
    start = match.end()
    depth = 1
    i = start
    while i < len(source) and depth > 0:
        if source[i] == "{":
            depth += 1
        elif source[i] == "}":
            depth -= 1
        i += 1
    return source[start : i - 1]


def test_editorial_root_declares_every_series_token() -> None:
    css = _read(EDITORIAL)
    root = _root_block(css)
    missing: list[str] = []
    wrong_value: list[tuple[str, str, str]] = []
    for token, expected in {**EXPECTED_SERIES_TOKENS, **EXPECTED_PATTERN_FILL_TOKENS}.items():
        pattern = re.compile(rf"{re.escape(token)}\s*:\s*([^;]+);")
        m = pattern.search(root)
        if m is None:
            missing.append(token)
            continue
        actual = m.group(1).strip().replace(" ", "")
        expected_norm = expected.replace(" ", "")
        if actual != expected_norm:
            wrong_value.append((token, expected_norm, actual))
    assert not missing, f"editorial.css :root missing series tokens: {missing}"
    assert not wrong_value, (
        "Series token value drift in editorial.css: "
        + ", ".join(f"{a} want={w!r} got={g!r}" for a, w, g in wrong_value)
    )


def test_charts_js_exposes_series_api() -> None:
    src = _read(CHARTS_JS)
    # Frozen registry constants must be present.
    for marker in (
        "const SERIES_FALLBACK = Object.freeze(",
        "const CHART_SERIES = Object.freeze(",
        'export function getSeriesColor(',
        'export function getPatternFill(',
        "globalThis.__CHART_SERIES__",
    ):
        assert marker in src, f"charts.js missing series marker: {marker!r}"


def test_charts_js_fallBACK_covers_expected_labels() -> None:
    """Sanity: SERIES_FALLBACK must include the canonical label set so a
    fresh SSR / unit-test bootstrap resolves to the documented hex."""
    src = _read(CHARTS_JS)
    expected_labels = (
        "EMA12", "EMA30", "EMA60", "EMA120", "EMA200",
        "VWAP20", "VWAP50", "VWAP100",
        "RSI", "MACD",
        "Call OI", "Put OI", "Call Wall", "Put Wall", "Max Pain",
        "Funding", "IV", "Basis",
        "XAUT", "MA50", "SMA200",
        "swing", "neckline", "support", "resistance",
    )
    # SERIES_FALLBACK keys are valid JS identifiers when they don't contain
    # whitespace, so they appear unquoted (e.g. `EMA12:`). Multi-word keys
    # (e.g. "Call Wall") are quoted. Match both forms.
    missing = []
    for label in expected_labels:
        bare_match = re.search(rf"^\s*{re.escape(label)}\s*:", src, re.MULTILINE)
        quoted_match = re.search(rf'"{re.escape(label)}"\s*:', src)
        if bare_match is None and quoted_match is None:
            missing.append(label)
    assert not missing, f"SERIES_FALLBACK missing labels: {missing}"


def test_pages_route_through_get_series_color() -> None:
    """Pages that previously had hardcoded series colors must now resolve
    them through `getSeriesColor(label)`. We assert the import + use of
    the helper is in place; the legacy CHART_COLORS object must NOT be
    re-declared inside btc_derivatives.js (it lived there pre-cleanup).
    """
    for path in PAGES_WITH_SERIES:
        src = _read(path)
        rel = path.relative_to(ROOT).as_posix()
        # 1. Import must be present.
        assert "getSeriesColor" in src, (
            f"{rel} does not import or call getSeriesColor — series colors must "
            "route through ui/charts.js"
        )
        # 2. btc_derivatives specifically: legacy CHART_COLORS map is gone.
        if path.name == "btc_derivatives.js":
            assert "const CHART_COLORS = {" not in src, (
                f"{rel} still declares const CHART_COLORS = {{ ... }}; the 43-entry "
                "map was migrated into ui/charts.js SERIES_FALLBACK / CHART_SERIES"
            )


def test_pages_no_more_hex_literals_in_line_or_bar_dataset_calls() -> None:
    """After the §13.2 #4 cleanup, `lineDataset(...)` and `barDataset(...)`
    calls in pages/*.js must use getSeriesColor(...) — not literal hex.
    Three exemptions are allowed (see comments): analysis.js keeps the
    K-line up/down fills (themeColor-driven), gold_v5 keeps MACD柱 colors
    which use a per-element callback (also themeColor-driven), and
    ashare_etf is excluded by file scope because it already routes through
    _monetToken.

    We assert the count of inline hex strings inside `lineDataset(...)`
    and `barDataset(...)` calls in the four series pages is zero.
    """
    inline_hex_pattern = re.compile(
        r'(?:line|bar)Dataset\(\s*"[^"]*"\s*,\s*[^,]+,\s*"#[0-9a-fA-F]{3,8}"',
        re.MULTILINE,
    )
    for path in PAGES_WITH_SERIES:
        src = _read(path)
        matches = inline_hex_pattern.findall(src)
        assert not matches, (
            f"{path.relative_to(ROOT).as_posix()} still has hex inside line/barDataset: "
            f"{matches}"
        )


if __name__ == "__main__":
    sys.exit(__import__("pytest").main([__file__, "-v"]))