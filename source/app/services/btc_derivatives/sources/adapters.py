from __future__ import annotations

import asyncio
from dataclasses import dataclass, field
from datetime import datetime, timezone
from typing import Any

from app.schemas.btc_derivatives_sources import (
    EndpointProbeResult,
    NormalizedOptionQuote,
    NormalizedPerpSnapshot,
)
from app.services.btc_derivatives.sources.cache import LiveSourceCache
from app.services.btc_derivatives.sources.http import SourceHttpClient
from app.services.btc_derivatives.sources.normalizer import (
    normalize_binance_perp,
    normalize_bybit_options,
    normalize_deribit_option,
    normalize_okx_options,
    normalize_simple_perp,
)
from app.services.btc_derivatives.sources.registry import (
    EndpointSpec,
    ProviderSpec,
)


def _list(payload: Any, *path: str) -> list[dict[str, Any]]:
    value = payload
    for key in path:
        if not isinstance(value, dict):
            return []
        value = value.get(key)
    return [item for item in value if isinstance(item, dict)] if isinstance(value, list) else []


@dataclass
class AdapterResult:
    provider: str
    options: list[NormalizedOptionQuote] = field(default_factory=list)
    perps: list[NormalizedPerpSnapshot] = field(default_factory=list)
    history: list[dict[str, Any]] = field(default_factory=list)
    errors: list[str] = field(default_factory=list)
    endpoint_success: int = 0
    endpoint_total: int = 0
    latency_ms: float | None = None


