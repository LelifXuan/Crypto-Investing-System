from __future__ import annotations

from sqlalchemy import delete, select
from sqlalchemy.ext.asyncio import AsyncSession

from app.db.models.position import Fill, PositionSnapshot, PositionView


class PositionRepository:
    def __init__(self, session: AsyncSession) -> None:
        self.session = session

    async def add_fill(self, fill: Fill) -> Fill:
        self.session.add(fill)
        await self.session.flush()
        return fill

    async def list_fills(
        self,
        account_id: str,
        instrument_id: str | None = None,
        strategy_id: str | None = None,
    ) -> list[Fill]:
        stmt = select(Fill).where(Fill.account_id == account_id)
        if instrument_id:
            stmt = stmt.where(Fill.instrument_id == instrument_id)
        if strategy_id is not None:
            stmt = stmt.where(Fill.strategy_id == strategy_id)
        stmt = stmt.order_by(Fill.ts_event, Fill.fill_pk)
        result = await self.session.execute(stmt)
        return list(result.scalars().all())

    async def upsert_position_view(self, view: PositionView) -> PositionView:
        existing = await self.session.get(
            PositionView,
            {
                "account_id": view.account_id,
                "strategy_id": view.strategy_id or "",
                "instrument_id": view.instrument_id,
                "cost_method": view.cost_method,
            },
        )
        if existing is None:
            self.session.add(view)
            await self.session.flush()
            return view

        existing.net_qty = view.net_qty
        existing.avg_cost_price = view.avg_cost_price
        existing.gross_notional = view.gross_notional
        existing.realized_pnl_json = view.realized_pnl_json
        existing.unrealized_pnl_json = view.unrealized_pnl_json
        existing.margin_used = view.margin_used
        existing.leverage = view.leverage
        await self.session.flush()
        return existing

    async def list_position_views(self, account_id: str, cost_method: str | None = None) -> list[PositionView]:
        stmt = select(PositionView).where(PositionView.account_id == account_id)
        if cost_method:
            stmt = stmt.where(PositionView.cost_method == cost_method)
        stmt = stmt.order_by(PositionView.instrument_id)
        result = await self.session.execute(stmt)
        return list(result.scalars().all())

    async def replace_position_snapshot(self, snapshot: PositionSnapshot) -> PositionSnapshot:
        stmt = delete(PositionSnapshot).where(PositionSnapshot.account_id == snapshot.account_id)
        if snapshot.strategy_id is None:
            stmt = stmt.where(PositionSnapshot.strategy_id.is_(None))
        else:
            stmt = stmt.where(PositionSnapshot.strategy_id == snapshot.strategy_id)
        await self.session.execute(stmt)
        self.session.add(snapshot)
        await self.session.flush()
        return snapshot
