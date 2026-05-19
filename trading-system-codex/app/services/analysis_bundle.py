from __future__ import annotations

import time
from datetime import datetime, timezone

from app.db.models.market import MarkPrice
from app.repositories.market_repository import MarketRepository
from app.schemas.market import AnalysisBundleRead, CandleRead, MarkPriceRead
from app.services.cache_registry import CACHE_SOURCE_VERSION
from app.services.contract_snapshot import ContractSnapshotService
from app.services.final_decision import FinalDecisionService
from app.services.indicator_matrix import IndicatorMatrixService
from app.services.indicator_monitoring import IndicatorMonitoringService
from app.services.market import MarketService
from app.services.market_data_bundle import MarketDataBundleService
from app.services.page_snapshot_cache import (
    analysis_cache_key,
    bundle_status_message,
    cache_status,
    expires_at_for_page,
)

UTC = timezone.utc

WINDOW_PROFILES = {
    "1h": {
        "short": {"visibleBars": 96, "calcBars": 360},
        "default": {"visibleBars": 240, "calcBars": 720},
        "long": {"visibleBars": 480, "calcBars": 1200},
    },
    "4h": {
        "short": {"visibleBars": 90, "calcBars": 300},
        "default": {"visibleBars": 180, "calcBars": 480},
        "long": {"visibleBars": 360, "calcBars": 900},
    },
    "1d": {
        "short": {"visibleBars": 90, "calcBars": 240},
        "default": {"visibleBars": 180, "calcBars": 420},
        "long": {"visibleBars": 360, "calcBars": 900},
    },
    "1w": {
        "short": {"visibleBars": 52, "calcBars": 156},
        "default": {"visibleBars": 104, "calcBars": 260},
        "long": {"visibleBars": 208, "calcBars": 520},
    },
    "30d": {
        "short": {"visibleBars": 36, "calcBars": 120},
        "default": {"visibleBars": 60, "calcBars": 180},
        "long": {"visibleBars": 120, "calcBars": 360},
    },
}


