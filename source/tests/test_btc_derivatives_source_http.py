from __future__ import annotations

import httpx
import pytest

from app.services.btc_derivatives.sources import http as source_http
from app.services.btc_derivatives.sources.http import SourceHttpClient
from app.services.btc_derivatives.sources.registry import EndpointSpec, ProviderSpec


@pytest.mark.asyncio
async def test_permanent_provider_4xx_is_not_retried(monkeypatch) -> None:
    calls = 0

    def handler(request: httpx.Request) -> httpx.Response:
        nonlocal calls
        calls += 1
        return httpx.Response(451, json={"msg": "restricted"}, request=request)

    def fake_client_for_source(*_args, **_kwargs):
        return httpx.AsyncClient(transport=httpx.MockTransport(handler))

    monkeypatch.setattr(source_http, "client_for_source", fake_client_for_source)
    provider = ProviderSpec(
        key="restricted",
        label="Restricted",
        base_url="https://example.test",
        capabilities=("perps",),
        endpoints=(),
    )
    endpoint = EndpointSpec(
        name="ticker",
        capability="perps",
        method="GET",
        path="/ticker",
        ttl_seconds=60,
    )

    with pytest.raises(RuntimeError, match="permanent HTTP 451"):
        await SourceHttpClient().request(provider, endpoint, force=True)

    assert calls == 1
