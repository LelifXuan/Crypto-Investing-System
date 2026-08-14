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
            limit_per_key=1,
        )
        if not observations:
            return self._missing(now)

        latest_ts = max(self._aware(item.observation_ts) for item in observations)
        age_seconds = max(0, int((now - latest_ts).total_seconds()))
        missing = sorted(CORE_ONCHAIN_KEYS - {item.indicator_key for item in observations})
        metrics = {item.indicator_key: self._metric_payload(item, now) for item in observations}
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
        score = round(45.0 + min(10.0, len(usable) * 2.5), 2)
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