class AnalysisBundleService:
    def __init__(self, repository: MarketRepository) -> None:
        self.repository = repository

    async def get_bundle(
        self, instrument_id: str, timeframe: str, view_window: str = "default"
    ) -> AnalysisBundleRead:
        limit = limit_for_view_window(timeframe, view_window)
        cache_key = analysis_cache_key(instrument_id, timeframe, limit)
        cache = await self.repository.get_page_snapshot_cache(cache_key)
        status = cache_status(cache)
        payload = cache.payload_json if cache is not None else {}
        return AnalysisBundleRead.model_validate(
            {
                "instrument_id": instrument_id,
                "timeframe": timeframe,
                "view_window": view_window,
                "candles": payload.get("candles", []),
                "mark": payload.get("mark"),
                "contract_snapshot": payload.get("contract_snapshot", {}),
                "core_indicator_series": payload.get("core_indicator_series", {}),
                "secondary_indicator_series": payload.get("secondary_indicator_series", {}),
                "final_decision": payload.get("final_decision", {}),
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

    async def refresh_bundle(
        self,
        instrument_id: str,
        timeframe: str,
        view_window: str = "default",
        *,
        sync_inputs: bool = True,
    ) -> AnalysisBundleRead:
        started = time.perf_counter()
        now = datetime.now(timezone.utc)
        market_service = MarketService(self.repository)
        monitoring_service = IndicatorMonitoringService(self.repository)
        normalized_timeframe = "30d" if timeframe == "1M" else timeframe
        limit = limit_for_view_window(normalized_timeframe, view_window)
        if sync_inputs:
            await MarketDataBundleService(self.repository).get_bundle(
                instrument_id=instrument_id,
                timeframe=normalized_timeframe,
                limit=limit,
                allow_stale=False,
                refresh=True,
            )
            try:
                await monitoring_service.sync_technical(
                    instrument_id=instrument_id,
                    timeframe=normalized_timeframe,
                )
            except Exception:
                # Keep bundle generation resilient if indicator sync is temporarily unavailable.
                pass
        # These helpers share the same SQLAlchemy session and may write computed
        # caches. Keep them sequential to avoid concurrent flushes on one session.
        contract_snapshot = await ContractSnapshotService(self.repository).get_snapshot(
            instrument_id, include_stats=True
        )
        mark = await market_service.get_best_mark(instrument_id=instrument_id, prefer_live=True)
        indicator_matrix = await IndicatorMatrixService(self.repository).get_matrix(
            instrument_id=instrument_id, timeframe=normalized_timeframe, limit=limit
        )
        final_decision = await FinalDecisionService(self.repository).build(
            instrument_id, normalized_timeframe
        )
        market_bundle = await MarketDataBundleService(self.repository).get_bundle(
            instrument_id=instrument_id,
            timeframe=normalized_timeframe,
            limit=limit,
            allow_stale=False,
            refresh=False,
        )
        candles = [
            CandleRead.model_validate(item)
            for item in market_bundle.get("candles", [])
        ]
        source_updated_at = candles[-1].ts_open if candles else (mark.ts_event if mark else now)
        core_indicator_series = {
            key: value
            for key, value in indicator_matrix["series"].items()
            if key
            in {
                "ema_20",
                "ema_50",
                "ema_200",
                "ema_30",
                "ema_60",
                "ema_120",
                "ema_12",
                "rsi_14",
                "macd_line",
                "macd_signal",
                "macd_hist",
                "atr_14",
                "natr_14",
            }
        }
        secondary_indicator_series = {
            key: value
            for key, value in indicator_matrix["series"].items()
            if key not in core_indicator_series
        }
        payload = {
            "candles": [item.model_dump(mode="json") for item in candles],
            "mark": self._mark_payload(mark),
            "contract_snapshot": contract_snapshot,
            "core_indicator_series": core_indicator_series,
            "secondary_indicator_series": secondary_indicator_series,
            "final_decision": final_decision,
        }
        cost_ms = int((time.perf_counter() - started) * 1000)
        cache = await self.repository.upsert_page_snapshot_cache(
            cache_key=analysis_cache_key(instrument_id, normalized_timeframe, limit),
            page_type="analysis",
            instrument_id=instrument_id,
            timeframe=normalized_timeframe,
            payload_json=payload,
            status="ready",
            cache_state="fresh",
            snapshot_at=now,
            data_ts=source_updated_at,
            expires_at=expires_at_for_page("analysis", now),
            source_updated_at=source_updated_at,
            source_version=CACHE_SOURCE_VERSION,
            cost_ms=cost_ms,
            meta_json={"view_window": view_window, "limit": limit, "profile": view_window},
        )
        return AnalysisBundleRead.model_validate(
            {
                "instrument_id": instrument_id,
                "timeframe": normalized_timeframe,
                "view_window": view_window,
                "candles": payload["candles"],
                "mark": payload["mark"],
                "contract_snapshot": payload["contract_snapshot"],
                "core_indicator_series": core_indicator_series,
                "secondary_indicator_series": secondary_indicator_series,
                "final_decision": final_decision,
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

    @staticmethod
    def _mark_payload(mark: MarkPrice | None) -> dict | None:
        if mark is None:
            return None
        if getattr(mark, "mark_id", None) in (None, 0):
            payload = {
                "mark_id": 0,
                "instrument_id": mark.instrument_id,
                "mark_price": mark.mark_price,
                "source": mark.source,
                "ts_event": mark.ts_event,
            }
            return MarkPriceRead.model_validate(payload).model_dump(mode="json")
        return MarkPriceRead.model_validate(mark).model_dump(mode="json")


def limit_for_view_window(timeframe: str, view_window: str = "default") -> int:
    profile = WINDOW_PROFILES.get(timeframe, WINDOW_PROFILES["1d"]).get(
        view_window,
        WINDOW_PROFILES.get(timeframe, WINDOW_PROFILES["1d"])["default"],
    )
    return min(int(profile["calcBars"]), 1000)
