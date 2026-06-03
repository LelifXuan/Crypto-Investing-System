from __future__ import annotations

from datetime import UTC, datetime, timedelta
from decimal import Decimal
from pathlib import Path

import pytest
from fastapi.testclient import TestClient

from app.core.config import settings
from app.core.db import db_manager
from app.db.models.instrument import Instrument
from app.db.models.market import MarketCandle
from app.main import create_app
from app.repositories.market_repository import MarketRepository
from app.services.indicator_monitoring import IndicatorMonitoringService


@pytest.fixture()
async def monitoring_db(tmp_path: Path, monkeypatch):
    db_path = tmp_path / "monitoring.db"
    monkeypatch.setattr(settings, "database_url", f"sqlite+aiosqlite:///{db_path.as_posix()}")
    monkeypatch.setattr(settings, "monitoring_scheduler_enabled", False)
    await db_manager.disconnect()
    await db_manager.connect()
    await db_manager.create_schema()
    try:
        yield
    finally:
        await db_manager.disconnect()


@pytest.mark.asyncio
async def test_seed_defaults_loads_catalog_and_rules(monitoring_db) -> None:
    async with db_manager.session() as session:
        service = IndicatorMonitoringService(MarketRepository(session))
        await service.seed_defaults()
        repo = MarketRepository(session)
        definitions = await repo.list_indicator_definitions(enabled_only=True)
        policies = await repo.list_monitoring_policies(enabled_only=True)
        rules = await repo.list_alert_rules(enabled_only=True)

    assert any(item.category == "technical" for item in definitions)
    assert any(item.category == "macro" for item in definitions)
    assert any(item.category == "onchain" for item in definitions)
    assert any(item.indicator_key == "ema_20" for item in policies)
    assert any(item.rule_key == "macro_fomc_pre_window" for item in rules)


@pytest.mark.asyncio
async def test_sync_macro_creates_observations(monitoring_db, monkeypatch) -> None:
    async with db_manager.session() as session:
        service = IndicatorMonitoringService(MarketRepository(session))
        await service.seed_defaults()

        async def fake_fred_latest(symbol: str):
            values = {"DFF": "5.25", "DGS2": "4.60", "DGS10": "4.10"}
            return service._mid_month_release(2026, 4, 1), Decimal(values[symbol])

        monkeypatch.setattr(service, "_fred_latest", fake_fred_latest)
        runs = await service.sync_macro()
        observations = await MarketRepository(session).list_indicator_observations(
            category="macro", limit=50
        )

    assert runs
    assert any(item.indicator_key == "us_dff" for item in observations)
    assert any(item.indicator_key == "fomc_event_window" for item in observations)


@pytest.mark.asyncio
async def test_latest_by_key_returns_observation_models(monitoring_db, monkeypatch) -> None:
    async with db_manager.session() as session:
        service = IndicatorMonitoringService(MarketRepository(session))
        await service.seed_defaults()

        async def fake_fred_latest(symbol: str):
            values = {"DFF": "5.25", "DGS2": "4.60", "DGS10": "4.10"}
            return service._mid_month_release(2026, 4, 1), Decimal(values[symbol])

        monkeypatch.setattr(service, "_fred_latest", fake_fred_latest)
        await service.sync_macro()

        latest = await MarketRepository(session).list_latest_observations_by_key(
            category="macro",
            limit_per_key=1,
        )

    assert latest
    assert all(hasattr(item, "indicator_key") for item in latest)
    assert any(item.indicator_key == "us_dff" for item in latest)


@pytest.mark.asyncio
async def test_derivatives_contract_uses_policy_instrument_mapping(monitoring_db) -> None:
    async with db_manager.session() as session:
        repo = MarketRepository(session)
        session.add(
            Instrument(
                instrument_id="eth-usdt-perp",
                venue="GATEIO",
                symbol="ETH_USDT",
                asset_class="PERP",
                base_ccy="ETH",
                quote_ccy="USDT",
                settle_ccy="USDT",
                tick_size=Decimal("0.01"),
                lot_size=Decimal("0.001"),
                contract_multiplier=Decimal("1"),
                margin_model="ISOLATED",
                metadata_json={
                    "gateio": {"product_type": "futures", "contract": "ETH_USDT", "settle": "usdt"}
                },
            )
        )
        service = IndicatorMonitoringService(repo)
        await service.seed_defaults(default_instrument_id="eth-usdt-perp")
        calls: list[tuple[str, str]] = []

        async def fake_contract(settle: str, contract: str):
            calls.append((settle, contract))
            return {
                "mark_price": Decimal("3000"),
                "index_price": Decimal("2990"),
                "last_price": Decimal("3005"),
                "funding_rate": Decimal("0.0001"),
            }

        service.market_service.gate_client.get_futures_contract = fake_contract
        policies = await repo.list_monitoring_policies(
            enabled_only=True,
            instrument_id="eth-usdt-perp",
            category="technical",
        )
        policy = next(item for item in policies if item.indicator_key == "funding_rate")
        await service.run_policy(policy)

    assert calls == [("usdt", "ETH_USDT")]


