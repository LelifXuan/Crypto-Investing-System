from __future__ import annotations

from dataclasses import dataclass
from datetime import datetime
from decimal import Decimal

from app.core.decimal_utils import D, DECIMAL_ZERO
from app.db.models.pnl import PnLSnapshot
from app.repositories.pnl_repository import PnLRepository
from app.schemas.reviews import ReviewRead


@dataclass
class ReviewStats:
    realized_trade_count: int
    winning_trade_count: int
    win_rate: Decimal
    pnl_ratio: Decimal
    max_drawdown: Decimal
    total_fees: Decimal
    total_realized_pnl: Decimal
    instrument_contribution: dict[str, str]


class ReviewService:
    def __init__(self, repository: PnLRepository) -> None:
        self.pnl_repository = repository

    async def review(
        self,
        account_id: str,
        limit: int = 200,
        start_ts: datetime | None = None,
        end_ts: datetime | None = None,
    ) -> ReviewRead:
        stats = await self.build_summary(account_id=account_id, start_ts=start_ts, end_ts=end_ts, limit=limit)
        return ReviewRead(
            account_id=account_id,
            start_ts=start_ts,
            end_ts=end_ts,
            realized_trade_count=stats.realized_trade_count,
            winning_trade_count=stats.winning_trade_count,
            win_rate=stats.win_rate,
            pnl_ratio=stats.pnl_ratio,
            max_drawdown=stats.max_drawdown,
            total_fees=stats.total_fees,
            total_realized_pnl=stats.total_realized_pnl,
            instrument_contribution=stats.instrument_contribution,
        )

    async def build_summary(
        self,
        account_id: str,
        start_ts: datetime | None = None,
        end_ts: datetime | None = None,
        limit: int = 200,
    ) -> ReviewStats:
        fills = await self.pnl_repository.list_fills(account_id)
        snapshots = await self.pnl_repository.list_snapshots(account_id, limit=max(limit, 1))

        contributions: dict[str, Decimal] = {}
        realized_values: list[Decimal] = []
        total_fees = DECIMAL_ZERO
        for fill in fills:
            if start_ts and fill.ts_event < start_ts:
                continue
            if end_ts and fill.ts_event > end_ts:
                continue
            fee = D(fill.fee)
            total_fees += fee
            contributions.setdefault(fill.instrument_id, DECIMAL_ZERO)
            contributions[fill.instrument_id] -= fee

        for snap in snapshots:
            value = D(snap.realized_pnl)
            if value != DECIMAL_ZERO:
                realized_values.append(value)
            for item in snap.payload.get("positions", []):
                contributions.setdefault(item["instrument_id"], DECIMAL_ZERO)
                contributions[item["instrument_id"]] += D(item.get("realized", "0"))

        winning = [v for v in realized_values if v > 0]
        losing = [abs(v) for v in realized_values if v < 0]
        realized_trade_count = len(realized_values)
        winning_trade_count = len(winning)
        win_rate = (Decimal(winning_trade_count) / Decimal(realized_trade_count)) if realized_trade_count else DECIMAL_ZERO
        avg_win = sum(winning, DECIMAL_ZERO) / Decimal(len(winning)) if winning else DECIMAL_ZERO
        avg_loss = sum(losing, DECIMAL_ZERO) / Decimal(len(losing)) if losing else DECIMAL_ZERO
        pnl_ratio = (avg_win / avg_loss) if avg_loss != DECIMAL_ZERO else DECIMAL_ZERO

        max_drawdown = self.compute_max_drawdown(snapshots)
        total_realized_pnl = sum(realized_values, DECIMAL_ZERO)
        return ReviewStats(
            realized_trade_count=realized_trade_count,
            winning_trade_count=winning_trade_count,
            win_rate=win_rate,
            pnl_ratio=pnl_ratio,
            max_drawdown=max_drawdown,
            total_fees=total_fees,
            total_realized_pnl=total_realized_pnl,
            instrument_contribution={k: str(v) for k, v in contributions.items()},
        )

    @staticmethod
    def compute_max_drawdown(snapshots: list[PnLSnapshot]) -> Decimal:
        ordered = sorted(snapshots, key=lambda s: s.as_of_ts)
        peak = None
        max_drawdown = DECIMAL_ZERO
        for snap in ordered:
            equity = D(snap.equity)
            if peak is None or equity > peak:
                peak = equity
            if peak and peak != DECIMAL_ZERO:
                drawdown = (peak - equity) / peak
                if drawdown > max_drawdown:
                    max_drawdown = drawdown
        return max_drawdown
