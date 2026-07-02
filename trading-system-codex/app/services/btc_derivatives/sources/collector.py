from __future__ import annotations

import asyncio
from datetime import datetime, timezone

from app.core.config import settings
from app.core.paths import app_paths
from app.schemas.btc_derivatives_sources import (
    LiveSnapshotEnvelope,
    ProviderStatus,
    SourceProbeResponse,
)
from app.services.btc_derivatives.archive import DerivativesArchive
from app.services.btc_derivatives.sources.adapters import (
    AdapterResult,
    PublicProviderAdapter,
)
from app.services.btc_derivatives.sources.cache import LiveSourceCache
from app.services.btc_derivatives.sources.http import SourceHttpClient
from app.services.btc_derivatives.sources.registry import PROVIDER_REGISTRY

OPTION_PRIORITY = ("deribit", "okx", "bybit")


class LiveCollector:
    def __init__(
        self,
        *,
        cache: LiveSourceCache | None = None,
        http: SourceHttpClient | None = None,
        archive: DerivativesArchive | None = None,
    ) -> None:
        self.cache = cache or LiveSourceCache()
        self.http = http or SourceHttpClient(
            timeout_seconds=settings.btc_derivatives_timeout_seconds,
            provider_concurrency=settings.btc_derivatives_provider_concurrency,
            failure_threshold=settings.btc_derivatives_circuit_failure_threshold,
            circuit_seconds=settings.btc_derivatives_circuit_cooldown_seconds,
        )
        archive_root = (
            self.cache.root.parent / "derivatives_archive"
            if cache is not None
            else app_paths.data_dir / "derivatives_archive"
        )
        self.archive = archive or DerivativesArchive(
            archive_root,
            quota_bytes=settings.btc_derivatives_archive_quota_bytes,
        )
        self.archive.migrate_legacy(self.cache.root)
        self.adapters = {
            key: PublicProviderAdapter(spec, self.http, self.cache)
            for key, spec in PROVIDER_REGISTRY.items()
        }

    def statuses(self, results: list[AdapterResult] | None = None) -> list[ProviderStatus]:
        result_map = {item.provider: item for item in (results or [])}
        cached_health = {
            item.get("provider"): item for item in self.cache.read_health()
        }
        statuses: list[ProviderStatus] = []
        for key, spec in PROVIDER_REGISTRY.items():
            result = result_map.get(key)
            state = self.http.state(key)
            if result is None and key in cached_health:
                statuses.append(ProviderStatus.model_validate(cached_health[key]))
                continue
            if state.is_open():
                status = "circuit_open"
            elif result and result.endpoint_success == result.endpoint_total:
                status = "ok"
            elif result and result.endpoint_success:
                status = "partial"
            elif result:
                status = "failed"
            else:
                status = "unknown"
            statuses.append(
                ProviderStatus(
                    provider=key,
                    status=status,
                    capabilities=list(spec.capabilities),
                    latency_ms=result.latency_ms if result else state.latency_ms,
                    last_attempt_at=state.last_attempt_at,
                    last_success_at=state.last_success_at,
                    last_error=(
                        "; ".join(result.errors)
                        if result and result.errors
                        else state.last_error
                    ),
                    circuit_open_until=state.open_until,
                    endpoint_success=result.endpoint_success if result else 0,
                    endpoint_total=result.endpoint_total if result else len(spec.endpoints),
                )
            )
        return statuses

    async def collect(self, *, force: bool = False) -> LiveSnapshotEnvelope:
        if not settings.btc_derivatives_live_enabled:
            return LiveSnapshotEnvelope(
                snapshot_state="data_insufficient",
                source_status=self.statuses(),
                missing_reasons=["真实数据采集已禁用"],
            )
        results = await asyncio.gather(
            *(adapter.collect(force=force) for adapter in self.adapters.values())
        )
        primary = next(
            (
                provider
                for provider in OPTION_PRIORITY
                if any(
                    item.provider == provider
                    and any((quote.open_interest or 0) > 0 for quote in item.options)
                    for item in results
                )
            ),
            None,
        )
        options = next(
            (item.options for item in results if item.provider == primary), []
        )
        perps = [perp for item in results for perp in item.perps]
        history = next(
            (item.history for item in results if item.provider == "binance_futures"), []
        )
        statuses = self.statuses(results)
        self.cache.write_health([item.model_dump(mode="json") for item in statuses])
        usable = bool(options or perps)
        envelope = LiveSnapshotEnvelope(
            snapshot_state="live" if usable else "data_insufficient",
            data_timestamp=datetime.now(timezone.utc) if usable else None,
            options=options,
            perps=perps,
            price_history=history,
            source_status=statuses,
            primary_option_provider=primary,
            missing_reasons=[] if usable else ["所有公开数据源当前均不可用"],
        )
        if usable:
            self.cache.write_snapshot(envelope.model_dump(mode="json"))
            captured_at = envelope.data_timestamp or datetime.now(timezone.utc)
            if options and primary:
                self.archive.append(
                    provider=primary,
                    underlying="BTC",
                    data_type="option_chain_15m",
                    captured_at=captured_at,
                    records=[item.model_dump(mode="json") for item in options],
                )
            for item in results:
                if item.provider in OPTION_PRIORITY and item.provider != primary and item.options:
                    self.archive.append(
                        provider=item.provider,
                        underlying="BTC",
                        data_type="option_chain_1h",
                        captured_at=captured_at.replace(minute=0, second=0, microsecond=0),
                        records=[quote.model_dump(mode="json") for quote in item.options],
                    )
            if perps:
                self.archive.append(
                    provider="multi_provider",
                    underlying="BTC",
                    data_type="perp_snapshot_15m",
                    captured_at=captured_at,
                    records=[item.model_dump(mode="json") for item in perps],
                )
            self.archive.maintain(now=captured_at)
        return envelope

    async def snapshot(
        self,
        *,
        force: bool = False,
        allow_network: bool = True,
    ) -> LiveSnapshotEnvelope:
        if not force:
            fresh = self.cache.read_snapshot(30)
            if fresh:
                return LiveSnapshotEnvelope.model_validate(fresh)
            stale = self.cache.read_snapshot(settings.btc_derivatives_stale_max_seconds)
            if stale:
                envelope = LiveSnapshotEnvelope.model_validate(stale)
                envelope.snapshot_state = "stale"
                envelope.source_status = self.statuses()
                envelope.missing_reasons = ["实时快照过期，正在使用最近真实缓存"]
                return envelope
            hard_stale = self.cache.read_snapshot(settings.btc_derivatives_hard_stale_max_seconds)
            if hard_stale:
                envelope = LiveSnapshotEnvelope.model_validate(hard_stale)
                envelope.snapshot_state = "stale"
                envelope.source_status = self.statuses()
                envelope.missing_reasons = ["实时快照超过软时效，正在使用 2 小时内的最近真实缓存"]
                return envelope
            if not allow_network:
                return LiveSnapshotEnvelope(
                    snapshot_state="data_insufficient",
                    source_status=self.statuses(),
                    missing_reasons=["尚无真实缓存，请触发刷新任务"],
                )
        live = await self.collect(force=force)
        if live.snapshot_state == "live":
            return live
        stale = self.cache.read_snapshot(settings.btc_derivatives_stale_max_seconds)
        if stale:
            envelope = LiveSnapshotEnvelope.model_validate(stale)
            envelope.snapshot_state = "stale"
            envelope.source_status = live.source_status
            envelope.missing_reasons = ["实时采集失败，正在使用 15 分钟内的最近真实缓存"]
            return envelope
        hard_stale = self.cache.read_snapshot(settings.btc_derivatives_hard_stale_max_seconds)
        if hard_stale:
            envelope = LiveSnapshotEnvelope.model_validate(hard_stale)
            envelope.snapshot_state = "stale"
            envelope.source_status = live.source_status
            envelope.missing_reasons = ["实时采集失败，正在使用 2 小时内的最近真实缓存"]
            return envelope
        return live

    async def probe(self) -> SourceProbeResponse:
        endpoints = [
            item
            for group in await asyncio.gather(
                *(adapter.probe() for adapter in self.adapters.values())
            )
            for item in group
        ]
        statuses = self.statuses()
        self.cache.write_health([item.model_dump(mode="json") for item in statuses])
        return SourceProbeResponse(
            generated_at=datetime.now(timezone.utc),
            providers=statuses,
            endpoints=endpoints,
        )
