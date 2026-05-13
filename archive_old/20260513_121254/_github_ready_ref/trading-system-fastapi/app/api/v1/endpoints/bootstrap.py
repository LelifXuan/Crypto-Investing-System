from __future__ import annotations

from fastapi import APIRouter, Depends
from sqlalchemy.ext.asyncio import AsyncSession

from app.api.dependencies import get_db_session
from app.core.config import settings
from app.db.models.account import Account
from app.db.models.core_entities import Strategy, Tenant
from app.db.models.instrument import Instrument
from app.repositories.auth_repository import AuthRepository
from app.repositories.bootstrap_repository import BootstrapRepository
from app.schemas.bootstrap import BootstrapSeedResponse
from app.services.auth import AuthService

router = APIRouter(prefix="/bootstrap", tags=["bootstrap"])


@router.post("/seed", response_model=BootstrapSeedResponse)
async def seed_demo_data(session: AsyncSession = Depends(get_db_session)) -> dict:
    repo = BootstrapRepository(session)
    auth_service = AuthService(AuthRepository(session))
    tenant = await repo.add_tenant(Tenant(tenant_id="demo_tenant", name="Demo Tenant"))
    account = await repo.add_account(
        Account(account_id="demo_account", tenant_id=tenant.tenant_id, venue="GATEIO", base_currency="USD")
    )
    strategy = await repo.add_strategy(
        Strategy(strategy_id="demo_strategy", tenant_id=tenant.tenant_id, name="Trend Follow", tags=["demo"])
    )
    instrument = await repo.add_instrument(
        Instrument(
            instrument_id="btc-usdt-perp",
            venue="GATEIO",
            symbol="BTC_USDT",
            asset_class="PERP",
            base_ccy="BTC",
            quote_ccy="USDT",
            settle_ccy="USDT",
            tick_size="0.1",
            lot_size="0.001",
            contract_multiplier="1",
            margin_model="ISOLATED",
            metadata_json={
                "seeded": True,
                "gateio": {"product_type": "futures", "contract": "BTC_USDT", "settle": "usdt"},
            },
        )
    )
    if settings.single_user_mode:
        return {
            "tenant_id": tenant.tenant_id,
            "account_id": account.account_id,
            "strategy_id": strategy.strategy_id,
            "instrument_id": instrument.instrument_id,
            "message": "demo seed inserted for single-user local mode",
            "mode": "single_user_local",
            "admin_username": None,
            "admin_password_hint": None,
        }

    user = await auth_service.register_bootstrap_admin(
        tenant_id=tenant.tenant_id,
        username=settings.bootstrap_admin_username,
        password=settings.bootstrap_admin_password,
    )
    return {
        "tenant_id": tenant.tenant_id,
        "account_id": account.account_id,
        "strategy_id": strategy.strategy_id,
        "instrument_id": instrument.instrument_id,
        "message": "demo seed inserted",
        "mode": "multi_user_auth",
        "admin_username": user.username,
        "admin_password_hint": "configured in BOOTSTRAP_ADMIN_PASSWORD",
    }
