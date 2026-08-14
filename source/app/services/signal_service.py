from __future__ import annotations

from datetime import datetime, timezone
from decimal import Decimal
from typing import Any
from uuid import uuid4

from sqlalchemy.ext.asyncio import AsyncSession

from app.db.models.market import (
    StrategyRecommendation,
    StrategySignal,
    StrategySignalOutcome,
    StrategyTemplate,
)
from app.repositories.signal_repository import StrategyRepository


class StrategyService:
    """Legacy strategy template/recommendation service kept for compatibility."""

    def __init__(self, session: AsyncSession) -> None:
        self.repository = StrategyRepository(session)
        self.session = session

    async def register_template(
        self,
        template_key: str,
        display_name: str,
        category: str,
        family: str,
        direction: str,
        entry_conditions: list,
        exit_conditions: list,
        description: str | None = None,
        risk_params: dict | None = None,
        applicable_instruments: list | None = None,
        applicable_timeframes: list | None = None,
        required_indicators: list | None = None,
        strength_score: float = 0,
        confidence_ceiling: float = 100,
        is_enabled: bool = True,
        is_active: bool = True,
        version: str = "v1",
        model_version: str = "legacy",
    ) -> StrategyTemplate:
        template = StrategyTemplate(
            template_key=template_key,
            display_name=display_name,
            category=category,
            family=family,
            description=description,
            direction=direction,
            entry_conditions=entry_conditions,
            exit_conditions=exit_conditions,
            risk_params_json=risk_params or {},
            applicable_instruments_json=applicable_instruments or [],
            applicable_timeframes_json=applicable_timeframes or [],
            required_indicators_json=required_indicators or [],
            strength_score=Decimal(str(strength_score)),
            confidence_ceiling=Decimal(str(confidence_ceiling)),
            is_enabled=is_enabled,
            is_active=is_active,
            version=version,
            model_version=model_version,
        )
        saved = await self.repository.upsert_strategy_template(template)
        await self.session.commit()
        return saved

    async def get_template(self, template_key: str) -> StrategyTemplate | None:
        return await self.repository.get_strategy_template_by_key(template_key)

    async def get_all_templates(
        self,
        include_disabled: bool = False,
        only_active: bool = True,
    ) -> list[StrategyTemplate]:
        return await self.repository.get_all_strategy_templates(include_disabled, only_active)

    async def get_templates_by_category(
        self,
        category: str,
        include_disabled: bool = False,
    ) -> list[StrategyTemplate]:
        return await self.repository.get_templates_by_category(category, include_disabled)

    async def create_recommendation(
        self,
        instrument_id: str,
        timeframe: str,
        direction: str,
        bias_label: str,
        confidence_score: float,
        strength_score: float,
        entry_price_range: dict | None = None,
        stop_loss_price: float | None = None,
        take_profit_prices: list | None = None,
        risk_reward_ratio: float | None = None,
        position_size_pct: float | None = None,
        current_market: dict | None = None,
        entry_conditions: list | None = None,
        exit_conditions: list | None = None,
        risk_warnings: list | None = None,
        market_conflicts: list | None = None,
        reasoning: str | None = None,
        template_key: str | None = None,
        expires_at: datetime | None = None,
        model_version: str = "legacy",
    ) -> StrategyRecommendation:
        recommendation = StrategyRecommendation(
            recommendation_id=str(uuid4()),
            instrument_id=instrument_id,
            timeframe=timeframe,
            recommendation_ts=datetime.now(timezone.utc),
            template_key=template_key,
            direction=direction,
            bias_label=bias_label,
            confidence_score=Decimal(str(confidence_score)),
            strength_score=Decimal(str(strength_score)),
            entry_price_range_json=entry_price_range or {},
            stop_loss_price=Decimal(str(stop_loss_price)) if stop_loss_price is not None else None,
            take_profit_prices_json=take_profit_prices or [],
            risk_reward_ratio=Decimal(str(risk_reward_ratio))
            if risk_reward_ratio is not None
            else None,
            position_size_pct=Decimal(str(position_size_pct))
            if position_size_pct is not None
            else None,
            current_market_json=current_market or {},
            entry_conditions_json=entry_conditions or [],
            exit_conditions_json=exit_conditions or [],
            risk_warnings_json=risk_warnings or [],
            market_conflicts_json=market_conflicts or [],
            reasoning=reasoning,
            status="active",
            expires_at=expires_at,
            model_version=model_version,
        )
        saved = await self.repository.add_strategy_recommendation(recommendation)
        await self.session.commit()
        return saved

    async def get_recommendation(self, recommendation_id: str) -> StrategyRecommendation | None:
        return await self.repository.get_recommendation_by_id(recommendation_id)

    async def get_latest_recommendation(
        self,
        instrument_id: str,
        timeframe: str,
    ) -> StrategyRecommendation | None:
        return await self.repository.get_latest_recommendation(instrument_id, timeframe)

    async def list_recommendations(
        self,
        instrument_id: str | None = None,
        timeframe: str | None = None,
        direction: str | None = None,
        status: str | None = None,
        limit: int = 20,
    ) -> list[StrategyRecommendation]:
        return await self.repository.get_recommendations(
            instrument_id,
            timeframe,
            direction,
            status,
            limit,
        )

    async def trigger_recommendation(
        self,
        recommendation_id: str,
        triggered_price: float,
    ) -> StrategyRecommendation | None:
        return await self.repository.update_recommendation_status(
            recommendation_id,
            "triggered",
            triggered_at=datetime.now(timezone.utc),
            triggered_price=Decimal(str(triggered_price)),
        )

    async def expire_recommendation(self, recommendation_id: str) -> StrategyRecommendation | None:
        return await self.repository.update_recommendation_status(recommendation_id, "expired")

    async def create_signal_from_recommendation(
        self,
        recommendation_id: str,
        entry_price: float,
        stop_loss_price: float | None = None,
        take_profit_price: float | None = None,
        confidence_score: float | None = None,
        risk_reward_ratio: float | None = None,
        position_size_pct: float | None = None,
        trigger_indicators: list | None = None,
        context_snapshot: dict | None = None,
        market_condition: dict | None = None,
        metadata: dict | None = None,
    ) -> StrategySignal:
        recommendation = await self.get_recommendation(recommendation_id)
        if recommendation is None:
            raise ValueError(f"Recommendation {recommendation_id} not found")

        signal_ts = datetime.now(timezone.utc)
        signal = StrategySignal(
            signal_key=str(uuid4()),
            recommendation_id=recommendation_id,
            template_key=recommendation.template_key,
            signal_type=(recommendation.template_key or "legacy").split("_")[0],
            instrument_id=recommendation.instrument_id,
            timeframe=recommendation.timeframe,
            signal_ts=signal_ts,
            direction=recommendation.direction,
            signal_state="active",
            confidence_score=Decimal(str(confidence_score))
            if confidence_score is not None
            else recommendation.confidence_score,
            entry_price=Decimal(str(entry_price)),
            stop_loss_price=Decimal(str(stop_loss_price))
            if stop_loss_price is not None
            else recommendation.stop_loss_price,
            take_profit_price=Decimal(str(take_profit_price))
            if take_profit_price is not None
            else None,
            risk_reward_ratio=Decimal(str(risk_reward_ratio))
            if risk_reward_ratio is not None
            else recommendation.risk_reward_ratio,
            position_size_pct=Decimal(str(position_size_pct))
            if position_size_pct is not None
            else recommendation.position_size_pct,
            signal_source="legacy_recommendation",
            trigger_indicators_json=trigger_indicators or [],
            context_snapshot_json=context_snapshot or recommendation.current_market_json,
            market_condition_json=market_condition or {},
            metadata_json=metadata or {},
        )
        await self.repository.upsert_strategy_signal(signal)
        await self.repository.upsert_signal_outcome(
            StrategySignalOutcome(
                signal_key=signal.signal_key,
                signal_type=signal.signal_type,
                recommendation_id=recommendation_id,
                instrument_id=recommendation.instrument_id,
                timeframe=recommendation.timeframe,
                signal_ts=signal_ts,
                direction=recommendation.direction,
                entry_ref_price=Decimal(str(entry_price)),
                outcome_status="active",
            )
        )
        await self.session.commit()
        return signal

    async def get_recent_signals(
        self,
        instrument_id: str,
        timeframe: str | None = None,
        limit: int = 50,
    ) -> list[StrategySignal]:
        return await self.repository.get_recent_signals(instrument_id, timeframe, limit)

    async def update_signal_outcome(
        self,
        signal_key: str,
        signal_ts: datetime,
        **changes: Any,
    ) -> StrategySignalOutcome | None:
        outcome = await self.repository.get_signal_outcome(signal_key, signal_ts)
        if outcome is None:
            return None
        for key, value in changes.items():
            if value is not None and hasattr(outcome, key):
                setattr(outcome, key, Decimal(str(value)) if isinstance(value, float) else value)
        await self.session.commit()
        return outcome

    async def get_outcomes_by_instrument(
        self,
        instrument_id: str,
        timeframe: str | None = None,
        limit: int = 100,
    ) -> list[StrategySignalOutcome]:
        return await self.repository.get_outcomes_by_instrument(instrument_id, timeframe, limit)

    async def get_template_performance(
        self,
        template_key: str | None = None,
        from_ts: datetime | None = None,
    ) -> dict[str, Any]:
        return await self.repository.get_template_performance(template_key, from_ts)

    async def get_direction_win_rates(
        self,
        instrument_id: str | None = None,
        timeframe: str | None = None,
    ) -> list[dict[str, Any]]:
        return await self.repository.get_direction_win_rates(instrument_id, timeframe)

    async def bulk_import_templates(self, templates: list[dict[str, Any]]) -> int:
        count = 0
        for item in templates:
            await self.register_template(
                template_key=item["template_key"],
                display_name=item.get("display_name", item["template_key"]),
                category=item.get("category", "custom"),
                family=item.get("family", "custom"),
                direction=item.get("direction", "long"),
                entry_conditions=item.get("entry_conditions", []),
                exit_conditions=item.get("exit_conditions", []),
                description=item.get("description"),
                risk_params=item.get("risk_params", {}),
                applicable_instruments=item.get("applicable_instruments", []),
                applicable_timeframes=item.get("applicable_timeframes", []),
                required_indicators=item.get("required_indicators", []),
                strength_score=item.get("strength_score", 0),
                confidence_ceiling=item.get("confidence_ceiling", 100),
                is_enabled=item.get("is_enabled", True),
                is_active=item.get("is_active", True),
                version=item.get("version", "v1"),
                model_version=item.get("model_version", "legacy"),
            )
            count += 1
        return count
