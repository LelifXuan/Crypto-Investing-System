"""Static guard for the unified governance ledger (§13.2 #3).

Background:
    2026-08-27 §13.2 #3 cleanup: the data-governance footer / panel
    previously lived as five near-duplicate CSS blocks
    (.gold-governance / .etf-governance / .btc-governance /
    .strategy-governance / .monitoring-governance) and matching JSX
    templates. They now share a single base + variant layer:

      • editorial.css owns .governance-ledger + .governance-ledger--{variant}
      • ui/governanceLedger.js exposes renderGovernanceLedger()
      • page JSX only renders items via the shared function; per-page
        hooks (.gold-governance class / #etf-governance id) are preserved
        explicitly as JS-routing hooks, not as CSS targets.

    This test enforces that contract.
"""
from __future__ import annotations

import re
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
EDITORIAL = ROOT / "app" / "static" / "editorial.css"
STYLES = ROOT / "app" / "static" / "styles.css"
GOVERNANCE_JS = ROOT / "app" / "static" / "ui" / "governanceLedger.js"

EXPECTED_VARIANTS = (
    "gold",
    "ashare_etf",
    "btc",
    "strategy",
    "monitoring",
)

# Per-page JSX renderGovernance entry points. Each must import
# renderGovernanceLedger from ui/governanceLedger.js.
PAGES_WITH_GOVERNANCE = (
    ROOT / "app" / "static" / "pages" / "gold_v5.js",
    ROOT / "app" / "static" / "pages" / "ashare_etf.js",
    ROOT / "app" / "static" / "pages" / "btc_derivatives.js",
    ROOT / "app" / "static" / "pages" / "strategy" / "adapter.js",
    ROOT / "app" / "static" / "pages" / "monitoring.js",
)


def _read(path: Path) -> str:
    return path.read_text(encoding="utf-8", errors="replace")


def test_editorial_owns_base_class() -> None:
    css = _read(EDITORIAL)
    # The §13.2 #3 base class must live in editorial.css (the post-token-
    # ownership single source of truth, see test_undeclared_token_visual_regression).
    assert ".governance-ledger {" in css, (
        "editorial.css missing .governance-ledger base class"
    )
    assert ".governance-ledger__head {" in css, "missing .governance-ledger__head"
    assert ".governance-ledger__grid {" in css, "missing .governance-ledger__grid"
    assert ".governance-ledger__item {" in css, "missing .governance-ledger__item"
    assert ".governance-ledger__dot {" in css, "missing .governance-ledger__dot"


def test_editorial_declares_every_variant_modifier() -> None:
    css = _read(EDITORIAL)
    missing = [
        v
        for v in EXPECTED_VARIANTS
        if f".governance-ledger--{v}" not in css
    ]
    assert not missing, f"editorial.css missing variant modifiers: {missing}"


def test_editorial_includes_state_to_tone_mapping() -> None:
    """Per-state dot tone overrides. `fresh` is the default so the base
    `.governance-ledger__dot` rule covers it; we only require explicit
    overrides for the remaining states. The selectors may combine
    multiple states (e.g. `[data-state="degraded"], [data-state="stale"]`)
    so we only check that the state token appears in a data-state
    attribute adjacent to `.governance-ledger__dot`."""
    css = _read(EDITORIAL)
    # `fresh` falls back to the base .governance-ledger__dot rule; verify
    # the base rule exists.
    assert re.search(
        r"\.governance-ledger__dot\s*\{[^}]*background:\s*var\(--info\)",
        css,
    ), "base .governance-ledger__dot must default to --info"
    for state in ("degraded", "stale", "missing", "unknown", "danger", "error"):
        pattern = re.compile(
            rf'data-state="{state}"[^}}]*\.governance-ledger__dot',
        )
        assert pattern.search(css), (
            f"editorial.css missing data-state=\"{state}\" dot mapping"
        )


