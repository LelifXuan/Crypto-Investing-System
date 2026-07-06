from __future__ import annotations

from dataclasses import dataclass
from typing import Any

from app.services.strategy_signal.risk_reward import (
    clamp,
    compute_risk_reward,
    number,
    risk_reward_score_ev,  # NEW
    round2,
)


@dataclass(slots=True)
class DirectionScores:
    data_quality_score: float
    long_score: float
    short_score: float
    neutral_score: float
    confidence: float
    conflict_score: float
    rr_long: float | None
    rr_short: float | None
    long_penalty: float
    short_penalty: float

    def as_dict(self) -> dict[str, Any]:
        return {
            "data_quality_score": round2(self.data_quality_score),
            "long_score": round2(self.long_score),
            "short_score": round2(self.short_score),
            "neutral_score": round2(self.neutral_score),
            "confidence": round2(self.confidence),
            "conflict_score": round2(self.conflict_score),
            "RR_long": round(self.rr_long, 2) if self.rr_long is not None else None,
            "RR_short": round(self.rr_short, 2) if self.rr_short is not None else None,
            "long_penalty": round2(self.long_penalty),
            "short_penalty": round2(self.short_penalty),
        }


def weighted_score(values: dict[str, Any], weights: dict[str, float]) -> float:
    return clamp(sum(clamp(values.get(key, 0)) * weight for key, weight in weights.items()))


def weighted_score_skip(
    values: dict[str, Any], weights: dict[str, float]
) -> float:
    """Variant of weighted_score that skips slots with None values.

    Used by V1.7.6 funding_pressure slots when V2 derivatives_regime is
    degraded. The remaining slots are renormalized so the total weight
    contribution equals sum(weights.values()), avoiding score inflation.

    Returns 50.0 if all slots are None (degraded fallback).
    """
    used_pairs: list[tuple[float, float]] = []
    target_weight_sum = sum(weights.values())
    for key, weight in weights.items():
        value = values.get(key)
        if value is None:
            continue
        used_pairs.append((clamp(value), weight))
    if not used_pairs:
        return 50.0
    used_weight_sum = sum(w for _, w in used_pairs)
    if used_weight_sum <= 0:
        return 50.0
    raw = sum(v * w for v, w in used_pairs) / used_weight_sum * target_weight_sum
    return clamp(raw)


class DirectionScoringEngine:
    def __init__(self, config: dict[str, Any]) -> None:
        self.config = config

    def compute(self, snapshot: dict[str, Any]) -> DirectionScores:
        data_quality = weighted_score(
            snapshot,
            self.config["data_quality_weights"],
        )
        rr_long = compute_risk_reward(
            "long",
            number(snapshot.get("long_entry") or snapshot.get("current_price")),
            number(snapshot.get("long_stop")),
            number(snapshot.get("long_tp1")),
        )
        rr_short = compute_risk_reward(
            "short",
            number(snapshot.get("short_entry") or snapshot.get("current_price")),
            number(snapshot.get("short_stop")),
            number(snapshot.get("short_tp1")),
        )

        long_values = dict(snapshot)
        p_win = snapshot.get("setup_probability", 0.5)
        long_values["long_risk_reward"] = risk_reward_score_ev(
            snapshot.get("long_risk_reward"), p_win
        )
        short_values = dict(snapshot)
        short_values["short_risk_reward"] = risk_reward_score_ev(
            snapshot.get("short_risk_reward"), p_win
        )

        # V1.7.6: weighted_score_skip handles degraded funding slots
        # (when V2 derivatives_regime is missing) by skipping None values
        # and renormalizing remaining slots to original weight sum.
        raw_long = weighted_score_skip(long_values, self.config["long_weights"])
        raw_short = weighted_score_skip(short_values, self.config["short_weights"])
        long_penalty = self._long_penalty(snapshot)
        short_penalty = self._short_penalty(snapshot)

        long_score = clamp(raw_long - long_penalty)
        short_score = clamp(raw_short - short_penalty)
        gap = abs(long_score - short_score)

        neutral_values = dict(snapshot)
        neutral_values["low_directional_spread"] = 100 - clamp(gap)
        neutral_values["high_conflict_score"] = max(
            clamp(snapshot.get("conflict_score", 0)),
            min(long_score, short_score),
        )
        neutral_values["event_uncertainty"] = clamp(snapshot.get("event_risk_score", 0))
        neutral_score = weighted_score(neutral_values, self.config["neutral_weights"])
        conflict_score = clamp(max(neutral_values["high_conflict_score"], 100 - gap * 1.4))
        confidence = clamp(
            max(long_score, short_score) - neutral_score * 0.18 - conflict_score * 0.08
        )

        return DirectionScores(
            data_quality_score=data_quality,
            long_score=long_score,
            short_score=short_score,
            neutral_score=neutral_score,
            confidence=confidence,
            conflict_score=conflict_score,
            rr_long=rr_long,
            rr_short=rr_short,
            long_penalty=long_penalty,
            short_penalty=short_penalty,
        )

    @staticmethod
    def _long_penalty(snapshot: dict[str, Any]) -> float:
        return clamp(
            0.18 * clamp(snapshot.get("funding_crowding_score", 0))
            + 0.15 * clamp(snapshot.get("opposite_divergence_risk_score", 0))
            + 0.10 * clamp(snapshot.get("late_entry_risk_score", 0))
            + 0.12 * clamp(snapshot.get("event_risk_score", 0)),
            0,
            40,
        )

    @staticmethod
    def _short_penalty(snapshot: dict[str, Any]) -> float:
        return clamp(
            0.12 * clamp(snapshot.get("funding_crowding_score", 0))
            + 0.15 * clamp(snapshot.get("opposite_divergence_risk_score", 0))
            + 0.10 * clamp(snapshot.get("late_entry_risk_score", 0))
            + 0.12 * clamp(snapshot.get("event_risk_score", 0)),
            0,
            40,
        )