@pytest.mark.asyncio
async def test_sync_onchain_can_generate_alerts(monitoring_db, monkeypatch) -> None:
    async with db_manager.session() as session:
        service = IndicatorMonitoringService(MarketRepository(session))
        await service.seed_defaults()

        def fake_demo_value(indicator_key: str, asset_code: str, now):
            mapping = {
                "btc_mvrv": 4,
                "eth_mvrv": 2,
                "btc_sth_mvrv": 2,
                "btc_lth_mvrv": 2,
                "btc_exchange_net_position_change": -100,
                "eth_exchange_net_position_change": -10,
                "btc_active_addresses": 2000000,
                "eth_active_addresses": 800000,
            }
            return Decimal(str(mapping[indicator_key]))

        monkeypatch.setattr(service, "_demo_onchain_value", fake_demo_value)
        await service.sync_onchain()
        alerts = await MarketRepository(session).list_alert_events(limit=50)

    assert any(item.rule_key == "onchain_btc_mvrv_overheated" for item in alerts)


@pytest.mark.asyncio
async def test_risk_evaluate_endpoint_returns_guardrails(monitoring_db) -> None:
    async with db_manager.session() as session:
        base = datetime(2026, 4, 1, tzinfo=UTC)
        session.add(
            Instrument(
                instrument_id="btc-usdt-perp",
                venue="GATEIO",
                symbol="BTC_USDT",
                asset_class="PERP",
                base_ccy="BTC",
                quote_ccy="USDT",
                settle_ccy="USDT",
                tick_size=Decimal("0.1"),
                lot_size=Decimal("0.001"),
                contract_multiplier=Decimal("1"),
                margin_model="ISOLATED",
                metadata_json={
                    "gateio": {"product_type": "futures", "contract": "BTC_USDT", "settle": "usdt"}
                },
            )
        )
        candles = []
        for index in range(80):
            close = Decimal("100000") + Decimal(index * 150)
            candles.append(
                MarketCandle(
                    instrument_id="btc-usdt-perp",
                    timeframe="1h",
                    ts_open=base + timedelta(hours=index),
                    open=close - Decimal("120"),
                    high=close + Decimal("260"),
                    low=close - Decimal("240"),
                    close=close,
                    volume=Decimal("1000") + Decimal(index * 10),
                    source="test",
                )
            )
        session.add_all(candles)

    with TestClient(create_app(enable_lifespan=False)) as client:
        response = client.post(
            "/api/v1/monitoring/risk-evaluate",
            json={
                "instrument_id": "btc-usdt-perp",
                "timeframe": "1h",
                "entry_price": "112000",
                "equity": "100000",
                "current_total_exposure": "300000",
                "requested_notional": "120000",
                "leverage": "3",
                "liquidation_price": "96000",
            },
        )

    assert response.status_code == 200
    payload = response.json()
    assert "recommended_position_notional" in payload
    assert "allowed_to_trade" in payload
    assert isinstance(payload["reasons"], list)


@pytest.mark.asyncio
async def test_sync_technical_reuses_shared_candle_and_contract_fetches(
    monitoring_db,
    monkeypatch,
) -> None:
    async with db_manager.session() as session:
        repo = MarketRepository(session)
        session.add(
            Instrument(
                instrument_id="eth-usdt-perp",
                venue="GATEIO",
                symbol="ETH_USDT",
                asset_class="PERP",
                base_ccy="ETH",
                quote_ccy="USDT",
                settle_ccy="USDT",
                tick_size=Decimal("0.01"),
                lot_size=Decimal("0.001"),
                contract_multiplier=Decimal("1"),
                margin_model="ISOLATED",
                metadata_json={
                    "gateio": {"product_type": "futures", "contract": "ETH_USDT", "settle": "usdt"}
                },
            )
        )
        service = IndicatorMonitoringService(repo)
        await service.seed_defaults(default_instrument_id="eth-usdt-perp")

        base = datetime(2026, 4, 1, tzinfo=UTC)
        candle_calls = 0
        contract_calls = 0

        async def fake_candles(*, instrument_id, timeframe, limit=240, persist=True, **kwargs):
            nonlocal candle_calls
            candle_calls += 1
            candles = []
            for index in range(limit):
                close = Decimal("3000") + Decimal(index)
                candles.append(
                    MarketCandle(
                        instrument_id=instrument_id,
                        timeframe=timeframe,
                        ts_open=base + timedelta(hours=index),
                        open=close - Decimal("5"),
                        high=close + Decimal("10"),
                        low=close - Decimal("10"),
                        close=close,
                        volume=Decimal("1000") + Decimal(index),
                        source="test",
                    )
                )
            return candles

        async def fake_contract(settle: str, contract: str):
            nonlocal contract_calls
            contract_calls += 1
            return {
                "mark_price": Decimal("3000"),
                "index_price": Decimal("2995"),
                "last_price": Decimal("3002"),
                "funding_rate": Decimal("0.0001"),
            }

        async def fake_evaluate_alerts(observations):
            return None

        monkeypatch.setattr(service.market_service, "sync_candles_from_provider", fake_candles)
        monkeypatch.setattr(
            service.market_service.gate_client,
            "get_futures_contract",
            fake_contract,
        )
        monkeypatch.setattr(service, "_evaluate_alerts", fake_evaluate_alerts)

        await service.sync_technical(
            instrument_id="eth-usdt-perp",
            timeframe="1h",
            include_microstructure=False,
        )

    assert candle_calls == 1
    assert contract_calls == 1
