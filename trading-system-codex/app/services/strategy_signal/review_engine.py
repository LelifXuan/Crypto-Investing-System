from __future__ import annotations

import logging
from collections import Counter
from datetime import UTC, datetime
from typing import Any

from sqlalchemy import desc, select

from app.db.models.market import StrategySignal, StrategySignalOutcome
from app.repositories.market_repository import MarketRepository
from app.services.strategy_signal.outcome_engine import StrategyOutcomeEngine

logger = logging.getLogger(__name__)


class ReviewEngine:
    def __init__(self, repository: MarketRepository) -> None:
        self.repository = repository

    async def build_review(
        self,
        instrument_id: str | None = None,
        timeframe: str | None = None,
        *,
        limit: int = 100,
        update_outcomes: bool = True,
    ) -> dict[str, Any]:
        if update_outcomes:
            try:
                await StrategyOutcomeEngine(self.repository).update_signal_outcomes(
                    instrument_id=instrument_id,
                    timeframe=timeframe,
                    limit=limit,
                )
            except Exception:
                logger.exception("failed to update strategy signal outcomes before review")

        stmt = select(StrategySignal).where(
            StrategySignal.signal_type == "market_strategy_signal"
        )
        if instrument_id:
            stmt = stmt.where(StrategySignal.instrument_id == instrument_id)
        if timeframe:
            stmt = stmt.where(StrategySignal.timeframe == timeframe)
        stmt = stmt.order_by(desc(StrategySignal.signal_ts)).limit(limit)
        result = await self.repository.session.execute(stmt)
        signals = list(result.scalars().all())

        signal_keys = [item.signal_key for item in signals]
        outcomes_by_key: dict[str, StrategySignalOutcome] = {}
        if signal_keys:
            outcome_result = await self.repository.session.execute(
                select(StrategySignalOutcome)
                .where(StrategySignalOutcome.signal_key.in_(signal_keys))
            )
            for o in outcome_result.scalars().all():
                outcomes_by_key[o.signal_key] = o

        state_counts = Counter(item.signal_state for item in signals)
        direction_counts = Counter(item.direction for item in signals)
        outcome_statuses = [o.outcome_status for o in outcomes_by_key.values()]
        outcome_counts = Counter(outcome_statuses)

        latest_records = self._build_latest_records(signals, outcomes_by_key)

        cls = sum(1 for o in outcomes_by_key.values() if o.outcome_status not in ("active", "insufficient_data"))
        tp1_hits = outcome_counts.get("tp1_hit", 0) + outcome_counts.get("tp2_hit", 0)
        sl_hits = outcome_counts.get("stop_hit", 0)
        mfes = [float(o.mfe or 0) for o in outcomes_by_key.values() if o.mfe is not None]
        maes = [float(o.mae or 0) for o in outcomes_by_key.values() if o.mae is not None]

        summary = {
            "total_signals": len(signals),
            "closed_signals": cls,
            "active_signals": len(signals) - cls,
            "tp1_hit_rate": round(tp1_hits / cls * 100, 1) if cls > 0 else 0,
            "stop_hit_rate": round(sl_hits / cls * 100, 1) if cls > 0 else 0,
            "expectation_match_rate": round(
                sum(1 for o in outcomes_by_key.values()
                    if o.outcome_status in ("tp1_hit", "tp2_hit", "active")) / cls * 100, 1
            ) if cls > 0 else 0,
            "avg_mfe": round(sum(mfes) / len(mfes) * 100, 2) if mfes else 0,
            "avg_mae": round(sum(maes) / len(maes) * 100, 2) if maes else 0,
        }

        review_warnings: list[str] = []
        ambiguous_count = sum(
            1
            for o in outcomes_by_key.values()
            if (o.payload_json or {}).get("hit_order") == "ambiguous_same_bar"
        )
        if ambiguous_count > 0:
            review_warnings.append(
                f"有 {ambiguous_count} 条在同根 K 线内 TP/SL 同时触及，缺少更低周期确认"
            )
        if outcome_counts.get("insufficient_data", 0) > 0:
            review_warnings.append(
                f"有 {outcome_counts['insufficient_data']} 条后续 K 线不足，无法评估"
            )

        by_state = {k: v for k, v in state_counts.items()}
        by_direction = {k: v for k, v in direction_counts.items()}
        by_outcome = {k: v for k, v in outcome_counts.items()}

        return {
            "instrument_id": instrument_id,
            "timeframe": timeframe,
            "generated_at": datetime.now(UTC),
            "summary": summary,
            "latest_records": latest_records,
            "outcome_windows": {"1bar": {}, "3bar": {}, "6bar": {}, "12bar": {}, "24bar": {}},
            "by_state": by_state,
            "by_direction": by_direction,
            "by_outcome": by_outcome,
            "review_warnings": review_warnings,
            "total_signals": len(signals),
            "state_counts": dict(state_counts),
            "direction_counts": dict(direction_counts),
            "outcome_counts": dict(outcome_counts),
            "confidence_buckets": self._confidence_buckets(signals),
            "latest_signals": latest_records,
        }

    def _build_latest_records(
        self,
        signals: list[StrategySignal],
        outcomes: dict[str, StrategySignalOutcome],
    ) -> list[dict[str, Any]]:
        records = []
        for item in signals[:30]:
            o = outcomes.get(item.signal_key)
            record = {
                "signal_key": item.signal_key,
                "instrument_id": item.instrument_id,
                "timeframe": item.timeframe,
                "state": item.signal_state,
                "direction": item.direction,
                "confidence_score": float(item.confidence_score or 0),
                "risk_reward_ratio": float(item.risk_reward_ratio or 0),
                "entry_price": float(item.entry_price) if item.entry_price else None,
                "stop_loss_price": float(item.stop_loss_price) if item.stop_loss_price else None,
                "take_profit_price": float(item.take_profit_price) if item.take_profit_price else None,
                "signal_ts": item.signal_ts.isoformat(),
                "signal_source": item.signal_source,
            }
            if o is not None:
                record["outcome_status"] = o.outcome_status
                record["return_1"] = float(o.return_1) if o.return_1 is not None else None
                record["return_6"] = float(o.return_6) if o.return_6 is not None else None
                record["return_24"] = float(o.return_24) if o.return_24 is not None else None
                record["mfe"] = float(o.mfe) if o.mfe is not None else None
                record["mae"] = float(o.mae) if o.mae is not None else None
                record["stop_hit_first"] = o.stop_hit_first
                record["take_profit_hit_first"] = o.take_profit_hit_first
                record["hit_ambiguous"] = (
                    o.payload_json.get("hit_order") == "ambiguous_same_bar"
                    if o.payload_json else False
                )
            else:
                record["outcome_status"] = "pending"
                record["return_1"] = None
                record["return_6"] = None
                record["return_24"] = None
                record["mfe"] = None
                record["mae"] = None
                record["stop_hit_first"] = None
                record["take_profit_hit_first"] = None
                record["hit_ambiguous"] = False
            records.append(record)
        return records

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
