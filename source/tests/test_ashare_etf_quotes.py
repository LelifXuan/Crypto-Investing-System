from __future__ import annotations

import asyncio

import pytest

from app.services.ashare_etf_quotes import (
    AShareETFQuote,
    AShareETFQuoteService,
    EastmoneyDirectETFClient,
    SinaETFQuoteClient,
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


def test_sina_quote_parser_preserves_live_source_and_utc_timestamp() -> None:
    fields = [
        "军工ETF",
        "1.100",
        "1.090",
        "1.120",
        "1.130",
        "1.080",
        "1.119",
        "1.120",
        "123400",
        "138000.50",
        *(["0"] * 20),
        "2026-08-24",
        "14:30:00",
        "00",
    ]
    text = f'var hq_str_sh512660="{",".join(fields)}";'
    quotes = SinaETFQuoteClient._parse_payload(
        text,
        {
            "sh512660": {
                "code": "512660",
                "name": "军工ETF",
                "group": "halo",
                "group_label": "HALO",
            }
        },
    )

    assert len(quotes) == 1
    assert quotes[0].status == "ok"
    assert quotes[0].source == "sina_quote"
    assert quotes[0].last_price == pytest.approx(1.12)
    assert quotes[0].change_pct == pytest.approx((1.12 - 1.09) / 1.09 * 100)
    assert quotes[0].quote_time is not None
    assert quotes[0].quote_time.isoformat() == "2026-08-24T06:30:00+00:00"


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


@pytest.mark.asyncio
async def test_etf_normal_read_returns_persistent_close_before_live_refresh(tmp_path) -> None:
    cache_path = tmp_path / "ashare_etf_quotes.json"
    seed = AShareETFQuoteService(
        providers=[SuccessfulProvider()],
        ttl_seconds=15,
        stale_cache_seconds=1800,
        cache_path=cache_path,
    )
    await seed.get_quotes(group="all", force=True)

    release = asyncio.Event()

    class SlowProvider(SuccessfulProvider):
        async def fetch_quotes(self, requested_items):
            await release.wait()
            return await super().fetch_quotes(requested_items)

    service = AShareETFQuoteService(
        providers=[SlowProvider()],
        ttl_seconds=15,
        stale_cache_seconds=1800,
        cache_path=cache_path,
    )
    payload = await asyncio.wait_for(
        service.get_quotes(group="all", force=False),
        timeout=0.1,
    )

    assert payload["cache_status"] == "stale"
    assert payload["freshness_state"] == "usable_stale"
    assert payload["refresh_enqueued"] is True
    release.set()
    await asyncio.sleep(1.1)
