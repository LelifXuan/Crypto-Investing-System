from __future__ import annotations

from datetime import UTC, datetime
from uuid import uuid4

from .common import (
    DetectionBundle,
    Pivot,
    ScoreBundle,
    StructureActiveItem,
    StructureAlert,
    StructureEvent,
    StructureGeometry,
    build_structure_dedupe_key,
    build_structure_id,
    clamp,
    event_name,
    isoformat,
    to_decimal,
    to_float,
)


class ClassicScorer:
    def detect(
        self, instrument_id: str, timeframe: str, candles: list, pivots: list[Pivot]
    ) -> DetectionBundle:
        generated_at = candles[-1].ts_open if candles else datetime.now(UTC)
        pattern = detect_classic_pattern(candles, pivots)
        if not pattern:
            score = ScoreBundle(
                system="classic",
                direction="neutral",
                direction_score=0.0,
                confidence=0.30,
                quality=0.45,
                freshness=0.70,
                evidence_count=0,
                top_reasons=["经典图形模块暂未识别到高质量确认形态。"],
                conflict_flags=[],
                metadata={"regime_hint": "transition", "candidate_weight": 0.0},
            )
            return DetectionBundle(score=score)
        pattern_type = pattern["type"]
        status = pattern["status"]
        bias = pattern["bias"]
        direction_score = pattern["direction_score"]
        confidence = clamp(pattern["confidence"], 0.05, 0.95)
        quality = clamp(pattern["quality"], 0.10, 1.0)
        freshness = clamp(pattern["freshness"], 0.20, 1.0)
        reasons = pattern["reasons"]
        metadata = {
            "regime_hint": "transition",
            "candidate_weight": 0.75 if status != "confirmed" else 0.25,
        }
        score = ScoreBundle(
            system="classic",
            direction=bias,
            direction_score=direction_score,
            confidence=confidence,
            quality=quality,
            freshness=freshness,
            evidence_count=len(pattern["points"]),
            top_reasons=reasons,
            conflict_flags=["candidate_only"] if status != "confirmed" else [],
            metadata=metadata,
        )
        structure_id = build_structure_id("classic", timeframe, pattern_type)
        active_item = StructureActiveItem(
            structure_id=structure_id,
            instrument_id=instrument_id,
            timeframe=timeframe,
            snapshot_version="pending",
            system="classic",
            structure_type=pattern_type,
            display_name=pattern["display_name"],
            lifecycle_status=status,
            directional_bias=bias,
            confidence=to_decimal(confidence),
            event_ts=generated_at,
            confirmation_ts=generated_at if status == "confirmed" else None,
            invalidation_ts=None,
            summary=reasons[0],
            reasoning_json=reasons,
            key_levels_json=pattern["levels"],
            payload_json={"pattern": pattern_type},
            is_active=True,
        )
        geometry = [
            StructureGeometry(
                geometry_id=build_structure_id("classic", timeframe, "pattern"),
                instrument_id=instrument_id,
                timeframe=timeframe,
                snapshot_version="pending",
                system="classic",
                kind=pattern_type,
                status=status,
                visible=True,
                points_json=[
                    {"ts": point.ts.isoformat(), "price": point.price, "label": point.kind}
                    for point in pattern["points"]
                ],
                labels_json=[pattern["display_name"]],
                meta_json=pattern["levels"],
                created_at=generated_at,
            )
        ]
        event = StructureEvent(
            event_id=f"evt:{uuid4().hex}",
            instrument_id=instrument_id,
            timeframe=timeframe,
            system="classic",
            event_name=event_name("classic", pattern_type, status),
            structure_id=structure_id,
            bias=bias,
            status=status,
            confidence=to_decimal(confidence),
            anchor_bar_ts=pattern["points"][-1].ts,
            confirmation_bar_ts=generated_at if status == "confirmed" else None,
            event_ts=generated_at,
            detection_ts=datetime.now(UTC),
            dedupe_key=build_structure_dedupe_key(
                "classic",
                instrument_id,
                timeframe,
                pattern_type,
                status,
                isoformat(pattern["points"][-1].ts)
                if pattern.get("points")
                else isoformat(generated_at),
            ),
            payload_json={"levels": pattern["levels"], "reasons": reasons},
        )
        alerts = []
        if status == "confirmed":
            alert_key = "structure_breakout_confirmed"
            alerts.append(
                StructureAlert(
                    alert_id=f"alt:{uuid4().hex}",
                    instrument_id=instrument_id,
                    timeframe=timeframe,
                    snapshot_version="pending",
                    event_id=event.event_id,
                    rule_key=alert_key,
                    alert_name="结构突破已确认",
                    severity="medium",
                    status="open",
                    dedupe_key=build_structure_dedupe_key(
                        alert_key,
                        instrument_id,
                        timeframe,
                        pattern_type,
                        status,
                    ),
                    title="结构突破已确认",
                    message=reasons[0],
                    triggered_at=generated_at,
                    resolved_at=None,
                    event_payload_json={"pattern": pattern_type},
                )
            )
        return DetectionBundle(
            score=score,
            active_items=[active_item],
            geometry=geometry,
            events=[event],
            alerts=alerts,
        )


