from __future__ import annotations

from fastapi import APIRouter, Depends, HTTPException, Query
from sqlalchemy.ext.asyncio import AsyncSession

from app.api.dependencies import CurrentUser, get_db_session, require_roles
from app.repositories.market_repository import MarketRepository
from app.schemas.gold_allocation import (
    GoldAllocationPlanRequest,
    GoldAllocationPlanResponse,
    GoldExecutionPlanRequest,
    GoldExecutionPlanResponse,
    GoldFundamentalsResponse,
    GoldMarketStateResponse,
)
from app.services.gold_allocation_engine import build_gold_allocation_plan
from app.services.gold_dca_dip import (
    GoldExecutionComposer,
    GoldExecutionState,
    GoldSettings,
    QuoteSnapshot,
    build_indicator_snapshot,
    indicator_from_mapping,
    normalize_candle,
    now_utc,
)
from app.services.gold_macro_adapter import macro_overview_to_gold_macro
from app.services.goldhub_data import GoldhubDataService
from app.services.macro_overview import MacroOverviewService
from app.services.xaut_market_state import XAUT_INSTRUMENT_ID, XautMarketStateService

router = APIRouter(prefix="/gold", tags=["gold"])


def _repository(session: AsyncSession | None) -> MarketRepository | None:
    return MarketRepository(session) if session is not None else None


async def _macro_payload(repo: MarketRepository | None) -> dict:
    if repo is None:
        return {}
    try:
        overview = await MacroOverviewService(repo).build_overview()
    except Exception:
        return {}
    return macro_overview_to_gold_macro(overview)


async def _market_state(repo: MarketRepository | None, *, force: bool = False) -> dict:
    return await XautMarketStateService(repo).build_state(force=force)


def _fundamentals() -> dict:
    return GoldhubDataService().load_snapshot()


def _aware(value):
    if value.tzinfo is None:
        return value.replace(tzinfo=None).astimezone()
    return value


def _settings(payload: GoldExecutionPlanRequest) -> GoldSettings:
    values = {
        "daily_dca_amount": payload.daily_dca_amount,
        "dip_add_amount": payload.dip_add_amount,
        "cooldown_days": payload.cooldown_days,
        "quote_max_age_seconds": payload.quote_max_age_seconds,
        "available_cash": payload.available_cash,
    }
    if payload.settings is not None:
        values.update(payload.settings.model_dump(exclude_none=True))
    return GoldSettings(**values)


async def _execution_inputs(
    payload: GoldExecutionPlanRequest,
    repo: MarketRepository | None,
) -> tuple[QuoteSnapshot, object | None, dict]:
    diagnostics: dict = {"source": "request_override" if payload.quote else "xaut_daily_cache"}
    candles = [
        item
        for item in (normalize_candle(item) for item in (payload.candles or []))
        if item
    ]
    if not candles and repo is not None:
        try:
            candles = [
                item
                for item in (
                    normalize_candle(candle)
                    for candle in await repo.list_candles(XAUT_INSTRUMENT_ID, "1d", limit=260)
                )
                if item
            ]
        except Exception:
            candles = []
    indicators = indicator_from_mapping(payload.indicators) or build_indicator_snapshot(candles)
    if payload.quote is not None:
        quote = QuoteSnapshot(
            price=payload.quote.price,
            updated_at=_aware(payload.quote.updated_at),
        )
    elif candles:
        latest = candles[-1]
        quote = QuoteSnapshot(price=latest.close, updated_at=_aware(latest.ts))
    else:
        quote = QuoteSnapshot(price=0.0, updated_at=now_utc().replace(year=1970))
    diagnostics["candle_count"] = len(candles)
    diagnostics["has_indicators"] = indicators is not None
    return quote, indicators, diagnostics


@router.post("/allocation/plan", response_model=GoldAllocationPlanResponse)
async def plan_gold_allocation(
    payload: GoldAllocationPlanRequest,
    _: CurrentUser = Depends(require_roles("admin", "trader", "analyst", "viewer")),
) -> GoldAllocationPlanResponse:
    try:
        plan = build_gold_allocation_plan(
            payload.portfolio.model_dump(),
            macro=payload.macro or {},
            goldhub=payload.goldhub or {},
            market=payload.market or {},
            options=payload.options.model_dump(),
        )
    except ValueError as exc:
        raise HTTPException(status_code=400, detail=str(exc)) from exc
    return GoldAllocationPlanResponse.model_validate(plan.to_dict())


@router.post("/execution-plan", response_model=GoldExecutionPlanResponse)
async def plan_gold_execution(
    payload: GoldExecutionPlanRequest,
    session: AsyncSession = Depends(get_db_session),
    _: CurrentUser = Depends(require_roles("admin", "trader", "analyst", "viewer")),
) -> GoldExecutionPlanResponse:
    repo = _repository(session)
    now = _aware(payload.now) if payload.now else now_utc()
    quote, indicators, input_diagnostics = await _execution_inputs(payload, repo)
    plan = GoldExecutionComposer().compose(
        symbol=payload.symbol,
        quote=quote,
        now=now,
        settings=_settings(payload),
        state=GoldExecutionState(
            executed_today=payload.executed_today,
            last_dip_add_date=payload.last_dip_add_date,
            last_dip_cycle_id=payload.last_dip_cycle_id,
        ),
        indicators=indicators,
    ).to_dict()
    plan["diagnostics"].update(input_diagnostics)
    return GoldExecutionPlanResponse.model_validate(plan)


@router.get("/fundamentals", response_model=GoldFundamentalsResponse)
async def get_gold_fundamentals(
    _: CurrentUser = Depends(require_roles("admin", "trader", "analyst", "viewer")),
) -> GoldFundamentalsResponse:
    return GoldFundamentalsResponse.model_validate(_fundamentals())


@router.get("/market-state", response_model=GoldMarketStateResponse)
async def get_gold_market_state(
    force: bool = Query(default=False),
    session: AsyncSession = Depends(get_db_session),
    _: CurrentUser = Depends(require_roles("admin", "trader", "analyst", "viewer")),
) -> GoldMarketStateResponse:
    state = await _market_state(_repository(session), force=force)
    return GoldMarketStateResponse.model_validate(state)


@router.get("/allocation", response_model=GoldAllocationPlanResponse)
async def get_gold_allocation(
    session: AsyncSession = Depends(get_db_session),
    _: CurrentUser = Depends(require_roles("admin", "trader", "analyst", "viewer")),
) -> GoldAllocationPlanResponse:
    repo = _repository(session)
    portfolio = {
        "total_portfolio_value": 200_000,
        "current_gold_value": 10_000,
        "monthly_new_cash": 5_000,
        "current_gold_cost": 9_500,
        "is_quarterly_rebalance_month": False,
    }
    plan = build_gold_allocation_plan(
        portfolio,
        macro=await _macro_payload(repo),
        goldhub=_fundamentals(),
        market=await _market_state(repo),
    )
    return GoldAllocationPlanResponse.model_validate(plan.to_dict())
