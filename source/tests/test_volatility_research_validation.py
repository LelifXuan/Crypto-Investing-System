from __future__ import annotations

from datetime import datetime, timedelta, timezone
from decimal import Decimal

from app.services.volatility_research.validation import (
    DatasetManifest,
    PromotionEvidence,
    anchored_walk_forward_splits,
    block_bootstrap_mean_interval,
    cpcv_splits,
    deflated_sharpe_confidence,
    probability_of_backtest_overfitting,
    promotion_status,
    validate_point_in_time,
)

UTC = timezone.utc


def test_point_in_time_contract_rejects_naive_or_future_availability() -> None:
    event = datetime(2026, 1, 1, tzinfo=UTC)
    available = event + timedelta(minutes=1)
    decision = available + timedelta(minutes=1)
    assert validate_point_in_time(event, available, decision)
    assert not validate_point_in_time(event, decision + timedelta(seconds=1), decision)
    assert not validate_point_in_time(event.replace(tzinfo=None), available, decision)


def test_dataset_manifest_hash_is_deterministic_and_marks_observed_status() -> None:
    now = datetime(2026, 1, 1, tzinfo=UTC)
    kwargs = {
        "dataset_id": "fixture",
        "source": "deribit",
        "event_times": [now, now + timedelta(hours=1)],
        "retrieved_at": now + timedelta(hours=2),
        "missing_count": 0,
        "methodology_version": "v1",
        "license_status": "public",
        "observed_or_backtested": "observed",
        "canonical_rows": [{"value": "50.1"}, {"value": "50.2"}],
    }
    first = DatasetManifest.build(**kwargs)
    second = DatasetManifest.build(**kwargs)
    assert first.content_sha256 == second.content_sha256
    assert first.as_dict()["observed_or_backtested"] == "observed"


def test_walk_forward_and_cpcv_are_ordered_and_purged() -> None:
    splits = anchored_walk_forward_splits(100, minimum_train=40, test_size=20)
    assert [(len(train), len(test)) for train, test in splits] == [(40, 20), (60, 20), (80, 20)]
    cpcv = cpcv_splits(60, groups=6, test_groups=2, embargo=1)
    assert len(cpcv) == 15
    assert all(set(train).isdisjoint(test) for train, test in cpcv)


def test_block_bootstrap_is_seeded_and_decimal() -> None:
    values = [Decimal("0.01"), Decimal("0.02"), Decimal("0.03"), Decimal("0.04")]
    first = block_bootstrap_mean_interval(values, block_size=2, samples=200)
    second = block_bootstrap_mean_interval(values, block_size=2, samples=200)
    assert first == second
    assert all(isinstance(value, Decimal) for value in first)


def test_pbo_and_promotion_gate_are_fail_closed() -> None:
    pbo = probability_of_backtest_overfitting(
        [[Decimal(3), Decimal(2), Decimal(1)], [Decimal(1), Decimal(3), Decimal(2)]],
        [[Decimal(1), Decimal(2), Decimal(3)], [Decimal(3), Decimal(1), Decimal(2)]],
    )
    assert pbo == Decimal(1)
    status, failures = promotion_status(
        PromotionEvidence(
            point_in_time_valid=True,
            independent_years_or_regimes=2,
            consistent_effect=True,
            bootstrap_lower=Decimal("-0.01"),
            bootstrap_upper=Decimal("0.03"),
            dsr_confidence=Decimal("0.90"),
            pbo=Decimal("0.60"),
            other_primary_risk_degradation=Decimal("0.06"),
            single_source_dependency=True,
            single_parameter_dependency=True,
        )
    )
    assert status == "diagnostic_only"
    assert "cross_regime_stability_failure" in failures
    assert "bootstrap_interval_includes_zero" in failures


def test_deflated_sharpe_is_decimal_probability_and_penalizes_trials() -> None:
    returns = [Decimal(value) for value in ("0.02", "0.01", "0.03", "-0.01", "0.02", "0.01")]
    one_trial = deflated_sharpe_confidence(returns, trials=1)
    many_trials = deflated_sharpe_confidence(returns, trials=20)
    assert Decimal(0) <= many_trials <= one_trial <= Decimal(1)
