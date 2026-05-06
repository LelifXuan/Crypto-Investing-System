from __future__ import annotations

from app.db.models.market import StructureSnapshot, StructureSystemScore
from app.repositories.market_repository import MarketRepository
from app.schemas.structure import (
    StructureActiveItemRead,
    StructureDiagnosticsRead,
    StructureGeometryRead,
    StructureOverallJudgementRead,
    StructureSystemJudgementRead,
    StructureTabSnapshotRead,
)

from .common import STRUCTURE_DETECTOR_VERSION, direction_from_score, to_float


async def read_snapshot(
    repository: MarketRepository,
    snapshot: StructureSnapshot,
    *,
    include_geometry: bool = True,
    include_diagnostics: bool = False,
) -> StructureTabSnapshotRead:
    system_rows = await repository.list_structure_system_scores(
        snapshot.instrument_id, snapshot.timeframe, snapshot.snapshot_version
    )
    active_items = await repository.list_structure_active_items(
        snapshot.instrument_id, snapshot.timeframe, snapshot.snapshot_version, active_only=False
    )
    geometry_rows = (
        await repository.list_structure_geometry(
            snapshot.instrument_id, snapshot.timeframe, snapshot.snapshot_version
        )
        if include_geometry
        else []
    )
    diagnostics = snapshot.diagnostics_json or {}
    overall = StructureOverallJudgementRead(
        overall_bias=snapshot.overall_bias,
        score=to_float(snapshot.score),
        confidence=to_float(snapshot.confidence),
        overall_score=to_float(snapshot.overall_score),
        overall_confidence=to_float(snapshot.overall_confidence),
        regime=snapshot.regime,
        weight_template=snapshot.weight_template,
        weights={
            "swing": to_float(snapshot.weight_swing),
            "classic": to_float(snapshot.weight_classic),
            "profile": to_float(snapshot.weight_profile),
        },
        conflict_state=bool(snapshot.conflict_state),
        conflict_type=diagnostics.get("conflict_type"),
        dominant_side=diagnostics.get("dominant_side"),
        opposing_side=diagnostics.get("opposing_side"),
        meaning=diagnostics.get("meaning"),
        risk=diagnostics.get("risk"),
        mode=diagnostics.get("mode") or diagnostics.get("suggested_mode"),
        need_confirmation=diagnostics.get("need_confirmation"),
        invalidation=diagnostics.get("invalidation"),
        suggested_mode=diagnostics.get("suggested_mode"),
        suggested_action=diagnostics.get("suggested_action"),
        contribution_breakdown=snapshot.contribution_json or {},
        primary_drivers=snapshot.primary_drivers_json or [],
        opposing_factors=snapshot.opposing_factors_json or [],
        last_updated_at=snapshot.generated_at,
        detection_latency_ms=int(diagnostics.get("detection_latency_ms", 0)),
        timeframe=snapshot.timeframe,
    )
    systems = [map_system_score(row) for row in system_rows]
    diagnostics_read = None
    if include_diagnostics:
        diagnostics_read = StructureDiagnosticsRead(
            detector_version=STRUCTURE_DETECTOR_VERSION,
            compute_mode=str(diagnostics.get("compute_mode", "snapshot")),
            candles_loaded=int(diagnostics.get("candles_loaded", 0)),
            profile_precision=str(diagnostics.get("profile_precision", "ohlcv_approx")),
            geometry_count=int(diagnostics.get("geometry_count", len(geometry_rows))),
            event_count=int(diagnostics.get("event_count", 0)),
            alert_count=int(diagnostics.get("alert_count", 0)),
            latest_event_name=diagnostics.get("latest_event_name"),
            generated_at=snapshot.generated_at,
            notes=list(diagnostics.get("notes", [])),
        )
    return StructureTabSnapshotRead(
        instrument_id=snapshot.instrument_id,
        timeframe=snapshot.timeframe,
        snapshot_version=snapshot.snapshot_version,
        detector_version=snapshot.detector_version,
        generated_at=snapshot.generated_at,
        overall=overall,
        systems=systems,
        active_items=[StructureActiveItemRead.model_validate(item) for item in active_items],
        geometry=[StructureGeometryRead.model_validate(item) for item in geometry_rows],
        diagnostics=diagnostics_read,
    )


def map_system_score(row: StructureSystemScore) -> StructureSystemJudgementRead:
    return StructureSystemJudgementRead(
        system=row.system,
        bias=row.direction or direction_from_score(to_float(row.direction_score)),
        score=to_float(row.effective_score),
        confidence=to_float(row.confidence),
        direction=row.direction,
        direction_score=to_float(row.direction_score),
        quality=to_float(row.quality),
        freshness=to_float(row.freshness),
        effective_score=to_float(row.effective_score),
        evidence_count=row.evidence_count,
        weight=to_float(row.weight),
        weighted_contribution=to_float(row.weighted_contribution),
        top_reasons=list(row.top_reasons_json or []),
        conflict_flags=list(row.conflict_flags_json or []),
        metadata=dict(row.metadata_json or {}),
        status="confirmed",
        drivers_json=list(row.top_reasons_json or []),
        opposing_factors_json=list(row.conflict_flags_json or []),
        active_structures_json=[],
        generated_at=row.generated_at,
    )
