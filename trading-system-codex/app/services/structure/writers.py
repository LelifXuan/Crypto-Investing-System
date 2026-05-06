from __future__ import annotations

from datetime import datetime

from app.db.models.market import (
    StructureActiveItem,
    StructureSnapshot,
    StructureSystemJudgement,
    StructureSystemScore,
)

from .common import STRUCTURE_DETECTOR_VERSION, FusionResult, ScoreBundle, to_decimal


def build_snapshot_model(
    *,
    instrument_id: str,
    timeframe: str,
    snapshot_version: str,
    generated_at: datetime,
    fusion: FusionResult,
    active_items: list[StructureActiveItem],
    diagnostics: dict,
) -> StructureSnapshot:
    return StructureSnapshot(
        instrument_id=instrument_id,
        timeframe=timeframe,
        snapshot_version=snapshot_version,
        detector_version=STRUCTURE_DETECTOR_VERSION,
        is_latest=True,
        overall_bias=fusion.overall_bias,
        score=to_decimal(fusion.overall_score),
        confidence=to_decimal(fusion.overall_confidence),
        regime=fusion.regime,
        weight_template=fusion.weight_template,
        weight_swing=to_decimal(fusion.weights["swing"]),
        weight_classic=to_decimal(fusion.weights["classic"]),
        weight_profile=to_decimal(fusion.weights["profile"]),
        swing_effective_score=to_decimal(
            fusion.contribution_breakdown.get("swing", 0.0) / max(fusion.weights["swing"], 0.0001)
        ),
        classic_effective_score=to_decimal(
            fusion.contribution_breakdown.get("classic", 0.0)
            / max(fusion.weights["classic"], 0.0001)
        ),
        profile_effective_score=to_decimal(
            fusion.contribution_breakdown.get("profile", 0.0)
            / max(fusion.weights["profile"], 0.0001)
        ),
        overall_score=to_decimal(fusion.overall_score),
        overall_confidence=to_decimal(fusion.overall_confidence),
        conflict_state=fusion.conflict_state,
        primary_drivers_json=fusion.primary_drivers,
        opposing_factors_json=fusion.opposing_factors,
        top_reasons_json=fusion.top_reasons,
        contribution_json={
            key: round(value, 4) for key, value in fusion.contribution_breakdown.items()
        },
        active_structure_ids_json=[item.structure_id for item in active_items],
        diagnostics_json=diagnostics,
        generated_at=generated_at,
    )


def build_legacy_judgements(
    instrument_id: str,
    timeframe: str,
    snapshot_version: str,
    generated_at: datetime,
    bundles: dict[str, ScoreBundle],
) -> list[StructureSystemJudgement]:
    return [
        StructureSystemJudgement(
            instrument_id=instrument_id,
            timeframe=timeframe,
            snapshot_version=snapshot_version,
            system=bundle.system,
            bias=bundle.direction,
            score=to_decimal(bundle.effective_score),
            confidence=to_decimal(bundle.confidence),
            status="confirmed",
            drivers_json=bundle.top_reasons,
            opposing_factors_json=bundle.conflict_flags,
            active_structures_json=[],
            generated_at=generated_at,
        )
        for bundle in bundles.values()
    ]


def build_system_scores(
    instrument_id: str,
    timeframe: str,
    snapshot_version: str,
    generated_at: datetime,
    bundles: dict[str, ScoreBundle],
    fusion: FusionResult,
) -> list[StructureSystemScore]:
    return [
        StructureSystemScore(
            instrument_id=instrument_id,
            timeframe=timeframe,
            snapshot_version=snapshot_version,
            system=bundle.system,
            as_of_ts=generated_at,
            direction=bundle.direction,
            direction_score=to_decimal(bundle.direction_score),
            confidence=to_decimal(bundle.confidence),
            quality=to_decimal(bundle.quality),
            freshness=to_decimal(bundle.freshness),
            evidence_count=bundle.evidence_count,
            effective_score=to_decimal(bundle.effective_score),
            weight=to_decimal(fusion.weights[bundle.system]),
            weighted_contribution=to_decimal(fusion.contribution_breakdown[bundle.system]),
            top_reasons_json=bundle.top_reasons,
            conflict_flags_json=bundle.conflict_flags,
            metadata_json=bundle.metadata,
            generated_at=generated_at,
        )
        for bundle in bundles.values()
    ]
