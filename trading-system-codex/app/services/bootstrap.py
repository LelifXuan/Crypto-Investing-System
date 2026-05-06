from __future__ import annotations

import logging
from dataclasses import dataclass

from app.core.config import settings
from app.db.models.account import Account
from app.db.models.core_entities import Strategy, Tenant
from app.db.models.instrument import Instrument
from app.db.models.market import IndicatorRefreshPolicy
from app.repositories.auth_repository import AuthRepository
from app.repositories.bootstrap_repository import BootstrapRepository
from app.repositories.market_repository import MarketRepository
from app.services.alerts_bundle import AlertsBundleService
from app.services.analysis_bundle import AnalysisBundleService
from app.services.auth import AuthService
from app.services.indicator_monitoring import IndicatorMonitoringService
from app.services.indicators import SUPPORTED_INDICATOR_TIMEFRAMES, IndicatorService
from app.services.market import MarketService
from app.services.monitoring_dashboard import MonitoringDashboardService
from app.services.structure import StructureSnapshotService

logger = logging.getLogger(__name__)

DEFAULT_GATEIO_INSTRUMENTS: tuple[tuple[str, str, str], ...] = (
    ("btc-usdt-perp", "BTC_USDT", "BTC"),
    ("eth-usdt-perp", "ETH_USDT", "ETH"),
    ("hype-usdt-perp", "HYPE_USDT", "HYPE"),
    ("bnb-usdt-perp", "BNB_USDT", "BNB"),
    ("okb-usdt-perp", "OKB_USDT", "OKB"),
)


@dataclass(slots=True)
class BootstrapSeedResult:
    tenant_id: str
    account_id: str
    strategy_id: str
    instrument_id: str
    admin_username: str


class LocalBootstrapService:
    def __init__(
        self,
        bootstrap_repository: BootstrapRepository,
        market_repository: MarketRepository,
        auth_service: AuthService,
    ) -> None:
        self.bootstrap_repository = bootstrap_repository
        self.market_repository = market_repository
        self.auth_service = auth_service

    async def seed_defaults(self) -> BootstrapSeedResult:
        repo = self.bootstrap_repository
        tenant = await repo.add_tenant(Tenant(tenant_id="demo_tenant", name="Demo Tenant"))
        account = await repo.add_account(
            Account(
                account_id="demo_account",
                tenant_id=tenant.tenant_id,
                venue="GATEIO",
                base_currency="USD",
            )
        )
        strategy = await repo.add_strategy(
            Strategy(
                strategy_id="demo_strategy",
                tenant_id=tenant.tenant_id,
                name="Trend Follow",
                tags=["demo"],
            )
        )
        seeded_instruments: list[Instrument] = []
        for instrument_id, symbol, base_ccy in DEFAULT_GATEIO_INSTRUMENTS:
            seeded_instruments.append(
                await repo.add_instrument(
                    Instrument(
                        instrument_id=instrument_id,
                        venue="GATEIO",
                        symbol=symbol,
                        asset_class="PERP",
                        base_ccy=base_ccy,
                        quote_ccy="USDT",
                        settle_ccy="USDT",
                        tick_size="0.1",
                        lot_size="0.001",
                        contract_multiplier="1",
                        margin_model="ISOLATED",
                        metadata_json={
                            "seeded": True,
                            "gateio": {
                                "product_type": "futures",
                                "contract": symbol,
                                "settle": "usdt",
                            },
                        },
                    )
                )
            )
        default_instrument = seeded_instruments[0]
        user = await self.auth_service.register_bootstrap_admin(
            tenant_id=tenant.tenant_id,
            username=settings.bootstrap_admin_username,
            password=settings.bootstrap_admin_password,
        )
        await self._seed_indicator_refresh_policies(seeded_instruments)
        await IndicatorMonitoringService(self.market_repository).seed_defaults(
            default_instrument_id=default_instrument.instrument_id
        )
        return BootstrapSeedResult(
            tenant_id=tenant.tenant_id,
            account_id=account.account_id,
            strategy_id=strategy.strategy_id,
            instrument_id=default_instrument.instrument_id,
            admin_username=user.username,
        )

    async def _seed_indicator_refresh_policies(self, instruments: list[Instrument]) -> None:
        default_params = IndicatorService.default_parameters()
        default_params["bbands_stddev"] = str(default_params["bbands_stddev"])
        for instrument in instruments:
            for timeframe in SUPPORTED_INDICATOR_TIMEFRAMES:
                await self.market_repository.upsert_indicator_refresh_policy(
                    IndicatorRefreshPolicy(
                        instrument_id=instrument.instrument_id,
                        timeframe=timeframe,
                        price_kind="last",
                        source_preference="gateio",
                        is_enabled=True,
                        persist_candles=True,
                        fetch_limit=300,
                        parameters_json=default_params,
                    )
                )


async def seed_local_defaults(
    bootstrap_repository: BootstrapRepository,
    market_repository: MarketRepository,
    auth_repository: AuthRepository,
) -> BootstrapSeedResult:
    return await LocalBootstrapService(
        bootstrap_repository,
        market_repository,
        AuthService(auth_repository),
    ).seed_defaults()


async def warm_local_market_data(market_repository: MarketRepository, instrument_id: str) -> None:
    if not settings.local_bootstrap_warmup_enabled:
        return
    market_service = MarketService(market_repository)
    monitoring_service = IndicatorMonitoringService(market_repository)
    structure_service = StructureSnapshotService(market_repository)

    try:
        await market_service.fetch_and_persist_live_mark(instrument_id)
    except Exception as exc:  # pragma: no cover - depends on external provider
        logger.warning("startup warmup: live mark fetch failed for %s: %s", instrument_id, exc)

    for timeframe in settings.local_bootstrap_warmup_timeframes:
        try:
            await market_service.sync_candles_from_provider(
                instrument_id=instrument_id,
                timeframe=timeframe,
                limit=settings.local_bootstrap_candle_limit,
                persist=True,
            )
        except Exception as exc:  # pragma: no cover - depends on external provider
            logger.warning(
                "startup warmup: candle sync failed for %s %s: %s",
                instrument_id,
                timeframe,
                exc,
            )

    try:
        await monitoring_service.sync_technical(instrument_id)
    except Exception as exc:  # pragma: no cover - depends on external provider
        logger.warning("startup warmup: technical sync failed for %s: %s", instrument_id, exc)

    for timeframe in settings.local_bootstrap_structure_timeframes:
        try:
            await structure_service.refresh_snapshot(
                instrument_id,
                timeframe,
                include_geometry=True,
                include_diagnostics=True,
            )
        except Exception as exc:  # pragma: no cover - depends on external provider
            logger.warning(
                "startup warmup: structure refresh failed for %s %s: %s",
                instrument_id,
                timeframe,
                exc,
            )
    try:
        await AnalysisBundleService(market_repository).refresh_bundle(
            instrument_id, "1d", "default"
        )
    except Exception as exc:  # pragma: no cover - depends on external provider
        logger.warning("startup warmup: analysis bundle failed for %s: %s", instrument_id, exc)
    try:
        await AlertsBundleService(market_repository).refresh_bundle(instrument_id, "1d")
    except Exception as exc:  # pragma: no cover - depends on external provider
        logger.warning("startup warmup: alerts bundle failed for %s: %s", instrument_id, exc)
    try:
        await MonitoringDashboardService(market_repository).refresh_bundle(instrument_id, "1d")
    except Exception as exc:  # pragma: no cover - depends on external provider
        logger.warning("startup warmup: monitoring bundle failed for %s: %s", instrument_id, exc)
