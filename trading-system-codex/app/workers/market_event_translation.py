from __future__ import annotations

import asyncio
import contextlib
import logging
import time

from app.core.config import settings
from app.core.db import db_manager
from app.db.models.market import MarketEvent
from app.repositories.market_repository import MarketRepository
from app.services.translation import MarketEventTranslationService

logger = logging.getLogger(__name__)


class MarketEventTranslationWorker:
    def __init__(self) -> None:
        self._task: asyncio.Task | None = None
        self._stopping: asyncio.Event | None = None
        self._queue: asyncio.Queue[str] | None = None
        self._queued_ids: set[str] = set()
        self._inflight_ids: set[str] = set()
        self._loop: asyncio.AbstractEventLoop | None = None
        self._failure_streak = 0
        self._last_error_log_at = 0.0

    async def start(self) -> None:
        if (
            not settings.market_events_translation_worker_enabled
            or not settings.market_events_translate_enabled
            or self._task is not None
        ):
            return
        self._loop = asyncio.get_running_loop()
        self._stopping = asyncio.Event()
        self._queue = asyncio.Queue()
        self._failure_streak = 0
        self._last_error_log_at = 0.0
        self._task = asyncio.create_task(self._run_loop(), name="market-event-translation-worker")

    async def stop(self) -> None:
        if self._task is None:
            return
        if self._stopping is not None:
            self._stopping.set()
        self._task.cancel()
        with contextlib.suppress(asyncio.CancelledError):
            await self._task
        self._task = None
        self._loop = None
        self._queued_ids.clear()
        self._inflight_ids.clear()
        while self._queue is not None and not self._queue.empty():
            with contextlib.suppress(asyncio.QueueEmpty):
                self._queue.get_nowait()
        self._queue = None
        self._stopping = None

    async def enqueue_event_ids(self, event_ids: list[str]) -> int:
        if self._queue is None:
            return 0
        queued = 0
        for event_id in event_ids:
            if not event_id or event_id in self._queued_ids or event_id in self._inflight_ids:
                continue
            self._queued_ids.add(event_id)
            await self._queue.put(event_id)
            queued += 1
        return queued

    async def run_once(self) -> int:
        batch = await self._collect_queued_batch(wait_for_first=False)
        if not batch:
            batch = await self._load_backlog_batch()
        if not batch:
            return 0
        return await self._translate_event_ids(batch)

    async def _run_loop(self) -> None:
        while self._stopping is not None and not self._stopping.is_set():
            try:
                batch = await self._collect_queued_batch(wait_for_first=True)
                if not batch:
                    batch = await self._load_backlog_batch()
                if batch:
                    translated = await self._translate_event_ids(batch)
                    logger.info("market event translations processed %s items", translated)
                self._failure_streak = 0
            except asyncio.CancelledError:
                raise
            except Exception as exc:  # pragma: no cover
                self._failure_streak += 1
                self._log_failure(exc)
                await asyncio.sleep(min(30, 2 ** min(self._failure_streak, 4)))

    async def _collect_queued_batch(self, *, wait_for_first: bool) -> list[str]:
        batch: list[str] = []
        if self._queue is None:
            return batch
        if wait_for_first:
            try:
                first = await asyncio.wait_for(
                    self._queue.get(),
                    timeout=settings.market_events_translation_poll_seconds,
                )
                self._queued_ids.discard(first)
                self._inflight_ids.add(first)
                batch.append(first)
            except TimeoutError:
                return []
        while len(batch) < settings.market_events_translation_batch_size:
            try:
                event_id = self._queue.get_nowait()
            except asyncio.QueueEmpty:
                break
            self._queued_ids.discard(event_id)
            self._inflight_ids.add(event_id)
            batch.append(event_id)
        return batch

    async def _load_backlog_batch(self) -> list[str]:
        translator = MarketEventTranslationService(enabled=True)
        async with db_manager.session() as session:
            repo = MarketRepository(session)
            events = await repo.list_market_events(
                limit=settings.market_events_translation_batch_size * 3
            )
        pending = [
            event.event_id
            for event in events
            if translator.needs_translation(event.payload_json, event.title, event.summary)
            and event.event_id not in self._queued_ids
            and event.event_id not in self._inflight_ids
        ]
        return pending[: settings.market_events_translation_batch_size]

    async def _translate_event_ids(self, event_ids: list[str]) -> int:
        semaphore = asyncio.Semaphore(max(1, settings.market_events_translation_concurrency))
        text_cache: dict[tuple[str, str], str] = {}

        async def translate_one(event_id: str) -> bool:
            async with semaphore:
                async with db_manager.session() as session:
                    repo = MarketRepository(session)
                    translator = MarketEventTranslationService(enabled=True)
                    event = await repo.get_market_event(event_id)
                    if event is None or not translator.needs_translation(
                        event.payload_json, event.title, event.summary
                    ):
                        return False
                    original_translate_text = translator.translate_text

                    async def cached_translate_text(text: str, *, client):  # noqa: ANN001
                        cache_key = (translator.target_language, text.strip())
                        if cache_key in text_cache:
                            return text_cache[cache_key]
                        translated = await original_translate_text(text, client=client)
                        text_cache[cache_key] = translated
                        return translated

                    translator.translate_text = cached_translate_text
                    bundle = await translator.translate_event_texts(
                        event.title,
                        event.summary,
                        event_id=event.event_id,
                    )
                    payload_json = translator.build_payload(event.payload_json, bundle)
                    await repo.add_market_event(
                        MarketEvent(
                            event_id=event.event_id,
                            category=event.category,
                            title=event.title,
                            summary=event.summary,
                            source=event.source,
                            reliability=event.reliability,
                            ts_event=event.ts_event,
                            payload_json=payload_json,
                        )
                    )
                    return bundle.translation_status == "translated"

        results = await asyncio.gather(
            *(translate_one(event_id) for event_id in event_ids), return_exceptions=True
        )
        translated = 0
        for event_id, result in zip(event_ids, results, strict=False):
            self._inflight_ids.discard(event_id)
            if isinstance(result, Exception):  # pragma: no cover
                self._log_failure(result)
                continue
            translated += int(bool(result))
        return translated

    def _log_failure(self, error: Exception) -> None:
        now = time.monotonic()
        if now - self._last_error_log_at < 10:
            return
        self._last_error_log_at = now
        logger.warning(
            "market event translation worker failed (%s): %s", self._failure_streak, error
        )


market_event_translation_worker = MarketEventTranslationWorker()
