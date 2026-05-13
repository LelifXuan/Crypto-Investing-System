from __future__ import annotations

from collections.abc import AsyncIterator
from contextlib import asynccontextmanager

from sqlalchemy import text
from sqlalchemy.ext.asyncio import (
    AsyncEngine,
    AsyncSession,
    async_sessionmaker,
    create_async_engine,
)

from app.core.config import settings
from app.core.schema_compat import ensure_schema_compatibility
from app.db.base import Base
from app.db.models import *  # noqa: F401,F403


class DatabaseManager:
    def __init__(self) -> None:
        self._engine: AsyncEngine | None = None
        self._session_factory: async_sessionmaker[AsyncSession] | None = None

    async def connect(self) -> None:
        if self._engine is None:
            engine_kwargs = {"pool_pre_ping": True}
            if settings.database_url.startswith("sqlite+aiosqlite:"):
                engine_kwargs["connect_args"] = {"timeout": 30}
            self._engine = create_async_engine(settings.database_url, **engine_kwargs)
            self._session_factory = async_sessionmaker(self._engine, expire_on_commit=False)
            if settings.database_url.startswith("sqlite+aiosqlite:"):
                async with self._engine.begin() as connection:
                    await connection.execute(text("PRAGMA journal_mode=WAL"))
                    await connection.execute(text("PRAGMA synchronous=NORMAL"))
                    await connection.execute(text("PRAGMA busy_timeout=30000"))
                    cache_kb = int(getattr(settings, "sqlite_cache_size_kb", 65536))
                    await connection.execute(text(f"PRAGMA cache_size=-{cache_kb}"))
                    await connection.execute(text("PRAGMA temp_store=MEMORY"))
                    checkpoint_pages = int(getattr(settings, "sqlite_wal_autocheckpoint_pages", 1000))
                    await connection.execute(text(f"PRAGMA wal_autocheckpoint={checkpoint_pages}"))
                    mmap_mb = int(getattr(settings, "sqlite_mmap_size_mb", 256))
                    if mmap_mb > 0:
                        await connection.execute(text(f"PRAGMA mmap_size={mmap_mb * 1024 * 1024}"))
                    await connection.execute(text("PRAGMA foreign_keys=ON"))

    async def disconnect(self) -> None:
        if self._engine is not None:
            await self._engine.dispose()
            self._engine = None
            self._session_factory = None

    @property
    def engine(self) -> AsyncEngine:
        if self._engine is None:
            raise RuntimeError("Database engine has not been initialized.")
        return self._engine

    @property
    def session_factory(self) -> async_sessionmaker[AsyncSession]:
        if self._session_factory is None:
            raise RuntimeError("Session factory has not been initialized.")
        return self._session_factory

    @asynccontextmanager
    async def session(self) -> AsyncIterator[AsyncSession]:
        session = self.session_factory()
        try:
            yield session
            await session.commit()
        except Exception:
            await session.rollback()
            raise
        finally:
            await session.close()

    async def ping(self) -> bool:
        async with self.engine.connect() as connection:
            await connection.execute(text("select 1"))
        return True

    async def create_schema(self) -> None:
        async with self.engine.begin() as connection:
            await connection.run_sync(Base.metadata.create_all)

    async def ensure_schema_compatibility(self) -> None:
        await ensure_schema_compatibility(self.engine)

    async def create_tables(self, *tables) -> None:
        if not tables:
            return
        async with self.engine.begin() as connection:
            await connection.run_sync(
                lambda sync_conn: Base.metadata.create_all(sync_conn, tables=list(tables))
            )


db_manager = DatabaseManager()
