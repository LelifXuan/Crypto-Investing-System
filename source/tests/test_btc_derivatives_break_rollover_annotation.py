"""Tests for the chart annotation labels emitted for risk-history breaks.

The backend writes a ``series_break_detail`` on each broken point
(e.g. ``"expiry_rollover:2026-08-28->2026-09-25"`` /
``"method_change:otm_estimate->constant_delta"``). ``chart_builder`` is
responsible for turning that into a human-readable vertical-line label on the
"期权情绪与保护成本" chart so users can tell why the line was split.
"""

from __future__ import annotations

from typing import Any

from app.services.btc_derivatives.chart_builder import (
    build_consolidated_dashboard_charts,
)


def _empty_inputs() -> dict[str, Any]:
    return {
        "price_history": [],
        "futures_rows": [],
        "basis_points": [],
        "atm_iv_points": [],
        "strike_rows": [],
        "history": [],
        "spot_price": 60_000.0,
        "call_wall": None,
        "put_wall": None,
        "max_pain": None,
    }


def _risk_row(
    *,
    timestamp: str,
    call: float | None = 0.025,
    put: float | None = 0.030,
    debit: float | None = 0.018,
    break_reason: str | None = None,
    detail: str | None = None,
    source_expiry: str = "2026-09-25",
    selection_method: str = "otm_estimate",
    skew: float | None = 0.0,
    put_call_oi: float | None = 1.0,
    put_call_volume: float | None = 1.0,
) -> dict[str, Any]:
    row: dict[str, Any] = {
        "timestamp": timestamp,
        "spot_price": 60_000,
        "call_protection_cost_pct": call,
        "put_protection_cost_pct": put,
        "debit_spread_cost_pct": debit,
        "skew_25d": skew,
        "put_call_oi_ratio": put_call_oi,
        "put_call_volume_ratio": put_call_volume,
        "source_expiry": source_expiry,
        "selection_method": selection_method,
    }
    if break_reason is not None:
        row["series_break_reason"] = break_reason
    if detail is not None:
        row["series_break_detail"] = detail
    return row


def _annotation_labels(annotations: list[dict[str, Any]]) -> list[tuple[str, str]]:
    """Return (x, label) tuples for every verticalLine annotation."""
    return [
        (annotation["x"], annotation.get("label", ""))
        for annotation in annotations
        if annotation.get("type") == "verticalLine"
        and annotation.get("label")
    ]


# ---------------------------------------------------------------------------
# Expiry rollover label: "到期日切换：MM-DD → MM-DD"
# ---------------------------------------------------------------------------


def test_expiry_rollover_label_includes_from_to_expiries() -> None:
    risk_history = [
        _risk_row(timestamp="2026-07-13T08:23", source_expiry="2026-08-28"),
        _risk_row(
            timestamp="2026-07-14T05:39",
            source_expiry="2026-09-25",
            break_reason="expiry_rollover",
            detail="expiry_rollover:2026-08-28->2026-09-25",
        ),
    ]

    charts = build_consolidated_dashboard_charts(
        **_empty_inputs(),
        risk_history=risk_history,
    )
    chart = charts["charts"]["options_risk_premium_history"]
    labels = _annotation_labels(chart["annotations"])

    assert ("2026-07-14T05:39", "到期日切换：08-28 → 09-25") in labels, (
        f"expiry_rollover annotation not rendered with from/to dates. Got: {labels}"
    )


# ---------------------------------------------------------------------------
# Method change label: "方法切换：otm_estimate → constant_delta"
# ---------------------------------------------------------------------------


def test_method_change_label_includes_from_to_methods() -> None:
    risk_history = [
        _risk_row(
            timestamp="2026-07-14T05:39",
            source_expiry="2026-09-25",
            selection_method="otm_estimate",
        ),
        _risk_row(
            timestamp="2026-07-14T09:46",
            source_expiry="2026-09-25",
            selection_method="constant_delta",
            break_reason="method_change",
            detail="method_change:otm_estimate->constant_delta",
        ),
    ]

    charts = build_consolidated_dashboard_charts(
        **_empty_inputs(),
        risk_history=risk_history,
    )
    chart = charts["charts"]["options_risk_premium_history"]
    labels = _annotation_labels(chart["annotations"])

    assert (
        "2026-07-14T09:46",
        "方法切换：otm_estimate → constant_delta",
    ) in labels, f"method_change annotation not rendered with from/to methods. Got: {labels}"


# ---------------------------------------------------------------------------
# Non-break rows emit no verticalLine annotations
# ---------------------------------------------------------------------------


def test_no_vertical_line_annotations_when_no_breaks() -> None:
    risk_history = [
        _risk_row(timestamp="2026-07-13T08:23"),
        _risk_row(timestamp="2026-07-14T09:46"),
    ]

    charts = build_consolidated_dashboard_charts(
        **_empty_inputs(),
        risk_history=risk_history,
    )
    chart = charts["charts"]["options_risk_premium_history"]
    labels = _annotation_labels(chart["annotations"])

    assert labels == [], f"unexpected vertical-line labels: {labels}"