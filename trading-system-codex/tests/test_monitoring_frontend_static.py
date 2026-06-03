from __future__ import annotations

from pathlib import Path

REPO = Path(__file__).resolve().parents[1]
MONITORING_JS = REPO / "app" / "static" / "pages" / "monitoring.js"
STYLES_CSS = REPO / "app" / "static" / "styles.css"

REQUIRED_DECISION_LABELS = (
    "市场观察",
)

OLD_PRIMARY_LABELS = (
    "交易指引",
    "风险点 / 失效条件",
)


def _read(path: Path) -> str:
    return path.read_text(encoding="utf-8")


def test_monitoring_js_exposes_decision_rows_helpers() -> None:
    content = _read(MONITORING_JS)
    assert "function getTerminalDecisionRows" in content
    assert "function renderTerminalDecisionRow" in content
    assert "decision_brief" in content
    assert "terminal-summary-brief" in content
    assert "renderTerminalSummary" in content


def test_monitoring_js_primary_labels_are_new_three_rows() -> None:
    content = _read(MONITORING_JS)
    for label in REQUIRED_DECISION_LABELS:
        assert label in content, f"Missing primary label: {label}"


def test_monitoring_js_old_card_titles_not_used_as_primary() -> None:
    """The old 主要矛盾 / 策略含义 / 观察条件 cards must be gone from the
    active render path. The test confirms the renderTerminalSummary() block
    does not embed these strings as primary labels.
    """

    content = _read(MONITORING_JS)
    start = content.find("function renderTerminalSummary")
    assert start > 0
    end = content.find("\nfunction ", start + 1)
    if end < 0:
        end = len(content)
    block = content[start:end]
    for label in OLD_PRIMARY_LABELS:
        assert label not in block, (
            f"Old label {label!r} still appears as primary card title in "
            "renderTerminalSummary()."
        )


def test_monitoring_css_has_terminal_brief_classes() -> None:
    content = _read(STYLES_CSS)
    for cls in (
        ".terminal-summary-brief",
        ".terminal-brief-row",
        ".terminal-brief-row-head",
        ".terminal-brief-bullets",
        ".terminal-brief-sources",
        ".terminal-brief-tone-bullish",
        ".terminal-brief-tone-bearish",
        ".terminal-brief-tone-neutral",
        ".terminal-brief-tone-warning",
    ):
        assert cls in content, f"Missing CSS class: {cls}"


def test_monitoring_js_handles_decision_brief_only() -> None:
    """V1.5.2 row set is sourced exclusively from the backend
    decision_brief.rows payload; no synthetic fallback rows are
    rendered for missing fields. The function only normalises the
    shape returned by the backend.
    """

    content = _read(MONITORING_JS)
    fn_idx = content.find("function getTerminalDecisionRows")
    assert fn_idx > 0
    end = content.find("\nfunction ", fn_idx + 1)
    block = content[fn_idx:end] if end > 0 else content[fn_idx:]
    assert "decision_brief" in block
    assert "trading_guidance" not in block
    assert "risk_invalidation" not in block
    assert "summary.headline" not in block
    assert "summary.bias" not in block


def test_monitoring_js_renders_three_rows_via_terminal_brief_wrapper() -> None:
    content = _read(MONITORING_JS)
    start = content.find("function renderTerminalSummary")
    end = content.find("\nfunction ", start + 1)
    block = content[start:end]
    assert "terminal-summary-brief" in block
    assert "getTerminalDecisionRows" in block
    assert "renderTerminalDecisionRow" in block
