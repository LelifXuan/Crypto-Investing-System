from __future__ import annotations

from dataclasses import replace
from datetime import UTC, datetime

from app.cache.shared_query_cache import shared_query_cache
from app.core.timeframes import normalize_timeframe_for_cache
from app.repositories.market_repository import MarketRepository
from app.schemas.market import CandleRead
from app.schemas.structure import (
    StructureAlertRead,
    StructureDiagnosticsRead,
    StructureEventRead,
    StructureRefreshResponse,
    StructureTabBundleRead,
    StructureTabSnapshotRead,
)
from app.services.data_quality import DataQualityMonitor
from app.services.market_data_bundle import MarketDataBundleService
from app.services.page_snapshot_cache import (
    CACHE_SOURCE_VERSION,
    expires_at_for_page,
    structure_bundle_cache_key,
)
from app.services.page_snapshot_cache import (
    bundle_status_message as page_cache_status_message,
)

from .classic import ClassicScorer
from .common import LOOKBACK_BY_TIMEFRAME, ScoringConfig, clamp
from .diagnostics import build_diagnostics_payload, bundle_status_message, empty_diagnostics
from .events import build_fused_alerts, build_fused_events
from .fusion import StructureFusionEngine
from .pivots import detect_pivots
from .profile import ProfileScorer
from .readers import read_snapshot
from .swing import SwingScorer
from .writers import build_legacy_judgements, build_snapshot_model, build_system_scores


