#!/usr/bin/env python
"""Macro API healthcheck CLI. Tests connectivity to all configured sources.

Usage:
    python -m app.services.macro.healthcheck
    python -m app.services.macro.healthcheck --source bls
    python -m app.services.macro.healthcheck --source fred

Never outputs API keys or secret values.
"""

from __future__ import annotations

import asyncio
import json
import sys
from datetime import datetime, timezone
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[3]))

try:
    from dotenv import load_dotenv
    load_dotenv()
except Exception:
    pass

from app.services.macro.secret_loader import SecretLoader, redact
from app.services.macro.cache_store import CacheStore
from app.services.macro.providers.fred import FredMacroProvider
from app.services.macro.providers.bls import BlsMacroProvider
from app.services.macro.providers.bea import BeaMacroProvider
from app.services.macro.providers.treasury import TreasuryMacroProvider
from app.services.macro.providers.coinmarketcap import CoinMarketCapMacroProvider
from app.services.macro.providers.tiingo import TiingoMacroProvider
from app.services.macro.providers.twelvedata import TwelveDataMacroProvider
from app.services.macro.providers.alpha_vantage import AlphaVantageMacroProvider
from app.services.macro.providers.openexchangerates import OpenExchangeRatesMacroProvider
from app.services.macro.providers.tushare import TushareMacroProvider
from app.services.macro.providers.agushuju import AgushujuMacroProvider
from app.services.macro.providers.zhituapi import ZhituapiMacroProvider


async def _check_provider(provider, name: str, secrets: SecretLoader, auth_envs: list[str]) -> dict:
    try:
        status, error = await provider.healthcheck()
        return {"source": name, "status": status, "auth": secrets.auth_state(auth_envs), "error": str(error) if error else None}
    except Exception as exc:
        return {"source": name, "status": "error", "auth": secrets.auth_state(auth_envs), "error": str(exc)[:200]}


async def main():
    args = set(sys.argv[1:])
    filter_source = None
    for arg in args:
        if arg.startswith("--source="):
            filter_source = arg.split("=", 1)[1]

    checked_at = datetime.now(timezone.utc).isoformat()
    secrets = SecretLoader()
    cache = CacheStore()

    providers = [
        (FredMacroProvider(), "fred", ["FRED_API_KEY"]),
        (BlsMacroProvider(secrets, cache), "bls", ["BLS_API_KEY"]),
        (BeaMacroProvider(secrets, cache), "bea", ["BEA_API_KEY"]),
        (TreasuryMacroProvider(secrets, cache), "treasury_fiscaldata", []),
        (CoinMarketCapMacroProvider(secrets, cache), "coinmarketcap", ["COINMARKETCAP_API_KEY"]),
        (TiingoMacroProvider(secrets, cache), "tiingo", ["TIINGO_API_KEY"]),
        (TwelveDataMacroProvider(secrets, cache), "twelvedata", ["TWELVEDATA_API_KEY"]),
        (AlphaVantageMacroProvider(secrets, cache), "alpha_vantage", ["ALPHA_VANTAGE_API_KEY"]),
        (OpenExchangeRatesMacroProvider(secrets, cache), "openexchangerates", ["OPENEXCHANGERATES_APP_ID"]),
        (TushareMacroProvider(secrets, cache), "tushare", ["TUSHARE_TOKEN"]),
        (AgushujuMacroProvider(secrets, cache), "agushuju", ["AGUSHUJU_API_KEY"]),
        (ZhituapiMacroProvider(secrets, cache), "zhituapi", ["ZHITUAPI_TOKEN"]),
    ]

    results = []
    for provider, name, auth_envs in providers:
        if filter_source and name != filter_source:
            continue
        result = await _check_provider(provider, name, secrets, auth_envs)
        results.append(result)

    output = {"checked_at": checked_at, "sources": redact(results)}
    print(json.dumps(output, ensure_ascii=False, indent=2))

    failures = [r for r in results if r.get("status") not in ("ok", "healthy")]
    pending = [r for r in failures if r.get("status") == "unknown"]
    real_failures = [r for r in failures if r.get("status") not in ("unknown",)]
    if real_failures:
        print(f"\n通信失败 ({len(real_failures)} 个源):")
        for f in real_failures:
            print(f"  {f['source']}: {f.get('status')} - {str(f.get('error') or '未知错误')[:120]}")
    if pending:
        print(f"\n待核验 ({len(pending)} 个源，密钥已就绪，需后续实现SDK集成):")
        for f in pending:
            print(f"  {f['source']}: 密钥 {f.get('auth')}")
    if not failures:
        print("\n所有源通信正常。")


if __name__ == "__main__":
    asyncio.run(main())
