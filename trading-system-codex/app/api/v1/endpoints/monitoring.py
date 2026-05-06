from __future__ import annotations

from datetime import UTC, datetime, timedelta, timezone

from fastapi import APIRouter, Body, Depends, HTTPException, Query, status
from sqlalchemy.ext.asyncio import AsyncSession

from app.api.dependencies import CurrentUser, get_db_session, require_roles
from app.cache.shared_query_cache import shared_query_cache
from app.core.config import settings
from app.repositories.market_repository import MarketRepository
from app.schemas.market import (
    AlertEventRead,
    AlertEventStatusUpdate,
    AlertRuleRead,
    AlertsBundleRead,
    ChipStructureRead,
    DivergenceSummaryRead,
    IndicatorDefinitionRead,
    IndicatorObservationRead,
    IndicatorRefreshRequest,
    MacroEventCalendarRead,
    MacroOverviewResponse,
    MonitoringDashboardRead,
    MonitoringPolicyRead,
    MonitoringSyncResponse,
    PrecomputeHintRequest,
    RiskEvaluationRead,
    RiskEvaluationRequest,
)
from app.services.alerts_bundle import AlertsBundleService
from app.services.chip_structure import ChipStructureService
from app.services.divergence import DivergenceService
from app.services.final_decision import FinalDecisionService
from app.services.indicator_monitoring import IndicatorMonitoringService
from app.services.macro_overview import MacroOverviewService
from app.services.monitoring_dashboard import MonitoringDashboardService
from app.services.precompute import precompute_service
from app.services.risk import RiskEngine, RiskInput

router = APIRouter(tags=["monitoring"])

indicators_catalog_router = APIRouter(prefix="/indicators", tags=["indicators-monitoring"])
alerts_router = APIRouter(prefix="/alerts", tags=["alerts"])
macro_router = APIRouter(prefix="/macro", tags=["macro"])
onchain_router = APIRouter(prefix="/onchain", tags=["onchain"])

MONITORING_FRESHNESS_MAX_AGE = timedelta(days=1)


async def _latest_category_observation_ts(
    repository: MarketRepository,
    *,
    category: str,
    instrument_id: str | None = None,
    timeframe: str | None = None,
) -> datetime | None:
    items = await repository.list_indicator_observations(
        category=category,
        instrument_id=instrument_id,
        timeframe=timeframe,
        limit=1,
    )
    if not items:
        return None
    ts = items[0].observation_ts
    return ts if ts.tzinfo else ts.replace(tzinfo=UTC)


async def _ensure_monitoring_category_fresh(
    session: AsyncSession,
    *,
    category: str,
    instrument_id: str | None = None,
    timeframe: str | None = None,
) -> bool:
    repository = MarketRepository(session)
    latest_ts = await _latest_category_observation_ts(
        repository,
        category=category,
        instrument_id=instrument_id,
        timeframe=timeframe,
    )
    now = datetime.now(UTC)
    is_stale = latest_ts is None or latest_ts < now - MONITORING_FRESHNESS_MAX_AGE
    if not is_stale:
        return False

    service = IndicatorMonitoringService(repository)
    if category == "technical":
        await service.sync_technical(
            instrument_id=instrument_id or "btc-usdt-perp", timeframe=timeframe
        )
    elif category == "onchain":
        await service.sync_onchain()
    elif category == "macro":
        await service.sync_macro()
    else:
        return False
    return True


@router.get("/monitoring/macro-overview", response_model=MacroOverviewResponse)
async def get_macro_overview(
    session: AsyncSession = Depends(get_db_session),
    _: CurrentUser = Depends(require_roles("admin", "trader", "analyst", "viewer")),
):
    async def producer() -> dict:
        payload = await MacroOverviewService(MarketRepository(session)).build_overview()
        return payload.model_dump(mode="json")

    cached = await shared_query_cache.get_or_set(
        "monitoring:macro_overview",
        settings.macro_calendar_cache_seconds,
        producer,
    )
    return MacroOverviewResponse.model_validate(cached)


@indicators_catalog_router.get("/catalog", response_model=list[IndicatorDefinitionRead])
async def list_indicator_catalog(
    category: str | None = Query(default=None),
    family: str | None = Query(default=None),
    source_provider: str | None = Query(default=None),
    session: AsyncSession = Depends(get_db_session),
    _: CurrentUser = Depends(require_roles("admin", "trader", "analyst", "viewer")),
):
    return await MarketRepository(session).list_indicator_definitions(
        category=category,
        family=family,
        source_provider=source_provider,
        enabled_only=True,
    )


