from __future__ import annotations

import logging
import time
from datetime import datetime, timezone

from app.repositories.market_repository import MarketRepository
from app.schemas.market import (
    AlertEventRead,
    AlertsBundleRead,
    DivergenceSummaryRead,
    PrecomputeHintRequest,
)
from app.services.cache_registry import CACHE_SOURCE_VERSION, source_freshness
from app.services.final_decision import FinalDecisionService
from app.services.indicator_matrix import IndicatorMatrixService
from app.services.market_data_bundle import MarketDataBundleService
from app.services.page_snapshot_cache import (
    alerts_bundle_cache_key,
    bundle_status_message,
    cache_status,
    expires_at_for_page,
)
from app.services.technical_risk import build_divergence_risk

UTC = timezone.utc
logger = logging.getLogger(__name__)


def _candle_ts(candle, fallback: datetime) -> datetime:
    if candle is None:
        return fallback
    value = candle.get("ts_open") if isinstance(candle, dict) else candle.ts_open
    if isinstance(value, datetime):
        return value
    return datetime.fromisoformat(str(value).replace("Z", "+00:00"))


class AlertsBundleService:
    """Build the alerts-compatible technical risk bundle.

    The standalone alert center is being retired, but existing callers still
    depend on this bundle shape. New bundles intentionally exclude proxy chip
    structure and contract-book fields; divergence is the reusable risk module.
    """

    def __init__(self, repository: MarketRepository) -> None:
        self.repository = repository

    async def get_bundle(
        self,
        instrument_id: str,
        timeframe: str,
        *,
        allow_refresh: bool = True,
    ) -> AlertsBundleRead:
        cache = await self.repository.get_page_snapshot_cache(
            alerts_bundle_cache_key(instrument_id, timeframe)
        )
        status = cache_status(cache)
        if allow_refresh and cache is None:
            try:
                return await self.refresh_bundle(instrument_id, timeframe)
            except Exception:
                logger.warning("alerts bundle auto-refresh failed", exc_info=True)
        refresh_enqueued = False
        refresh_task_key = None
        if allow_refresh and cache is not None and status in {"stale", "error", "updating"}:
            try:
                from app.services.precompute import precompute_service

                queued = await precompute_service.enqueue_hint(
                    PrecomputeHintRequest(
                        current_page="alerts",
                        instrument_id=instrument_id,
                        timeframe=timeframe,
                        reason="alerts_bundle_stale_read",
                        visible=True,
                        candidates=["alerts"],
                        priority=3,
                    )
                )
                refresh_enqueued = queued.accepted > 0 or queued.deduped > 0
                refresh_task_key = queued.queued_keys[0] if queued.queued_keys else None
            except Exception:
                logger.warning("alerts bundle background refresh enqueue failed", exc_info=True)
        payload = cache.payload_json if cache is not None else {}
        freshness = source_freshness(
            cache.source_updated_at if cache is not None else None,
            timeframe,
        )
        return AlertsBundleRead.model_validate(
            {
                "instrument_id": instrument_id,
                "timeframe": timeframe,
                "chip_structure": payload.get("chip_structure"),
                "divergence_summary": payload.get("divergence_summary"),
                "technical_risk": payload.get("technical_risk"),
                "alert_events": payload.get("alert_events", []),
                "final_decision": payload.get("final_decision", {}),
                "contract_snapshot": payload.get("contract_snapshot", {}),
                "status": "ready" if status == "fresh" else status,
                "cache_state": status,
                "freshness_state": freshness.state,
                "source_age_seconds": freshness.age_seconds,
                "refresh_enqueued": refresh_enqueued,
                "refresh_task_key": refresh_task_key,
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

    async def refresh_bundle(self, instrument_id: str, timeframe: str) -> AlertsBundleRead:
        started = time.perf_counter()
        now = datetime.now(UTC)
        market_bundle = await MarketDataBundleService(self.repository).get_bundle(
            instrument_id=instrument_id,
            timeframe=timeframe,
            limit=220,
            allow_stale=False,
            refresh=True,
        )
        normalized_timeframe = market_bundle.get("cache_timeframe", timeframe)
        candles = market_bundle.get("candles", [])
        indicator_matrix = await IndicatorMatrixService(self.repository).get_matrix(
            instrument_id=instrument_id,
            timeframe=normalized_timeframe,
            limit=220,
        )
        divergence = self._divergence_payload(
            instrument_id,
            normalized_timeframe,
            candles,
            indicator_matrix=indicator_matrix,
        )
        alert_events = await self.repository.list_alert_events(
            instrument_id=instrument_id,
            timeframe=normalized_timeframe,
            limit=50,
        )
        final_decision = await FinalDecisionService(self.repository).build(
            instrument_id, normalized_timeframe
        )
        source_updated_at = _candle_ts(candles[-1], now) if candles else now
        technical_risk = {
            "divergence": build_divergence_risk(
                divergence,
                strategy_bias=(final_decision or {}).get("strategy_bias", "neutral"),
                timeframe=normalized_timeframe,
            )
        }
        payload = {
            "chip_structure": None,
            "divergence_summary": DivergenceSummaryRead.model_validate(divergence).model_dump(
                mode="json"
            ),
            "technical_risk": technical_risk,
            "alert_events": [
                AlertEventRead.model_validate(item).model_dump(mode="json") for item in alert_events
            ],
            "final_decision": final_decision,
            "contract_snapshot": {},
        }
        cache = await self.repository.upsert_page_snapshot_cache(
            cache_key=alerts_bundle_cache_key(instrument_id, normalized_timeframe),
            page_type="alerts",
            instrument_id=instrument_id,
            timeframe=normalized_timeframe,
            payload_json=payload,
            status="ready",
            cache_state="fresh",
            snapshot_at=now,
            data_ts=source_updated_at,
            expires_at=expires_at_for_page("alerts", now),
            source_updated_at=source_updated_at,
            source_version=CACHE_SOURCE_VERSION,
            cost_ms=int((time.perf_counter() - started) * 1000),
            meta_json={"alert_limit": 50, "source": "technical_risk_divergence"},
        )
        return AlertsBundleRead.model_validate(
            {
                "instrument_id": instrument_id,
                "timeframe": normalized_timeframe,
                **payload,
                "status": "ready",
                "cache_state": "fresh",
                "freshness_state": source_freshness(
                    source_updated_at,
                    normalized_timeframe,
                    now=now,
                ).state,
                "source_age_seconds": 0,
                "refresh_completed_at": now,
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

    def _divergence_payload(
        self,
        instrument_id: str,
        timeframe: str,
        candles: list,
        *,
        indicator_matrix: dict,
    ) -> dict:
        try:
            from app.services.divergence import DivergenceService

            return DivergenceService().analyze(
                instrument_id,
                timeframe,
                candles,
                indicator_matrix=indicator_matrix,
            )
        except Exception as exc:
            logger.warning("divergence payload fetch failed: %s", exc)
            return {
                "instrument_id": instrument_id,
                "timeframe": timeframe,
                "overall": {
                    "tone": "neutral",
                    "title": "背离分析暂不可用",
                    "score": 0.0,
                    "confidence": 0.0,
                    "leaders": [],
                    "message": "未发现有效背离风险。",
                },
                "signals": [],
                "filters": [],
                "trend_context": None,
                "generated_at": datetime.now(UTC),
            }
