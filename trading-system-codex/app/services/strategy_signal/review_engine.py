from __future__ import annotations

from collections import Counter
from datetime import UTC, datetime
from typing import Any

from sqlalchemy import desc, select

from app.db.models.market import StrategySignal, StrategySignalOutcome
from app.repositories.market_repository import MarketRepository


class ReviewEngine:
    def __init__(self, repository: MarketRepository) -> None:
        self.repository = repository

    async def build_review(
        self,
        instrument_id: str | None = None,
        timeframe: str | None = None,
        *,
        limit: int = 100,
    ) -> dict[str, Any]:
        stmt = select(StrategySignal)
        if instrument_id:
            stmt = stmt.where(StrategySignal.instrument_id == instrument_id)
        if timeframe:
            stmt = stmt.where(StrategySignal.timeframe == timeframe)
        stmt = stmt.order_by(desc(StrategySignal.signal_ts)).limit(limit)
        result = await self.repository.session.execute(stmt)
        signals = list(result.scalars().all())
        signal_keys = [item.signal_key for item in signals]
        outcomes = []
        if signal_keys:
            outcome_result = await self.repository.session.execute(
                select(StrategySignalOutcome)
                .where(StrategySignalOutcome.signal_key.in_(signal_keys))
                .order_by(desc(StrategySignalOutcome.created_at))
                .limit(limit * 3)
            )
            outcomes = list(outcome_result.scalars().all())

        state_counts = Counter(item.signal_state for item in signals)
        direction_counts = Counter(item.direction for item in signals)
        review_counts = Counter(item.outcome_status for item in outcomes)
        latest = [
            {
                "signal_key": item.signal_key,
                "instrument_id": item.instrument_id,
                "timeframe": item.timeframe,
                "state": item.signal_state,
                "direction": item.direction,
                "confidence_score": float(item.confidence_score or 0),
                "risk_reward_ratio": float(item.risk_reward_ratio or 0),
                "signal_ts": item.signal_ts.isoformat(),
            }
            for item in signals[:10]
        ]
        return {
            "instrument_id": instrument_id,
            "timeframe": timeframe,
            "generated_at": datetime.now(UTC),
            "total_signals": len(signals),
            "total_decisions": len(signals),
            "state_counts": dict(state_counts),
            "action_counts": dict(state_counts),
            "direction_counts": dict(direction_counts),
            "outcome_counts": dict(review_counts),
            "outcome_windows": {},
            "confidence_buckets": self._confidence_buckets(signals),
            "latest_signals": latest,
            "latest_decisions": latest,
        }

    @staticmethod
    def _confidence_buckets(signals: list[StrategySignal]) -> dict[str, int]:
        buckets = {"0-40": 0, "40-60": 0, "60-75": 0, "75+": 0}
        for item in signals:
            score = float(item.confidence_score or 0)
            if score < 40:
                buckets["0-40"] += 1
            elif score < 60:
                buckets["40-60"] += 1
            elif score < 75:
                buckets["60-75"] += 1
            else:
                buckets["75+"] += 1
        return buckets

