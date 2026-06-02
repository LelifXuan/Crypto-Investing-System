from __future__ import annotations

from app.services.translation.providers.mymemory import MyMemoryTranslationProvider
from app.services.translation.providers.tencent import TencentTmtTranslationProvider


def get_translation_provider(provider_key: str):
    key = (provider_key or "none").strip().lower()
    if key in {"mymemory", "memory"}:
        return MyMemoryTranslationProvider()
    if key in {"tencent_tmt", "tencent", "tmt"}:
        return TencentTmtTranslationProvider()
    if key in {"local", "local_glossary", "glossary"}:
        return None
    return None
