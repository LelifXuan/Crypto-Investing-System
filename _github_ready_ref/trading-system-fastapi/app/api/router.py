from fastapi import APIRouter

from app.api.v1.endpoints import (
    auth,
    bootstrap,
    health,
    indicators,
    local_secrets,
    market_events,
    market_prices,
    pnl,
    positions,
    reviews,
)
from app.core.config import settings

api_router = APIRouter()
api_router.include_router(health.router)

v1_router = APIRouter(prefix=settings.api_v1_prefix)
v1_router.include_router(auth.router)
v1_router.include_router(bootstrap.router)
v1_router.include_router(local_secrets.router)
v1_router.include_router(market_prices.router)
v1_router.include_router(positions.router)
v1_router.include_router(pnl.router)
v1_router.include_router(indicators.router)
v1_router.include_router(market_events.router)
v1_router.include_router(reviews.router)

api_router.include_router(v1_router)
