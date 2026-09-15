"""Static guards for the U1-U5 UI audit P2 leftovers (2026-09-16).

U1: AI audit detail脱术语化 (model version + price_source + microsecond
    ISO 兜底 + renderEventWatch 旁路)
U2: 黄金成交量轴整数格式化 (charts.js volume profile value_format=integer)
U3+U5: 监控冷启动骨架补占位 + styles.css 重复声明合并 + gap 16px
U4: ETF 触屏命中区 ≥44×44 (coarse pointer 扩展 + .primary-action 默认规则)
"""

import re
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
STYLES = (ROOT / "app/static/styles.css").read_text(encoding="utf-8")
EDITORIAL = (ROOT / "app/static/editorial.css").read_text(encoding="utf-8")
DOM = (ROOT / "app/static/core/dom.js").read_text(encoding="utf-8")
CHARTS = (ROOT / "app/static/ui/charts.js").read_text(encoding="utf-8")
MONITORING = (ROOT / "app/static/pages/monitoring.js").read_text(encoding="utf-8")
AUDIT = (ROOT / "app/static/pages/strategy/renderDecisionAudit.js").read_text(encoding="utf-8")
EVENT_WATCH = (ROOT / "app/static/pages/strategy/renderEventWatch.js").read_text(encoding="utf-8")


# ---------------------------------------------------------------------------
# U1: AI 审计详情脱术语化
# ---------------------------------------------------------------------------

def test_u1_model_version_humanizer_defined() -> None:
    assert "humanizeModelVersion" in AUDIT, (
        "renderDecisionAudit.js must expose humanizeModelVersion() to translate "
        "implementation identifiers like 'legacy-cross-horizon-v2' for end users."
    )


def test_u1_price_source_humanizer_defined() -> None:
    assert "humanizePriceSource" in AUDIT, (
        "renderDecisionAudit.js must expose humanizePriceSource() to translate "
        "provider:detail tags like 'gateio:futures.contracts' for end users."
    )


def test_u1_audit_summary_uses_humanizers() -> None:
    summary_match = re.search(
        r'<div class="strategy-audit-summary">(.*?)</div>\s*<div class="strategy-audit-columns">',
        AUDIT,
        re.DOTALL,
    )
    assert summary_match, "strategy-audit-summary block missing"
    block = summary_match.group(1)
    assert "humanizeModelVersion(model.active_model_version)" in block
    assert "humanizeModelVersion(model.candidate_model_version)" in block
    assert "humanizePriceSource(model.price_source)" in block


def test_u1_no_raw_implementation_terms_leak_to_strong_tags() -> None:
    """The audit <strong> tags must never render raw implementation IDs."""
    summary_match = re.search(
        r'<div class="strategy-audit-summary">(.*?)</div>\s*<div class="strategy-audit-columns">',
        AUDIT,
        re.DOTALL,
    )
    block = summary_match.group(1)
    # The humanised text is allowed, the raw IDs are not.
    assert "legacy-cross-horizon-v2" not in block, (
        "Raw 'legacy-cross-horizon-v2' must not leak to the rendered audit <strong> tags."
    )
    assert "auditable-rules-v3-shadow" not in block, (
        "Raw 'auditable-rules-v3-shadow' must not leak to the rendered audit <strong> tags."
    )


def test_u1_format_datetime_strips_subsecond_precision() -> None:
    """formatDateTime must defensively strip .ffffff microseconds from ISO inputs."""
    body_match = re.search(
        r"export function formatDateTime\([^)]*\)\s*\{(.*?)return `",
        DOM,
        re.DOTALL,
    )
    assert body_match, "formatDateTime function body not located in dom.js"
    body = body_match.group(1)
    assert re.search(r"replace\(/\\\.\\d\+", body) or re.search(r"replace\(/\.", body), (
        "formatDateTime must include a sub-second strip (e.g. /\\.\\d+/) before "
        "parsing the date so microsecond ISO strings never reach the DOM."
    )


def test_u1_event_watch_always_formats_next_check_time() -> None:
    """renderEventWatch must call formatDateTime unconditionally for next_check_time."""
    # The old code routed non-'T' strings around formatDateTime. That branch is gone.
    assert "next_check_time" in EVENT_WATCH
    next_check_match = re.search(
        r"item\.next_check_time\s*\?\s*([^:]+?)\s*:",
        EVENT_WATCH,
    )
    assert next_check_match, "next_check_time branch not located"
    expr = next_check_match.group(1).strip()
    assert expr.startswith("formatDateTime("), (
        f"next_check_time must always flow through formatDateTime, got: {expr!r}"
    )


# ---------------------------------------------------------------------------
# U2: 黄金成交量轴整数格式化
# ---------------------------------------------------------------------------

def test_u2_volume_profile_uses_integer_format() -> None:
    """buildAdaptiveAxisOptions must return integer value_format for the volume profile."""
    # Match the volume branch body in buildAdaptiveAxisOptions
    match = re.search(
        r'if\s*\(profile\s*===\s*"volume"\)\s*\{(.*?)\}',
        CHARTS,
        re.DOTALL,
    )
    assert match, "volume profile branch not located in charts.js"
    body = match.group(1)
    assert "value_format" in body, (
        "volume profile must set ticks.value_format to route through "
        "formatChartValue's integer branch."
    )
    assert re.search(r'"integer"', body), (
        'volume profile must set ticks.value_format to the literal "integer".'
    )


# ---------------------------------------------------------------------------
# U3+U5: 监控冷启动骨架补占位 + styles.css 重复声明合并
# ---------------------------------------------------------------------------

