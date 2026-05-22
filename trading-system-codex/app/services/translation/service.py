from __future__ import annotations

import hashlib
import re
import time
from dataclasses import dataclass

import httpx

from app.core.config import settings
from app.services.translation.normalizer import is_probably_mojibake, looks_like_english

LOCAL_GLOSSARY = {
    "Bitcoin": "比特币",
    "BTC": "BTC",
    "Ethereum": "以太坊",
    "ETH": "ETH",
    "stablecoin": "稳定币",
    "stablecoins": "稳定币",
    "ETF": "ETF",
    "spot ETF": "现货 ETF",
    "futures": "期货",
    "funding": "资金费率",
    "open interest": "未平仓量",
    "liquidation": "爆仓",
    "inflows": "资金流入",
    "outflows": "资金流出",
    "exchange": "交易所",
    "regulatory": "监管",
    "macro": "宏观",
}


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
    """Small, resilient translation facade for market event text."""

    _provider_backoff_until: dict[str, float] = {}

    def __init__(self, *, enabled: bool | None = None, provider: str | None = None) -> None:
        portable_forces_local = (
            settings.app_distribution_mode == "portable"
            and not settings.portable_remote_translation_enabled
        )
        configured_enabled = settings.market_events_translate_enabled and not portable_forces_local
        self.enabled = configured_enabled if enabled is None else enabled
        self.provider = (provider or settings.market_events_translation_provider or "none").lower()
        self.target_language = settings.market_events_translation_target_lang
        self.source_language = "en"

    def _mark_provider_backoff(self, reason: str, *, seconds: int = 300) -> None:
        if "429" in str(reason) or "too many" in str(reason).lower():
            self._provider_backoff_until[self.provider] = time.monotonic() + seconds

    def _provider_in_backoff(self) -> bool:
        until = self._provider_backoff_until.get(self.provider, 0)
        return until > time.monotonic()

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
        if not self.enabled or self.provider in {"none", "disabled"}:
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
        status = (
            "pending" if self.needs_translation(existing_payload, title, summary) else "skipped"
        )
        if not self.enabled:
            status = "disabled"
        bundle = TranslationBundle(
            original_title=self._clean_text(title),
            original_summary=self._clean_text(summary),
            translation_status=status,
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
        original_title = self._clean_text(title)
        original_summary = self._clean_text(summary)
        if not self.enabled or self.provider in {"none", "disabled"}:
            return TranslationBundle(
                original_title=original_title,
                original_summary=original_summary,
                translation_status="disabled",
                provider="none",
            )
        if self._provider_in_backoff():
            return TranslationBundle(
                original_title=original_title,
                original_summary=original_summary,
                translated_title=original_title,
                translated_summary=original_summary,
                translated=False,
                translation_status="pending",
                provider=self.provider,
                target_language=self.target_language,
            )
        own_client = client is None
        if own_client:
            client = httpx.AsyncClient(timeout=15)
        try:
            texts = [original_title]
            if original_summary:
                texts.append(original_summary)
            translated = [await self.translate_text(item, client=client) for item in texts]
            translated_title = translated[0] if len(translated) > 0 else original_title
            translated_summary = translated[1] if len(translated) > 1 else original_summary
            return TranslationBundle(
                original_title=original_title,
                original_summary=original_summary,
                translated_title=translated_title,
                translated_summary=translated_summary,
                translated=True,
                translation_status="translated",
                provider=self.provider,
                target_language=self.target_language,
            )
        except Exception as exc:
            self._mark_provider_backoff(str(exc))
            return TranslationBundle(
                original_title=original_title,
                original_summary=original_summary,
                translated_title=original_title,
                translated_summary=original_summary,
                translated=False,
                translation_status="error",
                provider=self.provider,
                target_language=self.target_language,
                error=str(exc),
            )
        finally:
            if own_client and client is not None:
                await client.aclose()

    async def translate_text(self, text: str, *, client: httpx.AsyncClient) -> str:
        cleaned = self._clean_text(text)
        if not cleaned:
            return cleaned
        if self.provider in {"local", "local_glossary", "glossary"}:
            return self.local_glossary_translate(cleaned)
        from app.services.translation.providers.router import get_translation_provider

        provider_obj = get_translation_provider(self.provider)
        if provider_obj is None:
            return self.local_glossary_translate(cleaned)
        translated = await provider_obj.translate_many(
            [cleaned],
            source_language=self.source_language,
            target_language=self.target_language,
            client=client,
        )
        result = self._clean_text(translated[0] if translated else "")
        return result or self.local_glossary_translate(cleaned)

    def local_glossary_translate(self, text: str) -> str:
        translated = self._clean_text(text)
        for source, target in sorted(LOCAL_GLOSSARY.items(), key=lambda item: -len(item[0])):
            translated = re.sub(
                rf"\b{re.escape(source)}\b",
                target,
                translated,
                flags=re.IGNORECASE,
            )
        return translated

    def build_payload(self, existing_payload: dict | None, bundle: TranslationBundle) -> dict:
        payload = dict(existing_payload or {})
        payload["original_title"] = self._clean_text(bundle.original_title)
        payload["original_summary"] = self._clean_text(bundle.original_summary)
        payload["translation_provider"] = bundle.provider
        payload["translation_target_language"] = bundle.target_language
        payload["translation_status"] = bundle.translation_status
        if bundle.translated_title:
            payload["translated_title"] = self._clean_text(bundle.translated_title)
        if bundle.translated_summary:
            payload["translated_summary"] = self._clean_text(bundle.translated_summary)
        if bundle.error:
            payload["translation_error"] = bundle.error
        else:
            payload.pop("translation_error", None)
            payload.pop("translation_retry_after", None)
        return payload

    def text_cache_key(self, text: str) -> str:
        return hashlib.sha256(text.strip().encode("utf-8")).hexdigest()

    @staticmethod
    def _clean_text(value: str | None) -> str:
        text = str(value or "")
        replacements = {
            "\ufffds": "'s",
            "\ufffdS": "'s",
            "\ufffd": "'",
            "\u2018": "'",
            "\u2019": "'",
            "\u201c": '"',
            "\u201d": '"',
        }
        for old, new in replacements.items():
            text = text.replace(old, new)
        return text.strip()
