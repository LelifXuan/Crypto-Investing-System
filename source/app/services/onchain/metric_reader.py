"""Shared contract reader for onchain metric payloads.

``OnchainFeatureEngine`` exposes ``features["metrics"][key]`` as a mapping
with ``value / signal_state / source_provider / quality_score / observation_ts
/ age_seconds``. Strategy engines must not guess this schema (P1-QNT-002):
they read it through this helper, which applies per-metric freshness and
quality gates instead of trusting the outer context cache state — an outer
context rebuilt moments ago does not make an old observation fresh.
"""

from __future__ import annotations

from dataclasses import dataclass
from typing import Any, Mapping

# A flow observation older than 3 days cannot back a directional claim; a
# quality score below 0.5 (0..1 scale, as produced by the monitoring surface)
# degrades the metric to unusable.
DEFAULT_MAX_AGE_SECONDS = 3 * 24 * 3600.0
DEFAULT_MIN_QUALITY = 0.5


@dataclass(frozen=True)
class MetricReading:
    key: str
    value: float | None
    quality_score: float | None
    observation_ts: str
    age_seconds: float | None
    fresh: bool
    usable: bool
    unusable_reason: str = ""


def _to_float(value: Any) -> float | None:
    if value is None or isinstance(value, bool) or value == "":
        return None
    try:
        return float(value)
    except (TypeError, ValueError):
        return None


def read_metric(
    metrics: Any,
    key: str,
    *,
    max_age_seconds: float = DEFAULT_MAX_AGE_SECONDS,
    min_quality: float = DEFAULT_MIN_QUALITY,
) -> MetricReading:
    """Read one metric under the documented payload contract, fail closed."""
    payload = metrics.get(key) if isinstance(metrics, Mapping) else None
    if not isinstance(payload, Mapping):
        return MetricReading(key, None, None, "", None, False, False, "missing_or_invalid_payload")
    value = _to_float(payload.get("value"))
    quality = _to_float(payload.get("quality_score"))
    age = _to_float(payload.get("age_seconds"))
    base = {
        "key": key,
        "value": value,
        "quality_score": quality,
        "observation_ts": str(payload.get("observation_ts") or ""),
        "age_seconds": age,
        "fresh": age is not None and age <= max_age_seconds,
    }
    if value is None:
        return MetricReading(**base, usable=False, unusable_reason="missing_value")
    if quality is not None and quality < min_quality:
        return MetricReading(**base, usable=False, unusable_reason="low_quality")
    if not base["fresh"]:
        return MetricReading(**base, usable=False, unusable_reason="stale_observation")
    return MetricReading(**base, usable=True)
