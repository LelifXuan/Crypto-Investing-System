from __future__ import annotations

from dataclasses import dataclass
from datetime import UTC, datetime, timedelta
from decimal import Decimal
from typing import Any, Sequence

from app.db.models.market import IndicatorObservation
from app.repositories.market_repository import MarketRepository

ONCHAIN_TTL = timedelta(hours=24)
CORE_ONCHAIN_KEYS = {
    "defi_total_tvl",
    "stablecoin_total_mcap",
    "dex_volume_24h",
    "protocol_fees_24h",
}
# Keys whose HISTORY backs derived capital-flow change features. Direction may
# only come from change/trend/deviation, never from an absolute positive level
# (P1-QNT-002 / INV-002). 64 samples per key is enough to locate a ~1d and a
# ~7d reference point without scanning the whole table.
FLOW_SERIES_KEYS = {"stablecoin_total_mcap", "dex_volume_24h"}
FLOW_SERIES_LIMIT_PER_KEY = 64
# (label, target age in days, tolerance in days) for reference-point lookup.
FLOW_CHANGE_WINDOWS = (("1d", 1.0, 0.75), ("7d", 7.0, 2.0))
_FLOW_SHORT_NAME = {"stablecoin_total_mcap": "stablecoin", "dex_volume_24h": "dex_volume"}


@dataclass(frozen=True)
class OnchainFeatureRead:
    features: dict[str, Any]
    dependency: dict[str, Any]


