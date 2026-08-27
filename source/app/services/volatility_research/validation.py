from __future__ import annotations

import hashlib
import json
import random
from dataclasses import asdict, dataclass
from datetime import datetime
from decimal import Decimal
from itertools import combinations
from math import sqrt
from statistics import NormalDist
from typing import Sequence

ZERO = Decimal(0)


@dataclass(frozen=True, slots=True)
class DatasetManifest:
    dataset_id: str
    source: str
    first_event_time: datetime
    last_event_time: datetime
    retrieved_at: datetime
    observation_count: int
    missing_count: int
    methodology_version: str
    license_status: str
    observed_or_backtested: str
    content_sha256: str

    @classmethod
    def build(
        cls,
        *,
        dataset_id: str,
        source: str,
        event_times: Sequence[datetime],
        retrieved_at: datetime,
        missing_count: int,
        methodology_version: str,
        license_status: str,
        observed_or_backtested: str,
        canonical_rows: Sequence[dict[str, str]],
    ) -> DatasetManifest:
        if not event_times:
            raise ValueError("dataset manifest requires event timestamps")
        payload = json.dumps(list(canonical_rows), sort_keys=True, separators=(",", ":"))
        return cls(
            dataset_id=dataset_id,
            source=source,
            first_event_time=min(event_times),
            last_event_time=max(event_times),
            retrieved_at=retrieved_at,
            observation_count=len(event_times),
            missing_count=missing_count,
            methodology_version=methodology_version,
            license_status=license_status,
            observed_or_backtested=observed_or_backtested,
            content_sha256=hashlib.sha256(payload.encode("utf-8")).hexdigest(),
        )

    def as_dict(self) -> dict:
        payload = asdict(self)
        for key in ("first_event_time", "last_event_time", "retrieved_at"):
            payload[key] = payload[key].isoformat()
        return payload


def validate_point_in_time(
    event_time: datetime, available_at: datetime, decision_time: datetime
) -> bool:
    if any(value.tzinfo is None for value in (event_time, available_at, decision_time)):
        return False
    return event_time <= available_at <= decision_time


def anchored_walk_forward_splits(
    observation_count: int, *, minimum_train: int, test_size: int
) -> list[tuple[range, range]]:
    if minimum_train < 1 or test_size < 1:
        raise ValueError("split sizes must be positive")
    output: list[tuple[range, range]] = []
    train_end = minimum_train
    while train_end + test_size <= observation_count:
        output.append((range(0, train_end), range(train_end, train_end + test_size)))
        train_end += test_size
    return output


def cpcv_splits(
    observation_count: int, *, groups: int, test_groups: int, embargo: int = 0
) -> list[tuple[tuple[int, ...], tuple[int, ...]]]:
    if groups < 2 or not 0 < test_groups < groups or embargo < 0:
        raise ValueError("invalid CPCV parameters")
    group_size = observation_count // groups
    if group_size < 1:
        raise ValueError("not enough observations for CPCV groups")
    grouped = [
        tuple(
            range(
                index * group_size,
                observation_count if index == groups - 1 else (index + 1) * group_size,
            )
        )
        for index in range(groups)
    ]
    output = []
    for selected in combinations(range(groups), test_groups):
        test = tuple(item for index in selected for item in grouped[index])
        excluded = set(test)
        for item in test:
            excluded.update(
                range(
                    max(0, item - embargo),
                    min(observation_count, item + embargo + 1),
                )
            )
        train = tuple(index for index in range(observation_count) if index not in excluded)
        output.append((train, test))
    return output


def block_bootstrap_mean_interval(
    values: Sequence[Decimal],
    *,
    block_size: int,
    samples: int = 1000,
    confidence: Decimal = Decimal("0.95"),
    seed: int = 1729,
) -> tuple[Decimal, Decimal]:
    if not values or block_size < 1 or samples < 2 or not ZERO < confidence < Decimal(1):
        raise ValueError("invalid block bootstrap inputs")
    generator = random.Random(seed)
    source = list(values)
    means: list[Decimal] = []
    for _ in range(samples):
        sample: list[Decimal] = []
        while len(sample) < len(source):
            start = generator.randrange(len(source))
            sample.extend(source[(start + offset) % len(source)] for offset in range(block_size))
        sample = sample[: len(source)]
        means.append(sum(sample, ZERO) / Decimal(len(sample)))
    means.sort()
    tail = (Decimal(1) - confidence) / Decimal(2)
    lower_index = int(tail * Decimal(samples - 1))
    upper_index = int((Decimal(1) - tail) * Decimal(samples - 1))
    return means[lower_index], means[upper_index]


