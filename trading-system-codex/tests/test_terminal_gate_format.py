"""Acceptance tests for T03: gates parsed as GateDiagnostic list.

The audit found that ``_decision_build_risk_row`` filtered blocking gates
with a literal string match ``item.lower() in {'block', 'blocked', ...}``,
which dropped every GateDiagnostic-shaped dict. The trading row joined
``gates`` with ``；`` without preserving the block / warn / pass structure.
These tests pin the new normalizer + formatter contract.
"""

from __future__ import annotations

from app.services.strategy_signal.setup_lifecycle import GateDiagnostic
from app.services.terminal_summary_engine import (
    TerminalSummaryEngine,
    _decision_format_gate_bullet,
    _decision_format_gates,
    _decision_normalize_gates,
)


def test_normalize_gatediagnostic_passthrough() -> None:
    gate = GateDiagnostic(code="X", status="fail", message="m", severity="block")
    out = _decision_normalize_gates(gate)
    assert len(out) == 1
    assert out[0].code == "X"
    assert out[0].severity == "block"


def test_normalize_dict_with_severity_block() -> None:
    out = _decision_normalize_gates(
        {
            "code": "HARD_GATE",
            "severity": "block",
            "message": "spread too wide",
            "current": 35.0,
            "required": 15.0,
        }
    )
    assert len(out) == 1
    assert out[0].code == "HARD_GATE"
    assert out[0].severity == "block"
    assert out[0].current == 35.0
    assert out[0].required == 15.0


def test_normalize_dict_without_severity_defaults_to_info() -> None:
    out = _decision_normalize_gates({"code": "X", "message": "m"})
    assert out[0].severity == "info"
    assert out[0].status == "info"


def test_normalize_list_of_mixed_shapes() -> None:
    out = _decision_normalize_gates(
        [
            {"code": "A", "severity": "block", "message": "ma"},
            "block",
            GateDiagnostic(code="C", status="warn", message="mc", severity="warning"),
            None,
            42,
            "",
        ]
    )
    codes = [gate.code for gate in out]
    assert "A" in codes
    assert "C" in codes
    assert "block" in codes
    assert len(out) == 3


def test_normalize_bare_string_block_is_severity_block() -> None:
    out = _decision_normalize_gates("block")
    assert out[0].severity == "block"
    assert out[0].status == "fail"


def test_normalize_bare_string_warning_is_severity_warning() -> None:
    out = _decision_normalize_gates("warning")
    assert out[0].severity == "warning"
    assert out[0].status == "warn"


def test_normalize_empty_inputs() -> None:
    assert _decision_normalize_gates(None) == []
    assert _decision_normalize_gates([]) == []
    assert _decision_normalize_gates({}) == []
    assert _decision_normalize_gates("") == []


def test_format_gates_returns_has_block_and_warnings() -> None:
    gates = [
        {"code": "HARD_GATE", "severity": "block", "message": "spread wide"},
        {"code": "FUNDING", "severity": "warn", "message": "crowding"},
        {"code": "DATA_OK", "severity": "info", "message": "ok", "status": "pass"},
    ]
    bullets, has_block, has_warn = _decision_format_gates(gates, limit=4)
    assert has_block is True
    assert has_warn is True
    assert any("未通过" in b for b in bullets)
    assert any("风险提示" in b for b in bullets)
    # Block gates are ordered first
    assert "未通过" in bullets[0]


def test_format_gates_no_block_no_warn_flags_false() -> None:
    bullets, has_block, has_warn = _decision_format_gates(
        [{"code": "OK", "status": "pass", "message": "ok"}]
    )
    assert bullets == []
    assert has_block is False
    assert has_warn is False


def test_format_gate_bullet_includes_current_and_required() -> None:
    gate = GateDiagnostic(
        code="DATA_QUALITY_LOW",
        status="warn",
        message="数据质量偏低",
        current=45.0,
        required=60.0,
        severity="warning",
    )
    rendered = _decision_format_gate_bullet(gate)
    assert "风险提示" in rendered
    assert "数据质量偏低" in rendered
    assert "45" in rendered
    assert "60" in rendered


def test_format_gate_bullet_block_severity_uses_未通过() -> None:
    gate = GateDiagnostic(
        code="HARD_GATE",
        status="fail",
        message="spread 35 bps",
        current=35.0,
        required=15.0,
        severity="block",
    )
    rendered = _decision_format_gate_bullet(gate)
    assert rendered.startswith("未通过")
    assert "spread 35 bps" in rendered


def test_format_gates_limit_caps_output() -> None:
    gates = [
        {"code": f"G{i}", "severity": "block", "message": f"m{i}"}
        for i in range(10)
    ]
    bullets, _, _ = _decision_format_gates(gates, limit=3)
    assert len(bullets) == 3


def _brief_with_gates(strategy_bundle: dict) -> dict:
    """Call the engine's decision_brief builder directly with crafted inputs."""

    engine = TerminalSummaryEngine()
    return engine._build_decision_brief(  # noqa: SLF001
        base_summary={"watch_points": []},
        alerts_bundle={},
        strategy_bundle=strategy_bundle,
        timeframe_snapshots={},
        structure={},
    )


def test_decision_brief_risk_row_contains_block_gates() -> None:
    """End-to-end: block-level gates must surface in the risk row."""

    brief = _brief_with_gates(
        {
            "strategy_state": "WAIT_TRIGGER",
            "strategy_state_label": "等待触发",
            "strategy_bias": "long",
            "strategy_bias_label": "偏多",
            "strategy_permission": "conditional",
            "next_trigger": "等待 4H 突破",
            "primary_strategy": {},
            "gates": [
                {
                    "code": "HARD_GATE",
                    "severity": "block",
                    "message": "spread too wide",
                    "current": 35,
                    "required": 15,
                },
                {"code": "FUNDING", "severity": "warn", "message": "funding crowding"},
            ],
            "blocking_gates": [
                {
                    "code": "HARD_GATE",
                    "severity": "block",
                    "message": "spread too wide",
                }
            ],
        }
    )

    risk_row = next(
        row for row in brief["rows"] if row.get("key") == "risk_invalidation"
    )
    bullets_text = "\n".join(risk_row["bullets"])
    assert "未通过的策略门槛" in bullets_text
    assert "spread too wide" in bullets_text

    trading_row = next(
        row for row in brief["rows"] if row.get("key") == "trading_guidance"
    )
    trading_text = "\n".join(trading_row["bullets"])
    assert "执行前必须通过的策略门槛" in trading_text or "策略门槛状态" in trading_text


def test_decision_brief_trading_row_downgrades_tone_on_block() -> None:
    brief = _brief_with_gates(
        {
            "strategy_state": "WAIT_TRIGGER",
            "strategy_state_label": "等待触发",
            "strategy_bias": "long",
            "strategy_bias_label": "偏多",
            "strategy_permission": "conditional",
            "next_trigger": "等待 4H 突破",
            "primary_strategy": {},
            "gates": [
                {
                    "code": "HARD_GATE",
                    "severity": "block",
                    "message": "spread too wide",
                }
            ],
        }
    )
    trading_row = next(
        row for row in brief["rows"] if row.get("key") == "trading_guidance"
    )
    assert trading_row["tone"] == "warning"