@indicators_catalog_router.get("/observations", response_model=list[IndicatorObservationRead])
async def list_indicator_observations(
    indicator_key: str | None = Query(default=None),
    instrument_id: str | None = Query(default=None),
    asset_code: str | None = Query(default=None),
    timeframe: str | None = Query(default=None),
    category: str | None = Query(default=None),
    start_ts: int | None = Query(default=None),
    end_ts: int | None = Query(default=None),
    limit: int = Query(default=100, le=500),
    session: AsyncSession = Depends(get_db_session),
    _: CurrentUser = Depends(require_roles("admin", "trader", "analyst", "viewer")),
):
    async def producer() -> list[dict]:
        items = await MarketRepository(session).list_indicator_observations(
            indicator_key=indicator_key,
            instrument_id=instrument_id,
            asset_code=asset_code,
            timeframe=timeframe,
            category=category,
            start_ts=datetime.fromtimestamp(start_ts, tz=timezone.utc) if start_ts else None,
            end_ts=datetime.fromtimestamp(end_ts, tz=timezone.utc) if end_ts else None,
            limit=limit,
        )
        return [
            IndicatorObservationRead.model_validate(item).model_dump(mode="json") for item in items
        ]

    cache_key = (
        "monitoring:observations:"
        f"{indicator_key or '-'}:{instrument_id or '-'}:{asset_code or '-'}:"
        f"{timeframe or '-'}:{category or '-'}:{start_ts or '-'}:{end_ts or '-'}:{limit}"
    )
    cached = await shared_query_cache.get_or_set(
        cache_key, settings.shared_query_cache_seconds, producer
    )
    return [IndicatorObservationRead.model_validate(item) for item in cached]


@router.get("/monitoring/dashboard", response_model=MonitoringDashboardRead)
async def get_monitoring_dashboard(
    instrument_id: str = Query(default="btc-usdt-perp"),
    timeframe: str = Query(default="1h"),
    session: AsyncSession = Depends(get_db_session),
    _: CurrentUser = Depends(require_roles("admin", "trader", "analyst", "viewer")),
):
    return await MonitoringDashboardService(MarketRepository(session)).get_bundle(
        instrument_id, timeframe
    )


@router.post("/monitoring/dashboard/refresh", response_model=MonitoringDashboardRead)
async def refresh_monitoring_dashboard(
    instrument_id: str = Query(default="btc-usdt-perp"),
    timeframe: str = Query(default="1h"),
    session: AsyncSession = Depends(get_db_session),
    _: CurrentUser = Depends(require_roles("admin", "trader", "analyst")),
):
    return await MonitoringDashboardService(MarketRepository(session)).refresh_bundle(
        instrument_id, timeframe
    )


@indicators_catalog_router.post("/refresh", response_model=MonitoringSyncResponse)
async def refresh_indicators(
    instrument_id: str = Query(default="btc-usdt-perp"),
    timeframe: str | None = Query(default=None),
    payload: IndicatorRefreshRequest | None = Body(default=None),
    session: AsyncSession = Depends(get_db_session),
    _: CurrentUser = Depends(require_roles("admin", "trader", "analyst")),
):
    if payload is not None:
        instrument_id = payload.instrument_id
        timeframe = payload.timeframe
    service = IndicatorMonitoringService(MarketRepository(session))
    runs = await service.sync_technical(instrument_id=instrument_id, timeframe=timeframe)
    await shared_query_cache.invalidate_prefix("monitoring:observations:")
    await precompute_service.enqueue_hint(
        PrecomputeHintRequest(
            current_page="monitoring-overview",
            instrument_id=instrument_id,
            timeframe=timeframe,
            reason="refresh_indicators",
            priority=3,
        )
    )
    return MonitoringSyncResponse(
        runs=[
            {
                "run_id": item.run_id,
                "indicator_key": item.indicator_key,
                "rows_written": item.rows_written,
            }
            for item in runs
        ]
    )


@indicators_catalog_router.post("/backfill", response_model=MonitoringSyncResponse)
async def backfill_indicators(
    instrument_id: str = Query(default="btc-usdt-perp"),
    timeframe: str = Query(default="1h"),
    session: AsyncSession = Depends(get_db_session),
    _: CurrentUser = Depends(require_roles("admin", "trader", "analyst")),
):
    service = IndicatorMonitoringService(MarketRepository(session))
    runs = await service.sync_technical(instrument_id=instrument_id, timeframe=timeframe)
    await shared_query_cache.invalidate_prefix("monitoring:observations:")
    await precompute_service.enqueue_hint(
        PrecomputeHintRequest(
            current_page="monitoring-overview",
            instrument_id=instrument_id,
            timeframe=timeframe,
            reason="backfill_indicators",
            priority=3,
        )
    )
    return MonitoringSyncResponse(
        runs=[
            {
                "run_id": item.run_id,
                "indicator_key": item.indicator_key,
                "rows_written": item.rows_written,
            }
            for item in runs
        ]
    )