def test_u3_macro_indicator_group_declared_once() -> None:
    """The legacy duplicate .macro-indicator-group declaration must be gone."""
    matches = list(re.finditer(r"^\.macro-indicator-group\s*\{", STYLES, re.MULTILINE))
    assert len(matches) == 1, (
        f".macro-indicator-group must be declared exactly once in styles.css; "
        f"found {len(matches)} declarations. Duplicate declarations cause "
        "the earlier 8px gap to be silently overridden."
    )


def test_u3_macro_indicator_group_gap_is_16px() -> None:
    match = re.search(r"^\.macro-indicator-group\s*\{(.*?)\}", STYLES, re.MULTILINE | re.DOTALL)
    assert match, ".macro-indicator-group block not found"
    assert "gap: 16px" in match.group(1), (
        "macro-indicator-group gap must be 16px (design-guidelines §1 同组独立卡 16px gap)."
    )


def test_u5_macro_panel_has_cold_placeholder() -> None:
    """#monitoring-macro-panel must host a cold-start placeholder."""
    # renderShellFallback must inject the placeholder when pending=true.
    fn = re.search(
        r"function renderShellFallback\(message, pending\s*=\s*false\)\s*\{(.*?)\n\}\n",
        MONITORING,
        re.DOTALL,
    )
    assert fn, "renderShellFallback function not located"
    body = fn.group(1)
    assert 'id="monitoring-macro-panel"' in body
    assert "monitoring-cold-placeholder" in body
    # And it must inject the placeholder only when pending=true.
    macro_panel_block = re.search(
        r'<div\s+id="monitoring-macro-panel">\s*(.*?)\s*</div>',
        body,
        re.DOTALL,
    )
    assert macro_panel_block, "#monitoring-macro-panel container not found in fallback"
    inner = macro_panel_block.group(1).strip()
    # Either inline placeholder or guarded by a pending ternary.
    assert "monitoring-cold-placeholder" in inner or "${pending ? coldPlaceholder : ''}" in inner


def test_u5_macro_grid_has_cold_placeholder() -> None:
    """#monitoring-macro-grid must host a macro-indicator-group skeleton with placeholders.

    The cold-start content is a JS template literal that interpolates via
    ``${pending ? macroGridPlaceholder : ''}``. The static guard accepts either
    an inline placeholder or a guarded interpolation that references one.
    """
    fn = re.search(
        r"function renderShellFallback\(message, pending\s*=\s*false\)\s*\{(.*?)\n\}\n",
        MONITORING,
        re.DOTALL,
    )
    body = fn.group(1)
    grid_block = re.search(
        r'<div\s+id="monitoring-macro-grid">\s*(.*?)\s*</div>',
        body,
        re.DOTALL,
    )
    assert grid_block, "#monitoring-macro-grid container not found in fallback"
    inner = grid_block.group(1).strip()
    has_inline = "macro-indicator-group" in inner and "monitoring-cold-placeholder" in inner
    has_guarded = "macroGridPlaceholder" in inner
    assert has_inline or has_guarded, (
        "#monitoring-macro-grid cold-start shell must include a macro-indicator-group "
        "skeleton (inline or via macroGridPlaceholder interpolation)."
    )


def test_u5_governance_has_cold_placeholder() -> None:
    """#monitoring-governance must host monitoring-cold-placeholder rows."""
    fn = re.search(
        r"function renderShellFallback\(message, pending\s*=\s*false\)\s*\{(.*?)\n\}\n",
        MONITORING,
        re.DOTALL,
    )
    body = fn.group(1)
    gov_block = re.search(
        r'<div\s+id="monitoring-governance">\s*(.*?)\s*</div>',
        body,
        re.DOTALL,
    )
    assert gov_block, "#monitoring-governance container not found in fallback"
    inner = gov_block.group(1).strip()
    has_inline = "monitoring-cold-placeholder" in inner
    has_guarded = "governancePlaceholder" in inner
    assert has_inline or has_guarded, (
        "#monitoring-governance cold-start shell must include monitoring-cold-placeholder "
        "rows (inline or via governancePlaceholder interpolation)."
    )


# ---------------------------------------------------------------------------
# U4: ETF 触屏命中区
# ---------------------------------------------------------------------------

def test_u4_coarse_pointer_block_includes_etf_selectors() -> None:
    """The @media (pointer: coarse) block must cover ETF form controls."""
    match = re.search(
        r"@media\s*\(pointer:\s*coarse\)\s*\{(.*?)\}\n",
        EDITORIAL,
        re.DOTALL,
    )
    assert match, "@media (pointer: coarse) block not located in editorial.css"
    body = match.group(1)
    required = [
        ".etf-equity-mode-btn",
        ".etf-equity-freq-btn",
        "#etf-equity-generate",
        ".etf-equity-from input",
        "min-height: 44px",
        "min-width: 44px",
    ]
    for token in required:
        assert token in body, (
            f"coarse pointer block must contain {token!r} so touch devices hit "
            "the 44×44 minimum (design-guidelines §10)."
        )


def test_u4_primary_action_has_default_rule() -> None:
    """`.primary-action` must have a non-coarse fallback rule so the button "
    "does not collapse to native UA height on desktop."""
    match = re.search(
        r"^\.primary-action\s*\{(.*?)\}",
        STYLES,
        re.MULTILINE | re.DOTALL,
    )
    assert match, ".primary-action rule missing from styles.css"
    body = match.group(1)
    assert "min-height" in body, ".primary-action must declare min-height"
    assert "padding" in body, ".primary-action must declare padding"