from __future__ import annotations

from datetime import date, datetime, timezone

from app.schemas.btc_derivatives_sources import LiveSnapshotEnvelope, NormalizedOptionQuote
from app.services.btc_derivatives.expiry_policy import classify_expiry, standard_expiries
from app.services.btc_derivatives.models import OptionQuote
from app.services.btc_derivatives.options_metrics import skew_25d
from app.services.btc_derivatives.service import BtcDerivativesService


def test_standard_expiry_policy_keeps_only_month_end_fridays() -> None:
    values = [
        "2026-07-14",
        "2026-07-24",
        "2026-07-31",
        "2026-08-28",
        "2026-09-25",
    ]
    assert standard_expiries(values, as_of=date(2026, 7, 14)) == [
        "2026-07-31",
        "2026-08-28",
        "2026-09-25",
    ]
    assert classify_expiry("2026-09-25", as_of=date(2026, 7, 14)).cycle == "QUARTERLY"
    assert classify_expiry("2026-07-24", as_of=date(2026, 7, 14)).is_standard is False


def test_25d_skew_uses_model_delta_when_provider_delta_is_missing() -> None:
    quotes = [
        OptionQuote("2026-09-25", 55_000, "put", iv=0.52),
        OptionQuote("2026-09-25", 60_000, "put", iv=0.48),
        OptionQuote("2026-09-25", 68_000, "call", iv=0.40),
        OptionQuote("2026-09-25", 75_000, "call", iv=0.42),
    ]
    result = skew_25d(quotes, 63_000, as_of=date(2026, 7, 14))
    assert result["status"] == "ok"
    assert result["delta_source"] == "model_estimate"
    assert result["provider_delta_coverage"] == 0


def _quote(expiry: str, strike: float, option_type: str, iv: float, oi: float):
    now = datetime(2026, 7, 14, tzinfo=timezone.utc)
    return NormalizedOptionQuote(
        provider="deribit",
        instrument=f"BTC-{expiry}-{strike}-{option_type}",
        expiry=expiry,
        strike=strike,
        option_type=option_type,
        bid=900,
        ask=1_000,
        mark_price=950,
        underlying_price=63_000,
        iv=iv,
        delta=None,
        open_interest=oi,
        volume_24h=10,
        collected_at=now,
    )


def test_dashboard_filters_nonstandard_expiries_and_constant_mode_ignores_fixed_date() -> None:
    options = []
    for expiry in ("2026-07-14", "2026-07-31", "2026-08-28", "2026-09-25"):
        options.extend(
            [
                _quote(expiry, 55_000, "put", 0.52, 100),
                _quote(expiry, 60_000, "put", 0.48, 200),
                _quote(expiry, 68_000, "call", 0.40, 180),
                _quote(expiry, 75_000, "call", 0.42, 120),
            ]
        )
    envelope = LiveSnapshotEnvelope(
        snapshot_state="live",
        data_timestamp=datetime(2026, 7, 14, tzinfo=timezone.utc),
        primary_option_provider="deribit",
        options=options,
    )
    dashboard = BtcDerivativesService().build_dashboard(
        live_snapshot=envelope,
        expiry="2026-07-14",
        expiry_mode="constant_maturity",
        maturity_bucket="60D",
    )
    assert dashboard.options.standard_expiries == [
        "2026-07-31",
        "2026-08-28",
        "2026-09-25",
    ]
    assert dashboard.selection.effective_expiry == "2026-09-25"
    assert dashboard.selection.effective_dte == 73
    assert dashboard.selection.selection_status == "constant_maturity_override"
    assert len(dashboard.options.maturity_ladder) == 3
    assert dashboard.options.metrics["options_direction"]["state"] != "DATA_INSUFFICIENT"


def test_fixed_nonstandard_expiry_is_normalized_with_explicit_reason() -> None:
    options = []
    for expiry in ("2026-07-31", "2026-08-28"):
        options.extend(
            [
                _quote(expiry, 60_000, "put", 0.48, 200),
                _quote(expiry, 68_000, "call", 0.40, 180),
            ]
        )
    envelope = LiveSnapshotEnvelope(
        snapshot_state="live",
        data_timestamp=datetime(2026, 7, 14, tzinfo=timezone.utc),
        primary_option_provider="deribit",
        options=options,
    )
    dashboard = BtcDerivativesService().build_dashboard(
        live_snapshot=envelope,
        expiry="2026-07-24",
        expiry_mode="fixed",
    )
    assert dashboard.selection.selection_status == "normalized"
    assert dashboard.selection.effective_expiry == "2026-07-31"
    assert "标准月末" in dashboard.selection.selection_reason
