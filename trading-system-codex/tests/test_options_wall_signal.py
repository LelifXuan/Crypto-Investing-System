from __future__ import annotations

import pytest

from app.services.btc_derivatives.options_wall_signal import evaluate_key_levels_axis


def test_call_put_and_max_pain_all_rise_with_spot_confirms_bullish_structure() -> None:
    result = evaluate_key_levels_axis(
        spot_price=63_000,
        previous_spot_price=60_000,
        call_wall=72_000,
        previous_call_wall=68_000,
        put_wall=56_000,
        previous_put_wall=53_000,
        max_pain=64_000,
        previous_max_pain=61_000,
        data_quality_status="live",
    )

    assert result["status"] == "ok"
    assert result["overall_signal"] == "bullish_confirmed"
    assert result["bias"] == "bullish"
    assert result["confirmation"] == "confirmed"
    assert result["confidence"] in {"medium", "high"}
    assert result["levels"]["call_wall"]["signal"] == "bullish_confirmed"
    assert result["levels"]["put_wall"]["signal"] == "bullish_confirmed"
    assert result["levels"]["max_pain"]["signal"] == "bullish_confirmed"
    assert result["direct_command"] is False


def test_call_wall_rises_but_put_wall_and_max_pain_do_not_confirm_is_not_strong_bullish() -> None:
    result = evaluate_key_levels_axis(
        spot_price=59_000,
        previous_spot_price=61_000,
        call_wall=72_000,
        previous_call_wall=68_000,
        put_wall=50_000,
        previous_put_wall=52_000,
        max_pain=60_000,
        previous_max_pain=62_000,
        data_quality_status="live",
    )

    assert result["overall_signal"] in {"bearish_confirmed", "divergence_watch", "mixed"}
    assert result["bias"] != "bullish"
    assert result["confirmation"] != "confirmed" or result["bias"] == "bearish"
    assert "分歧" in "".join(result["conflicts"]) or result["bias"] == "bearish"


def test_max_pain_migration_is_described_as_position_center_not_prediction() -> None:
    result = evaluate_key_levels_axis(
        spot_price=61_000,
        previous_spot_price=60_000,
        call_wall=70_000,
        previous_call_wall=70_000,
        put_wall=52_000,
        previous_put_wall=52_000,
        max_pain=64_000,
        previous_max_pain=60_000,
        data_quality_status="live",
    )

    text = f"{result['summary']} " + " ".join(
        item["explanation"] for item in result["evidence"]
    )
    assert "预测" not in text
    assert "目标价" not in text
    assert "持仓重心" in text


def test_missing_key_levels_returns_data_insufficient_not_neutral_success() -> None:
    result = evaluate_key_levels_axis(
        spot_price=61_000,
        previous_spot_price=60_000,
        call_wall=None,
        previous_call_wall=None,
        put_wall=None,
        previous_put_wall=None,
        max_pain=None,
        previous_max_pain=None,
        data_quality_status="live",
    )

    assert result["status"] == "data_insufficient"
    assert result["overall_signal"] == "data_insufficient"
    assert result["confidence"] == "low"
    assert result["bias"] == "neutral"


def test_rollover_or_provider_change_degrades_confidence_and_keeps_evidence() -> None:
    result = evaluate_key_levels_axis(
        spot_price=63_000,
        previous_spot_price=60_000,
        call_wall=72_000,
        previous_call_wall=68_000,
        put_wall=56_000,
        previous_put_wall=53_000,
        max_pain=64_000,
        previous_max_pain=61_000,
        data_quality_status="live",
        rollover=True,
        provider_changed=True,
    )

    assert result["confidence"] == "medium"
    assert any(item["code"] == "expiry_rollover" for item in result["evidence"])
    assert any(item["code"] == "provider_changed" for item in result["evidence"])


def test_comparison_metadata_is_exposed_for_daily_basis() -> None:
    result = evaluate_key_levels_axis(
        spot_price=59_218.52,
        previous_spot_price=60_074.63,
        call_wall=75_000,
        previous_call_wall=72_000,
        put_wall=50_000,
        previous_put_wall=50_000,
        max_pain=62_000,
        previous_max_pain=62_000,
        data_quality_status="stale",
        comparison_basis="previous_utc_day",
        comparison_timestamp="2026-06-30T00:34:43.271173+00:00",
        comparison_is_same_day=False,
    )

    assert result["comparison_basis"] == "previous_utc_day"
    assert result["comparison_timestamp"] == "2026-06-30T00:34:43.271173+00:00"
    assert result["comparison_is_same_day"] is False
    assert result["call_wall_previous"] == 72_000
    assert result["call_wall_today"] == 75_000
    assert result["call_wall_shift_pct"] == pytest.approx(0.0416666, rel=1e-4)
    assert result["levels"]["call_wall"]["signal"] == "divergence_watch"
    assert result["spot_direction"] == "down"


def test_expiry_calendar_context_marks_monthly_quarterly_and_event_windows() -> None:
    result = evaluate_key_levels_axis(
        spot_price=63_000,
        previous_spot_price=60_000,
        call_wall=72_000,
        previous_call_wall=68_000,
        put_wall=56_000,
        previous_put_wall=53_000,
        max_pain=64_000,
        previous_max_pain=61_000,
        data_quality_status="live",
        selected_expiry="2026-09-25",
        source_dte=86,
    )

    context = result["expiry_context"]
    assert context["selected_expiry"] == "2026-09-25"
    assert context["cycle"] == "quarterly"
    assert "季度交割" in context["labels"]
    assert "四巫日窗口" in context["labels"]
    assert "ETF调仓窗口" in context["labels"]
    assert any(item["code"] == "expiry_calendar" for item in result["evidence"])