class PublicProviderAdapter:
    def __init__(
        self,
        spec: ProviderSpec,
        http: SourceHttpClient,
        cache: LiveSourceCache,
    ) -> None:
        self.spec = spec
        self.http = http
        self.cache = cache

    async def _fetch(
        self,
        endpoint: EndpointSpec,
        *,
        force: bool,
    ) -> tuple[Any | None, float | None, str | None]:
        if not force:
            cached = self.cache.read_raw(
                self.spec.key, endpoint.name, endpoint.ttl_seconds
            )
            if cached is not None:
                return cached, 0, None
        try:
            payload, latency, _ = await self.http.request(
                self.spec, endpoint, force=force
            )
            self.cache.write_raw(self.spec.key, endpoint.name, payload)
            return payload, latency, None
        except Exception as exc:
            return None, None, str(exc)

    async def collect(self, *, force: bool = False) -> AdapterResult:
        result = AdapterResult(provider=self.spec.key, endpoint_total=len(self.spec.endpoints))
        fetched = await asyncio.gather(
            *(self._fetch(endpoint, force=force) for endpoint in self.spec.endpoints)
        )
        payloads: dict[str, Any] = {}
        latencies: list[float] = []
        for endpoint, (payload, latency, error) in zip(
            self.spec.endpoints, fetched, strict=True
        ):
            if error:
                result.errors.append(f"{endpoint.name}: {error}")
                continue
            payloads[endpoint.name] = payload
            result.endpoint_success += 1
            if latency:
                latencies.append(latency)
        result.latency_ms = max(latencies) if latencies else 0
        self._normalize(payloads, result)
        if result.endpoint_success:
            self.http.record_success(self.spec.key, result.latency_ms)
        else:
            self.http.record_failure(
                self.spec.key, "; ".join(result.errors) or "all endpoints failed"
            )
        return result

    async def probe(self) -> list[EndpointProbeResult]:
        checked_at = datetime.now(timezone.utc)
        output: list[EndpointProbeResult] = []
        for endpoint in self.spec.endpoints:
            _, latency, error = await self._fetch(endpoint, force=True)
            output.append(
                EndpointProbeResult(
                    provider=self.spec.key,
                    endpoint=endpoint.name,
                    capability=endpoint.capability,
                    ok=error is None,
                    latency_ms=latency,
                    checked_at=checked_at,
                    error=error,
                )
            )
        if any(item.ok for item in output):
            self.http.record_success(
                self.spec.key,
                max((item.latency_ms or 0) for item in output),
            )
        else:
            self.http.record_failure(
                self.spec.key,
                "; ".join(item.error or "failed" for item in output),
            )
        return output

    def _normalize(self, payloads: dict[str, Any], result: AdapterResult) -> None:
        key = self.spec.key
        if key == "deribit":
            for item in _list(payloads.get("option_book"), "result"):
                try:
                    result.options.append(normalize_deribit_option(item))
                except (ValueError, TypeError):
                    continue
            for item in _list(payloads.get("future_book"), "result"):
                instrument = str(item.get("instrument_name") or "")
                result.perps.append(
                    normalize_simple_perp(
                        key,
                        instrument,
                        mark_price=item.get("mark_price"),
                        open_interest_contracts=item.get("open_interest"),
                        volume_24h_usd=item.get("volume_usd"),
                        timestamp=item.get("timestamp"),
                    )
                )
        elif key == "okx":
            result.options = normalize_okx_options(
                _list(payloads.get("option_instruments"), "data"),
                _list(payloads.get("option_tickers"), "data"),
                _list(payloads.get("option_summary"), "data"),
            )
            oi_map = {
                str(item.get("instId")): item
                for item in _list(payloads.get("open_interest"), "data")
            }
            for item in _list(payloads.get("swap_tickers"), "data"):
                instrument = str(item.get("instId") or "")
                if not instrument.startswith("BTC-") or not instrument.endswith("-SWAP"):
                    continue
                oi = oi_map.get(instrument, {})
                result.perps.append(
                    normalize_simple_perp(
                        key,
                        instrument,
                        mark_price=item.get("last"),
                        open_interest_contracts=oi.get("oi"),
                        open_interest_usd=oi.get("oiUsd"),
                        volume_24h_usd=item.get("volCcy24h"),
                        timestamp=item.get("ts"),
                    )
                )
        elif key == "bybit":
            result.options = normalize_bybit_options(
                _list(payloads.get("option_instruments"), "result", "list"),
                _list(payloads.get("option_tickers"), "result", "list"),
            )
            for item in _list(payloads.get("linear_tickers"), "result", "list"):
                result.perps.append(
                    normalize_simple_perp(
                        key,
                        str(item.get("symbol") or "BTCUSDT"),
                        mark_price=item.get("markPrice"),
                        index_price=item.get("indexPrice"),
                        funding_rate=item.get("fundingRate"),
                        open_interest_contracts=item.get("openInterest"),
                        open_interest_usd=item.get("openInterestValue"),
                        volume_24h_usd=item.get("turnover24h"),
                        timestamp=item.get("timestamp"),
                    )
                )
        elif key == "binance_futures":
            premium = payloads.get("premium_index") or {}
            result.perps = [
                normalize_binance_perp(
                    premium,
                    open_interest=payloads.get("open_interest") or {},
                    ticker=payloads.get("ticker_24h") or {},
                )
            ]
            marks = payloads.get("mark_history") or []
            oi_rows = payloads.get("oi_history") or []
            funding_rows = payloads.get("funding_history") or []
            oi_by_day = {
                datetime.fromtimestamp(float(row.get("timestamp", 0)) / 1000, tz=timezone.utc)
                .date()
                .isoformat(): row
                for row in oi_rows
                if isinstance(row, dict)
            }
            funding_by_day: dict[str, list[float]] = {}
            for row in funding_rows:
                if not isinstance(row, dict) or row.get("fundingRate") in (None, ""):
                    continue
                day = datetime.fromtimestamp(
                    float(row.get("fundingTime", 0)) / 1000,
                    tz=timezone.utc,
                ).date().isoformat()
                funding_by_day.setdefault(day, []).append(float(row["fundingRate"]))
            all_funding = [
                value
                for values in funding_by_day.values()
                for value in values
            ]
            funding_mean = (
                sum(all_funding) / len(all_funding) if all_funding else None
            )
            funding_variance = (
                sum((value - funding_mean) ** 2 for value in all_funding)
                / len(all_funding)
                if all_funding and funding_mean is not None
                else None
            )
            funding_stdev = funding_variance**0.5 if funding_variance else None
            for row in marks:
                if not isinstance(row, list) or len(row) < 5:
                    continue
                day = (
                    datetime.fromtimestamp(
                        float(row[0]) / 1000,
                        tz=timezone.utc,
                    )
                    .date()
                    .isoformat()
                )
                oi_row = oi_by_day.get(day, {})
                daily_funding = funding_by_day.get(day, [])
                funding = (
                    sum(daily_funding) / len(daily_funding)
                    if daily_funding
                    else None
                )
                result.history.append(
                    {
                        "timestamp": day,
                        "spot_price": float(row[4]),
                        "aggregate_oi_usd": (
                            float(oi_row["sumOpenInterestValue"])
                            if oi_row.get("sumOpenInterestValue") not in (None, "")
                            else None
                        ),
                        "funding_rate": funding,
                        "funding_zscore": (
                            (funding - funding_mean) / funding_stdev
                            if funding is not None
                            and funding_mean is not None
                            and funding_stdev
                            else None
                        ),
                        "provider": key,
                    }
                )
        elif key == "bitget":
            ticker = (_list(payloads.get("ticker"), "data") or [{}])[0]
            funding = (_list(payloads.get("funding"), "data") or [{}])[0]
            oi = (_list(payloads.get("open_interest"), "data") or [{}])[0]
            result.perps = [
                normalize_simple_perp(
                    key,
                    str(ticker.get("symbol") or "BTCUSDT"),
                    mark_price=ticker.get("lastPr"),
                    funding_rate=funding.get("fundingRate"),
                    open_interest_contracts=oi.get("openInterestList", [{}])[0].get("size")
                    if isinstance(oi.get("openInterestList"), list)
                    else oi.get("size"),
                    volume_24h_usd=ticker.get("usdtVolume"),
                    timestamp=ticker.get("ts"),
                )
            ]
        elif key == "hyperliquid":
            payload = payloads.get("meta_and_contexts") or []
            if isinstance(payload, list) and len(payload) == 2:
                universe = payload[0].get("universe", [])
                contexts = payload[1]
                for meta, context in zip(universe, contexts, strict=False):
                    if meta.get("name") != "BTC":
                        continue
                    result.perps = [
                        normalize_simple_perp(
                            key,
                            "BTC-PERP",
                            mark_price=context.get("markPx"),
                            funding_rate=context.get("funding"),
                            open_interest_contracts=context.get("openInterest"),
                            volume_24h_usd=context.get("dayNtlVlm"),
                        )
                    ]
