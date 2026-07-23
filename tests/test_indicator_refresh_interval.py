from datetime import datetime, timedelta, timezone
from decimal import Decimal

from app.db.models.market import IndicatorValue
from app.services.indicators import IndicatorService


class DummyIndicatorRepo:
    def __init__(self, values: list[IndicatorValue]) -> None:
        self.values = values

    async def list_indicator_values(
        self,
        instrument_id: str,
        timeframe: str,
        indicator_name: str | None = None,
        limit: int = 50,
    ) -> list[IndicatorValue]:
        filtered = [
            item
            for item in self.values
            if item.instrument_id == instrument_id and item.timeframe == timeframe
        ]
        if indicator_name is not None:
            filtered = [item for item in filtered if item.indicator_name == indicator_name]
        return filtered[:limit]


def make_value(minutes_ago: int) -> IndicatorValue:
    return IndicatorValue(
        indicator_value_id=1,
        instrument_id="btc-usdt-perp",
        timeframe="1d",
        indicator_name="EMA",
        params_hash="hash",
        ts_value=datetime.now(timezone.utc) - timedelta(minutes=minutes_ago),
        value_json={"value": str(Decimal("64000"))},
    )


async def test_ensure_indicator_data_skips_refresh_when_data_is_fresh(monkeypatch) -> None:
    service = IndicatorService(DummyIndicatorRepo([make_value(5)]))

    async def fail_calculate(**kwargs):
        raise AssertionError("calculate_all should not be called for fresh data")

    monkeypatch.setattr(service, "calculate_all", fail_calculate)

    values, refreshed = await service.ensure_indicator_data(
        instrument_id="btc-usdt-perp",
        timeframe="1d",
        auto_calculate=True,
    )

    assert len(values) == 1
    assert refreshed is False


async def test_ensure_indicator_data_refreshes_when_data_is_stale(monkeypatch) -> None:
    repo = DummyIndicatorRepo([make_value(11)])
    service = IndicatorService(repo)

    async def fake_calculate_all(**kwargs):
        repo.values = [make_value(0)]
        return repo.values

    monkeypatch.setattr(service, "calculate_all", fake_calculate_all)

    values, refreshed = await service.ensure_indicator_data(
        instrument_id="btc-usdt-perp",
        timeframe="1d",
        auto_calculate=True,
    )

    assert len(values) == 1
    assert refreshed is True
