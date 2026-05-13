from __future__ import annotations

from datetime import datetime
from typing import Any

from sqlalchemy import and_, desc, func, select
from sqlalchemy.ext.asyncio import AsyncSession

from app.db.models.market import (
    StrategyRecommendation,
    StrategySignal,
    StrategySignalOutcome,
    StrategyTemplate,
)


class StrategyRepository:
    """Compatibility repository for legacy strategy templates and signals."""

    def __init__(self, session: AsyncSession) -> None:
        self.session = session

    async def upsert_strategy_template(self, template: StrategyTemplate) -> StrategyTemplate:
        existing = await self.get_strategy_template_by_key(template.template_key)
        if existing is None:
            self.session.add(template)
            await self.session.flush()
            return template
        for attr in (
            "display_name",
            "category",
            "family",
            "description",
            "direction",
            "entry_conditions",
            "exit_conditions",
            "risk_params_json",
            "applicable_instruments_json",
            "applicable_timeframes_json",
            "required_indicators_json",
            "strength_score",
            "confidence_ceiling",
            "is_enabled",
            "is_active",
            "version",
            "model_version",
        ):
            setattr(existing, attr, getattr(template, attr))
        await self.session.flush()
        return existing

    async def get_strategy_template_by_key(self, template_key: str) -> StrategyTemplate | None:
        result = await self.session.execute(
            select(StrategyTemplate).where(StrategyTemplate.template_key == template_key)
        )
        return result.scalar_one_or_none()

    async def get_all_strategy_templates(
        self,
        include_disabled: bool = False,
        only_active: bool = True,
    ) -> list[StrategyTemplate]:
        stmt = select(StrategyTemplate)
        if not include_disabled:
            stmt = stmt.where(StrategyTemplate.is_enabled.is_(True))
        if only_active:
            stmt = stmt.where(StrategyTemplate.is_active.is_(True))
        result = await self.session.execute(stmt.order_by(StrategyTemplate.template_key))
        return list(result.scalars().all())

    async def get_templates_by_category(
        self,
        category: str,
        include_disabled: bool = False,
    ) -> list[StrategyTemplate]:
        stmt = select(StrategyTemplate).where(StrategyTemplate.category == category)
        if not include_disabled:
            stmt = stmt.where(StrategyTemplate.is_enabled.is_(True))
        result = await self.session.execute(stmt.order_by(StrategyTemplate.template_key))
        return list(result.scalars().all())

    async def add_strategy_recommendation(
        self,
        recommendation: StrategyRecommendation,
    ) -> StrategyRecommendation:
        self.session.add(recommendation)
        await self.session.flush()
        return recommendation

    async def get_recommendation_by_id(
        self,
        recommendation_id: str,
    ) -> StrategyRecommendation | None:
        result = await self.session.execute(
            select(StrategyRecommendation).where(
                StrategyRecommendation.recommendation_id == recommendation_id
            )
        )
        return result.scalar_one_or_none()

    async def get_latest_recommendation(
        self,
        instrument_id: str,
        timeframe: str,
    ) -> StrategyRecommendation | None:
        result = await self.session.execute(
            select(StrategyRecommendation)
            .where(
                StrategyRecommendation.instrument_id == instrument_id,
                StrategyRecommendation.timeframe == timeframe,
            )
            .order_by(desc(StrategyRecommendation.recommendation_ts))
            .limit(1)
        )
        return result.scalar_one_or_none()

    async def get_recommendations(
        self,
        instrument_id: str | None = None,
        timeframe: str | None = None,
        direction: str | None = None,
        status: str | None = None,
        limit: int = 20,
    ) -> list[StrategyRecommendation]:
        stmt = select(StrategyRecommendation)
        if instrument_id:
            stmt = stmt.where(StrategyRecommendation.instrument_id == instrument_id)
        if timeframe:
            stmt = stmt.where(StrategyRecommendation.timeframe == timeframe)
        if direction:
            stmt = stmt.where(StrategyRecommendation.direction == direction)
        if status:
            stmt = stmt.where(StrategyRecommendation.status == status)
        result = await self.session.execute(
            stmt.order_by(desc(StrategyRecommendation.recommendation_ts)).limit(limit)
        )
        return list(result.scalars().all())

    async def update_recommendation_status(
        self,
        recommendation_id: str,
        status: str,
        **changes: Any,
    ) -> StrategyRecommendation | None:
        item = await self.get_recommendation_by_id(recommendation_id)
        if item is None:
            return None
        item.status = status
        for key, value in changes.items():
            setattr(item, key, value)
        await self.session.flush()
        return item

    async def upsert_strategy_signal(self, signal: StrategySignal) -> StrategySignal:
        existing = await self.get_strategy_signal(signal.signal_key, signal.signal_ts)
        if existing is None:
            self.session.add(signal)
            await self.session.flush()
            return signal
        for attr in (
            "recommendation_id",
            "template_key",
            "signal_type",
            "instrument_id",
            "timeframe",
            "direction",
            "signal_state",
            "confidence_score",
            "entry_price",
            "stop_loss_price",
            "take_profit_price",
            "risk_reward_ratio",
            "position_size_pct",
            "signal_source",
            "trigger_indicators_json",
            "context_snapshot_json",
            "market_condition_json",
            "metadata_json",
        ):
            setattr(existing, attr, getattr(signal, attr))
        await self.session.flush()
        return existing

    async def get_strategy_signal(
        self,
        signal_key: str,
        signal_ts: datetime,
    ) -> StrategySignal | None:
        result = await self.session.execute(
            select(StrategySignal).where(
                StrategySignal.signal_key == signal_key,
                StrategySignal.signal_ts == signal_ts,
            )
        )
        return result.scalar_one_or_none()

    async def get_recent_signals(
        self,
        instrument_id: str,
        timeframe: str | None = None,
        limit: int = 50,
    ) -> list[StrategySignal]:
        stmt = select(StrategySignal).where(StrategySignal.instrument_id == instrument_id)
        if timeframe:
            stmt = stmt.where(StrategySignal.timeframe == timeframe)
        result = await self.session.execute(
            stmt.order_by(desc(StrategySignal.signal_ts)).limit(limit)
        )
        return list(result.scalars().all())

    async def upsert_signal_outcome(
        self,
        outcome: StrategySignalOutcome,
    ) -> StrategySignalOutcome:
        existing = await self.get_signal_outcome(outcome.signal_key, outcome.signal_ts)
        if existing is None:
            self.session.add(outcome)
            await self.session.flush()
            return outcome
        for attr in (
            "signal_type",
            "recommendation_id",
            "instrument_id",
            "timeframe",
            "direction",
            "entry_ref_price",
            "exit_price",
            "outcome_status",
            "return_1",
            "return_3",
            "return_6",
            "return_12",
            "return_24",
            "mfe",
            "mae",
            "stop_hit_first",
            "take_profit_hit_first",
            "confirmation_hit",
            "invalidation_hit",
            "trailing_stop_activated",
            "atr_at_entry",
            "atr_at_exit",
            "risk_reward_actual",
            "payload_json",
        ):
            setattr(existing, attr, getattr(outcome, attr))
        await self.session.flush()
        return existing

    async def get_signal_outcome(
        self,
        signal_key: str,
        signal_ts: datetime,
    ) -> StrategySignalOutcome | None:
        result = await self.session.execute(
            select(StrategySignalOutcome).where(
                StrategySignalOutcome.signal_key == signal_key,
                StrategySignalOutcome.signal_ts == signal_ts,
            )
        )
        return result.scalar_one_or_none()

    async def get_outcomes_by_instrument(
        self,
        instrument_id: str,
        timeframe: str | None = None,
        limit: int = 100,
    ) -> list[StrategySignalOutcome]:
        stmt = select(StrategySignalOutcome).where(
            StrategySignalOutcome.instrument_id == instrument_id
        )
        if timeframe:
            stmt = stmt.where(StrategySignalOutcome.timeframe == timeframe)
        result = await self.session.execute(
            stmt.order_by(desc(StrategySignalOutcome.signal_ts)).limit(limit)
        )
        return list(result.scalars().all())

    async def get_template_performance(
        self,
        template_key: str | None = None,
        from_ts: datetime | None = None,
    ) -> dict[str, Any]:
        stmt = select(
            StrategySignal.template_key,
            func.count(StrategySignal.id).label("signal_count"),
        ).group_by(StrategySignal.template_key)
        if template_key:
            stmt = stmt.where(StrategySignal.template_key == template_key)
        if from_ts:
            stmt = stmt.where(StrategySignal.signal_ts >= from_ts)
        result = await self.session.execute(stmt)
        return {
            str(row.template_key or "unknown"): {"signal_count": int(row.signal_count or 0)}
            for row in result.all()
        }

    async def get_direction_win_rates(
        self,
        instrument_id: str | None = None,
        timeframe: str | None = None,
    ) -> list[dict[str, Any]]:
        conditions = []
        if instrument_id:
            conditions.append(StrategySignalOutcome.instrument_id == instrument_id)
        if timeframe:
            conditions.append(StrategySignalOutcome.timeframe == timeframe)
        stmt = select(
            StrategySignalOutcome.direction,
            func.count(StrategySignalOutcome.id).label("total"),
        ).group_by(StrategySignalOutcome.direction)
        if conditions:
            stmt = stmt.where(and_(*conditions))
        result = await self.session.execute(stmt)
        return [
            {"direction": row.direction, "total": int(row.total or 0), "win_rate": None}
            for row in result.all()
        ]