def test_styles_drops_per_page_governance_selectors() -> None:
    """styles.css used to own .gold-governance / .etf-governance /
    .btc-governance / .strategy-governance / .monitoring-governance +
    a shared body[data-page] block. After §13.2 #3 the legacy blocks
    are gone; .strategy-governance-paths is an unrelated component and
    is allowed."""
    css = _read(STYLES)
    forbidden_selectors = (
        ".gold-governance {",
        ".gold-governance-head {",
        ".gold-governance-grid {",
        ".gold-governance-item {",
        ".gold-governance-label {",
        ".gold-governance-dot {",
        ".gold-governance-snapshot ",
        ".etf-governance {",
        ".etf-governance-head {",
        ".etf-governance-grid {",
        ".etf-governance-item {",
        ".etf-governance-label {",
        ".etf-governance-dot {",
        ".btc-governance {",
        ".btc-governance-head {",
        ".btc-governance-grid {",
        ".btc-governance-item {",
        ".btc-governance-label {",
        ".btc-governance-dot {",
        ".monitoring-governance {",
        ".monitoring-governance-head {",
        ".monitoring-governance-grid {",
        ".monitoring-governance-item {",
        ".monitoring-governance-label {",
        ".monitoring-governance-dot {",
    )
    leaked = [sel for sel in forbidden_selectors if sel in css]
    assert not leaked, f"styles.css still contains legacy governance selectors: {leaked}"


def test_styles_drops_shared_body_data_page_block() -> None:
    css = _read(STYLES)
    # The old styles.css block had: body[data-page="btc-derivatives"] .governance-ledger,
    # body[data-page="ashare-etf"] .governance-ledger { ... }. That block
    # is replaced by .governance-ledger--{variant} modifiers in editorial.css.
    assert 'body[data-page="btc-derivatives"] .governance-ledger,' not in css, (
        "styles.css still owns the shared body[data-page] governance ledger block; "
        "the base + variant layer in editorial.css is the single source of truth"
    )
    assert 'body[data-page="ashare-etf"] .governance-ledger,' not in css, (
        "styles.css still owns the shared body[data-page] governance ledger block; "
        "the base + variant layer in editorial.css is the single source of truth"
    )


def test_governance_js_exposes_render_api() -> None:
    src = _read(GOVERNANCE_JS)
    for marker in (
        "export const GOVERNANCE_VARIANTS",
        "export function renderGovernanceItem(",
        "export function renderGovernanceLedger(",
        "export function defaultToneForState(",
    ):
        assert marker in src, f"governanceLedger.js missing export: {marker}"


def test_governance_js_lists_every_variant_in_config() -> None:
    src = _read(GOVERNANCE_JS)
    missing = [
        v
        for v in EXPECTED_VARIANTS
        if not re.search(rf'^\s*{v}\s*:\s*\{{', src, re.MULTILINE)
    ]
    assert not missing, f"GOVERNANCE_VARIANTS missing entries: {missing}"


def test_pages_route_through_render_governance_ledger() -> None:
    """Each page that previously owned a renderGovernance* function must
    now import renderGovernanceLedger from ui/governanceLedger.js and
    delegate to it. We assert the import + the literal call."""
    for path in PAGES_WITH_GOVERNANCE:
        src = _read(path)
        rel = path.relative_to(ROOT).as_posix()
        assert "renderGovernanceLedger" in src, (
            f"{rel} does not import or call renderGovernanceLedger — items must "
            "go through ui/governanceLedger.js"
        )


def test_pages_do_not_inline_full_section_template() -> None:
    """No page should still render `<section class=\"card governance-ledger` by
    hand. The base class lives in editorial.css and the JSX lives in
    ui/governanceLedger.js. Inline templates were the duplication source.
    """
    for path in PAGES_WITH_GOVERNANCE:
        src = _read(path)
        rel = path.relative_to(ROOT).as_posix()
        assert '<section class="card governance-ledger' not in src, (
            f"{rel} still inlines a <section class=\"card governance-ledger ...> "
            "template; route through renderGovernanceLedger()"
        )


if __name__ == "__main__":
    sys.exit(__import__("pytest").main([__file__, "-v"]))