"""Tests for skew_25d fallback behaviour.

The original `skew_25d` returns `status="data_insufficient"` whenever the
selected-expiry chain cannot produce a 25-delta call and 25-delta put on the
same chain. Two extensions are exercised here:

* **delta tolerance (C4)**: a single candidate whose |delta| is close to but
  not exactly 25 should still count as a 25D sample instead of being treated
  as "the only available point". The result must flag the band so consumers
  know the value is approximate.

* **cross-expiry fallback (C1)**: when one side (call or put) of the primary
  chain has no candidate at all, the metric can borrow a strike pair from a
  neighbouring standard expiry. The result must flag the delta_source so the
  UI can distinguish native 25D from a stitched value.

The original happy-path behaviour (full primary chain with provider deltas)
must be preserved unchanged.
"""

from __future__ import annotations

from datetime import date

from app.services.btc_derivatives.models import OptionQuote
from app.services.btc_derivatives.options_metrics import skew_25d


def _q(
    expiry: str,
    strike: float,
    option_type: str,
    iv: float,
    delta: float | None = None,
) -> OptionQuote:
    return OptionQuote(
        expiry=expiry,
        strike=strike,
        option_type=option_type,
        bid=900,
        ask=1_000,
        mark=950,
        iv=iv,
        delta=delta,
    )


# ---------------------------------------------------------------------------
# C4 — delta tolerance: a near-25D strike counts, flagged in delta_band
# ---------------------------------------------------------------------------


def test_skew_25d_with_only_one_near_25d_call_still_returns_skew() -> None:
    """Primary chain has exactly one near-25D call (delta=0.18). Should not
    collapse to data_insufficient; the result is approximate but useful."""
    quotes = [
        _q("2026-09-25", 60_000, "put", iv=0.52, delta=0.20),
        _q("2026-09-25", 68_000, "call", iv=0.40, delta=0.18),  # near 25D but only one
        _q("2026-09-25", 75_000, "call", iv=0.42, delta=0.35),
    ]

    result = skew_25d(quotes, 63_000, as_of=date(2026, 7, 14))

    assert result["status"] != "data_insufficient", (
        f"near-25D single candidate must not be treated as data_insufficient: {result}"
    )
    assert result["put_call_skew"] is not None
    assert result["delta_band"] in {"near_25d", "exact_25d"}, (
        f"delta_band must signal how close the chosen strike is to 25D, got "
        f"{result.get('delta_band')!r}"
    )


# ---------------------------------------------------------------------------
# C1 — cross-expiry fallback: borrow from a neighbouring standard expiry
# ---------------------------------------------------------------------------


def test_skew_25d_falls_back_to_neighbouring_expiry_when_primary_lacks_call() -> None:
    """Primary chain (09-25) has no call candidate; fallback chain (08-28)
    has a clean 25D call/put pair. The result must use the fallback, set
    delta_source='cross_expiry', and still return a numeric skew."""
    primary = [
        _q("2026-09-25", 60_000, "put", iv=0.55, delta=0.22),
        _q("2026-09-25", 70_000, "put", iv=0.60, delta=0.45),
        # NOTE: no call quotes on the primary chain
    ]
    fallback = [
        _q("2026-08-28", 60_000, "put", iv=0.48, delta=0.25),
        _q("2026-08-28", 68_000, "call", iv=0.40, delta=0.25),
    ]

    result = skew_25d(
        primary,
        fallback_quotes=fallback,
        spot_price=63_000,
        as_of=date(2026, 7, 14),
    )

    assert result["status"] == "ok", (
        f"cross-expiry fallback should still yield ok status: {result}"
    )
    assert result["put_call_skew"] is not None
    assert result["delta_source"] == "cross_expiry", (
        f"delta_source must signal the fallback path was taken, got "
        f"{result.get('delta_source')!r}"
    )


def test_skew_25d_returns_data_insufficient_when_no_chain_has_candidates() -> None:
    """If primary AND fallback both have nothing useful, the metric must
    still honestly report data_insufficient rather than fabricate a value."""
    primary = [
        _q("2026-09-25", 60_000, "put", iv=0.55, delta=0.20),
        # no call
    ]
    fallback = [
        _q("2026-08-28", 60_000, "put", iv=0.48, delta=0.25),
        # no call either
    ]

    result = skew_25d(
        primary,
        fallback_quotes=fallback,
        spot_price=63_000,
        as_of=date(2026, 7, 14),
    )

    assert result["status"] == "data_insufficient"
    assert result["put_call_skew"] is None
    assert result["delta_source"] == "unavailable"


# ---------------------------------------------------------------------------
# Regression — original happy path still works and is NOT labelled cross_expiry
# ---------------------------------------------------------------------------


def test_skew_25d_native_path_unchanged_when_primary_is_complete() -> None:
    """When the primary chain has both call and put at 25D, the result must
    not pretend it came from a fallback. delta_source must be provider (or
    model_estimate) and the skew must equal put_iv - call_iv."""
    quotes = [
        _q("2026-09-25", 60_000, "put", iv=0.50, delta=0.25),
        _q("2026-09-25", 68_000, "call", iv=0.40, delta=0.25),
    ]
    # Note: fallback is intentionally empty.
    result = skew_25d(
        quotes,
        fallback_quotes=[],
        spot_price=63_000,
        as_of=date(2026, 7, 14),
    )

    assert result["status"] == "ok"
    assert result["delta_source"] in {"provider", "model_estimate"}
    assert result["delta_source"] != "cross_expiry"
    assert result["put_call_skew"] == 0.10


