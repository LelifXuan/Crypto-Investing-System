from __future__ import annotations

from datetime import datetime, timezone

from app.core.timeframes import normalize_timeframe_for_cache
from app.repositories.market_repository import MarketRepository
from app.schemas.market import CandleRead
from app.schemas.structure import (
    StructureActiveItemRead,
    StructureAlertRead,
    StructureDiagnosticsRead,
    StructureEventRead,
    StructureGeometryRead,
    StructureOverallJudgementRead,
    StructureRefreshResponse,
    StructureSystemJudgementRead,
    StructureTabBundleRead,
    StructureTabSnapshotRead,
)
from app.services.cache_registry import (
    CACHE_SOURCE_VERSION,
    cache_status,
    expires_at_for_page,
    structure_bundle_cache_key,
)
from app.services.market_data_bundle import MarketDataBundleService

from .classic import ClassicScorer
from .common import LOOKBACK_BY_TIMEFRAME, STRUCTURE_DETECTOR_VERSION, ScoringConfig
from .diagnostics import bundle_status_message, empty_diagnostics
from .fusion import StructureFusionEngine
from .pivots import detect_pivots, detect_pivots_adaptive
from .profile import ProfileScorer
from .swing import SwingScorer

UTC = timezone.utc


class StructureSnapshotService:
    def __init__(self, repository: MarketRepository) -> None:
        self.repository = repository
        self.market_data = MarketDataBundleService(repository)

    async def get_snapshot(
        self,
        instrument_id: str,
        timeframe: str,
        *,
        include_geometry: bool = True,
        include_diagnostics: bool = False,
    ) -> StructureTabSnapshotRead:
        del include_geometry, include_diagnostics
        bundle = await self.get_bundle(instrument_id, timeframe)
        if bundle.snapshot is None:
            raise ValueError("structure snapshot missing")
        return bundle.snapshot

    async def get_bundle(
        self,
        instrument_id: str,
        timeframe: str,
        *,
        include_geometry: bool = True,
        candles_limit: int | None = None,
    ) -> StructureTabBundleRead:
        normalized = normalize_timeframe_for_cache(timeframe)
        candles = await self._load_candles(instrument_id, normalized, candles_limit)
        cache = await self._get_cached_bundle(
            instrument_id,
            normalized,
            include_geometry=include_geometry,
            candles_limit=candles_limit,
        )
        if not candles:
            if cache is not None:
                return self._bundle_from_cache(cache, candles=[])
            return StructureTabBundleRead(
                snapshot=None,
                candles=[],
                events=[],
                alerts=[],
                diagnostics=empty_diagnostics(),
                cache_state="missing",
                is_stale=False,
                status_message=bundle_status_message("missing"),
            )
        if cache is None:
            return StructureTabBundleRead(
                snapshot=None,
                candles=candles,
                events=[],
                alerts=[],
                diagnostics=empty_diagnostics(),
                cache_state="missing",
                is_stale=False,
                status_message=bundle_status_message("missing"),
            )

        bundle = self._bundle_from_cache(cache, candles=candles)
        latest_candle_ts = candles[-1].ts_open if candles else None
        generated_at = bundle.snapshot.generated_at if bundle.snapshot else None
        if latest_candle_ts and generated_at and latest_candle_ts > generated_at:
            bundle.cache_state = "stale"
            bundle.is_stale = True
            bundle.status_message = bundle_status_message("stale")
        return bundle

    async def refresh_response(
        self,
        instrument_id: str,
        timeframe: str,
    ) -> StructureRefreshResponse:
        snapshot = await self.refresh_snapshot(instrument_id, timeframe)
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
        del include_diagnostics
        normalized = normalize_timeframe_for_cache(timeframe)
        candles = await self._load_candles(instrument_id, normalized, None)
        if not candles:
            raise ValueError("structure snapshot missing")
        bundle = self._build_bundle_from_candles(
            instrument_id,
            normalized,
            candles,
            cache_state="fresh",
            include_geometry=include_geometry,
        )
        await self._persist_bundle(
            instrument_id,
            normalized,
            bundle,
            include_geometry=include_geometry,
            candles_limit=None,
        )
        return bundle.snapshot

    async def list_events(self, instrument_id: str, timeframe: str, *, limit: int = 80) -> list:
        try:
            bundle = await self.get_bundle(instrument_id, timeframe)
            events = bundle.events or []
            return events[:limit]
        except Exception:
            return list()

    async def list_alerts(self, instrument_id: str, timeframe: str, *, limit: int = 80) -> list:
        try:
            bundle = await self.get_bundle(instrument_id, timeframe)
            alerts = bundle.alerts or []
            return alerts[:limit]
        except Exception:
            return list()

    async def get_diagnostics(self, instrument_id: str, timeframe: str) -> StructureDiagnosticsRead:
        del instrument_id, timeframe
        return empty_diagnostics()

    async def persist_bundle_cache(
        self,
        instrument_id: str,
        timeframe: str,
        *,
        include_geometry: bool = True,
        candles_limit: int | None = None,
    ) -> StructureTabBundleRead:
        normalized = normalize_timeframe_for_cache(timeframe)
        candles = await self._load_candles(instrument_id, normalized, candles_limit)
        if not candles:
            return await self.get_bundle(
                instrument_id,
                normalized,
                include_geometry=include_geometry,
                candles_limit=candles_limit,
            )
        bundle = self._build_bundle_from_candles(
            instrument_id,
            normalized,
            candles,
            cache_state="fresh",
            include_geometry=include_geometry,
        )
        await self._persist_bundle(
            instrument_id,
            normalized,
            bundle,
            include_geometry=include_geometry,
            candles_limit=candles_limit,
        )
        return bundle

    async def _get_cached_bundle(
        self,
        instrument_id: str,
        timeframe: str,
        *,
        include_geometry: bool,
        candles_limit: int | None,
    ):
        requested_limit = candles_limit or LOOKBACK_BY_TIMEFRAME.get(timeframe, 180)
        cache_keys = [
            structure_bundle_cache_key(
                instrument_id,
                timeframe,
                include_geometry,
                requested_limit,
            )
        ]
        default_limit = LOOKBACK_BY_TIMEFRAME.get(timeframe, 180)
        fallback_key = structure_bundle_cache_key(
            instrument_id,
            timeframe,
            include_geometry,
            default_limit,
        )
        if fallback_key not in cache_keys:
            cache_keys.append(fallback_key)
        for cache_key in cache_keys:
            cache = await self.repository.get_page_snapshot_cache(cache_key)
            if cache is not None:
                return cache
        return None

    def _bundle_from_cache(self, cache, *, candles: list[CandleRead]) -> StructureTabBundleRead:
        payload = dict(cache.payload_json or {})
        if candles:
            payload["candles"] = candles
        bundle = StructureTabBundleRead.model_validate(payload)
        state = cache_status(cache)
        bundle.cache_state = state
        bundle.is_stale = state == "stale"
        bundle.status_message = bundle_status_message(state)
        return bundle

    def _build_bundle_from_candles(
        self,
        instrument_id: str,
        timeframe: str,
        candles: list[CandleRead],
        *,
        cache_state: str,
        include_geometry: bool,
    ) -> StructureTabBundleRead:
        del include_geometry
        snapshot, events, alerts = self._build_snapshot(instrument_id, timeframe, candles)
        return StructureTabBundleRead(
            snapshot=snapshot,
            candles=candles,
            events=events,
            alerts=alerts,
            diagnostics=snapshot.diagnostics,
            cache_state=cache_state,
            is_stale=cache_state == "stale",
            status_message=bundle_status_message(cache_state),
        )

    async def _persist_bundle(
        self,
        instrument_id: str,
        timeframe: str,
        bundle: StructureTabBundleRead,
        *,
        include_geometry: bool,
        candles_limit: int | None,
    ) -> None:
        snapshot_at = bundle.snapshot.generated_at if bundle.snapshot else datetime.now(UTC)
        data_ts = bundle.candles[-1].ts_open if bundle.candles else snapshot_at
        requested_limit = candles_limit or LOOKBACK_BY_TIMEFRAME.get(timeframe, 180)
        cache_keys = {
            structure_bundle_cache_key(
                instrument_id,
                timeframe,
                include_geometry,
                requested_limit,
            ),
            structure_bundle_cache_key(
                instrument_id,
                timeframe,
                include_geometry,
                LOOKBACK_BY_TIMEFRAME.get(timeframe, 180),
            ),
        }
        payload = bundle.model_dump(mode="json")
        for cache_key in cache_keys:
            await self.repository.upsert_page_snapshot_cache(
                cache_key=cache_key,
                page_type="structure",
                payload_json=payload,
                status="ready",
                cache_state="fresh",
                instrument_id=instrument_id,
                timeframe=timeframe,
                snapshot_at=snapshot_at,
                data_ts=data_ts,
                expires_at=expires_at_for_page("structure", snapshot_at),
                source_updated_at=data_ts,
                source_version=CACHE_SOURCE_VERSION,
                meta_json={"include_geometry": include_geometry},
            )

    async def _load_candles(
        self,
        instrument_id: str,
        timeframe: str,
        limit: int | None,
    ) -> list[CandleRead]:
        fetch_limit = limit or LOOKBACK_BY_TIMEFRAME.get(timeframe, 180)
        try:
            bundle = await self.market_data.get_bundle(
                instrument_id=instrument_id,
                timeframe=timeframe,
                limit=fetch_limit,
                allow_stale=True,
                refresh=False,
            )
            data = getattr(bundle, "data", None)
            raw_candles = (
                data.get("candles", [])
                if isinstance(data, dict)
                else bundle.get("candles", [])
            )
        except Exception:
            raw_candles = await self.repository.list_candles(
                instrument_id,
                timeframe,
                limit=fetch_limit,
            )
        candles: list[CandleRead] = []
        for item in raw_candles or []:
            candles.append(
                item if isinstance(item, CandleRead) else CandleRead.model_validate(item)
            )
        return candles

    def _build_snapshot(
        self,
        instrument_id: str,
        timeframe: str,
        candles: list[CandleRead],
    ) -> StructureTabSnapshotRead:
        generated_at = candles[-1].ts_open if candles else datetime.now(timezone.utc)
        snapshot_version = f"{timeframe}-{int(generated_at.timestamp())}"

        config = ScoringConfig()
        if len(candles) >= 40:
            try:
                pivots = detect_pivots_adaptive(candles, timeframe=timeframe)
            except Exception:
                pivots = detect_pivots(candles)
        else:
            pivots = []

        swing_bundle = SwingScorer(config).detect(instrument_id, timeframe, candles)
        classic_bundle = ClassicScorer().detect(instrument_id, timeframe, candles, pivots)
        profile_bundle = ProfileScorer().detect(instrument_id, timeframe, candles)

        score_bundles = {
            "swing": swing_bundle.score,
            "classic": classic_bundle.score,
            "profile": profile_bundle.score,
        }
        fusion = StructureFusionEngine(config).fuse(timeframe, score_bundles)

        overall = StructureOverallJudgementRead(
            overall_bias=fusion.overall_bias,
            score=round(fusion.overall_score, 2),
            confidence=round(fusion.overall_confidence, 2),
            overall_score=round(fusion.overall_score, 2),
            overall_confidence=round(fusion.overall_confidence, 2),
            regime=fusion.regime or "trend",
            weight_template=fusion.weight_template or "stable",
            weights=fusion.weights or {"swing": 0.4, "classic": 0.2, "profile": 0.4},
            conflict_state=fusion.conflict_state,
            conflict_type=fusion.conflict_type,
            dominant_side=fusion.dominant_side,
            opposing_side=fusion.opposing_side,
            meaning=fusion.meaning or "结构快照基于多系统融合分析生成。",
            risk=fusion.risk,
            mode=fusion.suggested_mode or "observe",
            need_confirmation=fusion.need_confirmation,
            invalidation=fusion.invalidation,
            suggested_mode=fusion.suggested_mode or "观察优先",
            suggested_action=fusion.suggested_action or "等待确认",
            contribution_breakdown=fusion.contribution_breakdown or {
                "swing": 0.0, "classic": 0.0, "profile": 0.0,
            },
            primary_drivers=fusion.primary_drivers or [],
            opposing_factors=fusion.opposing_factors or [],
            last_updated_at=generated_at,
            detection_latency_ms=0,
            timeframe=timeframe,
        )

        systems = []
        for sys_key in ("swing", "classic", "profile"):
            bundle = score_bundles[sys_key]
            systems.append(
                StructureSystemJudgementRead(
                    system=sys_key,
                    bias=bundle.direction,
                    score=round(bundle.direction_score, 2),
                    confidence=round(bundle.confidence, 2),
                    direction=bundle.direction,
                    direction_score=round(bundle.direction_score, 2),
                    quality=round(bundle.quality, 2),
                    freshness=round(bundle.freshness, 2),
                    effective_score=round(bundle.effective_score, 2),
                    evidence_count=bundle.evidence_count,
                    weight=fusion.weights.get(sys_key, 0.33),
                    weighted_contribution=round(
                        bundle.effective_score * fusion.weights.get(sys_key, 0.33), 2
                    ),
                    top_reasons=bundle.top_reasons or [],
                    conflict_flags=bundle.conflict_flags or [],
                    metadata=bundle.metadata or {},
                    status="confirmed",
                    drivers_json=bundle.top_reasons or [],
                    opposing_factors_json=bundle.conflict_flags or [],
                    active_structures_json=[
                        f"{item.structure_type}:{item.display_name}({item.directional_bias})"
                        for item in swing_bundle.active_items
                        if item.system == sys_key
                    ]
                    + [
                        f"{item.structure_type}:{item.display_name}({item.directional_bias})"
                        for item in classic_bundle.active_items
                        if item.system == sys_key
                    ]
                    + [
                        f"{item.structure_type}:{item.display_name}({item.directional_bias})"
                        for item in profile_bundle.active_items
                        if item.system == sys_key
                    ],
                    generated_at=generated_at,
                )
            )

        geometry = swing_bundle.geometry + classic_bundle.geometry + profile_bundle.geometry
        active_items = (
            swing_bundle.active_items
            + classic_bundle.active_items
            + profile_bundle.active_items
        )
        events = swing_bundle.events + classic_bundle.events + profile_bundle.events
        alerts = swing_bundle.alerts + classic_bundle.alerts + profile_bundle.alerts

        active_items_read = [
            StructureActiveItemRead.model_validate(item, from_attributes=True)
            for item in active_items
        ]
        geometry_read = [
            StructureGeometryRead.model_validate(item, from_attributes=True)
            for item in geometry
        ]
        events_read = [
            StructureEventRead.model_validate(item, from_attributes=True)
            for item in events
        ]
        alerts_read = [
            StructureAlertRead.model_validate(item, from_attributes=True)
            for item in alerts
        ]
        if not events_read and active_items_read:
            events_read = self._derive_events_from_active_items(
                active_items_read,
                snapshot_version=snapshot_version,
                generated_at=generated_at,
            )
        if not alerts_read and active_items_read:
            alerts_read = self._derive_alerts_from_active_items(
                active_items_read,
                snapshot_version=snapshot_version,
                generated_at=generated_at,
            )

        diagnostics = StructureDiagnosticsRead(
            detector_version=STRUCTURE_DETECTOR_VERSION,
            compute_mode="snapshot",
            candles_loaded=len(candles),
            profile_precision="ohlcv_approx",
            geometry_count=len(geometry),
            event_count=len(events_read),
            alert_count=len(alerts_read),
            latest_event_name=events_read[-1].event_name if events_read else None,
            generated_at=generated_at,
            notes=["结构页使用多系统融合检测引擎。"],
        )
        return StructureTabSnapshotRead(
            instrument_id=instrument_id,
            timeframe=timeframe,
            snapshot_version=snapshot_version,
            detector_version=STRUCTURE_DETECTOR_VERSION,
            generated_at=generated_at,
            overall=overall,
            systems=systems,
            active_items=active_items_read,
            geometry=geometry_read,
            diagnostics=diagnostics,
        ), events_read, alerts_read

    @staticmethod
    def _derive_events_from_active_items(
        active_items: list[StructureActiveItemRead],
        *,
        snapshot_version: str,
        generated_at: datetime,
    ) -> list[StructureEventRead]:
        items: list[StructureEventRead] = []
        for item in active_items[:8]:
            event_id = f"derived-{snapshot_version}-{item.structure_id}"
            items.append(
                StructureEventRead(
                    event_id=event_id,
                    system=item.system,
                    event_name=f"market.structure.{item.structure_type}",
                    structure_id=item.structure_id,
                    bias=item.directional_bias,
                    status=item.lifecycle_status,
                    confidence=float(item.confidence),
                    anchor_bar_ts=item.event_ts,
                    confirmation_bar_ts=item.confirmation_ts,
                    event_ts=item.event_ts or generated_at,
                    detection_ts=generated_at,
                    payload_json={
                        "derived": True,
                        "display_name": item.display_name,
                        "summary": item.summary,
                    },
                )
            )
        return items

    @staticmethod
    def _derive_alerts_from_active_items(
        active_items: list[StructureActiveItemRead],
        *,
        snapshot_version: str,
        generated_at: datetime,
    ) -> list[StructureAlertRead]:
        items: list[StructureAlertRead] = []
        for item in active_items[:4]:
            severity = "medium" if item.lifecycle_status == "confirmed" else "low"
            items.append(
                StructureAlertRead(
                    alert_id=f"derived-alert-{snapshot_version}-{item.structure_id}",
                    rule_key="structure.active_item",
                    alert_name="结构候选",
                    severity=severity,
                    status="open",
                    title=f"{item.display_name} · {item.directional_bias}",
                    message=item.summary or "结构模块识别到新的候选形态，请结合成交量与突破确认。",
                    triggered_at=item.event_ts or generated_at,
                    resolved_at=None,
                    event_payload_json={
                        "derived": True,
                        "structure_id": item.structure_id,
                        "structure_type": item.structure_type,
                    },
                )
            )
        return items
