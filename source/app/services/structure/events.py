from __future__ import annotations

from datetime import datetime, timezone
from uuid import uuid4

from .common import (
    FusionResult,
    StructureAlert,
    StructureEvent,
    build_structure_dedupe_key,
    event_name,
    to_decimal,
)

UTC = timezone.utc


def build_fused_events(
    instrument_id: str,
    timeframe: str,
    fusion: FusionResult,
    generated_at: datetime,
) -> list[StructureEvent]:
    """Build a single fused-structure event for the given fusion result.

    Returns the in-memory dataclass `StructureEvent` from `.common` — not
    the legacy SQLAlchemy ORM class. Active persistence flows through
    `StructureSnapshotService.persist_bundle_cache`, which writes the
    serialized bundle to `page_snapshot_cache`.
    """
    key = {
        "bullish": "bullish_alignment",
        "weak_bullish": "bullish_alignment",
        "bearish": "bearish_alignment",
        "weak_bearish": "bearish_alignment",
        "uncertain": "conflict_state",
        "neutral": "no_clear_structure",
        "no_clear_structure": "no_clear_structure",
    }.get(fusion.overall_bias, "no_clear_structure")
    detected_at = datetime.now(timezone.utc)
    return [
        StructureEvent(
            event_id=f"evt:{uuid4().hex}",
            instrument_id=instrument_id,
            timeframe=timeframe,
            system="fused",
            event_name=event_name("fused", key, "confirmed"),
            structure_id=None,
            bias=fusion.overall_bias,
            status="confirmed",
            confidence=to_decimal(fusion.overall_confidence),
            anchor_bar_ts=generated_at,
            confirmation_bar_ts=generated_at,
            event_ts=generated_at,
            detection_ts=detected_at,
            dedupe_key=build_structure_dedupe_key(
                "fused",
                instrument_id,
                timeframe,
                key,
                fusion.overall_bias,
                fusion.conflict_type,
            ),
            payload_json={
                "overall_score": fusion.overall_score,
                "regime": fusion.regime,
            },
        )
    ]


# NOTE: `build_fused_alerts` was deleted (commit cbd8384 follow-up).
# It produced the legacy SQLAlchemy `StructureAlert` ORM, which has no
# callers in app/ or tests/. The dataclass `StructureAlert` in
# `.common` is still available for anyone who needs to build an alert
# in-memory.
__all__ = ["build_fused_events"]
