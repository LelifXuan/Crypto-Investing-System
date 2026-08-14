from __future__ import annotations

from fastapi import APIRouter, Depends
from sqlalchemy.ext.asyncio import AsyncSession

from app.api.dependencies import get_db_session
from app.repositories.auth_repository import AuthRepository
from app.repositories.bootstrap_repository import BootstrapRepository
from app.repositories.market_repository import MarketRepository
from app.schemas.bootstrap import BootstrapSeedResponse
from app.services.bootstrap import seed_local_defaults

router = APIRouter(prefix="/bootstrap", tags=["bootstrap"])


@router.post("/seed", response_model=BootstrapSeedResponse)
async def seed_demo_data(session: AsyncSession = Depends(get_db_session)) -> dict:
    result = await seed_local_defaults(
        BootstrapRepository(session),
        MarketRepository(session),
        AuthRepository(session),
    )
    return {
        "tenant_id": result.tenant_id,
        "account_id": result.account_id,
        "strategy_id": result.strategy_id,
        "instrument_id": result.instrument_id,
        "message": "demo seed inserted",
        "admin_username": result.admin_username,
        "admin_password_hint": "configured in BOOTSTRAP_ADMIN_PASSWORD",
    }
