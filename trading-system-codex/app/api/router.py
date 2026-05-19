from fastapi import APIRouter

from app.api.v1.endpoints import (
    analysis,
    ashare_etf,
    auth,
    bootstrap,
    etf,
    health,
    indicators,
    market_events,
    market_prices,
    monitoring,
    precompute,
    signals,
    strategy,
    structure,
)
from app.core.config import settings

api_router = APIRouter()
api_router.include_router(health.router)

v1_router = APIRouter(prefix=settings.api_v1_prefix)
v1_router.include_router(auth.router)
v1_router.include_router(bootstrap.router)
v1_router.include_router(market_prices.router)
v1_router.include_router(market_prices.marketdata_router)
v1_router.include_router(analysis.router)
v1_router.include_router(ashare_etf.router)
v1_router.include_router(etf.router)
v1_router.include_router(indicators.router)
v1_router.include_router(monitoring.indicators_catalog_router)
v1_router.include_router(monitoring.alerts_router)
v1_router.include_router(monitoring.macro_router)
v1_router.include_router(monitoring.onchain_router)
v1_router.include_router(monitoring.router)
v1_router.include_router(market_events.router)
v1_router.include_router(market_events.marketevents_router)
v1_router.include_router(precompute.router)
v1_router.include_router(structure.router)
v1_router.include_router(strategy.router)
v1_router.include_router(signals.router)

api_router.include_router(v1_router)
