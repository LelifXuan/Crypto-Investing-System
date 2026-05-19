from __future__ import annotations

from app.services.macro.providers.agushuju import AgushujuMacroProvider
from app.services.macro.providers.alpha_vantage import AlphaVantageMacroProvider
from app.services.macro.providers.bls import BlsMacroProvider
from app.services.macro.providers.bea import BeaMacroProvider
from app.services.macro.providers.china import ChinaMacroProvider
from app.services.macro.providers.coinmarketcap import CoinMarketCapMacroProvider
from app.services.macro.providers.fed import FedMacroProvider
from app.services.macro.providers.fred import FredMacroProvider
from app.services.macro.providers.ism import IsmMacroProvider
from app.services.macro.providers.openexchangerates import OpenExchangeRatesMacroProvider
from app.services.macro.providers.tiingo import TiingoMacroProvider
from app.services.macro.providers.treasury import TreasuryMacroProvider
from app.services.macro.providers.tushare import TushareMacroProvider
from app.services.macro.providers.twelvedata import TwelveDataMacroProvider
from app.services.macro.providers.zhituapi import ZhituapiMacroProvider


class MacroProviderRegistry:
    def __init__(self, secrets=None, cache=None) -> None:
        self._providers = [
            FredMacroProvider(),
            BlsMacroProvider(secrets, cache),
            BeaMacroProvider(secrets, cache),
            TreasuryMacroProvider(secrets, cache),
            IsmMacroProvider(),
            FedMacroProvider(),
            ChinaMacroProvider(),
            CoinMarketCapMacroProvider(secrets, cache),
            TiingoMacroProvider(secrets, cache),
            TwelveDataMacroProvider(secrets, cache),
            AlphaVantageMacroProvider(secrets, cache),
            OpenExchangeRatesMacroProvider(secrets, cache),
            TushareMacroProvider(secrets, cache),
            AgushujuMacroProvider(secrets, cache),
            ZhituapiMacroProvider(secrets, cache),
        ]

    def resolve(self, *, source_provider: str, source_kind: str):
        for provider in self._providers:
            if provider.supports(source_provider, source_kind):
                return provider
        return None

    def providers(self) -> list:
        return list(self._providers)
