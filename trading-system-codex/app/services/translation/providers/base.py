from __future__ import annotations

from typing import Protocol

import httpx


class TranslationProvider(Protocol):
    provider_key: str

    async def translate_many(
        self,
        texts: list[str],
        *,
        source_language: str,
        target_language: str,
        client: httpx.AsyncClient,
    ) -> list[str]: ...
