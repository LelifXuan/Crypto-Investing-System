from __future__ import annotations

from datetime import UTC, datetime, timedelta
from decimal import Decimal
from pathlib import Path

import pytest
from fastapi.testclient import TestClient

from app.core.config import settings
from app.core.db import db_manager
from app.db.models.instrument import Instrument
from app.db.models.market import IndicatorObservation, MarketCandle
from app.main import create_app
from app.repositories.market_repository import MarketRepository
from app.services.indicator_monitoring import IndicatorMonitoringService


def _stub_gateio_rwa_provider(service: IndicatorMonitoringService, monkeypatch) -> None:
    provider = service.macro_provider_registry.resolve(
        source_provider="gateio_rwa",
        source_kind="raw_series",
    )

    class FakeResult:
        def __init__(self, symbol: str, value: str) -> None:
            self.observation_ts = datetime(2026, 4, 1, tzinfo=UTC)
            self.value = Decimal(value)
            self.source_ref = f"gateio_rwa:futures:{symbol}"
            self.source_granularity = "intraday"
            self.metadata = {}

    async def fake_fetch_latest(symbol: str):
        values = {
            "CL_USDT": "90.10",
            "VIX_USDT": "21.51",
            "NAS100_USDT": "29320.70",
            "SPX500_USDT": "7388.81",
        }
        return FakeResult(symbol, values.get(symbol, "100.00"))

    monkeypatch.setattr(provider, "fetch_latest", fake_fetch_latest)


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
        nfp_events = await repo.list_macro_events(event_key="us_nfp", limit=20)

    assert any(item.category == "technical" for item in definitions)
    assert any(item.category == "macro" for item in definitions)
    assert any(item.category == "onchain" for item in definitions)
    assert any(item.indicator_key == "ema_20" for item in policies)
    assert any(item.indicator_key == "real_yield_5y" for item in policies)
    assert any(item.rule_key == "macro_fomc_pre_window" for item in rules)
    assert nfp_events
    assert all(item.provider_key == "bls" for item in nfp_events)
    assert all(item.importance == "high" for item in nfp_events)
    assert all(item.scheduled_at.hour in {12, 13} for item in nfp_events)


@pytest.mark.asyncio
async def test_seed_defaults_prefers_gateio_rwa_for_wti_crude(monitoring_db) -> None:
    async with db_manager.session() as session:
        service = IndicatorMonitoringService(MarketRepository(session))
        await service.seed_defaults()
        definitions = await MarketRepository(session).list_indicator_definitions(enabled_only=True)

    wti = next(item for item in definitions if item.indicator_key == "wti_crude")
    assert wti.source_provider == "gateio_rwa"
    assert wti.calc_params_json["external_symbol"] == "CL_USDT"


@pytest.mark.asyncio
async def test_seed_defaults_prefers_gateio_rwa_contracts_for_us_indices(
    monitoring_db,
) -> None:
    async with db_manager.session() as session:
        service = IndicatorMonitoringService(MarketRepository(session))
        await service.seed_defaults()
        definitions = await MarketRepository(session).list_indicator_definitions(enabled_only=True)

    by_key = {item.indicator_key: item for item in definitions}
    vix = by_key["vix"]
    qqq = by_key["qqq"]
    spy = by_key["spy"]

    assert vix.source_provider == "gateio_rwa"
    assert vix.calc_params_json["external_symbol"] == "VIX_USDT"
    assert vix.calc_params_json["frequency"] == "intraday"
    assert qqq.source_provider == "gateio_rwa"
    assert qqq.calc_params_json["external_symbol"] == "NAS100_USDT"
    assert qqq.calc_params_json["frequency"] == "intraday"
    assert spy.source_provider == "gateio_rwa"
    assert spy.calc_params_json["external_symbol"] == "SPX500_USDT"
    assert spy.calc_params_json["frequency"] == "intraday"


