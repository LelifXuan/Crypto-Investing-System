from __future__ import annotations

from datetime import UTC, datetime, timedelta
from decimal import Decimal
from types import SimpleNamespace

from app.services.strategy_unified.shadow_validation import ShadowValidationService


def _row(index: int, *, mode: str, direction: str, return_value: str):
    decision = SimpleNamespace(
        decision_ts=datetime(2026, 1, 1, tzinfo=UTC) + timedelta(hours=4 * index),
        direction=direction,
        confidence_score=Decimal("70"),
        payload_json={"evaluation_mode": mode, "safety_gate_passed": True},
    )
    outcome = SimpleNamespace(slippage_adjusted_return=Decimal(return_value))
    return decision, outcome


def test_shadow_metrics_are_ordered_and_include_calibration_drawdown_and_reversals() -> None:
    rows = [
        _row(0, mode="shadow", direction="LONG", return_value="0.02"),
        _row(1, mode="shadow", direction="SHORT", return_value="-0.01"),
        _row(2, mode="shadow", direction="SHORT", return_value="0.03"),
    ]

    metrics = ShadowValidationService._metrics(rows)

    assert metrics["evaluated_decisions"] == 3
    assert metrics["direction_hit_rate"] == 0.666667
    assert metrics["brier_score"] >= 0
    assert metrics["max_drawdown"] > 0
    assert metrics["reversal_count"] == 1
