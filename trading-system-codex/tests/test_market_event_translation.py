from __future__ import annotations

import asyncio

import pytest

from app.services.translation import MarketEventTranslationService, TranslationBundle
from app.workers.market_event_translation import MarketEventTranslationWorker


def test_translation_service_detects_english_text() -> None:
    assert MarketEventTranslationService.looks_like_english("Bitcoin ETF demand rises")
    assert not MarketEventTranslationService.looks_like_english(
        "\u6bd4\u7279\u5e01 ETF \u6d41\u5165\u4e0a\u5347"
    )
    assert not MarketEventTranslationService.looks_like_english("")


async def test_translation_service_skips_when_disabled() -> None:
    service = MarketEventTranslationService(enabled=False)
    bundle = await service.translate_event_texts("Bitcoin surges after CPI", "Ethereum follows")
    assert bundle.translation_status == "disabled"
    assert not bundle.translated
    assert bundle.translated_title is None


async def test_translation_service_builds_payload_with_original_and_translated_text(
    monkeypatch,
) -> None:
    service = MarketEventTranslationService(enabled=True, provider="mymemory")

    async def fake_translate_text(text: str, *, client):  # noqa: ANN001
        return {
            "Bitcoin surges after CPI": "\u6bd4\u7279\u5e01\u5728 CPI \u540e\u8d70\u5f3a",
            "Ethereum follows higher": "\u4ee5\u592a\u574a\u8ddf\u968f\u8d70\u9ad8",
        }.get(text, text)

    monkeypatch.setattr(service, "translate_text", fake_translate_text)
    bundle = await service.translate_event_texts(
        "Bitcoin surges after CPI", "Ethereum follows higher"
    )
    payload = service.build_payload({"source_id": "feed.test"}, bundle)

    assert bundle.translation_status == "translated"
    assert payload["original_title"] == "Bitcoin surges after CPI"
    assert payload["translated_title"] == "\u6bd4\u7279\u5e01\u5728 CPI \u540e\u8d70\u5f3a"
    assert payload["translated_summary"] == "\u4ee5\u592a\u574a\u8ddf\u968f\u8d70\u9ad8"
    assert payload["translation_provider"] == "mymemory"


def test_translation_payload_preserves_existing_metadata() -> None:
    service = MarketEventTranslationService(enabled=True, provider="mymemory")
    payload = service.build_payload(
        {"source_id": "feed.test", "importance": "high"},
        TranslationBundle(
            original_title="Fed keeps rates unchanged",
            original_summary="Markets stay cautious",
            translated_title="\u7f8e\u8054\u50a8\u7ef4\u6301\u5229\u7387\u4e0d\u53d8",
            translated_summary="\u5e02\u573a\u4fdd\u6301\u8c28\u614e",
            translated=True,
            translation_status="translated",
            provider="mymemory",
        ),
    )

    assert payload["source_id"] == "feed.test"
    assert payload["importance"] == "high"
    assert payload["translated_title"] == "\u7f8e\u8054\u50a8\u7ef4\u6301\u5229\u7387\u4e0d\u53d8"


def test_translation_service_marks_english_items_as_pending() -> None:
    service = MarketEventTranslationService(enabled=True, provider="mymemory")
    payload = service.build_initial_payload(
        {"source_id": "feed.test"}, "Bitcoin ETF inflows rise", "Summary"
    )
    assert payload["translation_status"] == "pending"
    assert payload["original_title"] == "Bitcoin ETF inflows rise"


def test_translation_service_skips_already_translated_payload() -> None:
    service = MarketEventTranslationService(enabled=True, provider="mymemory")
    payload = {
        "translation_status": "translated",
        "translated_title": "\u6bd4\u7279\u5e01 ETF \u6d41\u5165\u4e0a\u5347",
        "translated_summary": "\u6458\u8981",
    }
    assert not service.needs_translation(payload, "Bitcoin ETF inflows rise", "Summary")


async def test_translation_service_respects_provider_cooldown() -> None:
    service = MarketEventTranslationService(enabled=True, provider="mymemory")
    service._mark_provider_backoff("429 Too Many Requests")
    bundle = await service.translate_event_texts("Bitcoin surges after CPI", "Ethereum follows")
    assert bundle.translation_status == "pending"


def test_build_initial_payload_stays_pending_during_provider_cooldown() -> None:
    service = MarketEventTranslationService(enabled=True, provider="mymemory")
    service._mark_provider_backoff("429 Too Many Requests")

    payload = service.build_initial_payload(
        {"source_id": "feed.test"}, "Bitcoin ETF inflows rise", "Summary"
    )

    assert payload["translation_status"] == "pending"


@pytest.mark.asyncio
async def test_worker_dedupes_queued_event_ids() -> None:
    worker = MarketEventTranslationWorker()
    from app.core.config import settings

    original_worker_enabled = settings.market_events_translation_worker_enabled
    original_translate_enabled = settings.market_events_translate_enabled
    settings.market_events_translation_worker_enabled = True
    settings.market_events_translate_enabled = True
    await worker.start()
    try:
        queued = await worker.enqueue_event_ids(["evt-1", "evt-1", "evt-2"])
        assert queued == 2
        assert worker._queue is not None
        assert worker._queue.qsize() == 2
    finally:
        settings.market_events_translation_worker_enabled = original_worker_enabled
        settings.market_events_translate_enabled = original_translate_enabled
        await worker.stop()


@pytest.mark.asyncio
async def test_worker_failure_backoff_grows(monkeypatch) -> None:
    worker = MarketEventTranslationWorker()
    from app.core.config import settings

    original_worker_enabled = settings.market_events_translation_worker_enabled
    original_translate_enabled = settings.market_events_translate_enabled
    original_poll = settings.market_events_translation_poll_seconds
    settings.market_events_translation_worker_enabled = True
    settings.market_events_translate_enabled = True
    settings.market_events_translation_poll_seconds = 1

    sleeps: list[int] = []

    async def fake_collect(*, wait_for_first: bool):  # noqa: ANN001
        raise RuntimeError("boom")

    async def fake_sleep(seconds: float) -> None:
        sleeps.append(int(seconds))
        if worker._stopping is not None:
            worker._stopping.set()

    monkeypatch.setattr(worker, "_collect_queued_batch", fake_collect)
    monkeypatch.setattr(asyncio, "sleep", fake_sleep)

    await worker.start()
    try:
        await worker._task
    finally:
        settings.market_events_translation_worker_enabled = original_worker_enabled
        settings.market_events_translate_enabled = original_translate_enabled
        settings.market_events_translation_poll_seconds = original_poll
        await worker.stop()

    assert sleeps
    assert sleeps[0] >= 2


def test_worker_logs_are_throttled(monkeypatch, caplog) -> None:
    worker = MarketEventTranslationWorker()
    timeline = iter([10.0, 12.0, 25.0])
    monkeypatch.setattr(
        "app.workers.market_event_translation.time.monotonic", lambda: next(timeline)
    )

    caplog.set_level("WARNING")
    worker._failure_streak = 1
    worker._log_failure(RuntimeError("first"))
    worker._failure_streak = 2
    worker._log_failure(RuntimeError("second"))
    worker._failure_streak = 3
    worker._log_failure(RuntimeError("third"))

    messages = [
        record.message
        for record in caplog.records
        if "market event translation worker failed" in record.message
    ]
    assert len(messages) == 2
