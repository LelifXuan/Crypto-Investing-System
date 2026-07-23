#!/usr/bin/env python
"""Macro API healthcheck CLI.

The output intentionally never includes API keys, key fragments, signed URLs,
or proxy credentials.
"""

from __future__ import annotations

import asyncio
import json
import sys
from datetime import datetime, timezone
from pathlib import Path
from time import perf_counter

sys.path.insert(0, str(Path(__file__).resolve().parents[3]))

try:
    from dotenv import load_dotenv

    load_dotenv()
except Exception:
    pass

from app.services.macro.cache_store import CacheStore
from app.services.macro.providers.agushuju import AgushujuMacroProvider
from app.services.macro.providers.alpha_vantage import AlphaVantageMacroProvider
from app.services.macro.providers.bea import BeaMacroProvider
from app.services.macro.providers.bls import BlsMacroProvider
from app.services.macro.providers.coinmarketcap import CoinMarketCapMacroProvider
from app.services.macro.providers.fred import FredMacroProvider
from app.services.macro.providers.openexchangerates import OpenExchangeRatesMacroProvider
from app.services.macro.providers.tiingo import TiingoMacroProvider
from app.services.macro.providers.treasury import TreasuryMacroProvider
from app.services.macro.providers.tushare import TushareMacroProvider
from app.services.macro.providers.twelvedata import TwelveDataMacroProvider
from app.services.macro.providers.zhituapi import ZhituapiMacroProvider
from app.services.macro.secret_loader import SecretLoader, redact
from app.services.network.http_client_factory import current_network_status, init_network


async def _check_provider(provider, name: str, secrets: SecretLoader, auth_envs: list[str]) -> dict:
    started = perf_counter()
    auth_present = secrets.auth_state(auth_envs) == "present" if auth_envs else True
    try:
        status, error = await provider.healthcheck()
        return {
            "source": name,
            "status": status,
            "latency_ms": int((perf_counter() - started) * 1000),
            "auth_present": auth_present,
            "error_type": type(error).__name__ if error else None,
        }
    except Exception as exc:
        return {
            "source": name,
            "status": "source_error",
            "latency_ms": int((perf_counter() - started) * 1000),
            "auth_present": auth_present,
            "error_type": type(exc).__name__,
        }


async def main() -> None:
    args = set(sys.argv[1:])
    filter_source = None
    for arg in args:
        if arg.startswith("--source="):
            filter_source = arg.split("=", 1)[1]

    checked_at = datetime.now(timezone.utc).isoformat()
    secrets = SecretLoader()
    cache = CacheStore()
    proxy_result = init_network()
    providers = [
        (FredMacroProvider(secrets), "fred", ["FRED_API_KEY"]),
        (BlsMacroProvider(secrets, cache), "bls", ["BLS_API_KEY"]),
        (BeaMacroProvider(secrets, cache), "bea", ["BEA_API_KEY"]),
        (TreasuryMacroProvider(secrets, cache), "treasury", []),
        (CoinMarketCapMacroProvider(secrets, cache), "coinmarketcap", ["COINMARKETCAP_API_KEY"]),
        (TiingoMacroProvider(secrets, cache), "tiingo", ["TIINGO_API_KEY"]),
        (TwelveDataMacroProvider(secrets, cache), "twelvedata", ["TWELVEDATA_API_KEY"]),
        (AlphaVantageMacroProvider(secrets, cache), "alpha_vantage", ["ALPHA_VANTAGE_API_KEY"]),
        (
            OpenExchangeRatesMacroProvider(secrets, cache),
            "openexchangerates",
            ["OPENEXCHANGERATES_APP_ID"],
        ),
        (TushareMacroProvider(secrets, cache), "tushare", ["TUSHARE_TOKEN"]),
        (AgushujuMacroProvider(secrets, cache), "agushuju", ["AGUSHUJU_API_KEY"]),
        (ZhituapiMacroProvider(secrets, cache), "zhituapi", ["ZHITUAPI_TOKEN"]),
    ]

    results = []
    for provider, name, auth_envs in providers:
        if filter_source and name != filter_source:
            continue
        results.append(await _check_provider(provider, name, secrets, auth_envs))

    output = {
        "checked_at": checked_at,
        "proxy_detected": proxy_result.proxy_detected,
        "proxy_source": proxy_result.selected_source,
        "proxy": current_network_status(),
        "sources": redact(results),
    }
    print(json.dumps(output, ensure_ascii=False, indent=2))

    failures = [item for item in results if item.get("status") not in {"ok", "healthy"}]
    if failures:
        print(f"\n通信失败或未配置 ({len(failures)} 个源):")
        for item in failures:
            error_type = item.get("error_type") or "无错误类型"
            print(f"  {item['source']}: {item.get('status')} - {error_type}")
    else:
        print("\n所有信源通信正常。")


if __name__ == "__main__":
    asyncio.run(main())
