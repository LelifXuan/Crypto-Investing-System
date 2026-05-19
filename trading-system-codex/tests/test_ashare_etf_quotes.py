from __future__ import annotations

import pytest

from app.services.ashare_etf_quotes import AShareETFQuoteService, EastmoneyDirectETFClient


class FailingProvider(EastmoneyDirectETFClient):
    provider_id = "failing_provider"

    def __init__(self) -> None:
        super().__init__(base_url="https://example.invalid", timeout_seconds=1)

    async def fetch_quotes(self, requested_items):
        raise RuntimeError("provider_down")


@pytest.mark.asyncio
async def test_etf_catalog_contains_configured_universe() -> None:
    service = AShareETFQuoteService(
        providers=[FailingProvider()],
        ttl_seconds=15,
        stale_cache_seconds=1800,
    )

    catalog = service.catalog()
    codes = {item["code"] for item in catalog["items"]}

    assert codes == {"159201", "563010", "512660", "516950", "512400", "159930", "561560"}
    assert {group["group"] for group in catalog["groups"]} == {"cashflow", "halo"}


@pytest.mark.asyncio
async def test_etf_provider_failure_keeps_rows_visible_without_zero_prices() -> None:
    service = AShareETFQuoteService(
        providers=[FailingProvider()],
        ttl_seconds=15,
        stale_cache_seconds=1800,
    )

    payload = await service.get_quotes(group="all", force=True)
    rows = [item for group in payload["groups"] for item in group["items"]]

    assert payload["source_status"] == "error"
    assert len(rows) == 7
    assert all(item["status"] == "unavailable" for item in rows)
    assert all(item["last_price"] is None for item in rows)
