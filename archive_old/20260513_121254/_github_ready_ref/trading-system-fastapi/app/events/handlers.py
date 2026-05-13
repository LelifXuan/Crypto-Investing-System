from __future__ import annotations

from app.core.config import settings
from app.repositories.market_repository import MarketRepository
from app.repositories.pnl_repository import PnLRepository
from app.repositories.position_repository import PositionRepository
from app.services.indicators import IndicatorService
from app.services.pnl import PnLService
from app.services.positions import PositionService


async def handle_domain_event(session, event) -> None:
    payload = event.payload
    event_type = event.event_type
    default_cost_method = str(payload.get("cost_method") or settings.default_cost_method)
    pnl_service = PnLService(PnLRepository(session))

    if event_type == "fill.ingested":
        position_service = PositionService(PositionRepository(session))
        await position_service.rebuild_positions(
            account_id=str(payload["account_id"]),
            instrument_id=payload.get("instrument_id"),
            strategy_id=payload.get("strategy_id") or None,
            cost_method=default_cost_method,
        )
        await pnl_service.recompute_for_account(
            account_id=str(payload["account_id"]),
            strategy_id=payload.get("strategy_id") or None,
            cost_method=default_cost_method,
            formula_version="v2-evented",
        )
        return

    if event_type in {"finance.cash.recorded", "finance.funding.recorded"}:
        await pnl_service.recompute_for_account(
            account_id=str(payload["account_id"]),
            strategy_id=payload.get("strategy_id") or None,
            cost_method=default_cost_method,
            formula_version="v2-evented",
        )
        return

    if event_type == "market.candle.closed":
        repo = MarketRepository(session)
        indicator_service = IndicatorService(repo)
        policies = await repo.list_indicator_refresh_policies(
            instrument_id=str(payload["instrument_id"]),
            timeframe=str(payload["timeframe"]),
            enabled_only=True,
        )
        if not policies:
            return
        for policy in policies:
            await indicator_service.calculate_from_policy(policy)
        return

    repo = PnLRepository(session)
    if event_type == "market.mark_price.updated":
        account_ids = await repo.list_accounts_by_instrument(
            instrument_id=str(payload["instrument_id"]),
            cost_method=default_cost_method,
        )
        for account_id in account_ids:
            await pnl_service.recompute_for_account(
                account_id=account_id,
                cost_method=default_cost_method,
                formula_version="v2-evented",
            )
        return

    if event_type == "market.fx_rate.updated":
        for account in await repo.list_accounts():
            await pnl_service.recompute_for_account(
                account_id=account.account_id,
                cost_method=default_cost_method,
                formula_version="v2-evented",
            )
