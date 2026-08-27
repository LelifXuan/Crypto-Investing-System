from __future__ import annotations

import asyncio
from collections.abc import AsyncIterator
from contextlib import asynccontextmanager

from sqlalchemy import event, text
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
        # 进程内写锁：SQLite 单写者。任何写入事务必须先 acquire 再
        # release，覆盖“写入 + flush + commit/rollback”完整边界，否则并发
        # 写会触发 database is locked（AGENTS.md §九.4）。
        self._write_lock = asyncio.Lock()

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
                    checkpoint_pages = int(
                        getattr(settings, "sqlite_wal_autocheckpoint_pages", 1000)
                    )
                    await connection.execute(text(f"PRAGMA wal_autocheckpoint={checkpoint_pages}"))
                    mmap_mb = int(getattr(settings, "sqlite_mmap_size_mb", 256))
                    if mmap_mb > 0:
                        await connection.execute(text(f"PRAGMA mmap_size={mmap_mb * 1024 * 1024}"))
                    await connection.execute(text("PRAGMA foreign_keys=ON"))

                # 每个池化连接也必须带 busy_timeout —— PRAGMA 是 per-connection
                # 状态，只对首个连接设置的话，并发会话的新连接会在等锁时立即
                # 失败（database is locked），busy_timeout 完全不生效。
                @event.listens_for(self._engine.sync_engine, "connect")
                def _set_sqlite_pragmas(dbapi_conn, _record):
                    cursor = dbapi_conn.cursor()
                    cursor.execute("PRAGMA busy_timeout=30000")
                    cursor.execute("PRAGMA foreign_keys=ON")
                    cursor.close()

    @asynccontextmanager
    async def writer_session(self) -> AsyncIterator[AsyncSession]:
        """Serialize write transactions behind the process-wide write lock.

        SQLite allows one writer; concurrent transactions that each span a
        network fetch (macro sync runs policy → fetch → flush) will otherwise
        contend on the same write lock and fail with ``database is locked``
        even with a busy_timeout. Wrap the session in the lock so only one
        transaction writes at a time.
        """
        async with self._write_lock:
            session = self.session_factory()
            try:
                yield session
                await session.commit()
            except Exception:
                await session.rollback()
                raise
            finally:
                await session.close()

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
