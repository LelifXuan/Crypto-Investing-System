from __future__ import annotations

import hashlib
import logging
from dataclasses import dataclass
from datetime import UTC, datetime, timedelta

import httpx

from app.core.config import settings
from app.core.db import db_manager
from app.db.models.market import TranslationCache
from app.repositories.market_repository import MarketRepository
from app.services.translation.cache import TranslationCacheStore
from app.services.translation.normalizer import (
    is_probably_mojibake,
    looks_like_english,
    normalize_segment,
    normalized_text_hash,
)
from app.services.translation.providers.router import get_translation_provider

logger = logging.getLogger(__name__)
_PROVIDER_COOLDOWNS: dict[str, datetime] = {}
_PROVIDER_COOLDOWN_LOGGED_UNTIL: dict[str, datetime] = {}


@dataclass(slots=True)
class TranslationBundle:
    original_title: str
    original_summary: str
    translated_title: str | None = None
    translated_summary: str | None = None
    translated: bool = False
    translation_status: str = "disabled"
    provider: str = "none"
    source_language: str = "en"
    target_language: str = settings.market_events_translation_target_lang
    error: str | None = None


class MarketEventTranslationService:
    def __init__(
        self,
        *,
        enabled: bool | None = None,
        provider: str | None = None,
    ) -> None:
        portable_forces_local = (
            settings.app_distribution_mode == "portable"
            and not settings.portable_remote_translation_enabled
        )
        configured_enabled = settings.market_events_translate_enabled and not portable_forces_local
        self.enabled = configured_enabled if enabled is None else enabled
        self.provider = (provider or settings.market_events_translation_provider or "none").lower()
        self.target_language = settings.market_events_translation_target_lang
        self.source_language = "en"

    @staticmethod
    def looks_like_english(text: str | None) -> bool:
        return looks_like_english(text)

    @staticmethod
    def is_probably_mojibake(text: str | None) -> bool:
        return is_probably_mojibake(text)

    @classmethod
    def should_translate_content(cls, title: str | None, summary: str | None) -> bool:
        return cls.looks_like_english(title) or cls.looks_like_english(summary)

    def needs_translation(
        self, payload: dict | None, title: str | None, summary: str | None
    ) -> bool:
        if not self.enabled:
            return False
        retry_after = _PROVIDER_COOLDOWNS.get(self.provider)
        if retry_after and retry_after > datetime.now(UTC):
            return False
        payload = dict(payload or {})
        translated_title = str(payload.get("translated_title") or "")
        translated_summary = str(payload.get("translated_summary") or "")
        status = str(payload.get("translation_status") or "").lower()
        if status == "translated" and not (
            self.is_probably_mojibake(translated_title)
            or self.is_probably_mojibake(translated_summary)
        ):
            return False
        return self.should_translate_content(title, summary)

    def build_initial_payload(
        self, existing_payload: dict | None, title: str | None, summary: str | None
    ) -> dict:
        bundle = TranslationBundle(
            original_title=title or "",
            original_summary=summary or "",
            translation_status="pending"
            if self.enabled and self.should_translate_content(title, summary)
            else ("disabled" if not self.enabled else "skipped"),
            provider=self.provider if self.enabled else "none",
            target_language=self.target_language,
        )
        return self.build_payload(existing_payload, bundle)

    async def translate_event_texts(
        self,
        title: str,
        summary: str | None,
        *,
        client: httpx.AsyncClient | None = None,
        event_id: str | None = None,
    ) -> TranslationBundle:
        bundle = TranslationBundle(
            original_title=title or "",
            original_summary=summary or "",
            provider=self.provider,
        )
        if not self.enabled:
            return bundle
        title_needed = self.looks_like_english(title)
        summary_needed = self.looks_like_english(summary)
        if not title_needed and not summary_needed:
            bundle.translation_status = "skipped"
            return bundle
        retry_after = _PROVIDER_COOLDOWNS.get(self.provider)
        if retry_after and retry_after > datetime.now(UTC):
            bundle.translation_status = "pending"
            return bundle

        own_client = client is None
        active_client = client or httpx.AsyncClient(
            timeout=settings.market_events_translation_timeout_seconds,
            follow_redirects=True,
        )
        try:
            try:
                _ = db_manager.session_factory
                db_available = True
            except RuntimeError:
                db_available = False
            fields = []
            if title_needed:
                fields.append(("title", title or ""))
            if summary_needed:
                fields.append(("summary", summary or ""))
            if db_available:
                segments = await self._translate_segments(
                    fields, client=active_client, event_id=event_id
                )
            else:
                segments = {}
                for field_name, raw_text in fields:
                    segments[field_name] = await self.translate_text(raw_text, client=active_client)
            bundle.translated_title = segments.get("title", title or "")
            bundle.translated_summary = segments.get("summary", summary or "")
            bundle.translated = (bundle.translated_title or "") != (title or "") or (
                bundle.translated_summary or ""
            ) != (summary or "")
            bundle.translation_status = "translated" if bundle.translated else "skipped"
            return bundle
        except Exception as exc:  # pragma: no cover
            retry_after = self._mark_provider_backoff(str(exc))
            if "429" in str(exc):
                self._log_provider_cooldown(retry_after)
            else:
                logger.warning("market event translation failed: %s", exc)
            bundle.translation_status = "error"
            bundle.error = str(exc)
            return bundle
        finally:
            if own_client:
                await active_client.aclose()

    async def translate_text(self, text: str, *, client: httpx.AsyncClient) -> str:
        if not text.strip() or self.provider in {"none", "disabled"}:
            return text
        translated = await self._translate_segments([("text", text)], client=client)
        return translated.get("text", text)

    def build_payload(self, existing_payload: dict | None, bundle: TranslationBundle) -> dict:
        payload = dict(existing_payload or {})
        payload["original_title"] = bundle.original_title
        payload["original_summary"] = bundle.original_summary
        payload["translation_provider"] = bundle.provider
        payload["translation_target_language"] = bundle.target_language
        payload["translation_status"] = bundle.translation_status
        if bundle.translated_title:
            payload["translated_title"] = bundle.translated_title
        if bundle.translated_summary:
            payload["translated_summary"] = bundle.translated_summary
        if bundle.error:
            payload["translation_error"] = bundle.error
            payload["translation_retry_after"] = (
                datetime.now(UTC)
                + timedelta(seconds=settings.market_events_translation_retry_delay_seconds)
            ).isoformat()
        else:
            payload.pop("translation_error", None)
            payload.pop("translation_retry_after", None)
        return payload

    def text_cache_key(self, text: str) -> str:
        return hashlib.sha256(text.strip().encode("utf-8")).hexdigest()

    async def _translate_segments(
        self,
        fields: list[tuple[str, str]],
        *,
        client: httpx.AsyncClient,
        event_id: str | None = None,
    ) -> dict[str, str]:
        provider = get_translation_provider(self.provider)
        if provider is None:
            return {field_name: text for field_name, text in fields}

        retry_after = _PROVIDER_COOLDOWNS.get(self.provider)
        if retry_after and retry_after > datetime.now(UTC):
            return {field_name: text for field_name, text in fields}

        try:
            _ = db_manager.session_factory
        except RuntimeError:
            translated_texts = await provider.translate_many(
                [raw_text for _, raw_text in fields],
                source_language=self.source_language,
                target_language=self.target_language,
                client=client,
            )
            return {
                field_name: translated
                for (field_name, _), translated in zip(fields, translated_texts, strict=False)
            }

        async with db_manager.session() as session:
            repo = MarketRepository(session)
            cache_store = TranslationCacheStore(repo)
            pending_fields: list[tuple[str, str, str, str]] = []
            translated_map: dict[str, str] = {}
            for field_name, raw_text in fields:
                normalized = normalize_segment(raw_text)
                normalized_hash = normalized_text_hash(raw_text)
                cached = await cache_store.get_segment(
                    provider=self.provider,
                    source_language=self.source_language,
                    target_language=self.target_language,
                    normalized_text=normalized,
                    normalized_hash=normalized_hash,
                )
                if cached and cached.status == "translated" and cached.translated_text:
                    translated_map[field_name] = cached.translated_text
                    if event_id:
                        await cache_store.mark_event_field(
                            event_id=event_id,
                            field_name=field_name,
                            provider=self.provider,
                            source_language=self.source_language,
                            target_language=self.target_language,
                            normalized_hash=normalized_hash,
                            status="cached",
                            translated_text=cached.translated_text,
                        )
                    continue
                pending_fields.append((field_name, raw_text, normalized, normalized_hash))

            if not pending_fields:
                return translated_map

            dedupe_key = hashlib.sha256(
                "|".join(
                    f"{field}:{normalized_hash}" for field, _, _, normalized_hash in pending_fields
                ).encode("utf-8")
            ).hexdigest()
            await cache_store.upsert_job(
                dedupe_key=dedupe_key,
                provider=self.provider,
                source_language=self.source_language,
                target_language=self.target_language,
                segment_count=len(pending_fields),
                status="running",
                started_at=datetime.now(UTC),
            )
            source_texts = [item[1] for item in pending_fields]
            try:
                translated_texts = await provider.translate_many(
                    source_texts,
                    source_language=self.source_language,
                    target_language=self.target_language,
                    client=client,
                )
                for (field_name, raw_text, normalized, normalized_hash), translated_text in zip(
                    pending_fields, translated_texts, strict=False
                ):
                    translated_map[field_name] = translated_text or raw_text
                    await cache_store.store_segment(
                        provider=self.provider,
                        source_language=self.source_language,
                        target_language=self.target_language,
                        normalized_text=normalized,
                        normalized_hash=normalized_hash,
                        translated_text=translated_text or raw_text,
                        status="translated",
                    )
                    await repo.upsert_translation_cache(
                        TranslationCache(
                            cache_id=f"compat_{normalized_hash}",
                            provider=self.provider,
                            target_language=self.target_language,
                            source_text_hash=self.text_cache_key(raw_text),
                            source_text=raw_text,
                            translated_text=translated_text or raw_text,
                            status="translated",
                            error_message=None,
                            retry_after=None,
                            hit_count=0,
                        )
                    )
                    if event_id:
                        await cache_store.mark_event_field(
                            event_id=event_id,
                            field_name=field_name,
                            provider=self.provider,
                            source_language=self.source_language,
                            target_language=self.target_language,
                            normalized_hash=normalized_hash,
                            status="fresh",
                            translated_text=translated_text or raw_text,
                        )
                await cache_store.upsert_job(
                    dedupe_key=dedupe_key,
                    provider=self.provider,
                    source_language=self.source_language,
                    target_language=self.target_language,
                    segment_count=len(pending_fields),
                    status="succeeded",
                    finished_at=datetime.now(UTC),
                )
            except Exception as exc:
                await cache_store.upsert_job(
                    dedupe_key=dedupe_key,
                    provider=self.provider,
                    source_language=self.source_language,
                    target_language=self.target_language,
                    segment_count=len(pending_fields),
                    status="failed",
                    error_message=str(exc),
                    finished_at=datetime.now(UTC),
                )
                for field_name, _raw_text, normalized, normalized_hash in pending_fields:
                    await cache_store.store_segment(
                        provider=self.provider,
                        source_language=self.source_language,
                        target_language=self.target_language,
                        normalized_text=normalized,
                        normalized_hash=normalized_hash,
                        translated_text=None,
                        status="error",
                        error_message=str(exc),
                    )
                    if event_id:
                        await cache_store.mark_event_field(
                            event_id=event_id,
                            field_name=field_name,
                            provider=self.provider,
                            source_language=self.source_language,
                            target_language=self.target_language,
                            normalized_hash=normalized_hash,
                            status="error",
                            translated_text=None,
                            error_message=str(exc),
                        )
                raise

            return translated_map

    def _mark_provider_backoff(self, error_message: str) -> datetime | None:
        if "429" not in error_message:
            return None
        retry_after = datetime.now(UTC) + timedelta(
            seconds=settings.market_events_translation_retry_delay_seconds
        )
        _PROVIDER_COOLDOWNS[self.provider] = retry_after
        return retry_after

    def _log_provider_cooldown(self, retry_after: datetime | None) -> None:
        if retry_after is None:
            return
        last_logged = _PROVIDER_COOLDOWN_LOGGED_UNTIL.get(self.provider)
        if last_logged and last_logged >= retry_after:
            return
        _PROVIDER_COOLDOWN_LOGGED_UNTIL[self.provider] = retry_after
        logger.info(
            "market event translation provider cooling down until %s",
            retry_after.isoformat(timespec="seconds"),
        )
