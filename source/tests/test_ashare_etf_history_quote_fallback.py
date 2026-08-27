from __future__ import annotations

import json
from types import SimpleNamespace

import pytest

from app.services import ashare_etf_quotes
from app.services.ashare_etf_quotes import AShareETFQuoteService


class _FailedProvider:
    provider_id = "failed"
    last_success_at = None
    last_error = "offline"

    async def fetch_quotes(self, _items):
        raise RuntimeError("offline")


@pytest.mark.asyncio
async def test_daily_history_is_explicit_stale_fallback(monkeypatch, tmp_path) -> None:
    cache_root = tmp_path / "cache"
    history_root = cache_root / "fund_history"
    history_root.mkdir(parents=True)
    (history_root / "512660.json").write_text(
        json.dumps(
            {
                "source": "sina_kline",
                "points": [
                    {"date": "2026-08-21", "close": 1.0},
                    {
                        "date": "2026-08-24",
                        "open": 1.01,
                        "high": 1.05,
                        "low": 1.0,
                        "close": 1.04,
                        "volume": 123,
                    },
                ],
            }
        ),
        encoding="utf-8",
    )
    monkeypatch.setattr(
        ashare_etf_quotes,
        "app_paths",
        SimpleNamespace(cache_dir=cache_root),
    )
    service = AShareETFQuoteService(
        providers=[_FailedProvider()],
        ttl_seconds=60,
        stale_cache_seconds=3600,
        cache_path=cache_root / "quotes.json",
    )
    monkeypatch.setattr(
        service,
        "list_items",
        lambda _group: [
            {
                "code": "512660",
                "name": "军工ETF",
                "group": "halo",
                "group_label": "HALO",
            }
        ],
    )

    payload = await service.get_quotes(group="all", force=True)

    item = payload["groups"][0]["items"][0]
    assert payload["source_status"] == "stale"
    assert payload["cache_status"] == "history_fallback"
    assert payload["freshness_state"] == "usable_stale"
    assert item["last_price"] == 1.04
    assert item["source"] == "sina_kline"