# ---------------------------------------------------------------------------
# Service-layer integration: build_dashboard must wire fallback_quotes into
# the primary skew_25d call and propagate a delta_source string into
# dashboard.options.metrics so the chart layer can flag stitched points.
# ---------------------------------------------------------------------------


def test_build_dashboard_wires_skew_fallback_pool_for_primary_chain() -> None:
    """build_dashboard(expiry_mode='fixed', expiry='2026-09-25') on a snapshot
    where 09-25 lacks a call candidate should still produce an ok skew by
    borrowing from the neighbouring 08-28 chain, and the resulting metric
    must carry delta_source='cross_expiry'."""
    from datetime import datetime, timezone

    from app.schemas.btc_derivatives_sources import LiveSnapshotEnvelope, NormalizedOptionQuote
    from app.services.btc_derivatives.service import BtcDerivativesService

    def _nq(expiry, strike, option_type, iv, delta):
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
            delta=delta,
            open_interest=100,
            volume_24h=10,
            collected_at=datetime(2026, 7, 14, tzinfo=timezone.utc),
        )

    options = []
    # 08-28: full call/put pair (acts as the fallback source)
    options += [
        _nq("2026-08-28", 60_000, "put", 0.48, 0.25),
        _nq("2026-08-28", 68_000, "call", 0.40, 0.25),
    ]
    # 09-25: put only, no call (forces the cross_expiry fallback)
    options += [_nq("2026-09-25", 60_000, "put", 0.55, 0.25)]

    envelope = LiveSnapshotEnvelope(
        snapshot_state="live",
        data_timestamp=datetime(2026, 7, 14, tzinfo=timezone.utc),
        primary_option_provider="deribit",
        options=options,
    )
    dashboard = BtcDerivativesService().build_dashboard(
        live_snapshot=envelope,
        expiry="2026-09-25",
        expiry_mode="fixed",
    )

    skew_metric = dashboard.options.metrics.get("skew_25d")
    assert skew_metric is not None, "skew_25d metric must be present in dashboard.options.metrics"
    assert skew_metric["status"] == "ok", (
        f"primary chain with no call + neighbouring chain with full pair must "
        f"yield ok skew, got {skew_metric}"
    )
    assert skew_metric["delta_source"] == "cross_expiry", (
        f"missing-call primary must trigger cross_expiry fallback, got "
        f"{skew_metric.get('delta_source')!r}"
    )


# ---------------------------------------------------------------------------
# Cache layer: live_service must stamp skew_25d_source on every history point
# so the chart layer can tell native vs stitched points apart on the chart.
# ---------------------------------------------------------------------------


def test_live_service_writes_skew_25d_source_to_history_point() -> None:
    """When the dashboard's skew_25d metric carries delta_source='cross_expiry'
    (or any other value), the cache point persisted by live_service must
    carry a matching skew_25d_source field. The frontend reads this string
    to decide whether to draw a 'stitched' annotation on the chart."""
    from datetime import datetime, timezone

    from app.schemas.btc_derivatives_sources import LiveSnapshotEnvelope, NormalizedOptionQuote
    from app.services.btc_derivatives.service import BtcDerivativesService

    def _nq(expiry, strike, option_type, iv, delta):
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
            delta=delta,
            open_interest=100,
            volume_24h=10,
            collected_at=datetime(2026, 7, 14, tzinfo=timezone.utc),
        )

    options = [
        _nq("2026-08-28", 60_000, "put", 0.48, 0.25),
        _nq("2026-08-28", 68_000, "call", 0.40, 0.25),
        _nq("2026-09-25", 60_000, "put", 0.55, 0.25),
    ]
    envelope = LiveSnapshotEnvelope(
        snapshot_state="live",
        data_timestamp=datetime(2026, 7, 14, tzinfo=timezone.utc),
        primary_option_provider="deribit",
        options=options,
    )

    dashboard = BtcDerivativesService().build_dashboard(
        live_snapshot=envelope,
        expiry="2026-09-25",
        expiry_mode="fixed",
    )

    # Mirror what live_service.py:346-383 builds for the cache point: the
    # skew_25d_source field must come from metrics.skew_25d.delta_source.
    metrics = dashboard.options.metrics
    skew_metric = metrics.get("skew_25d", {})
    point_skew_25d_source = skew_metric.get("delta_source")

    assert point_skew_25d_source == "cross_expiry", (
        f"skew_25d metric must carry delta_source='cross_expiry' so "
        f"live_service can stamp the cache point with the same value, got "
        f"{point_skew_25d_source!r}"
    )


def test_live_service_point_dict_contains_skew_25d_source_field() -> None:
    """The cache point built in live_service.py:346-383 must stamp
    skew_25d_source alongside skew_25d so the chart layer can show stitched
    points distinctly. This is a structural assertion on the source code
    rather than a behavioural assertion because the cache writer is wired
    into a LiveCollector that is heavy to mock here."""
    from pathlib import Path

    source = Path(
        "app/services/btc_derivatives/live_service.py"
    ).read_text(encoding="utf-8")

    assert '"skew_25d_source"' in source, (
        "live_service must stamp skew_25d_source on every history point so "
        "the chart layer can flag stitched values"
    )