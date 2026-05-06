from __future__ import annotations

from datetime import UTC, datetime, timedelta
from decimal import Decimal

import pytest

from app.repositories.market_repository import MarketRepository
from app.services.indicator_monitoring import IndicatorMonitoringService
from app.services.translation import MarketEventTranslationService


def test_translation_service_respects_retry_after_window() -> None:
    service = MarketEventTranslationService(enabled=True, provider="mymemory")
    payload = {
        "translation_status": "error",
        "translation_retry_after": (datetime.now(UTC) + timedelta(minutes=5)).isoformat(),
    }
    assert not service.needs_translation(payload, "Bitcoin ETF inflows rise", "Summary")


@pytest.mark.asyncio
async def test_fred_latest_accepts_case_insensitive_columns(monkeypatch) -> None:
    class DummyResponse:
        text = "date,dgs2\n2026-04-08,4.12\n2026-04-09,4.15\n"

        def raise_for_status(self) -> None:
            return None

    class DummyClient:
        async def __aenter__(self):
            return self

        async def __aexit__(self, exc_type, exc, tb):
            return None

        async def get(self, url, params=None):
            return DummyResponse()

    monkeypatch.setattr(
        "app.services.indicator_monitoring.httpx.AsyncClient", lambda timeout=10: DummyClient()
    )

    service = IndicatorMonitoringService(MarketRepository(None))  # type: ignore[arg-type]
    observation_ts, value = await service._fred_latest("DGS2")
    assert observation_ts == datetime(2026, 4, 9, tzinfo=UTC)
    assert value == Decimal("4.15")