def probability_of_backtest_overfitting(
    train_scores: Sequence[Sequence[Decimal]], test_scores: Sequence[Sequence[Decimal]]
) -> Decimal:
    if not train_scores or len(train_scores) != len(test_scores):
        raise ValueError("PBO requires matched train/test paths")
    failures = 0
    for train, test in zip(train_scores, test_scores, strict=True):
        if not train or len(train) != len(test):
            raise ValueError("each PBO path requires matched candidate scores")
        winner = max(range(len(train)), key=lambda index: train[index])
        ordered_test = sorted(test)
        median = ordered_test[len(ordered_test) // 2]
        failures += int(test[winner] < median)
    return Decimal(failures) / Decimal(len(train_scores))


def deflated_sharpe_confidence(
    returns: Sequence[Decimal],
    *,
    trials: int,
    sharpe_trials_std: Decimal = Decimal(1),
) -> Decimal:
    """Bailey/Lopez de Prado style DSR probability against trial inflation.

    The result is diagnostic research metadata. Inputs and persisted output are
    Decimal; ``NormalDist`` is used only for the normal CDF/inverse CDF.
    """

    if len(returns) < 4 or trials < 1 or sharpe_trials_std <= ZERO:
        raise ValueError("DSR requires at least four returns and one trial")
    values = [float(value) for value in returns]
    count = len(values)
    mean = sum(values) / count
    variance = sum((value - mean) ** 2 for value in values) / (count - 1)
    if variance <= 0:
        return Decimal(0)
    standard_deviation = sqrt(variance)
    sharpe = mean / standard_deviation
    skew = sum(((value - mean) / standard_deviation) ** 3 for value in values) / count
    kurtosis = sum(((value - mean) / standard_deviation) ** 4 for value in values) / count
    if trials == 1:
        expected_max_sharpe = 0.0
    else:
        normal = NormalDist()
        euler_gamma = 0.5772156649015329
        expected_max_sharpe = float(sharpe_trials_std) * (
            (1 - euler_gamma) * normal.inv_cdf(1 - 1 / trials)
            + euler_gamma * normal.inv_cdf(1 - 1 / (trials * 2.718281828459045))
        )
    denominator = sqrt(
        max(
            1e-12,
            1 - skew * sharpe + ((kurtosis - 1) / 4) * sharpe * sharpe,
        )
    )
    statistic = (sharpe - expected_max_sharpe) * sqrt(count - 1) / denominator
    return Decimal(str(NormalDist().cdf(statistic)))


@dataclass(frozen=True, slots=True)
class PromotionEvidence:
    point_in_time_valid: bool
    independent_years_or_regimes: int
    consistent_effect: bool
    bootstrap_lower: Decimal
    bootstrap_upper: Decimal
    dsr_confidence: Decimal
    pbo: Decimal
    other_primary_risk_degradation: Decimal
    single_source_dependency: bool
    single_parameter_dependency: bool


def promotion_status(evidence: PromotionEvidence) -> tuple[str, list[str]]:
    failures: list[str] = []
    if not evidence.point_in_time_valid:
        failures.append("look_ahead_or_timestamp_failure")
    if evidence.independent_years_or_regimes < 3 or not evidence.consistent_effect:
        failures.append("cross_regime_stability_failure")
    if evidence.bootstrap_lower <= ZERO <= evidence.bootstrap_upper:
        failures.append("bootstrap_interval_includes_zero")
    if evidence.dsr_confidence < Decimal("0.95"):
        failures.append("dsr_below_95pct")
    if evidence.pbo > Decimal("0.50"):
        failures.append("pbo_above_0_50")
    if evidence.other_primary_risk_degradation > Decimal("0.05"):
        failures.append("other_primary_risk_degradation_above_5pct")
    if evidence.single_source_dependency:
        failures.append("single_source_dependency")
    if evidence.single_parameter_dependency:
        failures.append("single_parameter_dependency")
    return ("accepted", []) if not failures else ("diagnostic_only", failures)
