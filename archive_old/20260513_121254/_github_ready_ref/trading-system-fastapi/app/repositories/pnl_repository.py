from __future__ import annotations

from datetime import datetime

from sqlalchemy import desc, or_, select
from sqlalchemy.ext.asyncio import AsyncSession

from app.db.models.account import Account
from app.db.models.market import MarkPrice
from app.db.models.pnl import CashMovement, FXRate, FundingEvent, PnLSnapshot
from app.db.models.position import Fill, PositionView


class PnLRepository:
    def __init__(self, session: AsyncSession) -> None:
        self.session = session

    async def list_positions(self, account_id: str, cost_method: str) -> list[PositionView]:
        result = await self.session.execute(
            select(PositionView)
            .where(PositionView.account_id == account_id, PositionView.cost_method == cost_method)
            .order_by(PositionView.instrument_id)
        )
        return list(result.scalars().all())

    async def list_fills(self, account_id: str, strategy_id: str | None = None) -> list[Fill]:
        stmt = select(Fill).where(Fill.account_id == account_id)
        if strategy_id is not None:
            stmt = stmt.where(Fill.strategy_id == strategy_id)
        result = await self.session.execute(stmt)
        return list(result.scalars().all())

    async def list_cash_movements(self, account_id: str, strategy_id: str | None = None) -> list[CashMovement]:
        stmt = select(CashMovement).where(CashMovement.account_id == account_id)
        if strategy_id is not None:
            stmt = stmt.where(or_(CashMovement.strategy_id == strategy_id, CashMovement.strategy_id.is_(None)))
        result = await self.session.execute(stmt.order_by(CashMovement.ts_event))
        return list(result.scalars().all())

    async def list_funding_events(self, account_id: str, strategy_id: str | None = None) -> list[FundingEvent]:
        stmt = select(FundingEvent).where(FundingEvent.account_id == account_id)
        if strategy_id is not None:
            stmt = stmt.where(or_(FundingEvent.strategy_id == strategy_id, FundingEvent.strategy_id.is_(None)))
        result = await self.session.execute(stmt.order_by(FundingEvent.ts_event))
        return list(result.scalars().all())

    async def add_cash_movement(self, movement: CashMovement) -> CashMovement:
        self.session.add(movement)
        await self.session.flush()
        return movement

    async def add_funding_event(self, funding: FundingEvent) -> FundingEvent:
        self.session.add(funding)
        await self.session.flush()
        return funding

    async def add_fx_rate(self, rate: FXRate) -> FXRate:
        self.session.add(rate)
        await self.session.flush()
        return rate

    async def list_cash_movement_reads(self, account_id: str, limit: int = 50) -> list[CashMovement]:
        result = await self.session.execute(
            select(CashMovement)
            .where(CashMovement.account_id == account_id)
            .order_by(desc(CashMovement.ts_event))
            .limit(limit)
        )
        return list(result.scalars().all())

    async def list_funding_event_reads(self, account_id: str, limit: int = 50) -> list[FundingEvent]:
        result = await self.session.execute(
            select(FundingEvent)
            .where(FundingEvent.account_id == account_id)
            .order_by(desc(FundingEvent.ts_event))
            .limit(limit)
        )
        return list(result.scalars().all())

    async def latest_fx_rate(self, base_currency: str, quote_currency: str, as_of_ts: datetime | None = None) -> FXRate | None:
        stmt = select(FXRate).where(
            FXRate.base_currency == base_currency,
            FXRate.quote_currency == quote_currency,
        )
        if as_of_ts is not None:
            stmt = stmt.where(FXRate.ts_event <= as_of_ts)
        stmt = stmt.order_by(desc(FXRate.ts_event)).limit(1)
        result = await self.session.execute(stmt)
        return result.scalar_one_or_none()

    async def latest_mark(self, instrument_id: str) -> MarkPrice | None:
        result = await self.session.execute(
            select(MarkPrice).where(MarkPrice.instrument_id == instrument_id).order_by(desc(MarkPrice.ts_event)).limit(1)
        )
        return result.scalar_one_or_none()

    async def add_snapshot(self, snapshot: PnLSnapshot) -> PnLSnapshot:
        self.session.add(snapshot)
        await self.session.flush()
        return snapshot

    async def list_snapshots(self, account_id: str, limit: int = 50) -> list[PnLSnapshot]:
        result = await self.session.execute(
            select(PnLSnapshot)
            .where(PnLSnapshot.account_id == account_id)
            .order_by(desc(PnLSnapshot.as_of_ts))
            .limit(limit)
        )
        return list(result.scalars().all())

    async def latest_snapshot(self, account_id: str) -> PnLSnapshot | None:
        result = await self.session.execute(
            select(PnLSnapshot).where(PnLSnapshot.account_id == account_id).order_by(desc(PnLSnapshot.as_of_ts)).limit(1)
        )
        return result.scalar_one_or_none()

    async def get_account(self, account_id: str) -> Account | None:
        result = await self.session.execute(select(Account).where(Account.account_id == account_id))
        return result.scalar_one_or_none()

    async def list_accounts(self) -> list[Account]:
        result = await self.session.execute(select(Account).order_by(Account.account_id))
        return list(result.scalars().all())

    async def list_accounts_by_instrument(self, instrument_id: str, cost_method: str) -> list[str]:
        result = await self.session.execute(
            select(PositionView.account_id)
            .where(PositionView.instrument_id == instrument_id, PositionView.cost_method == cost_method)
            .distinct()
            .order_by(PositionView.account_id)
        )
        return [row[0] for row in result.all()]