def detect_classic_pattern(candles: list, pivots: list[Pivot]) -> dict | None:
    highs = [pivot for pivot in pivots if pivot.kind == "high"]
    lows = [pivot for pivot in pivots if pivot.kind == "low"]
    closes = [to_float(candle.close) for candle in candles[-24:]]
    last_close = closes[-1] if closes else 0.0
    if len(highs) >= 2:
        left, right = highs[-2], highs[-1]
        mid_lows = [pivot.price for pivot in lows if left.index < pivot.index < right.index]
        if mid_lows:
            neckline = min(mid_lows)
            delta = abs(left.price - right.price) / max((left.price + right.price) / 2.0, 1.0)
            if delta <= 0.012:
                confirmed = last_close < neckline
                return {
                    "type": "double_top",
                    "display_name": "双顶",
                    "status": "confirmed" if confirmed else "candidate",
                    "bias": "bearish",
                    "direction_score": -0.72 if confirmed else -0.38,
                    "confidence": 0.78 if confirmed else 0.56,
                    "quality": clamp(0.80 - delta * 10, 0.35, 0.92),
                    "freshness": 0.88,
                    "points": [left, right],
                    "levels": {
                        "neckline": neckline,
                        "left_peak": left.price,
                        "right_peak": right.price,
                    },
                    "reasons": [
                        "最近两个高点在同一区域反复受压，构成双顶雏形。",
                        "若价格继续跌破颈线区域，空头结构将进一步确认。"
                        if not confirmed
                        else "价格已经跌破颈线区域，双顶结构进入确认状态。",
                    ],
                }
    if len(lows) >= 2:
        left, right = lows[-2], lows[-1]
        mid_highs = [pivot.price for pivot in highs if left.index < pivot.index < right.index]
        if mid_highs:
            neckline = max(mid_highs)
            delta = abs(left.price - right.price) / max((left.price + right.price) / 2.0, 1.0)
            if delta <= 0.012:
                confirmed = last_close > neckline
                return {
                    "type": "double_bottom",
                    "display_name": "双底",
                    "status": "confirmed" if confirmed else "candidate",
                    "bias": "bullish",
                    "direction_score": 0.72 if confirmed else 0.38,
                    "confidence": 0.78 if confirmed else 0.56,
                    "quality": clamp(0.80 - delta * 10, 0.35, 0.92),
                    "freshness": 0.88,
                    "points": [left, right],
                    "levels": {
                        "neckline": neckline,
                        "left_trough": left.price,
                        "right_trough": right.price,
                    },
                    "reasons": [
                        "最近两个低点在同一区域获得承接，构成双底雏形。",
                        "若价格继续站上颈线区域，多头结构将进一步确认。"
                        if not confirmed
                        else "价格已经站上颈线区域，双底结构进入确认状态。",
                    ],
                }
    return None
