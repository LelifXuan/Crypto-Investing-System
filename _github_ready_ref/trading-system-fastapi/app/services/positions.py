from __future__ import annotations

from dataclasses import dataclass, field
from datetime import datetime, timezone
from decimal import Decimal

from app.core.decimal_utils import D, DECIMAL_ZERO
from app.core.ids import new_id
from app.db.models.position import Fill, PositionSnapshot, PositionView
from app.repositories.event_repository import EventRepository
from app.repositories.position_repository import PositionRepository
from app.services.eventing import EventPublisher


@dataclass
class FifoLot:
    qty: Decimal
    price: Decimal


@dataclass
class PositionState:
    signed_qty: Decimal = DECIMAL_ZERO
    avg_cost_price: Decimal = DECIMAL_ZERO
    realized_pnl: Decimal = DECIMAL_ZERO
    fees: Decimal = DECIMAL_ZERO
    lots: list[FifoLot] = field(default_factory=list)


class PositionService:
    def __init__(self, repository: PositionRepository, event_repository: EventRepository | None = None) -> None:
        self.repository = repository
        self.event_repository = event_repository

    async def ingest_fill(self, fill: Fill) -> Fill:
        persisted = await self.repository.add_fill(fill)
        if self.event_repository is not None:
            publisher = EventPublisher(self.event_repository)
            await publisher.publish(
                event_type="fill.ingested",
                source="positions",
                partition_key=fill.account_id,
                payload={
                    "fill_id": fill.fill_id,
                    "account_id": fill.account_id,
                    "strategy_id": fill.strategy_id,
                    "instrument_id": fill.instrument_id,
                    "cost_method": "AVG_COST",
                },
                idempotency_key=f"fill:{fill.source}:{fill.account_id}:{fill.fill_id}",
            )
        return persisted

    async def rebuild_positions(
        self,
        account_id: str,
        cost_method: str,
        instrument_id: str | None = None,
        strategy_id: str | None = None,
    ) -> list[PositionView]:
        fills = await self.repository.list_fills(
            account_id=account_id,
            instrument_id=instrument_id,
            strategy_id=strategy_id,
        )
        grouped: dict[tuple[str, str | None], list[Fill]] = {}
        for fill in fills:
            grouped.setdefault((fill.instrument_id, fill.strategy_id), []).append(fill)

        views: list[PositionView] = []
        snapshot_payload: list[dict] = []
        for (inst_id, strat_id), bucket in grouped.items():
            state = self._rebuild_bucket(bucket, cost_method)
            view = PositionView(
                account_id=account_id,
                strategy_id=strat_id or "",
                instrument_id=inst_id,
                cost_method=cost_method,
                net_qty=state.signed_qty,
                avg_cost_price=state.avg_cost_price,
                gross_notional=abs(state.signed_qty) * state.avg_cost_price,
                realized_pnl_json={"base": str(state.realized_pnl), "fees": str(state.fees)},
                unrealized_pnl_json={"base": "0"},
                margin_used=DECIMAL_ZERO,
                leverage=DECIMAL_ZERO,
            )
            persisted = await self.repository.upsert_position_view(view)
            views.append(persisted)
            snapshot_payload.append(
                {
                    "instrument_id": inst_id,
                    "strategy_id": strat_id or "",
                    "cost_method": cost_method,
                    "net_qty": str(state.signed_qty),
                    "avg_cost_price": str(state.avg_cost_price),
                    "realized_pnl": str(state.realized_pnl),
                    "fees": str(state.fees),
                }
            )

        snapshot = PositionSnapshot(
            snapshot_id=new_id("possnap"),
            account_id=account_id,
            strategy_id=strategy_id,
            as_of_ts=datetime.now(timezone.utc),
            payload={"positions": snapshot_payload, "cost_method": cost_method},
        )
        await self.repository.replace_position_snapshot(snapshot)
        return views

    def _rebuild_bucket(self, fills: list[Fill], cost_method: str) -> PositionState:
        state = PositionState()
        method = cost_method.upper()
        for fill in fills:
            side_sign = Decimal("1") if fill.side.upper() == "BUY" else Decimal("-1")
            signed_qty = fill.qty * side_sign
            state.fees += D(fill.fee)
            if method == "FIFO":
                self._apply_fifo(state, signed_qty, D(fill.price))
            else:
                self._apply_avg_cost(state, signed_qty, D(fill.price))
        return state

    def _apply_avg_cost(self, state: PositionState, signed_qty: Decimal, price: Decimal) -> None:
        if state.signed_qty == DECIMAL_ZERO:
            state.signed_qty = signed_qty
            state.avg_cost_price = price
            return

        same_side = (state.signed_qty > 0 and signed_qty > 0) or (state.signed_qty < 0 and signed_qty < 0)
        if same_side:
            total_qty = abs(state.signed_qty) + abs(signed_qty)
            weighted_cost = abs(state.signed_qty) * state.avg_cost_price + abs(signed_qty) * price
            state.avg_cost_price = weighted_cost / total_qty if total_qty else DECIMAL_ZERO
            state.signed_qty += signed_qty
            return

        closing_qty = min(abs(state.signed_qty), abs(signed_qty))
        if state.signed_qty > 0:
            state.realized_pnl += closing_qty * (price - state.avg_cost_price)
        else:
            state.realized_pnl += closing_qty * (state.avg_cost_price - price)

        remaining = abs(state.signed_qty) - closing_qty
        if remaining > 0:
            state.signed_qty = remaining if state.signed_qty > 0 else -remaining
        else:
            residual_qty = abs(signed_qty) - closing_qty
            if residual_qty == 0:
                state.signed_qty = DECIMAL_ZERO
                state.avg_cost_price = DECIMAL_ZERO
            else:
                state.signed_qty = residual_qty if signed_qty > 0 else -residual_qty
                state.avg_cost_price = price

    def _apply_fifo(self, state: PositionState, signed_qty: Decimal, price: Decimal) -> None:
        if signed_qty > 0:
            qty = signed_qty
            while qty > 0 and state.lots and state.lots[0].qty < 0:
                head = state.lots[0]
                close_qty = min(qty, abs(head.qty))
                state.realized_pnl += close_qty * (head.price - price)
                head.qty += close_qty
                qty -= close_qty
                if head.qty == 0:
                    state.lots.pop(0)
            if qty > 0:
                state.lots.append(FifoLot(qty=qty, price=price))
        else:
            qty = abs(signed_qty)
            while qty > 0 and state.lots and state.lots[0].qty > 0:
                head = state.lots[0]
                close_qty = min(qty, head.qty)
                state.realized_pnl += close_qty * (price - head.price)
                head.qty -= close_qty
                qty -= close_qty
                if head.qty == 0:
                    state.lots.pop(0)
            if qty > 0:
                state.lots.append(FifoLot(qty=-qty, price=price))

        state.signed_qty = sum((lot.qty for lot in state.lots), DECIMAL_ZERO)
        total_abs_qty = sum((abs(lot.qty) for lot in state.lots), DECIMAL_ZERO)
        if total_abs_qty == 0:
            state.avg_cost_price = DECIMAL_ZERO
        else:
            weighted = sum((abs(lot.qty) * lot.price for lot in state.lots), DECIMAL_ZERO)
            state.avg_cost_price = weighted / total_abs_qty
