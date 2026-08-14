from __future__ import annotations

import hashlib
import json
import logging
from datetime import datetime, timezone

from fastapi.encoders import jsonable_encoder

from app.core.timeframes import (
    bucket_limit,
    normalize_instrument_id,
    normalize_timeframe_for_cache,
    normalize_timeframe_for_provider,
    normalize_timeframe_for_ui,
)
from app.repositories.market_repository import MarketRepository
from app.schemas.market import CandleRead
from app.services.cache_registry import (
    CACHE_SOURCE_VERSION,
    dataset_cache_status,
    expires_at_for_dataset,
)
from app.services.market import MarketService

UTC = timezone.utc
logger = logging.getLogger(__name__)


def market_bundle_cache_key(
    instrument_id: str,
    timeframe: str,
    limit: int,
    price_kind: str = "last",
    source_version: str = CACHE_SOURCE_VERSION,
) -> str:
    return (
        "market_bundle:"
        f"{normalize_instrument_id(instrument_id)}:"
        f"{normalize_timeframe_for_cache(timeframe)}:"
        f"{bucket_limit(limit)}:{price_kind}:{source_version}"
    )


class MarketDataBundleService:
    def __init__(self, repository: MarketRepository) -> None:
        self.repository = repository
        self.market_service = MarketService(repository)

    async def get_bundle(
        self,
        instrument_id: str,
        timeframe: str,
        limit: int,
        *,
        allow_stale: bool = True,
        refresh: bool = False,
        price_kind: str = "last",
    ) -> dict:
        normalized_instrument = normalize_instrument_id(instrument_id)
        provider_timeframe = normalize_timeframe_for_provider(timeframe)
        cache_timeframe = normalize_timeframe_for_cache(timeframe)
        ui_timeframe = normalize_timeframe_for_ui(timeframe)
        limit_bucket = bucket_limit(limit)
        cache_key = market_bundle_cache_key(
            normalized_instrument,
            cache_timeframe,
            limit_bucket,
            price_kind=price_kind,
        )
        cached = await self.repository.get_computed_dataset_cache(cache_key)
        cached_status = dataset_cache_status(cached)
        if (
            cached is not None
            and cached.payload_json
            and (cached_status == "fresh" or (allow_stale and cached_status == "stale"))
        ):
            payload = dict(cached.payload_json)
            payload["cache_state"] = cached_status
            payload["candles"] = payload.get("candles", [])[-limit:]
            payload["requested_limit"] = limit
            return payload

        if refresh:
            candles = await self.market_service.sync_candles_from_provider(
                instrument_id=normalized_instrument,
                timeframe=provider_timeframe,
                limit=limit_bucket,
                price_kind=price_kind,
                persist=True,
            )
        else:
            candles = await self.repository.list_candles(
                instrument_id=normalized_instrument,
                timeframe=cache_timeframe,
                limit=limit_bucket,
            )
            if len(candles) < min(limit, limit_bucket):
                try:
                    live_candles = await self.market_service.sync_candles_from_provider(
                        instrument_id=normalized_instrument,
                        timeframe=provider_timeframe,
                        limit=limit_bucket,
                        price_kind=price_kind,
                        persist=True,
                    )
                    if len(live_candles) > len(candles):
                        candles = live_candles
                except Exception:
                    logger.warning("provider fallback failed", exc_info=True)

        payload = self._build_payload(
            normalized_instrument,
            provider_timeframe,
            cache_timeframe,
            ui_timeframe,
            limit,
            limit_bucket,
            candles,
        )
        source_hash = self._fingerprint(
            normalized_instrument,
            cache_timeframe,
            limit_bucket,
            payload["source_max_ts"],
            len(candles),
        )
        await self.repository.upsert_computed_dataset_cache(
            cache_key=cache_key,
            dataset_type="market_bundle",
            instrument_id=normalized_instrument,
            timeframe=cache_timeframe,
            source_data_ts=payload["source_max_ts"],
            source_hash=source_hash,
            payload_json=jsonable_encoder(payload),
            cache_state="fresh" if candles else "missing",
            source_version=CACHE_SOURCE_VERSION,
            calculated_at=datetime.now(timezone.utc),
            expires_at=expires_at_for_dataset("market_bundle"),
            meta_json={
                "requested_limit": limit,
                "limit_bucket": limit_bucket,
                "price_kind": price_kind,
                "input_fingerprint": source_hash,
                "params_version": "market_bundle:v1",
                "algo_version": "market_bundle:v1",
            },
        )
        return payload

    def _build_payload(
        self,
        instrument_id: str,
        provider_timeframe: str,
        cache_timeframe: str,
        ui_timeframe: str,
        requested_limit: int,
        limit_bucket: int,
        candles: list,
    ) -> dict:
        source_max_ts = candles[-1].ts_open if candles else None
        actual_count = len(candles)
        requested_gap = (
            0.0
            if actual_count >= requested_limit
            else max(0.0, 1 - (actual_count / max(requested_limit, 1)))
        )
        bucket_gap = (
            0.0
            if actual_count >= limit_bucket
            else max(0.0, 1 - (actual_count / max(limit_bucket, 1)))
        )
        coverage = {
            "requested_limit": requested_limit,
            "bucket_limit": limit_bucket,
            "actual_count": actual_count,
            "requested_complete": actual_count >= requested_limit,
            "bucket_complete": actual_count >= limit_bucket,
            "gap_ratio_requested": round(requested_gap, 4),
            "gap_ratio_bucket": round(bucket_gap, 4),
        }
        warnings = []
        if not candles:
            warnings.append("缺少可用 K 线。")
        elif not coverage["requested_complete"]:
            warnings.append("K 线数量不足，当前只使用可用样本进行降级分析。")
        candle_payload = [
            CandleRead.model_validate(item).model_dump(mode="json")
            for item in candles[-requested_limit:]
        ]
        return {
            "instrument_id": instrument_id,
            "timeframe": provider_timeframe,
            "cache_timeframe": cache_timeframe,
            "ui_timeframe": ui_timeframe,
            "requested_limit": requested_limit,
            "limit_bucket": limit_bucket,
            "source_max_ts": source_max_ts,
            "generated_at": datetime.now(timezone.utc),
            "cache_state": "fresh" if candles else "missing",
            "candles": candle_payload,
            "coverage": coverage,
            "warnings": warnings,
        }

    @staticmethod
    def _fingerprint(
        instrument_id: str,
        timeframe: str,
        limit_bucket: int,
        source_max_ts: datetime | None,
        count: int,
    ) -> str:
        payload = {
            "dataset_type": "market_bundle",
            "instrument_id": instrument_id,
            "normalized_timeframe": timeframe,
            "source_max_ts": source_max_ts.isoformat() if source_max_ts else None,
            "limit_bucket": limit_bucket,
            "count": count,
            "source_version": CACHE_SOURCE_VERSION,
        }
        return hashlib.sha1(json.dumps(payload, sort_keys=True).encode("utf-8")).hexdigest()
