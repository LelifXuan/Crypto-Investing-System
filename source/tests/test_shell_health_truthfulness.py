"""P1-STATE-001 / INV-004: global health copy must reflect observable state.

The shell must not hardcode a healthy default (「系统在线/数据连接正常」),
service health and market-data quality must stay separate concepts, and the
fail-safe state on request failure is 服务不可达/未知 — never a green default.
"""

from __future__ import annotations

from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]


def test_shell_does_not_hardcode_healthy_data_state():
    template = (ROOT / "app/templates/page.html").read_text(encoding="utf-8")
    assert "系统在线" not in template
    assert "数据连接正常" not in template
    # Both chips ship in the unknown state; JS owns every transition.
    assert template.count('data-state="unknown"') >= 2
    assert 'data-shell-health-label="service"' in template
    assert 'data-shell-health-label="data"' in template
    assert ">服务状态未知<" in template
    assert ">数据状态未知<" in template


def test_shell_health_ready_state():
    text = (ROOT / "app/static/core/shellHealth.js").read_text(encoding="utf-8")
    assert 'ready: "服务正常"' in text
    assert 'if (status === "ready") return "ready";' in text


def test_shell_health_degraded_state():
    text = (ROOT / "app/static/core/shellHealth.js").read_text(encoding="utf-8")
    assert 'degraded: "服务降级"' in text
    assert 'if (status === "degraded") return "degraded";' in text
    # Data degradation derives from request outcomes, not from /health.
    assert "lastFailureAt > tracker.lastSuccessAt" in text
    assert 'degraded: "部分数据降级"' in text


def test_shell_health_unreachable_state():
    text = (ROOT / "app/static/core/shellHealth.js").read_text(encoding="utf-8")
    assert 'if (error) return "unreachable";' in text
    assert 'unreachable: "服务不可达"' in text
    assert 'unknown: "服务状态未知"' in text
    assert 'unknown: "数据状态未知"' in text


def test_service_online_with_page_data_degraded_is_representable():
    """The two chips are independent: service ready + data degraded must be a
    representable combination, so data state never reads the health payload."""
    text = (ROOT / "app/static/core/shellHealth.js").read_text(encoding="utf-8")
    assert "deriveServiceState(payload, error)" in text
    assert "deriveDataState(dataTracker)" in text
    assert text.count('render("data"') >= 1
    api_text = (ROOT / "app/static/core/api.js").read_text(encoding="utf-8")
    assert "dataQualityTracker" in api_text
    assert "isHealthRequest" in api_text
    main_text = (ROOT / "app/static/main.js").read_text(encoding="utf-8")
    assert "startShellHealth()" in main_text
    assert "registerDataQualityTracker(dataQualityTracker)" in main_text


def test_unknown_state_has_no_positive_color():
    css = (ROOT / "app/static/editorial.css").read_text(encoding="utf-8")
    # Gray base (muted) for the dot; positive colors only under explicit
    # observed states, never for "unknown".
    assert "background: var(--muted);" in css
    assert css.count(".app-sidebar-foot [data-shell-health-dot") >= 3
    assert '[data-state="ready"]' in css
    assert '[data-state="degraded"]' in css
    assert '[data-state="unreachable"]' in css
    # No positive/known styling for the shell health dots in unknown state:
    # gray base only (governance-ledger has its own unrelated unknown rule).
    shell_block = css[css.find("P1-STATE-001: chip color") : css.find(".app-main {")]
    assert '[data-state="unknown"]' not in shell_block
