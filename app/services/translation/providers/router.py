from __future__ import annotations

from app.services.translation.providers.tencent import TencentTmtTranslationProvider


def get_translation_provider(provider_key: str):
    """Resolve a remote translation provider by key.

    Returns ``None`` for any non-cloud key. The local glossary path is
    handled directly by ``MarketEventTranslationService`` (see
    ``service.local_glossary_translate``) before this router is consulted,
    so the router does not need a ``local`` branch.
    """
    key = (provider_key or "none").strip().lower()
    if key in {"tencent_tmt", "tencent", "tmt"}:
        return TencentTmtTranslationProvider()
    return None