@indicators_catalog_router.get("/monitoring-policies", response_model=list[MonitoringPolicyRead])
async def list_monitoring_policies(
    category: str | None = Query(default=None),
    session: AsyncSession = Depends(get_db_session),
    _: CurrentUser = Depends(require_roles("admin", "trader", "analyst", "viewer")),
):
    return await MarketRepository(session).list_monitoring_policies(
        enabled_only=False, category=category
    )


@alerts_router.get("/rules", response_model=list[AlertRuleRead])
async def list_alert_rules(
    category: str | None = Query(default=None),
    session: AsyncSession = Depends(get_db_session),
    _: CurrentUser = Depends(require_roles("admin", "trader", "analyst", "viewer")),
):
    return await MarketRepository(session).list_alert_rules(enabled_only=False, category=category)


@alerts_router.get("/events", response_model=list[AlertEventRead])
async def list_alert_events(
    status: str | None = Query(default=None),
    severity: str | None = Query(default=None),
    category: str | None = Query(default=None),
    limit: int = Query(default=100, le=500),
    session: AsyncSession = Depends(get_db_session),
    _: CurrentUser = Depends(require_roles("admin", "trader", "analyst", "viewer")),
):
    return await MarketRepository(session).list_alert_events(
        status=status, severity=severity, category=category, limit=limit
    )


@alerts_router.patch("/events/{alert_event_id}/status", response_model=AlertEventRead)
async def update_alert_event_status(
    alert_event_id: str,
    payload: AlertEventStatusUpdate,
    session: AsyncSession = Depends(get_db_session),
    _: CurrentUser = Depends(require_roles("admin", "trader", "analyst")),
):
    allowed_statuses = {"open", "acknowledged", "resolved", "suppressed"}
    next_status = payload.status.lower().strip()
    if next_status not in allowed_statuses:
        raise HTTPException(
            status_code=status.HTTP_422_UNPROCESSABLE_ENTITY, detail="invalid alert status"
        )
    event = await MarketRepository(session).update_alert_event_status(alert_event_id, next_status)
    if event is None:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="alert event not found")
    await shared_query_cache.invalidate_prefix("monitoring:alerts")
    return event


@alerts_router.get("/divergence", response_model=DivergenceSummaryRead)
async def get_divergence_summary(
    instrument_id: str = Query(default="btc-usdt-perp"),
    timeframe: str = Query(default="1h"),
    limit: int = Query(default=220, ge=50, le=400),
    session: AsyncSession = Depends(get_db_session),
    _: CurrentUser = Depends(require_roles("admin", "trader", "analyst", "viewer")),
):
    candles = await MarketRepository(session).list_candles(
        instrument_id=instrument_id, timeframe=timeframe, limit=limit
    )
    payload = DivergenceService().analyze(instrument_id, timeframe, candles)
    return DivergenceSummaryRead.model_validate(payload)


@alerts_router.get("/chip-structure", response_model=ChipStructureRead)
async def get_chip_structure(
    instrument_id: str = Query(default="btc-usdt-perp"),
    timeframe: str = Query(default="1h"),
    session: AsyncSession = Depends(get_db_session),
    _: CurrentUser = Depends(require_roles("admin", "trader", "analyst", "viewer")),
):
    repository = MarketRepository(session)
    latest_candles = await repository.list_candles(
        instrument_id=instrument_id, timeframe="1h", limit=1
    )
    latest_candle_ts = latest_candles[-1].ts_open.isoformat() if latest_candles else "missing"
    cache_key = f"monitoring:chip_structure:v2:{instrument_id}:{timeframe}:{latest_candle_ts}"

    async def producer() -> dict:
        payload = await ChipStructureService(repository).analyze(instrument_id, timeframe)
        return ChipStructureRead.model_validate(payload).model_dump(mode="json")

    cached = await shared_query_cache.get_or_set(
        cache_key, settings.shared_query_cache_seconds, producer
    )
    return ChipStructureRead.model_validate(cached)


@alerts_router.get("/bundle", response_model=AlertsBundleRead)
async def get_alerts_bundle(
    instrument_id: str = Query(default="btc-usdt-perp"),
    timeframe: str = Query(default="1h"),
    session: AsyncSession = Depends(get_db_session),
    _: CurrentUser = Depends(require_roles("admin", "trader", "analyst", "viewer")),
):
    return await AlertsBundleService(MarketRepository(session)).get_bundle(instrument_id, timeframe)


