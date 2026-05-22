from __future__ import annotations

from pathlib import Path
from typing import Any, Dict, Optional

from app.services.macro.cache_store import CacheStore
from app.services.macro.providers.bea import BeaMacroProvider
from app.services.macro.providers.bls import BlsMacroProvider
from app.services.macro.providers.fred import FredMacroProvider
from app.services.macro.providers.treasury import TreasuryMacroProvider
from app.services.macro.secret_loader import SecretLoader

DEFAULT_CONFIG_PATH = (
    Path(__file__).resolve().parents[3]
    / "app"
    / "monitoring"
    / "configs"
    / "macro_data_sources.v2.json"
)
LEGACY_CONFIG_PATH = (
    Path(__file__).resolve().parents[3]
    / "app"
    / "monitoring"
    / "configs"
    / "macro_data_sources.v1.json"
)


class SourceRegistry:
    def __init__(
        self,
        config_path: str | Path | None = None,
        cache_path: str = "data/cache/macro_api/cache.sqlite",
    ):
        self.config_path = Path(config_path) if config_path else DEFAULT_CONFIG_PATH
        self.secrets = SecretLoader()
        self.cache = CacheStore(cache_path)
        self.config = self._load_config()
        self.adapters: Dict[str, Any] = {}
        self._init_adapters()

    def _load_config(self) -> dict:
        import json

        path = self.config_path if self.config_path.exists() else LEGACY_CONFIG_PATH
        if path.exists():
            return json.loads(path.read_text(encoding="utf-8"))
        return {}

    def _init_adapters(self) -> None:
        sources = self.config.get("sources", {})
        if "fred" in sources:
            self.adapters["fred"] = FredMacroProvider(self.secrets)
        if "bls" in sources:
            self.adapters["bls"] = BlsMacroProvider(self.secrets, self.cache)
        if "bea" in sources:
            self.adapters["bea"] = BeaMacroProvider(self.secrets, self.cache)
        if "treasury" in sources:
            self.adapters["treasury"] = TreasuryMacroProvider(self.secrets, self.cache)
        if "treasury_fiscaldata" in sources:
            self.adapters["treasury_fiscaldata"] = TreasuryMacroProvider(self.secrets, self.cache)
        if "coinmarketcap" in sources:
            from app.services.macro.providers.coinmarketcap import CoinMarketCapMacroProvider

            self.adapters["coinmarketcap"] = CoinMarketCapMacroProvider(self.secrets, self.cache)
        if "tiingo" in sources:
            from app.services.macro.providers.tiingo import TiingoMacroProvider

            self.adapters["tiingo"] = TiingoMacroProvider(self.secrets, self.cache)
        if "twelvedata" in sources:
            from app.services.macro.providers.twelvedata import TwelveDataMacroProvider

            self.adapters["twelvedata"] = TwelveDataMacroProvider(self.secrets, self.cache)
        if "alpha_vantage" in sources or "alphavantage" in sources:
            from app.services.macro.providers.alpha_vantage import AlphaVantageMacroProvider

            self.adapters["alpha_vantage"] = AlphaVantageMacroProvider(self.secrets, self.cache)
            self.adapters["alphavantage"] = self.adapters["alpha_vantage"]
        if "openexchangerates" in sources:
            from app.services.macro.providers.openexchangerates import (
                OpenExchangeRatesMacroProvider,
            )

            self.adapters["openexchangerates"] = OpenExchangeRatesMacroProvider(
                self.secrets, self.cache
            )
        if "tushare" in sources:
            from app.services.macro.providers.tushare import TushareMacroProvider

            self.adapters["tushare"] = TushareMacroProvider(self.secrets, self.cache)

    def get_modules(self) -> list[dict]:
        return self.config.get("modules", [])

    def find_indicator(self, indicator_id: str) -> Optional[dict]:
        for module in self.get_modules():
            for ind in module.get("indicators", []):
                aliases = ind.get("alias_old") or []
                if isinstance(aliases, str):
                    aliases = [aliases]
                if ind.get("id") == indicator_id or indicator_id in aliases:
                    out = dict(ind)
                    out["module_id"] = module.get("id")
                    out["module_name_zh"] = module.get("name_zh", "")
                    out["module_weight"] = module.get("weight", 0)
                    return out
        return None

    def list_indicators(self) -> list[dict]:
        result = []
        for module in self.get_modules():
            for ind in module.get("indicators", []):
                out = dict(ind)
                out["module_id"] = module.get("id")
                out["module_name_zh"] = module.get("name_zh", "")
                out["module_weight"] = module.get("weight", 0)
                result.append(out)
        return result
