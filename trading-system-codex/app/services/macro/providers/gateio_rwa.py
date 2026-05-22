from __future__ import annotations

import time
from datetime import datetime, timezone
from typing import Optional, TypedDict

import httpx

from app.core.decimal_utils import D
from app.services.macro.cache_store import CacheStore
from app.services.macro.providers.base import MacroFetchResult
from app.services.macro.secret_loader import SecretLoader

UTC = timezone.utc

class GateQuoteCandidate(TypedDict):
    market: str
    symbol: str
    settle: str


RWA_CANDIDATES: dict[str, list[GateQuoteCandidate]] = {
    "qqq": [{"market": "spot", "symbol": "QQQ_USDT", "settle": "usdt"}],
    "spy": [{"market": "spot", "symbol": "SPY_USDT", "settle": "usdt"}],
    # Gate.io UI displays CLUSDT/BZUSDT, but API v4 futures contracts use CL_USDT/BZ_USDT.
    "wti_oil": [{"market": "futures", "symbol": "CL_USDT", "settle": "usdt"}],
    "brent_oil": [{"market": "futures", "symbol": "BZ_USDT", "settle": "usdt"}],
    "gold": [{"market": "spot", "symbol": "XAUT_USDT", "settle": "usdt"}],
}

MIN_QUOTE_VOLUME_USDT = 5000
MAX_STALENESS_SECONDS = 300


class GateioRwaMacroProvider:
    provider_key = "gateio_rwa"

    def __init__(self, secrets: SecretLoader | None = None, cache: CacheStore | None = None):
        self.secrets = secrets or SecretLoader()
        self.cache = cache
        self.base_url = "https://api.gateio.ws/api/v4"

    def supports(self, source_provider: str, source_kind: str) -> bool:
        return source_provider == self.provider_key and source_kind in ("raw_series", "spot_ticker")

    @staticmethod
    def _cache_key(candidate: GateQuoteCandidate) -> str:
        return f"{candidate['market']}:{candidate['settle']}:{candidate['symbol']}"

    async def _fetch_ticker(self, candidate: GateQuoteCandidate):
        market = candidate["market"]
        symbol = candidate["symbol"]
        settle = candidate["settle"]
        if market == "futures":
            url = f"{self.base_url}/futures/{settle}/tickers"
            params = {"contract": symbol}
        else:
            url = f"{self.base_url}/spot/tickers"
            params = {"currency_pair": symbol}
        cache_key = self._cache_key(candidate)
        if self.cache:
            cached = self.cache.get("gateio_rwa", f"ticker:{cache_key}", params)
            if cached is not None:
                return cached, 0, True

        start = time.time()
        async with httpx.AsyncClient(timeout=10) as client:
            resp = await client.get(url, params=params)
        latency = int((time.time() - start) * 1000)
        resp.raise_for_status()
        data = resp.json()

        if self.cache:
            self.cache.set("gateio_rwa", f"ticker:{cache_key}", params, data, 300)

        return data, latency, False

    async def _discover_active_pair(self, indicator_id: str) -> Optional[GateQuoteCandidate]:
        candidates = RWA_CANDIDATES.get(indicator_id, [])
        for candidate in candidates:
            try:
                data, _, _ = await self._fetch_ticker(candidate)
                if not isinstance(data, list) or not data:
                    continue
                ticker = data[0]
                vol = float(ticker.get("quote_volume") or ticker.get("volume_24h_quote") or 0)
                if vol < MIN_QUOTE_VOLUME_USDT:
                    continue
                return candidate
            except Exception:
                continue
        return None

    async def fetch_latest(self, source_key: str) -> MacroFetchResult:
        candidate = await self._discover_active_pair(source_key)
        if candidate is None:
            raise ValueError(f"No active Gate.io RWA pair for {source_key}")
        data, _, _ = await self._fetch_ticker(candidate)
        if not isinstance(data, list) or not data:
            raise ValueError(f"Gate.io empty ticker for {candidate['symbol']}")
        ticker = data[0]
        price = ticker.get("mark_price") or ticker.get("last") or ticker.get("index_price") or 0
        return MacroFetchResult(
            observation_ts=datetime.now(UTC),
            value=D(str(price)),
            source_ref=f"gateio_rwa:{candidate['market']}:{candidate['symbol']}",
            source_granularity="intraday",
        )

    async def healthcheck(self) -> tuple[str, str | None]:
        try:
            pair = await self._discover_active_pair("gold")
            if pair:
                return "healthy", None
            return "unhealthy", "No liquid RWA pair found"
        except Exception as exc:
            return "unhealthy", str(exc)

    async def connectivity_check(self) -> dict:
        start = time.time()
        try:
            pair = await self._discover_active_pair("gold")
            return {
                "source": "gateio_rwa",
                "status": "ok" if pair else "unhealthy",
                "latency_ms": int((time.time() - start) * 1000),
                "auth": "not_required",
                "active_pair": pair,
                "error": None if pair else "No liquid RWA pair",
            }
        except Exception as exc:
            return {
                "source": "gateio_rwa",
                "status": "error",
                "latency_ms": int((time.time() - start) * 1000),
                "auth": "not_required",
                "error": str(exc)[:200],
            }
