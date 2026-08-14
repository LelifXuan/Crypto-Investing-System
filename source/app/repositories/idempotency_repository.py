from __future__ import annotations

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.db.models.eventing import IdempotencyKeyRecord


class IdempotencyRepository:
    def __init__(self, session: AsyncSession) -> None:
        self.session = session

    async def find(self, idempotency_key: str, request_path: str) -> IdempotencyKeyRecord | None:
        result = await self.session.execute(
            select(IdempotencyKeyRecord).where(
                IdempotencyKeyRecord.idempotency_key == idempotency_key,
                IdempotencyKeyRecord.request_path == request_path,
            )
        )
        return result.scalar_one_or_none()

    async def add(self, record: IdempotencyKeyRecord) -> IdempotencyKeyRecord:
        self.session.add(record)
        await self.session.flush()
        return record
