from __future__ import annotations

import pytest

from app.services.ashare_etf_quotes import (
    AShareETFQuote,
    AShareETFQuoteService,
    EastmoneyDirectETFClient,
)


class FailingProvider(EastmoneyDirectETFClient):
    provider_id = "failing_provider"

    def __init__(self) -> None:
        super().__init__(base_url="https://example.invalid", timeout_seconds=1)

    async def fetch_quotes(self, requested_items):
        raise RuntimeError("provider_down")


class SuccessfulProvider(EastmoneyDirectETFClient):
    provider_id = "successful_provider"

    def __init__(self) -> None:
        super().__init__(base_url="https://example.invalid", timeout_seconds=1)

    async def fetch_quotes(self, requested_items):
        return [
            AShareETFQuote(
                code=str(item["code"]),
                name=str(item.get("name") or item["code"]),
                source_name=str(item.get("name") or item["code"]),
                group=str(item["group"]),
                group_label=str(item["group_label"]),
                market=str(item["market"]),
                secid=str(item["secid"]),
                last_price=1.23,
                change_pct=0.45,
                change_amount=0.01,
                volume=1000,
                amount=1230,
                high=1.25,
                low=1.2,
                open=1.21,
                prev_close=1.22,
                turnover_rate=None,
                volume_ratio=None,
                quote_time=None,
                source=self.provider_id,
                status="ok",
            )
            for item in requested_items
        ]


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
async def test_etf_provider_failure_keeps_rows_visible_without_zero_prices(tmp_path) -> None:
    service = AShareETFQuoteService(
        providers=[FailingProvider()],
        ttl_seconds=15,
        stale_cache_seconds=1800,
        cache_path=tmp_path / "empty_ashare_etf_quotes.json",
    )

    payload = await service.get_quotes(group="all", force=True)
    rows = [item for group in payload["groups"] for item in group["items"]]

    assert payload["source_status"] == "error"
    assert len(rows) == 7
    assert all(item["status"] == "unavailable" for item in rows)
    assert all(item["last_price"] is None for item in rows)


@pytest.mark.asyncio
async def test_etf_provider_failure_returns_persistent_cached_quotes(tmp_path) -> None:
    cache_path = tmp_path / "ashare_etf_quotes.json"
    service = AShareETFQuoteService(
        providers=[SuccessfulProvider()],
        ttl_seconds=15,
        stale_cache_seconds=1800,
        cache_path=cache_path,
    )

    live_payload = await service.get_quotes(group="all", force=True)
    assert live_payload["source_status"] == "ok"

    failing_service = AShareETFQuoteService(
        providers=[FailingProvider()],
        ttl_seconds=15,
        stale_cache_seconds=1800,
        cache_path=cache_path,
    )
    stale_payload = await failing_service.get_quotes(group="all", force=True)
    rows = [item for group in stale_payload["groups"] for item in group["items"]]

    assert stale_payload["source_status"] == "stale"
    assert stale_payload["cache_status"] == "stale"
    assert len(rows) == 7
    assert all(item["status"] == "ok" for item in rows)
    assert all(item["last_price"] == 1.23 for item in rows)