@pytest.mark.asyncio
async def test_wti_sync_replaces_stale_fred_observation_with_gateio_rwa(
    monitoring_db, monkeypatch
) -> None:
    async with db_manager.session() as session:
        repo = MarketRepository(session)
        service = IndicatorMonitoringService(repo)
        await service.seed_defaults()
        definitions = await repo.list_indicator_definitions(enabled_only=True)
        wti_definition = next(item for item in definitions if item.indicator_key == "wti_crude")
        session.add(
            IndicatorObservation(
                observation_id="obs_old_wti_fred",
                dedupe_key="old-wti-fred",
                indicator_key="wti_crude",
                category="macro",
                country_code="US",
                timeframe="1d",
                observation_ts=datetime(2026, 6, 1, tzinfo=UTC),
                effective_start_ts=datetime(2026, 6, 1, tzinfo=UTC),
                value_num=Decimal("95.96"),
                signal_state="neutral",
                source_provider="fred",
                source_ref="fred:DCOILWTICO",
                source_granularity="1d",
                run_id="old",
            )
        )
        await session.commit()

        provider = service.macro_provider_registry.resolve(
            source_provider="gateio_rwa",
            source_kind="raw_series",
        )

        class FakeResult:
            observation_ts = datetime.now(UTC)
            value = Decimal("90.10")
            source_ref = "gateio_rwa:futures:CL_USDT"
            source_granularity = "intraday"
            metadata = {}

        async def fake_fetch_latest(symbol: str):
            assert symbol == "CL_USDT"
            return FakeResult()

        monkeypatch.setattr(provider, "fetch_latest", fake_fetch_latest)
        observations = await service._sync_macro_definition(
            wti_definition,
            type("Policy", (), {"mode": "raw"})(),
            "run-wti",
        )

    assert observations
    latest = observations[0]
    assert latest.value_num == Decimal("90.10")
    assert latest.source_provider == "gateio_rwa"
    assert latest.source_ref == "gateio_rwa:futures:CL_USDT"


@pytest.mark.asyncio
async def test_real_yield_5y_can_fallback_to_tradingeconomics_web(
    monitoring_db,
    monkeypatch,
) -> None:
    async with db_manager.session() as session:
        repo = MarketRepository(session)
        service = IndicatorMonitoringService(repo)
        await service.seed_defaults()
        definitions = await repo.list_indicator_definitions(enabled_only=True)
        definition = next(item for item in definitions if item.indicator_key == "real_yield_5y")
        session.add(
            IndicatorObservation(
                observation_id="obs_old_dfii5",
                dedupe_key="old-dfii5",
                indicator_key="real_yield_5y",
                category="macro",
                country_code="US",
                timeframe="1d",
                observation_ts=datetime(2026, 6, 1, tzinfo=UTC),
                effective_start_ts=datetime(2026, 6, 1, tzinfo=UTC),
                value_num=Decimal("1.55"),
                signal_state="stable",
                source_provider="fred",
                source_ref="fred:DFII5",
                source_granularity="1d",
                run_id="old",
            )
        )
        await session.commit()

        fred_provider = service.macro_provider_registry.resolve(
            source_provider="fred",
            source_kind="raw_series",
        )
        te_provider = service.macro_provider_registry.resolve(
            source_provider="tradingeconomics_web",
            source_kind="raw_series",
        )

        class FakeStaleFredResult:
            observation_ts = datetime(2026, 6, 1, tzinfo=UTC)
            value = Decimal("1.55")
            source_ref = "fred:DFII5"
            source_granularity = "1d"
            metadata = {}

        async def fake_fred_fetch_latest(symbol: str):
            assert symbol == "DFII5"
            return FakeStaleFredResult()

        class FakeTeResult:
            observation_ts = datetime(2026, 6, 8, tzinfo=UTC)
            value = Decimal("1.83")
            source_ref = "tradingeconomics_web:US 5Y TIPS"
            source_granularity = "1d"
            metadata = {"day_change_pct": "0.030"}

        async def fake_te_fetch_latest(symbol: str):
            assert symbol == "US 5Y TIPS"
            return FakeTeResult()

        monkeypatch.setattr(fred_provider, "fetch_latest", fake_fred_fetch_latest)
        monkeypatch.setattr(te_provider, "fetch_latest", fake_te_fetch_latest)

        observations = await service._sync_macro_definition(
            definition,
            type("Policy", (), {"mode": "raw"})(),
            "run-real-yield-5y",
        )

    assert observations
    latest = observations[0]
    assert latest.value_num == Decimal("1.83")
    assert latest.source_provider == "tradingeconomics_web"
    assert latest.source_ref == "tradingeconomics_web:US 5Y TIPS"


