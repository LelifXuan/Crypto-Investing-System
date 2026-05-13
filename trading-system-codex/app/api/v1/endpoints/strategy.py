from __future__ import annotations

from fastapi import APIRouter, Depends, HTTPException, Query
from sqlalchemy.ext.asyncio import AsyncSession

from app.api.dependencies import CurrentUser, get_db_session, require_roles
from app.core.timeframes import normalize_instrument_id, normalize_timeframe_for_cache
from app.repositories.market_repository import MarketRepository
from app.schemas.market import PrecomputeHintRequest, PrecomputeHintResponse
from app.schemas.strategy import (
    StrategyBundleRead,
    StrategyReviewRead,
    StrategySignalSaveRead,
    StrategySnapshotRequest,
    StrategySnapshotSaveRead,
)
from app.services.precompute import precompute_service
from app.services.strategy_signal.iteration_engine import IterationEngine
from app.services.strategy_signal.review_engine import ReviewEngine
from app.services.strategy_signal.service import StrategySignalService, StrategySignalUnavailable

router = APIRouter(prefix="/strategy", tags=["strategy"])


def _instrument(value: str) -> str:
    return normalize_instrument_id(value)


def _timeframe(value: str) -> str:
    return normalize_timeframe_for_cache(value)


@router.get("/bundle", response_model=StrategyBundleRead)
async def get_strategy_bundle(
    instrument_id: str = Query(default="btc-usdt-perp"),
    timeframe: str = Query(default="1d"),
    session: AsyncSession = Depends(get_db_session),
    _: CurrentUser = Depends(require_roles("admin", "trader", "analyst", "viewer")),
):
    return await StrategySignalService(MarketRepository(session)).get_bundle(
        _instrument(instrument_id),
        _timeframe(timeframe),
    )


@router.get("/decision")
async def get_strategy_decision(
    instrument_id: str = Query(default="btc-usdt-perp"),
    timeframe: str = Query(default="1d"),
    session: AsyncSession = Depends(get_db_session),
    _: CurrentUser = Depends(require_roles("admin", "trader", "analyst", "viewer")),
):
    bundle = await StrategySignalService(MarketRepository(session)).get_bundle(
        _instrument(instrument_id),
        _timeframe(timeframe),
    )
    return bundle["decision"]


@router.post("/refresh", response_model=PrecomputeHintResponse)
async def refresh_strategy_bundle(
    instrument_id: str = Query(default="btc-usdt-perp"),
    timeframe: str = Query(default="1d"),
    session: AsyncSession = Depends(get_db_session),
    _: CurrentUser = Depends(require_roles("admin", "trader", "analyst")),
):
    del session
    return await precompute_service.enqueue_hint(
        PrecomputeHintRequest(
            current_page="strategy",
            instrument_id=_instrument(instrument_id),
            timeframe=_timeframe(timeframe),
            reason="manual_strategy_refresh",
            visible=True,
            candidates=["strategy"],
            priority=1,
        )
    )


@router.post("/signals", response_model=StrategySignalSaveRead)
async def save_strategy_signal(
    payload: StrategySnapshotRequest,
    session: AsyncSession = Depends(get_db_session),
    _: CurrentUser = Depends(require_roles("admin", "trader", "analyst")),
):
    try:
        return await StrategySignalService(MarketRepository(session)).save_signal(
            _instrument(payload.instrument_id),
            _timeframe(payload.timeframe),
        )
    except StrategySignalUnavailable as exc:
        raise HTTPException(status_code=409, detail=str(exc)) from exc


@router.post("/decision/snapshot", response_model=StrategySnapshotSaveRead)
async def save_strategy_decision_snapshot(
    payload: StrategySnapshotRequest,
    session: AsyncSession = Depends(get_db_session),
    _: CurrentUser = Depends(require_roles("admin", "trader", "analyst")),
):
    try:
        saved = await StrategySignalService(MarketRepository(session)).save_signal(
            _instrument(payload.instrument_id),
            _timeframe(payload.timeframe),
        )
    except StrategySignalUnavailable as exc:
        raise HTTPException(status_code=409, detail=str(exc)) from exc
    return {
        "decision_id": saved["signal_key"],
        "input_hash": saved["input_hash"],
        "model_version": saved["model_version"],
        "config_version": saved["config_version"],
        "payload": saved["payload"],
    }


@router.get("/review", response_model=StrategyReviewRead)
async def get_strategy_review(
    instrument_id: str | None = Query(default=None),
    timeframe: str | None = Query(default=None),
    session: AsyncSession = Depends(get_db_session),
    _: CurrentUser = Depends(require_roles("admin", "trader", "analyst", "viewer")),
):
    return await ReviewEngine(MarketRepository(session)).build_review(
        _instrument(instrument_id) if instrument_id else None,
        _timeframe(timeframe) if timeframe else None,
    )


@router.get("/iteration-proposals")
async def get_strategy_iteration_proposals(
    instrument_id: str | None = Query(default=None),
    timeframe: str | None = Query(default=None),
    session: AsyncSession = Depends(get_db_session),
    _: CurrentUser = Depends(require_roles("admin", "trader", "analyst", "viewer")),
):
    return await IterationEngine(MarketRepository(session)).list_proposals(
        _instrument(instrument_id) if instrument_id else None,
        _timeframe(timeframe) if timeframe else None,
    )
