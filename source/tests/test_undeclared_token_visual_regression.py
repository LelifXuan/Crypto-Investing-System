"""Static guard for the 10 undeclared-but-consumed CSS tokens.

Background:
    The 2026-07-31 UI/UX audit (docs/UI_UX_AUDIT_2026-07-31.md §6.1) found
    that 10 CSS variables were referenced inside app/static/styles.css but
    not declared in the :root block. CSS `var()` of an undefined token
    invalidates the entire declaration at consumption sites (e.g. an entire
    border shorthand becomes invalid -> border disappears). The fix landed
    in styles.css:81-90 (commit-by-commit, [config] styles.css: declare 9
    undeclared-but-consumed token aliases).

This test guards against silent regression by enumerating the 10 tokens
and asserting each one is declared exactly once inside :root.

It is intentionally *static* — it does not depend on Playwright or a
running backend. It catches only the structural regression; visual
verification remains with `tests/verify_pages.py` and the visual evidence
matrix in the audit document §13.
"""
from __future__ import annotations

import re
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
STYLES = ROOT / "app" / "static" / "styles.css"

# 10 tokens added by the audit fix (see audit 2026-07-31 §6.1 + A.1 commit).
# The audit also lists `--surface-muted`, but that one was already declared
# in the original :root block (styles.css:10), so it is checked separately
# to lock the alias was not removed by mistake.
#
# 2026-08-13: values aligned with the indigo accent re-theme (`--accent` now
# `#6366f1`); `--card-bg` is consumed again by the restored alert-chip styles.
EXPECTED_ALIASES = {
    "--line": "var(--border)",
    "--text": "var(--ink)",
    "--bg-surface": "var(--panel-strong)",
    "--bg-hover": "rgba(99, 102, 241, 0.10)",
    "--danger-strong": "#7a4630",
    "--info-strong": "#1d4ed8",
    "--border-light": "rgba(160, 140, 108, 0.14)",
    "--line-soft": "rgba(160, 140, 108, 0.10)",
    "--card-bg": "var(--surface-elevated)",
    "--ink-muted": "#5e6a78",
}

PREEXISTING_ALIASES = {
    "--surface-muted": "rgba(238, 241, 236, 0.82)",
}


def _root_block(source: str) -> str:
    """Return the first :root { ... } block, balanced."""
    match = re.search(r":root\s*\{", source)
    assert match, ":root block missing"
    start = match.end()
    depth = 1
    i = start
    while i < len(source) and depth > 0:
        c = source[i]
        if c == "{":
            depth += 1
        elif c == "}":
            depth -= 1
        i += 1
    assert depth == 0, ":root block unbalanced"
    return source[start : i - 1]


def _declaration_in(block: str, name: str) -> str | None:
    pattern = re.compile(rf"{re.escape(name)}\s*:\s*([^;]+?);")
    match = pattern.search(block)
    return match.group(1).strip() if match else None


def _consumers_outside_root(source: str, name: str) -> list[tuple[int, int]]:
    """Find each `var(<name>)` consumer and return (line_no, col)."""
    var_pattern = re.compile(rf"var\(\s*{re.escape(name)}\s*[,)]")
    consumers: list[tuple[int, int]] = []
    # Skip past the closing brace of the first :root block (the same approach
    # used by `_root_block`), then scan the remaining source.
    root_match = re.search(r":root\s*\{", source)
    assert root_match
    scan_start = root_match.end()
    depth = 1
    i = scan_start
    while i < len(source) and depth > 0:
        if source[i] == "{":
            depth += 1
        elif source[i] == "}":
            depth -= 1
        i += 1
    scan_target = source[i:]
    for m in var_pattern.finditer(scan_target):
        absolute = i + m.start()
        line_no = source.count("\n", 0, absolute) + 1
        col = absolute - (source.rfind("\n", 0, absolute) + 1)
        consumers.append((line_no, col))
    return consumers


def test_styles_root_declares_all_audit_aliases():
    source = STYLES.read_text(encoding="utf-8", errors="replace")
    root = _root_block(source)
    missing: list[str] = []
    wrong_value: list[tuple[str, str, str]] = []
    for alias, expected_value in EXPECTED_ALIASES.items():
        actual = _declaration_in(root, alias)
        if actual is None:
            missing.append(alias)
        elif actual.replace(" ", "") != expected_value.replace(" ", ""):
            wrong_value.append((alias, expected_value, actual))
    assert not missing, f"Missing token declarations in :root: {missing}"
    assert not wrong_value, (
        "Token value drift in :root: "
        + ", ".join(f"{a} want={w!r} got={g!r}" for a, w, g in wrong_value)
    )


def test_styles_root_preserves_preexisting_surface_muted():
    source = STYLES.read_text(encoding="utf-8", errors="replace")
    root = _root_block(source)
    actual = _declaration_in(root, "--surface-muted")
    expected = PREEXISTING_ALIASES["--surface-muted"]
    assert actual is not None, "--surface-muted unexpectedly missing"
    assert actual.replace(" ", "") == expected.replace(" ", ""), (
        f"--surface-muted drifted: got {actual!r}"
    )


def test_audit_aliases_still_have_consumer_sites():
    """A regression where someone removes all `var(--line)` etc. consumers
    without removing the alias tokens is allowed by the previous tests but
    still represents loss of intent. This test enforces that every alias added
    in the audit fix still has at least one consumer outside the :root block.
    """
    source = STYLES.read_text(encoding="utf-8", errors="replace")
    no_consumer: list[str] = []
    for alias in EXPECTED_ALIASES:
        if not _consumers_outside_root(source, alias):
            no_consumer.append(alias)
    assert not no_consumer, (
        "Audit aliases without consumer sites (alias added but unused): "
        + ", ".join(no_consumer)
    )


if __name__ == "__main__":
    sys.exit(pytest.main([__file__, "-v"]))
