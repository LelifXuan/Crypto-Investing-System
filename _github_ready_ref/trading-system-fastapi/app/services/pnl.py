from __future__ import annotations

from dataclasses import dataclass
from datetime import datetime, timezone
from decimal import Decimal

from app.core.decimal_utils import D, DECIMAL_ZERO
from app.core.ids import new_id
from app.db.models.pnl import CashMovement, FXRate, FundingEvent, PnLSnapshot
from app.repositories.pnl_repository import PnLRepository


@dataclass(slots=True)
class FXConversionTrace:
    amount: Decimal
    currency: str
    base_currency: str
    rate: Decimal
    converted: Decimal
    via_inverse: bool


class PnLService:
    def __init__(self, repository: PnLRepository) -> None:
        self.repository = repository

    async def record_cash_movement(self, movement: CashMovement) -> CashMovement:
        return await self.repository.add_cash_movement(movement)

    async def record_funding_event(self, funding: FundingEvent) -> FundingEvent:
        return await self.repository.add_funding_event(funding)

    async def record_fx_rate(self, rate: FXRate) -> FXRate:
        return await self.repository.add_fx_rate(rate)

    async def recompute(
        self,
        account_id: str,
        cost_method: str,
        base_currency: str,
        formula_version: str,
        strategy_id: str | None = None,
    ) -> PnLSnapshot:
        positions = await self.repository.list_positions(account_id=account_id, cost_method=cost_method)
        fills = await self.repository.list_fills(account_id=account_id, strategy_id=strategy_id)
        cash_movements = await self.repository.list_cash_movements(account_id=account_id, strategy_id=strategy_id)
        funding_events = await self.repository.list_funding_events(account_id=account_id, strategy_id=strategy_id)

        realized = DECIMAL_ZERO
        unrealized = DECIMAL_ZERO
        exposure = DECIMAL_ZERO
        fees = DECIMAL_ZERO
        funding = DECIMAL_ZERO
        cash_balance = DECIMAL_ZERO
        fx_traces: list[dict] = []

        for fill in fills:
            converted_fee, trace = await self.convert_amount(
                amount=D(fill.fee),
                currency=fill.fee_currency,
                base_currency=base_currency,
                as_of_ts=fill.ts_event,
            )
            fees += converted_fee
            if trace is not None:
                fx_traces.append(trace.__dict__ | {"kind": "fill_fee", "ref": fill.fill_id})

        for movement in cash_movements:
            normalized = self.normalize_cash_amount(movement.movement_type, D(movement.amount))
            converted_amount, trace = await self.convert_amount(
                amount=normalized,
                currency=movement.currency,
                base_currency=base_currency,
                as_of_ts=movement.ts_event,
            )
            cash_balance += converted_amount
            if trace is not None:
                fx_traces.append(trace.__dict__ | {"kind": "cash_movement", "ref": movement.movement_id})

        for event in funding_events:
            converted_funding, trace = await self.convert_amount(
                amount=D(event.payment),
                currency=event.currency,
                base_currency=base_currency,
                as_of_ts=event.ts_event,
            )
            funding += converted_funding
            if trace is not None:
                fx_traces.append(trace.__dict__ | {"kind": "funding", "ref": event.funding_id})

        breakdown: list[dict] = []
        for position in positions:
            if strategy_id is not None and position.strategy_id != strategy_id:
                continue
            realized_piece = D(position.realized_pnl_json.get("base", "0"))
            realized += realized_piece

            latest_mark = await self.repository.latest_mark(position.instrument_id)
            mark_price = D(latest_mark.mark_price if latest_mark else position.avg_cost_price)
            exposure += abs(D(position.net_qty)) * mark_price
            if D(position.net_qty) >= 0:
                unrealized_piece = D(position.net_qty) * (mark_price - D(position.avg_cost_price))
            else:
                unrealized_piece = abs(D(position.net_qty)) * (D(position.avg_cost_price) - mark_price)
            unrealized += unrealized_piece

            breakdown.append(
                {
                    "instrument_id": position.instrument_id,
                    "strategy_id": position.strategy_id,
                    "net_qty": str(position.net_qty),
                    "avg_cost_price": str(position.avg_cost_price),
                    "mark_price": str(mark_price),
                    "realized": str(realized_piece),
                    "unrealized": str(unrealized_piece),
                }
            )

        slippage_cost = DECIMAL_ZERO
        equity = cash_balance + realized + unrealized - fees + funding - slippage_cost

        snapshot = PnLSnapshot(
            snapshot_id=new_id("pnl"),
            account_id=account_id,
            strategy_id=strategy_id,
            as_of_ts=datetime.now(timezone.utc),
            base_currency=base_currency,
            equity=equity,
            cash_balance=cash_balance,
            realized_pnl=realized,
            unrealized_pnl=unrealized,
            fees=fees,
            funding=funding,
            slippage_cost=slippage_cost,
            exposure_notional=exposure,
            formula_version=formula_version,
            payload={
                "positions": breakdown,
                "cash_movements_count": len(cash_movements),
                "funding_events_count": len(funding_events),
                "fills_count": len(fills),
                "fx_traces": [self._serialize_trace(item) for item in fx_traces],
            },
        )
        return await self.repository.add_snapshot(snapshot)

    async def recompute_for_account(
        self,
        account_id: str,
        cost_method: str,
        formula_version: str,
        strategy_id: str | None = None,
    ) -> PnLSnapshot:
        account = await self.repository.get_account(account_id)
        if account is None:
            raise ValueError(f"unknown account: {account_id}")
        return await self.recompute(
            account_id=account_id,
            strategy_id=strategy_id,
            cost_method=cost_method,
            base_currency=account.base_currency,
            formula_version=formula_version,
        )

    async def convert_amount(
        self,
        amount: Decimal,
        currency: str,
        base_currency: str,
        as_of_ts: datetime,
    ) -> tuple[Decimal, FXConversionTrace | None]:
        if currency == base_currency:
            return amount, None

        direct = await self.repository.latest_fx_rate(currency, base_currency, as_of_ts)
        if direct is not None:
            rate = D(direct.rate)
            converted = amount * rate
            return converted, FXConversionTrace(amount, currency, base_currency, rate, converted, False)

        inverse = await self.repository.latest_fx_rate(base_currency, currency, as_of_ts)
        if inverse is not None:
            inverse_rate = D(inverse.rate)
            if inverse_rate == DECIMAL_ZERO:
                raise ValueError(f"invalid zero FX rate for {base_currency}/{currency}")
            rate = Decimal("1") / inverse_rate
            converted = amount * rate
            return converted, FXConversionTrace(amount, currency, base_currency, rate, converted, True)

        raise ValueError(f"missing FX rate for {currency}/{base_currency} at {as_of_ts.isoformat()}")

    @staticmethod
    def normalize_cash_amount(movement_type: str, amount: Decimal) -> Decimal:
        if amount < 0:
            return amount
        movement = movement_type.upper()
        if movement in {"WITHDRAWAL", "TRANSFER_OUT", "FEE", "TAX", "LOSS"}:
            return -amount
        return amount

    @staticmethod
    def _serialize_trace(item: dict) -> dict:
        payload = dict(item)
        for key in ("amount", "rate", "converted"):
            if key in payload:
                payload[key] = str(payload[key])
        return payload