class StructureSnapshotService:
    def __init__(self, repository: MarketRepository) -> None:
        self.repository = repository
        self.config = ScoringConfig()
        self.data_quality = DataQualityMonitor()
        self.swing = SwingScorer(self.config)
        self.classic = ClassicScorer()
        self.profile = ProfileScorer()
        self.fusion = StructureFusionEngine(self.config)

    async def get_snapshot(
        self,
        instrument_id: str,
        timeframe: str,
        *,
        include_geometry: bool = True,
        include_diagnostics: bool = False,
    ) -> StructureTabSnapshotRead:
        snapshot = await self.repository.get_latest_structure_snapshot(instrument_id, timeframe)
        if snapshot is None:
            raise ValueError("structure snapshot missing")
        return await read_snapshot(
            self.repository,
            snapshot,
            include_geometry=include_geometry,
            include_diagnostics=include_diagnostics,
        )

    async def get_bundle(
        self,
        instrument_id: str,
        timeframe: str,
        *,
        include_geometry: bool = True,
        candles_limit: int | None = None,
    ) -> StructureTabBundleRead:
        cache = await self.repository.get_page_snapshot_cache(
            structure_bundle_cache_key(
                instrument_id,
                timeframe,
                include_geometry,
                candles_limit or LOOKBACK_BY_TIMEFRAME.get(timeframe, 220),
            )
        )
        if cache is not None and cache.payload_json:
            payload = cache.payload_json
            cache_state = cache.cache_state or cache.status
            return StructureTabBundleRead.model_validate(
                {
                    "snapshot": payload.get("snapshot"),
                    "candles": payload.get("candles", []),
                    "events": payload.get("events", []),
                    "alerts": payload.get("alerts", []),
                    "diagnostics": payload.get("diagnostics"),
                    "cache_state": cache_state,
                    "is_stale": cache_state == "stale",
                    "status_message": cache.last_error or page_cache_status_message(cache_state),
                }
            )
        return await self._compose_bundle(
            instrument_id,
            timeframe,
            include_geometry=include_geometry,
            candles_limit=candles_limit,
        )

    async def refresh_response(
        self, instrument_id: str, timeframe: str
    ) -> StructureRefreshResponse:
        snapshot = await self.refresh_snapshot(
            instrument_id, timeframe, include_geometry=True, include_diagnostics=True
        )
        return StructureRefreshResponse(
            instrument_id=instrument_id,
            timeframe=timeframe,
            snapshot_version=snapshot.snapshot_version,
            generated_at=snapshot.generated_at,
            refreshed=True,
            systems=[item.system for item in snapshot.systems],
        )

    async def refresh_snapshot(
        self,
        instrument_id: str,
        timeframe: str,
        *,
        include_geometry: bool = True,
        include_diagnostics: bool = False,
    ) -> StructureTabSnapshotRead:
        await shared_query_cache.invalidate_prefix(f"candles:{instrument_id}:{timeframe}:")
        market_bundle_service = MarketDataBundleService(self.repository)
        try:
            market_bundle = await market_bundle_service.get_bundle(
                instrument_id=instrument_id,
                timeframe=timeframe,
                limit=LOOKBACK_BY_TIMEFRAME.get(timeframe, 220),
                allow_stale=False,
                refresh=True,
            )
        except Exception:
            market_bundle = await market_bundle_service.get_bundle(
                instrument_id=instrument_id,
                timeframe=timeframe,
                limit=LOOKBACK_BY_TIMEFRAME.get(timeframe, 220),
                allow_stale=True,
                refresh=False,
            )
        candles = [
            item
            if isinstance(item, CandleRead)
            else CandleRead.model_validate(item)
            for item in market_bundle.get("candles", [])
        ]
        generated_at = candles[-1].ts_open if candles else datetime.now(UTC)
        pivots = detect_pivots(candles)
        swing = self.swing.detect(instrument_id, timeframe, candles)
        classic = self.classic.detect(instrument_id, timeframe, candles, pivots)
        profile = self.profile.detect(instrument_id, timeframe, candles)
        bundles = {"swing": swing.score, "classic": classic.score, "profile": profile.score}
        fusion = self.fusion.fuse(timeframe, bundles)
        quality = self.data_quality.assess_candles(
            candles,
            expected_min_points=max(40, LOOKBACK_BY_TIMEFRAME.get(timeframe, 220) // 3),
        )
        if quality.data_quality_score < 100:
            risk_parts = [fusion.risk] if fusion.risk else []
            if quality.issues:
                risk_parts.append(f"数据质量状态：{quality.status}（{', '.join(quality.issues)}）")
            fusion = replace(
                fusion,
                overall_confidence=clamp(
                    fusion.overall_confidence * (quality.data_quality_score / 100.0), 0.0, 1.0
                ),
                risk="；".join(part for part in risk_parts if part) or None,
                suggested_action=(
                    "数据质量较弱，优先观望或仅保留轻仓确认单。"
                    if not quality.can_alert
                    else fusion.suggested_action
                ),
            )
        snapshot_version = f"{timeframe}-{int(generated_at.timestamp())}"
        active_items = swing.active_items + classic.active_items + profile.active_items
        geometry = swing.geometry + classic.geometry + profile.geometry
        events = (
            swing.events
            + classic.events
            + profile.events
            + build_fused_events(instrument_id, timeframe, fusion, generated_at)
        )
        alerts = classic.alerts + build_fused_alerts(
            instrument_id, timeframe, snapshot_version, fusion, generated_at
        )
        for item in active_items:
            item.snapshot_version = snapshot_version
        for item in geometry:
            item.snapshot_version = snapshot_version
        judgements = build_legacy_judgements(
            instrument_id, timeframe, snapshot_version, generated_at, bundles
        )
        scores = build_system_scores(
            instrument_id, timeframe, snapshot_version, generated_at, bundles, fusion
        )
        snapshot_model = build_snapshot_model(
            instrument_id=instrument_id,
            timeframe=timeframe,
            snapshot_version=snapshot_version,
            generated_at=generated_at,
            fusion=fusion,
            active_items=active_items,
            diagnostics=build_diagnostics_payload(
                candles, geometry, events, alerts, generated_at, fusion, quality
            ),
        )
        await self.repository.replace_structure_snapshot_bundle(
            snapshot_model, judgements, scores, active_items, geometry, events, alerts
        )
        await self.persist_bundle_cache(
            instrument_id,
            timeframe,
            include_geometry=include_geometry,
            candles_limit=LOOKBACK_BY_TIMEFRAME.get(timeframe, 220),
        )
        return await read_snapshot(
            self.repository,
            snapshot_model,
            include_geometry=include_geometry,
            include_diagnostics=include_diagnostics,
        )

    async def list_events(
        self, instrument_id: str, timeframe: str, *, limit: int = 80
    ) -> list[StructureEventRead]:
        items = await self.repository.list_structure_events(instrument_id, timeframe, limit=limit)
        return [StructureEventRead.model_validate(item) for item in items]

    async def list_alerts(
        self, instrument_id: str, timeframe: str, *, limit: int = 80
    ) -> list[StructureAlertRead]:
        items = await self.repository.list_structure_alerts(instrument_id, timeframe, limit=limit)
        return [StructureAlertRead.model_validate(item) for item in items]

    async def get_diagnostics(self, instrument_id: str, timeframe: str) -> StructureDiagnosticsRead:
        snapshot_row = await self.repository.get_latest_structure_snapshot(instrument_id, timeframe)
        if snapshot_row is not None:
            snapshot = await read_snapshot(
                self.repository, snapshot_row, include_geometry=False, include_diagnostics=True
            )
            if snapshot.diagnostics is not None:
                return snapshot.diagnostics
        return empty_diagnostics()

    async def persist_bundle_cache(
        self,
        instrument_id: str,
        timeframe: str,
        *,
        include_geometry: bool = True,
        candles_limit: int | None = None,
    ) -> StructureTabBundleRead:
        bundle = await self._compose_bundle(
            instrument_id,
            timeframe,
            include_geometry=include_geometry,
            candles_limit=candles_limit,
        )
        now = datetime.now(UTC)
        payload = bundle.model_dump(mode="json")
        await self.repository.upsert_page_snapshot_cache(
            cache_key=structure_bundle_cache_key(
                instrument_id,
                timeframe,
                include_geometry,
                candles_limit or LOOKBACK_BY_TIMEFRAME.get(timeframe, 220),
            ),
            page_type="structure",
            instrument_id=instrument_id,
            timeframe=timeframe,
            payload_json=payload,
            status=bundle.cache_state,
            cache_state="fresh" if bundle.cache_state == "ready" else bundle.cache_state,
            snapshot_at=now,
            data_ts=bundle.snapshot.generated_at if bundle.snapshot else None,
            expires_at=expires_at_for_page("structure", now),
            source_updated_at=bundle.snapshot.generated_at if bundle.snapshot else None,
            source_version=CACHE_SOURCE_VERSION,
            last_error=None,
            meta_json={
                "include_geometry": include_geometry,
                "candles_limit": candles_limit or LOOKBACK_BY_TIMEFRAME.get(timeframe, 220),
            },
        )
        return bundle

    async def _compose_bundle(
        self,
        instrument_id: str,
        timeframe: str,
        *,
        include_geometry: bool = True,
        candles_limit: int | None = None,
    ) -> StructureTabBundleRead:
        snapshot_row = await self.repository.get_latest_structure_snapshot(instrument_id, timeframe)
        snapshot = (
            await read_snapshot(
                self.repository,
                snapshot_row,
                include_geometry=include_geometry,
                include_diagnostics=True,
            )
            if snapshot_row is not None
            else None
        )
        candles = await self.repository.list_candles(
            instrument_id,
            normalize_timeframe_for_cache(timeframe),
            limit=candles_limit or LOOKBACK_BY_TIMEFRAME.get(timeframe, 220),
        )
        events = await self.list_events(instrument_id, timeframe, limit=40)
        alerts = await self.list_alerts(instrument_id, timeframe, limit=40)
        diagnostics = (
            snapshot.diagnostics
            if snapshot is not None and snapshot.diagnostics is not None
            else await self.get_diagnostics(instrument_id, timeframe)
        )
        latest_candle_ts = candles[-1].ts_open if candles else None
        snapshot_ts = snapshot.generated_at if snapshot is not None else None
        is_stale = bool(snapshot_ts and latest_candle_ts and latest_candle_ts > snapshot_ts)
        cache_state = "missing" if snapshot is None else ("stale" if is_stale else "fresh")
        return StructureTabBundleRead(
            snapshot=snapshot,
            candles=candles,
            events=events,
            alerts=alerts,
            diagnostics=diagnostics,
            cache_state=cache_state,
            is_stale=is_stale,
            status_message=bundle_status_message(cache_state),
        )