@alerts_router.post("/refresh", response_model=AlertsBundleRead)
async def refresh_alerts_bundle(
    instrument_id: str = Query(default="btc-usdt-perp"),
    timeframe: str = Query(default="1h"),
    session: AsyncSession = Depends(get_db_session),
    _: CurrentUser = Depends(require_roles("admin", "trader", "analyst")),
):
    return await AlertsBundleService(MarketRepository(session)).refresh_bundle(
        instrument_id, timeframe
    )


@alerts_router.get("/final-decision")
async def get_final_decision(
    instrument_id: str = Query(default="btc-usdt-perp"),
    timeframe: str = Query(default="1h"),
    session: AsyncSession = Depends(get_db_session),
    _: CurrentUser = Depends(require_roles("admin", "trader", "analyst", "viewer")),
):
    repository = MarketRepository(session)
    bundle = await AlertsBundleService(repository).get_bundle(instrument_id, timeframe)
    if bundle.final_decision:
        return bundle.final_decision
    return await FinalDecisionService(repository).build(instrument_id, timeframe)


@macro_router.get("/calendar", response_model=list[MacroEventCalendarRead])
async def list_macro_calendar(
    event_key: str | None = Query(default=None),
    status: str | None = Query(default=None),
    limit: int = Query(default=100, le=500),
    session: AsyncSession = Depends(get_db_session),
    _: CurrentUser = Depends(require_roles("admin", "trader", "analyst", "viewer")),
):
    async def producer() -> list[dict]:
        items = await MarketRepository(session).list_macro_events(
            event_key=event_key, status=status, limit=limit
        )
        return [
            MacroEventCalendarRead.model_validate(item).model_dump(mode="json") for item in items
        ]

    cache_key = f"monitoring:macro_calendar:{event_key or '-'}:{status or '-'}:{limit}"
    cached = await shared_query_cache.get_or_set(
        cache_key, settings.macro_calendar_cache_seconds, producer
    )
    return [MacroEventCalendarRead.model_validate(item) for item in cached]


@macro_router.post("/sync", response_model=MonitoringSyncResponse)
async def sync_macro(
    session: AsyncSession = Depends(get_db_session),
    _: CurrentUser = Depends(require_roles("admin", "trader", "analyst")),
):
    service = IndicatorMonitoringService(MarketRepository(session))
    runs = await service.sync_macro()
    await shared_query_cache.invalidate_prefix("monitoring:macro_calendar:")
    await shared_query_cache.invalidate_prefix("monitoring:macro_overview")
    await shared_query_cache.invalidate_prefix("monitoring:observations:")
    await precompute_service.enqueue_hint(
        PrecomputeHintRequest(
            current_page="macro-calendar",
            reason="macro_sync",
            priority=3,
        )
    )
    return MonitoringSyncResponse(
        runs=[
            {
                "run_id": item.run_id,
                "indicator_key": item.indicator_key,
                "rows_written": item.rows_written,
            }
            for item in runs
        ]
    )


@onchain_router.post("/sync", response_model=MonitoringSyncResponse)
async def sync_onchain(
    session: AsyncSession = Depends(get_db_session),
    _: CurrentUser = Depends(require_roles("admin", "trader", "analyst")),
):
    service = IndicatorMonitoringService(MarketRepository(session))
    runs = await service.sync_onchain()
    await shared_query_cache.invalidate_prefix("monitoring:observations:")
    return MonitoringSyncResponse(
        runs=[
            {
                "run_id": item.run_id,
                "indicator_key": item.indicator_key,
                "rows_written": item.rows_written,
            }
            for item in runs
        ]
    )


@router.post("/monitoring/risk-evaluate", response_model=RiskEvaluationRead)
async def evaluate_risk(
    payload: RiskEvaluationRequest,
    session: AsyncSession = Depends(get_db_session),
    _: CurrentUser = Depends(require_roles("admin", "trader", "analyst", "viewer")),
):
    candles = await MarketRepository(session).list_candles(
        payload.instrument_id, payload.timeframe, limit=80
    )
    assessment = RiskEngine().assess(
        RiskInput(
            entry_price=payload.entry_price,
            equity=payload.equity,
            leverage=payload.leverage,
            requested_notional=payload.requested_notional,
            current_total_exposure=payload.current_total_exposure,
            liquidation_price=payload.liquidation_price,
            data_quality_ok=payload.data_quality_ok,
            highs=[item.high for item in candles],
            lows=[item.low for item in candles],
            closes=[item.close for item in candles],
        )
    )
    return RiskEvaluationRead(
        recommended_position_notional=assessment.recommended_position_notional,
        recommended_stop_distance=assessment.recommended_stop_distance,
        allowed_to_trade=assessment.allowed_to_trade,
        reasons=assessment.reasons,
        reduce_size=assessment.reduce_size,
        pause_trading=assessment.pause_trading,
    )
