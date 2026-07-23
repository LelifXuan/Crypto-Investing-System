from __future__ import annotations

from datetime import datetime, timezone
from uuid import uuid4

from app.db.models.market import StructureAlert, StructureEvent

from .common import FusionResult, build_structure_dedupe_key, event_name, to_decimal

UTC = timezone.utc


def build_fused_events(
    instrument_id: str,
    timeframe: str,
    fusion: FusionResult,
    generated_at: datetime,
) -> list[StructureEvent]:
    key = {
        "bullish": "bullish_alignment",
        "weak_bullish": "bullish_alignment",
        "bearish": "bearish_alignment",
        "weak_bearish": "bearish_alignment",
        "uncertain": "conflict_state",
        "neutral": "no_clear_structure",
        "no_clear_structure": "no_clear_structure",
    }.get(fusion.overall_bias, "no_clear_structure")
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
            detection_ts=datetime.now(timezone.utc),
            dedupe_key=build_structure_dedupe_key(
                "fused",
                instrument_id,
                timeframe,
                key,
                fusion.overall_bias,
                fusion.conflict_type,
            ),
            payload_json={"overall_score": fusion.overall_score, "regime": fusion.regime},
        )
    ]


def build_fused_alerts(
    instrument_id: str,
    timeframe: str,
    snapshot_version: str,
    fusion: FusionResult,
    generated_at: datetime,
) -> list[StructureAlert]:
    if fusion.overall_bias in {"bullish", "weak_bullish"}:
        rule_key = "structure_bullish_alignment"
        title = "结构偏多提醒"
        severity = "medium"
    elif fusion.overall_bias in {"bearish", "weak_bearish"}:
        rule_key = "structure_bearish_alignment"
        title = "结构偏空提醒"
        severity = "medium"
    else:
        rule_key = "structure_observation"
        title = "结构观察提醒"
        severity = "low"
    return [
        StructureAlert(
            alert_id=f"alt:{uuid4().hex}",
            instrument_id=instrument_id,
            timeframe=timeframe,
            snapshot_version=snapshot_version,
            event_id=None,
            rule_key=rule_key,
            alert_name=title,
            severity=severity,
            status="open",
            dedupe_key=build_structure_dedupe_key(
                rule_key,
                instrument_id,
                timeframe,
                fusion.overall_bias,
                fusion.regime,
                fusion.conflict_type,
            ),
            title=title,
            message=(
                f"综合结构分 {fusion.overall_score:.2f}，置信度 {fusion.overall_confidence:.2f}。"
            ),
            triggered_at=generated_at,
            resolved_at=None,
            event_payload_json={"regime": fusion.regime, "weights": fusion.weights},
        )
    ]
