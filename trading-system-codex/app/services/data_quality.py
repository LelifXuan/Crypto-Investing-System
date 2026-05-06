from __future__ import annotations

from dataclasses import dataclass, field
from datetime import UTC, datetime
from decimal import Decimal

from app.core.decimal_utils import DECIMAL_ZERO


@dataclass(slots=True)
class DataQualityAssessment:
    data_quality_score: float
    status: str
    issues: list[str] = field(default_factory=list)
    can_analyze: bool = True
    can_alert: bool = True
    latest_ts: datetime | None = None


class DataQualityMonitor:
    def assess_candles(
        self,
        candles: list,
        *,
        expected_min_points: int = 50,
        stale_after_seconds: int | None = None,
        now: datetime | None = None,
    ) -> DataQualityAssessment:
        score = 1.0
        issues: list[str] = []
        can_analyze = True
        can_alert = True
        latest_ts = candles[-1].ts_open if candles else None

        if len(candles) < expected_min_points:
            score -= 0.35
            issues.append("candles_insufficient")
            can_alert = False
        if not candles:
            return DataQualityAssessment(
                data_quality_score=0.0,
                status="missing",
                issues=["candles_missing"],
                can_analyze=False,
                can_alert=False,
                latest_ts=None,
            )

        zero_volume_ratio = sum(
            1
            for candle in candles
            if Decimal(str(getattr(candle, "volume", DECIMAL_ZERO) or DECIMAL_ZERO)) <= 0
        ) / max(len(candles), 1)
        if zero_volume_ratio >= 0.35:
            score -= 0.15
            issues.append("volume_sparse")

        flat_ratio = sum(
            1
            for candle in candles
            if Decimal(str(getattr(candle, "high", DECIMAL_ZERO)))
            == Decimal(str(getattr(candle, "low", DECIMAL_ZERO)))
        ) / max(len(candles), 1)
        if flat_ratio >= 0.20:
            score -= 0.15
            issues.append("price_flat_segments")

        if stale_after_seconds is not None and latest_ts is not None:
            now = now or datetime.now(UTC)
            latest = latest_ts if latest_ts.tzinfo else latest_ts.replace(tzinfo=UTC)
            age_seconds = (now - latest).total_seconds()
            if age_seconds > stale_after_seconds:
                score -= 0.2
                issues.append("stale")
                can_alert = False

        score = max(score, 0.0)
        if score < 0.35:
            status = "bad"
            can_analyze = False
            can_alert = False
        elif score < 0.6:
            status = "degraded"
            can_alert = False
        elif score < 0.8:
            status = "fair"
        else:
            status = "good"
        return DataQualityAssessment(
            data_quality_score=round(score * 100, 2),
            status=status,
            issues=issues,
            can_analyze=can_analyze,
            can_alert=can_alert,
            latest_ts=latest_ts,
        )
