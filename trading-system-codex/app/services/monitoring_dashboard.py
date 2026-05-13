from __future__ import annotations

import logging
import time
from datetime import datetime, timedelta, timezone

from app.core.config import settings
from app.repositories.market_repository import MarketRepository
from app.schemas.market import (
    AlertEventRead,
    IndicatorObservationRead,
    MacroOverviewResponse,
    MonitoringDashboardRead,
)
from app.services.cache_registry import CACHE_SOURCE_VERSION
from app.services.indicator_monitoring import IndicatorMonitoringService
from app.services.page_snapshot_cache import (
    bundle_status_message,
    cache_status,
    expires_at_for_page,
    monitoring_dashboard_cache_key,
)

logger = logging.getLogger(__name__)

UTC = timezone.utc

MONITORING_STALE_MAX_AGE = timedelta(days=1)


class MonitoringDashboardService:
    def __init__(self, repository: MarketRepository) -> None:
        self.repository = repository

    async def get_bundle(
        self,
        instrument_id: str,
        timeframe: str,
        *,
        allow_refresh: bool = True,
    ) -> MonitoringDashboardRead:
        cache = await self.repository.get_page_snapshot_cache(
            monitoring_dashboard_cache_key(instrument_id, timeframe)
        )
        status = cache_status(cache)
        if allow_refresh and (cache is None or status in {"missing", "stale"}):
            try:
                return await self.refresh_bundle(instrument_id, timeframe)
            except Exception:
                logger.warning("monitoring dashboard auto-refresh failed", exc_info=True)
                pass
        payload = cache.payload_json if cache is not None else {}
        macro_overview = payload.get("macro_overview")
        if isinstance(macro_overview, dict) and macro_overview.get("status") == "unavailable":
            macro_overview = None
        return MonitoringDashboardRead.model_validate(
            {
                "instrument_id": instrument_id,
                "timeframe": timeframe,
                "macro_overview": macro_overview,
                "technical_observations": payload.get("technical_observations", []),
                "onchain_observations": payload.get("onchain_observations", []),
                "alert_events": payload.get("alert_events", []),
                "cross_asset": payload.get("cross_asset", []),
                "source_status": payload.get("source_status", {}),
                "status": "ready" if status == "fresh" else status,
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
        now = datetime.now(timezone.utc)
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
                logger.warning("sync failed for %s", exc_info=True)
        if await self._category_is_stale("macro"):
            try:
                await monitoring_service.sync_macro()
            except Exception:
                logger.warning("sync failed for %s", exc_info=True)
        if await self._category_is_stale("onchain"):
            try:
                await monitoring_service.sync_onchain()
            except Exception:
                logger.warning("sync failed for %s", exc_info=True)

        macro_overview = await self._macro_overview_payload()
        if isinstance(macro_overview, dict) and macro_overview.get("regime_key") == "unknown":
            macro_overview = None
        cross_asset = await self._cross_asset_snapshot()
        source_status = await self._data_source_status()
        technical_raw = await self.repository.list_indicator_observations(
            category="technical",
            instrument_id=instrument_id,
            timeframe=timeframe,
            limit=50,  # Frontend can page/filter but the dashboard should return all enabled indicators
        )
        onchain_raw = await self.repository.list_indicator_observations(
            category="onchain",
            limit=50,  # Frontend can page/filter but the dashboard should return all enabled indicators
        )
        alert_events = await self.repository.list_alert_events(limit=20)
        all_ts = [item.observation_ts for item in technical_raw + onchain_raw]
        source_updated_at = max(all_ts, default=now)
        payload = {
            "macro_overview": macro_overview,
            "technical_observations": [
                self._annotate_observation(
                    IndicatorObservationRead.model_validate(item).model_dump(mode="json"),
                    item,
                    now,
                )
                for item in technical_raw
            ],
            "onchain_observations": [
                self._annotate_observation(
                    IndicatorObservationRead.model_validate(item).model_dump(mode="json"),
                    item,
                    now,
                )
                for item in onchain_raw
            ],
            "alert_events": [
                AlertEventRead.model_validate(item).model_dump(mode="json") for item in alert_events
            ],
            "cross_asset": cross_asset,
            "source_status": source_status,
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
            meta_json={"alert_limit": 20, "technical_limit": 50, "onchain_limit": 50},
        )
        return MonitoringDashboardRead.model_validate(
            {
                "instrument_id": instrument_id,
                "timeframe": timeframe,
                **payload,
                "status": "ready",
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
        return ts < datetime.now(timezone.utc) - MONITORING_STALE_MAX_AGE

    async def _macro_overview_payload(self) -> dict:
        try:
            from app.services.macro_overview import MacroOverviewService

            macro_overview = await MacroOverviewService(self.repository).build_overview()
            return MacroOverviewResponse.model_validate(macro_overview).model_dump(mode="json")
        except Exception as exc:
            logger.warning("macro overview build failed: %s", exc)
            return {
                # NOTE: This is a fallback placeholder state; consumers should treat
                # operation_bias and scores as unavailable, not as a real recommendation.
                "regime_key": "unknown",
                "regime_label_cn": "宏观暂不可用",
                "regime_summary": f"数据构建异常：{exc}",
                "policy_score": 0,
                "inflation_score": 0,
                "growth_score": 0,
                "liquidity_score": 0,
                "operation_bias": "观望",
                "event_window_status": "inactive",
                "event_window_summary": "无法获取事件窗口信息",
                "next_event_title": None,
                "next_event_at": None,
                "event_items": [],
                "layers": [],
            }

    async def _cross_asset_snapshot(self) -> list[dict]:
        tokens = {
            "xau-usdt-perp": "黄金",
            "xaut-usdt-perp": "泰达金",
            "spyx-usdt-perp": "标普500",
            "qqqx-usdt-perp": "纳斯达克",
            "slvon-usdt-perp": "白银",
        }
        results = []
        for instrument_id, label in tokens.items():
            try:
                candles = await self.repository.list_candles(
                    instrument_id=instrument_id,
                    timeframe="1d",
                    limit=2,
                )
                if candles:
                    latest = candles[-1]
                    prev = candles[-2] if len(candles) > 1 else None
                    change_pct = (
                        (float(latest.close) - float(prev.close))
                        / float(prev.close)
                        * 100
                        if prev and prev.close
                        else None
                    )
                    results.append({
                        "instrument_id": instrument_id,
                        "label": label,
                        "price": float(latest.close),
                        "change_pct": round(change_pct, 2) if change_pct is not None else None,
                        "ts": latest.ts_open.isoformat(),
                    })
            except Exception:
                pass
        return results

    async def _data_source_status(self) -> dict[str, str]:
        status = {}
        try:
            candles = await self.repository.list_candles(instrument_id="btc-usdt-perp", timeframe="1h", limit=1)
            status["gateio"] = "online" if candles else "no_data"
        except Exception:
            status["gateio"] = "offline"
        try:
            dff = await self.repository.latest_observation("us_dff")
            status["fred"] = "online" if dff and dff.value_num is not None else "no_data"
        except Exception:
            status["fred"] = "offline"
        status["glassnode"] = "online" if settings.glassnode_api_key else "未配置（使用 demo 数据）"
        return status

    @staticmethod
    def _annotate_observation(d: dict, item, now: datetime) -> dict:
        obs_ts = item.observation_ts
        if obs_ts.tzinfo is None:
            obs_ts = obs_ts.replace(tzinfo=UTC)
        age_seconds = (now - obs_ts).total_seconds()
        freshness_seconds = 86400 if item.category == "onchain" else 7200
        d["status"] = "fresh" if age_seconds < freshness_seconds else "stale"
        is_demo = (item.value_json or {}).get("is_demo", False)
        is_preliminary = getattr(item, "is_preliminary", False) or False
        d["recommendation_usable"] = not is_demo and not is_preliminary and d["status"] == "fresh"
        return d