@pytest.mark.asyncio
async def test_sync_macro_creates_observations(monitoring_db, monkeypatch) -> None:
    async with db_manager.session() as session:
        service = IndicatorMonitoringService(MarketRepository(session))
        await service.seed_defaults()
        _stub_gateio_rwa_provider(service, monkeypatch)

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
async def test_nfp_calendar_release_fetches_series_and_updates_calendar(
    monitoring_db, monkeypatch
) -> None:
    async with db_manager.session() as session:
        repo = MarketRepository(session)
        service = IndicatorMonitoringService(repo)
        await service.seed_defaults()
        definition = await repo.get_indicator_definition("us_nfp")
        policies = await repo.list_monitoring_policies(enabled_only=True, category="macro")
        policy = next(item for item in policies if item.indicator_key == "us_nfp")

        bls_provider = service.macro_provider_registry.resolve(
            source_provider="bls",
            source_kind="raw_series",
        )
        fred_provider = service.macro_provider_registry.resolve(
            source_provider="fred",
            source_kind="raw_series",
        )

        async def failing_bls_history(*_args, **_kwargs):
            raise RuntimeError("BLS unavailable")

        class FakePoint:
            def __init__(self, observation_ts: datetime, value: Decimal) -> None:
                self.observation_ts = observation_ts
                self.value = value
                self.status = "ok"

        async def fake_fred_history(symbol: str, *, lookback_points: int = 4):
            assert symbol == "PAYEMS"
            assert lookback_points == 4
            return [
                FakePoint(datetime(2026, 4, 1, tzinfo=UTC), Decimal("159500")),
                FakePoint(datetime(2026, 5, 1, tzinfo=UTC), Decimal("159650")),
            ]

        monkeypatch.setattr(bls_provider, "fetch_history", failing_bls_history)
        monkeypatch.setattr(fred_provider, "fetch_history", fake_fred_history)

        observations = await service._sync_macro_definition(definition, policy, "run-nfp")
        nfp_events = await repo.list_macro_events(event_key="us_nfp", limit=20)
        event = next((item for item in nfp_events if item.source_ref == "fred:PAYEMS"), None)

    assert observations
    latest = observations[0]
    assert latest.indicator_key == "us_nfp"
    assert latest.value_num == Decimal("150")
    assert latest.source_provider == "fred"
    assert latest.value_json["transform"] == "mom_change"
    assert latest.value_json["policy_link"] == "NFP affects Fed rate-cut/hike expectations"
    assert event is not None
    assert event.actual_value_num == Decimal("150")
    assert event.source_ref == "fred:PAYEMS"
    assert event.payload_json["policy_sensitivity"] == "fed_rate_expectations"


@pytest.mark.asyncio
async def test_latest_by_key_returns_observation_models(monitoring_db, monkeypatch) -> None:
    async with db_manager.session() as session:
        service = IndicatorMonitoringService(MarketRepository(session))
        await service.seed_defaults()
        _stub_gateio_rwa_provider(service, monkeypatch)

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
async def test_default_onchain_is_degraded_not_demo(monitoring_db, monkeypatch) -> None:
    async with db_manager.session() as session:
        service = IndicatorMonitoringService(MarketRepository(session))
        await service.seed_defaults()

        async def fake_fetch_metric(indicator_key: str):
            return {
                "provider": "defillama",
                "status": "live",
                "value": 10,
                "indicators": {indicator_key: 10},
                "missing_fields": [],
            }

        monkeypatch.setattr(service.onchain_provider_router, "fetch_metric", fake_fetch_metric)
        await service.sync_onchain()
        alerts = await MarketRepository(session).list_alert_events(limit=50)
        observations = await MarketRepository(session).list_indicator_observations(
            category="onchain", limit=50
        )

    assert not any(item.rule_key == "onchain_btc_mvrv_overheated" for item in alerts)
    assert observations
    assert not any((item.value_json or {}).get("source") == "demo_onchain" for item in observations)
    assert any((item.value_json or {}).get("source") == "defillama" for item in observations)
    assert all(
        Decimal(item.quality_score) == Decimal("0")
        for item in observations
        if (item.value_json or {}).get("source") != "defillama"
    )


@pytest.mark.asyncio
async def test_sync_onchain_writes_defillama_observations(monitoring_db, monkeypatch) -> None:
    async with db_manager.session() as session:
        service = IndicatorMonitoringService(MarketRepository(session))
        await service.seed_defaults()

        async def fake_fetch_metric(indicator_key: str):
            return {
                "provider": "defillama",
                "status": "live",
                "value": 123.45,
                "indicators": {indicator_key: 123.45},
                "missing_fields": [],
            }

        monkeypatch.setattr(service.onchain_provider_router, "fetch_metric", fake_fetch_metric)
        await service.sync_onchain()
        observations = await MarketRepository(session).list_indicator_observations(
            indicator_key="defi_total_tvl", category="onchain", limit=5
        )

    assert observations
    latest = observations[0]
    assert latest.source_provider == "defillama"
    assert latest.value_num == Decimal("123.45")
    assert (latest.value_json or {}).get("source") == "defillama"


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


def test_macro_indicator_api_map_contains_fed_operations_indicators() -> None:
    """api_map must declare all 10 new fed_operations indicators."""
    import json
    from pathlib import Path

    api_map_path = Path("app/monitoring/configs/macro_indicator_api_map.v1.json")
    data = json.loads(api_map_path.read_text(encoding="utf-8"))
    required_keys = {
        "fed_iorb",
        "fed_on_rrp_rate",
        "fed_soma_treasury",
        "fed_soma_mbs",
        "fed_srf_usage",
        "fed_discount_window",
        "fed_soma_avg_duration",
        "fed_tga_net_change_4w",
        "fed_fima",
        "fed_qt_cap",
    }
    actual_keys = set(data["indicators"].keys())
    missing = required_keys - actual_keys
    assert not missing, f"missing fed_operations indicators: {missing}"