class OnchainFeatureEngine:
    """Normalize already-collected monitoring observations for strategy use.

    This layer deliberately does not call any external on-chain provider. It
    consumes the monitoring/onchain observations produced by the secondary
    monitoring surface and exposes a compact, strategy-facing feature payload.
    """

    def __init__(self, repository: MarketRepository) -> None:
        self.repository = repository

    async def build(self, *, now: datetime | None = None) -> OnchainFeatureRead:
        now = now or datetime.now(UTC)
        if not hasattr(self.repository, "list_latest_observations_by_key"):
            return self._missing(now)
        observations = await self.repository.list_latest_observations_by_key(
            category="onchain",
            limit_per_key=FLOW_SERIES_LIMIT_PER_KEY,
        )
        if not observations:
            return self._missing(now)

        latest_by_key: dict[str, IndicatorObservation] = {}
        for item in observations:
            latest_by_key.setdefault(item.indicator_key, item)
        latest_ts = max(self._aware(item.observation_ts) for item in observations)
        age_seconds = max(0, int((now - latest_ts).total_seconds()))
        missing = sorted(CORE_ONCHAIN_KEYS - set(latest_by_key))
        metrics = {
            key: self._metric_payload(item, now) for key, item in latest_by_key.items()
        }
        stale = age_seconds > int(ONCHAIN_TTL.total_seconds())
        cache_state = "stale" if stale else "fresh"
        bias, score, confidence, summary = self._infer_state(
            observations,
            missing_inputs=missing,
            stale=stale,
        )
        features = {
            "state": "ONCHAIN_STALE" if stale else "ONCHAIN_AVAILABLE",
            "bias": bias,
            "summary": summary,
            "score": score,
            "confidence": confidence,
            "data_status": "stale" if stale else "fresh",
            "metrics": metrics,
            "capital_flow_inputs": self._capital_flow_inputs(observations, now),
            "missing_inputs": missing,
            "source_page": "monitoring/onchain",
            "source_modules": ["IndicatorObservation", "IndicatorMonitoringService"],
            "source_updated_at": latest_ts.isoformat(),
            "source_age_seconds": age_seconds,
        }
        return OnchainFeatureRead(
            features=features,
            dependency=self._dependency(cache_state, latest_ts, age_seconds),
        )

    @staticmethod
    def _missing(now: datetime) -> OnchainFeatureRead:
        missing = sorted(CORE_ONCHAIN_KEYS)
        features = {
            "state": "ONCHAIN_UPSTREAM_MISSING",
            "bias": "NEUTRAL",
            "summary": "上游监控页未产出链上数据，链上维度本轮不参与强方向判断。",
            "score": 0,
            "confidence": 0,
            "data_status": "upstream_missing",
            "metrics": {},
            "capital_flow_inputs": {"available": False},
            "missing_inputs": missing,
            "source_page": "monitoring/onchain",
            "source_modules": ["IndicatorObservation"],
            "source_updated_at": None,
            "source_age_seconds": None,
        }
        return OnchainFeatureRead(
            features=features,
            dependency={
                "source_page": "monitoring/onchain",
                "cache_state": "upstream_missing",
                "freshness_state": "upstream_missing",
                "source_updated_at": None,
                "source_age_seconds": None,
                "missing_inputs": missing,
            },
        )

    @staticmethod
    def _capital_flow_inputs(
        observations: Sequence[IndicatorObservation], now: datetime
    ) -> dict[str, Any]:
        """Derive change features for capital-flow direction from real history.

        Direction may only be inferred from change/trend/deviation (INV-002).
        When history does not contain a usable reference point (~1d / ~7d
        older), the change feature stays ``None`` — consumers must treat that
        as DATA_INSUFFICIENT instead of reading the absolute level as flow.
        """
        series: dict[str, list[tuple[datetime, float]]] = {}
        for item in observations:
            if item.indicator_key not in FLOW_SERIES_KEYS:
                continue
            value = OnchainFeatureEngine._number(item.value_num)
            if value is None:
                continue
            series.setdefault(item.indicator_key, []).append(
                (OnchainFeatureEngine._aware(item.observation_ts), float(value))
            )
        inputs: dict[str, Any] = {"available": bool(series)}
        for key, points in series.items():
            short = _FLOW_SHORT_NAME[key]
            points.sort(key=lambda pair: pair[0])
            latest_ts, latest_value = points[-1]
            inputs[f"{short}_observed_at"] = latest_ts.isoformat()
            inputs[f"{short}_age_days"] = round(
                max(0.0, (now - latest_ts).total_seconds()) / 86400.0, 4
            )
            inputs[f"{short}_level"] = latest_value
            for label, days, tolerance in FLOW_CHANGE_WINDOWS:
                reference = OnchainFeatureEngine._reference_before(
                    points, latest_ts, days, tolerance
                )
                inputs[f"{short}_change_{label}_pct"] = (
                    None
                    if reference is None or reference == 0
                    else round((latest_value / reference - 1.0) * 100.0, 4)
                )
        return inputs

    @staticmethod
    def _reference_before(
        points: list[tuple[datetime, float]],
        latest_ts: datetime,
        days: float,
        tolerance_days: float,
    ) -> float | None:
        target = latest_ts - timedelta(days=days)
        best: tuple[float, float] | None = None
        for ts, value in points:
            distance = abs((ts - target).total_seconds())
            if distance <= tolerance_days * 86400.0 and (best is None or distance < best[0]):
                best = (distance, value)
        return None if best is None else best[1]

    @staticmethod
    def _metric_payload(item: IndicatorObservation, now: datetime) -> dict[str, Any]:
        ts = OnchainFeatureEngine._aware(item.observation_ts)
        return {
            "value": OnchainFeatureEngine._number(item.value_num),
            "signal_state": item.signal_state,
            "source_provider": item.source_provider,
            "source_ref": item.source_ref,
            "source_granularity": item.source_granularity,
            "quality_score": OnchainFeatureEngine._number(item.quality_score),
            "observation_ts": ts.isoformat(),
            "age_seconds": max(0, int((now - ts).total_seconds())),
            "value_json": dict(item.value_json or {}),
        }

    @staticmethod
    def _infer_state(
        observations: Sequence[IndicatorObservation],
        *,
        missing_inputs: list[str],
        stale: bool,
    ) -> tuple[str, float, float, str]:
        usable = [item for item in observations if item.value_num is not None]
        if not usable:
            return (
                "NEUTRAL",
                0.0,
                0.0,
                "链上 observations 已存在但缺少可用数值，链上维度本轮不参与强方向判断。",
            )
        quality_values = [OnchainFeatureEngine._float(item.quality_score, 0.0) for item in usable]
        coverage = len(set(item.indicator_key for item in usable)) / max(len(CORE_ONCHAIN_KEYS), 1)
        confidence = round(min(70.0, (sum(quality_values) / len(quality_values)) * coverage), 2)
        if stale:
            confidence = round(confidence * 0.55, 2)
        # Coverage breadth (distinct keys), not sample count, drives the score:
        # history depth must not look like broader metric coverage.
        distinct_keys = len({item.indicator_key for item in usable})
        score = round(45.0 + min(10.0, distinct_keys * 2.5), 2)
        status_text = "已过期，仅作低权重观察" if stale else "可参与低频链上确认"
        missing_text = f"；缺失 {', '.join(missing_inputs)}" if missing_inputs else ""
        return (
            "NEUTRAL",
            score,
            confidence,
                (
                    f"监控链上数据{status_text}，覆盖 "
                    f"{len(usable)}/{len(CORE_ONCHAIN_KEYS)} 个核心指标{missing_text}。"
                ),
        )

    @staticmethod
    def _dependency(
        cache_state: str,
        source_updated_at: datetime,
        age_seconds: int,
    ) -> dict[str, Any]:
        return {
            "source_page": "monitoring/onchain",
            "cache_state": cache_state,
            "freshness_state": cache_state,
            "source_updated_at": source_updated_at.isoformat(),
            "source_age_seconds": age_seconds,
        }

    @staticmethod
    def _aware(value: datetime) -> datetime:
        return value if value.tzinfo else value.replace(tzinfo=UTC)

    @staticmethod
    def _number(value: Decimal | float | int | None) -> float | None:
        if value is None:
            return None
        return float(value)

    @staticmethod
    def _float(value: Decimal | float | int | None, default: float) -> float:
        parsed = OnchainFeatureEngine._number(value)
        return default if parsed is None else parsed
