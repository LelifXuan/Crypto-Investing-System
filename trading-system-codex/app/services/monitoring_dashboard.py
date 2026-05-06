from __future__ import annotations

import time
from datetime import UTC, datetime, timedelta

from app.repositories.market_repository import MarketRepository
from app.schemas.market import (
    AlertEventRead,
    IndicatorObservationRead,
    MacroOverviewResponse,
    MonitoringDashboardRead,
)
from app.services.cache_registry import CACHE_SOURCE_VERSION
from app.services.indicator_monitoring import IndicatorMonitoringService
from app.services.macro_overview import MacroOverviewService
from app.services.page_snapshot_cache import (
    bundle_status_message,
    cache_status,
    expires_at_for_page,
    monitoring_dashboard_cache_key,
)

MONITORING_STALE_MAX_AGE = timedelta(days=1)


class MonitoringDashboardService:
    def __init__(self, repository: MarketRepository) -> None:
        self.repository = repository

    async def get_bundle(self, instrument_id: str, timeframe: str) -> MonitoringDashboardRead:
        cache = await self.repository.get_page_snapshot_cache(
            monitoring_dashboard_cache_key(instrument_id, timeframe)
        )
        status = cache_status(cache)
        payload = cache.payload_json if cache is not None else {}
        return MonitoringDashboardRead.model_validate(
            {
                "instrument_id": instrument_id,
                "timeframe": timeframe,
                "macro_overview": payload.get("macro_overview"),
                "technical_observations": payload.get("technical_observations", []),
                "onchain_observations": payload.get("onchain_observations", []),
                "alert_events": payload.get("alert_events", []),
                "status": status,
                "cache_state": status,
                "snapshot_at": cache.snapshot_at if cache else None,
                "data_ts": cache.data_ts if cache else None,
                "source_updated_at": cache.source_updated_at if cache else None,
                "expires_at": cache.expires_at if cache else None,
                "source_version": cache.source_version if cache else CACHE_SOURCE_VERSION,
                "cost_ms": cache.cost_ms if cache else None,
                "refreshed": False,
                "status_message": bundle_status_message(status),
            }
        )

    async def refresh_bundle(self, instrument_id: str, timeframe: str) -> MonitoringDashboardRead:
        started = time.perf_counter()
        now = datetime.now(UTC)
        monitoring_service = IndicatorMonitoringService(self.repository)
        if await self._category_is_stale(
            "technical", instrument_id=instrument_id, timeframe=timeframe
        ):
            try:
                await monitoring_service.sync_technical(
                    instrument_id=instrument_id,
                    timeframe=timeframe,
                )
            except Exception:
                pass
        if await self._category_is_stale("macro"):
            try:
                await monitoring_service.sync_macro()
            except Exception:
                pass
        if await self._category_is_stale("onchain"):
            try:
                await monitoring_service.sync_onchain()
            except Exception:
                pass

        macro_overview = await MacroOverviewService(self.repository).build_overview()
        technical_items = await self.repository.list_indicator_observations(
            category="technical",
            instrument_id=instrument_id,
            timeframe=timeframe,
            limit=10,
        )
        onchain_items = await self.repository.list_indicator_observations(
            category="onchain",
            limit=10,
        )
        alert_events = await self.repository.list_alert_events(limit=20)
        all_ts = [item.observation_ts for item in technical_items + onchain_items]
        source_updated_at = max(all_ts, default=now)
        payload = {
            "macro_overview": MacroOverviewResponse.model_validate(macro_overview).model_dump(
                mode="json"
            ),
            "technical_observations": [
                IndicatorObservationRead.model_validate(item).model_dump(mode="json")
                for item in technical_items
            ],
            "onchain_observations": [
                IndicatorObservationRead.model_validate(item).model_dump(mode="json")
                for item in onchain_items
            ],
            "alert_events": [
                AlertEventRead.model_validate(item).model_dump(mode="json") for item in alert_events
            ],
        }
        cache = await self.repository.upsert_page_snapshot_cache(
            cache_key=monitoring_dashboard_cache_key(instrument_id, timeframe),
            page_type="monitoring",
            instrument_id=instrument_id,
            timeframe=timeframe,
            payload_json=payload,
            status="ready",
            cache_state="fresh",
            snapshot_at=now,
            data_ts=source_updated_at,
            expires_at=expires_at_for_page("monitoring", now),
            source_updated_at=source_updated_at,
            source_version=CACHE_SOURCE_VERSION,
            cost_ms=int((time.perf_counter() - started) * 1000),
            meta_json={"alert_limit": 20, "technical_limit": 10, "onchain_limit": 10},
        )
        return MonitoringDashboardRead.model_validate(
            {
                "instrument_id": instrument_id,
                "timeframe": timeframe,
                **payload,
                "status": "fresh",
                "cache_state": "fresh",
                "snapshot_at": cache.snapshot_at,
                "data_ts": cache.data_ts,
                "source_updated_at": cache.source_updated_at,
                "expires_at": cache.expires_at,
                "source_version": cache.source_version,
                "cost_ms": cache.cost_ms,
                "refreshed": True,
                "status_message": bundle_status_message("fresh"),
            }
        )

    async def _category_is_stale(
        self,
        category: str,
        *,
        instrument_id: str | None = None,
        timeframe: str | None = None,
    ) -> bool:
        items = await self.repository.list_indicator_observations(
            category=category,
            instrument_id=instrument_id,
            timeframe=timeframe,
            limit=1,
        )
        if not items:
            return True
        ts = (
            items[0].observation_ts
            if items[0].observation_ts.tzinfo
            else items[0].observation_ts.replace(tzinfo=UTC)
        )
        return ts < datetime.now(UTC) - MONITORING_STALE_MAX_AGE
