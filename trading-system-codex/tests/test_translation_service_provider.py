from __future__ import annotations

from app.services.translation.service import MarketEventTranslationService


def test_local_glossary_replaces_crypto_terms():
    service = MarketEventTranslationService(enabled=True, provider="local_glossary")
    result = service.local_glossary_translate("Bitcoin ETF inflows and Ethereum futures funding")
    assert "比特币" in result
    assert "以太坊" in result
    assert "ETF" in result


def test_translation_disabled_returns_skipped():
    service = MarketEventTranslationService(enabled=False)
    assert not service.enabled
