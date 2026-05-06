from __future__ import annotations

import time
from datetime import UTC, datetime

from app.repositories.market_repository import MarketRepository
from app.schemas.market import (
    AlertEventRead,
    AlertsBundleRead,
    ChipStructureRead,
    DivergenceSummaryRead,
)
from app.services.cache_registry import CACHE_SOURCE_VERSION
from app.services.chip_structure import ChipStructureService
from app.services.contract_snapshot import ContractSnapshotService
from app.services.divergence import DivergenceService
from app.services.final_decision import FinalDecisionService
from app.services.indicator_matrix import IndicatorMatrixService
from app.services.market_data_bundle import MarketDataBundleService
from app.services.page_snapshot_cache import (
    alerts_bundle_cache_key,
    bundle_status_message,
    cache_status,
    expires_at_for_dataset,
    expires_at_for_page,
    microstructure_cache_key,
)


def _candle_ts(candle, fallback: datetime) -> datetime:
    if candle is None:
        return fallback
    value = candle.get("ts_open") if isinstance(candle, dict) else candle.ts_open
    if isinstance(value, datetime):
        return value
    return datetime.fromisoformat(str(value).replace("Z", "+00:00"))


class AlertsBundleService:
    def __init__(self, repository: MarketRepository) -> None:
        self.repository = repository

    async def get_bundle(self, instrument_id: str, timeframe: str) -> AlertsBundleRead:
        cache = await self.repository.get_page_snapshot_cache(
            alerts_bundle_cache_key(instrument_id, timeframe)
        )
        status = cache_status(cache)
        payload = cache.payload_json if cache is not None else {}
        return AlertsBundleRead.model_validate(
            {
                "instrument_id": instrument_id,
                "timeframe": timeframe,
                "chip_structure": payload.get("chip_structure"),
                "divergence_summary": payload.get("divergence_summary"),
                "alert_events": payload.get("alert_events", []),
                "final_decision": payload.get("final_decision", {}),
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

    async def refresh_bundle(self, instrument_id: str, timeframe: str) -> AlertsBundleRead:
        started = time.perf_counter()
        now = datetime.now(UTC)
        market_bundle = await MarketDataBundleService(self.repository).get_bundle(
            instrument_id=instrument_id,
            timeframe=timeframe,
            limit=220,
            allow_stale=False,
            refresh=False,
        )
        normalized_timeframe = market_bundle.get("cache_timeframe", timeframe)
        candles = market_bundle.get("candles", [])
        indicator_matrix = await IndicatorMatrixService(self.repository).get_matrix(
            instrument_id=instrument_id,
            timeframe=normalized_timeframe,
            limit=220,
        )
        chip = await ChipStructureService(self.repository).analyze(
            instrument_id, normalized_timeframe
        )
        divergence = DivergenceService().analyze(
            instrument_id,
            normalized_timeframe,
            candles,
            indicator_matrix=indicator_matrix,
        )
        alert_events = await self.repository.list_alert_events(limit=50)
        final_decision = await FinalDecisionService(self.repository).build(
            instrument_id, normalized_timeframe
        )
        contract_snapshot = await ContractSnapshotService(self.repository).get_snapshot(
            instrument_id,
            include_stats=True,
            include_book=True,
        )
        source_updated_at = _candle_ts(candles[-1], now) if candles else now
        await self._persist_microstructure_summary(
            instrument_id=instrument_id,
            timeframe=normalized_timeframe,
            chip=chip,
            source_updated_at=source_updated_at,
        )
        payload = {
            "chip_structure": ChipStructureRead.model_validate(chip).model_dump(mode="json"),
            "divergence_summary": DivergenceSummaryRead.model_validate(divergence).model_dump(
                mode="json"
            ),
            "contract_snapshot": contract_snapshot,
            "alert_events": [
                AlertEventRead.model_validate(item).model_dump(mode="json")
                for item in alert_events
            ],
            "final_decision": final_decision,
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
            meta_json={"alert_limit": 50},
        )
        return AlertsBundleRead.model_validate(
            {
                "instrument_id": instrument_id,
                "timeframe": normalized_timeframe,
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

    async def _persist_microstructure_summary(
        self,
        *,
        instrument_id: str,
        timeframe: str,
        chip: dict,
        source_updated_at: datetime,
    ) -> None:
        payload = {
            "evidence_quality": chip.get("evidence_quality"),
            "missing_inputs": chip.get("missing_inputs", []),
            "risk_gates": chip.get("risk_gates", []),
            "components": chip.get("components", {}),
            "explain": chip.get("explain", []),
        }
        await self.repository.upsert_computed_dataset_cache(
            cache_key=microstructure_cache_key(instrument_id, timeframe),
            dataset_type="microstructure",
            instrument_id=instrument_id,
            timeframe=timeframe,
            source_data_ts=source_updated_at,
            payload_json=payload,
            cache_state="fresh",
            source_version=CACHE_SOURCE_VERSION,
            calculated_at=datetime.now(UTC),
            expires_at=expires_at_for_dataset("microstructure", datetime.now(UTC)),
            meta_json={"source": "chip_structure"},
        )
