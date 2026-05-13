from __future__ import annotations

import html
import json

import httpx

from app.core.config import settings


class MyMemoryTranslationProvider:
    provider_key = "mymemory"

    async def translate_many(
        self,
        texts: list[str],
        *,
        source_language: str,
        target_language: str,
        client: httpx.AsyncClient,
    ) -> list[str]:
        translated: list[str] = []
        for text in texts:
            response = await client.get(
                settings.market_events_translation_base_url,
                params={"q": text, "langpair": f"{source_language}|{target_language}"},
            )
            response.raise_for_status()
            payload = json.loads(response.content.decode("utf-8", errors="replace"))
            translated_text = str(
                payload.get("responseData", {}).get("translatedText", "")
            ).strip()
            translated.append(html.unescape(translated_text) or text)
        return translated
