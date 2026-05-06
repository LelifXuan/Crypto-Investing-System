from __future__ import annotations

from decimal import Decimal

from pydantic import BaseModel, Field

from app.schemas.common import ORMModel


class TenantCreate(BaseModel):
    tenant_id: str
    name: str


class TenantRead(ORMModel):
    tenant_id: str
    name: str


class AccountCreate(BaseModel):
    account_id: str
    tenant_id: str
    venue: str
    base_currency: str
    status: str = "ACTIVE"


class AccountRead(ORMModel):
    account_id: str
    tenant_id: str
    venue: str
    base_currency: str
    status: str


class StrategyCreate(BaseModel):
    strategy_id: str
    tenant_id: str
    name: str
    tags: list[str] = Field(default_factory=list)
    status: str = "ACTIVE"


class StrategyRead(ORMModel):
    strategy_id: str
    tenant_id: str
    name: str
    tags: list[str]
    status: str


class InstrumentCreate(BaseModel):
    instrument_id: str
    venue: str
    symbol: str
    asset_class: str
    base_ccy: str
    quote_ccy: str
    settle_ccy: str
    tick_size: Decimal
    lot_size: Decimal
    contract_multiplier: Decimal = Decimal("1")
    margin_model: str = "NONE"
    metadata: dict = Field(default_factory=dict)


class InstrumentRead(ORMModel):
    instrument_id: str
    venue: str
    symbol: str
    asset_class: str
    base_ccy: str
    quote_ccy: str
    settle_ccy: str
    tick_size: Decimal
    lot_size: Decimal
    contract_multiplier: Decimal
    margin_model: str


class BootstrapSeedResponse(BaseModel):
    tenant_id: str
    account_id: str
    strategy_id: str
    instrument_id: str
    message: str
    mode: str
    admin_username: str | None = None
    admin_password_hint: str | None = None
