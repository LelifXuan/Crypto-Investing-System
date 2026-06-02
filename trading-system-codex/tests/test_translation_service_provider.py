from __future__ import annotations

import json

import pytest

from app.core.config import settings
from app.services.translation.providers.tencent import TencentTmtTranslationProvider
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


class _FakeTencentResponse:
    def raise_for_status(self) -> None:
        return None

    def json(self) -> dict:
        return {"Response": {"TargetText": "你好"}}


class _FakeTencentClient:
    def __init__(self) -> None:
        self.calls: list[dict] = []

    async def post(self, url: str, *, content: bytes, headers: dict):
        self.calls.append({"url": url, "content": content, "headers": headers})
        return _FakeTencentResponse()


@pytest.mark.asyncio
async def test_tencent_provider_signs_and_parses_without_leaking_secret(monkeypatch):
    monkeypatch.setattr(settings, "tencent_tmt_secret_id", "AKID_TEST_ONLY")
    monkeypatch.setattr(settings, "tencent_tmt_secret_key", "SECRET_TEST_ONLY")
    monkeypatch.setattr(settings, "tencent_tmt_region", "ap-guangzhou")
    monkeypatch.setattr(settings, "tencent_tmt_endpoint", "https://tmt.tencentcloudapi.com")

    client = _FakeTencentClient()
    provider = TencentTmtTranslationProvider()
    result = await provider.translate_many(
        ["hello"],
        source_language="en",
        target_language="zh-CN",
        client=client,
    )

    assert result == ["你好"]
    assert client.calls
    headers = client.calls[0]["headers"]
    assert headers["X-TC-Action"] == "TextTranslate"
    assert headers["X-TC-Version"] == "2018-03-21"
    assert "TC3-HMAC-SHA256" in headers["Authorization"]
    assert "SECRET_TEST_ONLY" not in headers["Authorization"]
    payload = json.loads(client.calls[0]["content"].decode("utf-8"))
    assert payload["Source"] == "en"
    assert payload["Target"] == "zh"
