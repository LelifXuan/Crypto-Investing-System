from __future__ import annotations

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.db.models.account import Account
from app.db.models.core_entities import Strategy, Tenant
from app.db.models.instrument import Instrument


class BootstrapRepository:
    def __init__(self, session: AsyncSession) -> None:
        self.session = session

    async def get_tenant(self, tenant_id: str) -> Tenant | None:
        return await self.session.get(Tenant, tenant_id)

    async def add_tenant(self, tenant: Tenant) -> Tenant:
        existing = await self.get_tenant(tenant.tenant_id)
        if existing is not None:
            return existing
        self.session.add(tenant)
        await self.session.flush()
        return tenant

    async def get_account(self, account_id: str) -> Account | None:
        return await self.session.get(Account, account_id)

    async def add_account(self, account: Account) -> Account:
        existing = await self.get_account(account.account_id)
        if existing is not None:
            return existing
        self.session.add(account)
        await self.session.flush()
        return account

    async def get_strategy(self, strategy_id: str) -> Strategy | None:
        return await self.session.get(Strategy, strategy_id)

    async def add_strategy(self, strategy: Strategy) -> Strategy:
        existing = await self.get_strategy(strategy.strategy_id)
        if existing is not None:
            return existing
        self.session.add(strategy)
        await self.session.flush()
        return strategy

    async def get_instrument(self, instrument_id: str) -> Instrument | None:
        return await self.session.get(Instrument, instrument_id)

    async def add_instrument(self, instrument: Instrument) -> Instrument:
        existing = await self.get_instrument(instrument.instrument_id)
        if existing is not None:
            return existing
        self.session.add(instrument)
        await self.session.flush()
        return instrument

    async def list_accounts(self) -> list[Account]:
        result = await self.session.execute(select(Account).order_by(Account.account_id))
        return list(result.scalars().all())
