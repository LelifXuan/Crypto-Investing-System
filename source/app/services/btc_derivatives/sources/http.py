from __future__ import annotations

import asyncio
from dataclasses import dataclass, field
from datetime import datetime, timedelta, timezone
from decimal import Decimal
from time import perf_counter
from typing import Any

import httpx

from app.services.btc_derivatives.sources.registry import EndpointSpec, ProviderSpec
from app.services.network.http_client_factory import client_for_source


def utc_now() -> datetime:
    return datetime.now(timezone.utc)


@dataclass
class CircuitState:
    consecutive_failures: int = 0
    open_until: datetime | None = None
    last_attempt_at: datetime | None = None
    last_success_at: datetime | None = None
    last_error: str | None = None
    latency_ms: float | None = None

    def is_open(self) -> bool:
        return self.open_until is not None and self.open_until > utc_now()


@dataclass
class SourceHttpClient:
    timeout_seconds: float = 8
    provider_concurrency: int = 2
    failure_threshold: int = 3
    circuit_seconds: int = 300
    states: dict[str, CircuitState] = field(default_factory=dict)
    _semaphores: dict[str, asyncio.Semaphore] = field(default_factory=dict)

    def state(self, provider: str) -> CircuitState:
        return self.states.setdefault(provider, CircuitState())

    def _semaphore(self, provider: str) -> asyncio.Semaphore:
        return self._semaphores.setdefault(
            provider, asyncio.Semaphore(self.provider_concurrency)
        )

    async def request(
        self,
        provider: ProviderSpec,
        endpoint: EndpointSpec,
        *,
        force: bool = False,
        decimal_json: bool = False,
    ) -> tuple[Any, float, int]:
        state = self.state(provider.key)
        if state.is_open() and not force:
            raise RuntimeError(f"{provider.key} circuit open")
        started = perf_counter()
        last_error: Exception | None = None
        async with self._semaphore(provider.key):
            async with client_for_source(
                provider.key,
                timeout=httpx.Timeout(self.timeout_seconds),
                headers={"User-Agent": "Crypto-Investing-System/1.0"},
            ) as client:
                for attempt in range(4):
                    try:
                        response = await client.request(
                            endpoint.method,
                            f"{provider.base_url}{endpoint.path}",
                            params=endpoint.params,
                            json=endpoint.json_body,
                        )
                        if response.status_code == 429 or response.status_code >= 500:
                            raise httpx.HTTPStatusError(
                                f"retryable status {response.status_code}",
                                request=response.request,
                                response=response,
                            )
                        response.raise_for_status()
                        latency = (perf_counter() - started) * 1000
                        payload = (
                            response.json(parse_float=Decimal)
                            if decimal_json
                            else response.json()
                        )
                        return payload, latency, response.status_code
                    except (httpx.HTTPError, ValueError) as exc:
                        last_error = exc
                        status_code = (
                            exc.response.status_code
                            if isinstance(exc, httpx.HTTPStatusError)
                            and exc.response is not None
                            else None
                        )
                        # Authentication, permission and geo-policy responses
                        # are deterministic for the current route. Retrying the
                        # same request only adds 8 seconds of latency per source
                        # and cannot recover. Keep 408/429 and 5xx retryable.
                        if (
                            status_code is not None
                            and 400 <= status_code < 500
                            and status_code not in {408, 429}
                        ):
                            raise RuntimeError(
                                f"permanent HTTP {status_code}: {exc}"
                            ) from exc
                        if attempt == 3:
                            break
                        await asyncio.sleep((1, 2, 5)[attempt])
        raise RuntimeError(str(last_error or "request failed"))

    def record_success(self, provider: str, latency_ms: float | None = None) -> None:
        state = self.state(provider)
        state.consecutive_failures = 0
        state.open_until = None
        state.last_attempt_at = utc_now()
        state.last_success_at = state.last_attempt_at
        state.last_error = None
        state.latency_ms = latency_ms

    def record_failure(self, provider: str, error: str) -> None:
        state = self.state(provider)
        state.last_attempt_at = utc_now()
        state.last_error = error
        state.consecutive_failures += 1
        if state.consecutive_failures >= self.failure_threshold:
            state.open_until = utc_now() + timedelta(seconds=self.circuit_seconds)
