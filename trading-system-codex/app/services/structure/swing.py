from __future__ import annotations

from datetime import UTC, datetime
from uuid import uuid4

from .common import (
    DetectionBundle,
    Pivot,
    ScoreBundle,
    ScoringConfig,
    StructureActiveItem,
    StructureEvent,
    StructureGeometry,
    build_structure_dedupe_key,
    build_structure_id,
    clamp,
    direction_from_score,
    event_name,
    isoformat,
    parse_timeframe_hours,
    safe_mean,
    to_decimal,
    to_float,
)
from .pivots import detect_pivots


class SwingScorer:
    def __init__(self, config: ScoringConfig) -> None:
        self.config = config

    def detect(self, instrument_id: str, timeframe: str, candles: list) -> DetectionBundle:
        generated_at = candles[-1].ts_open if candles else datetime.now(UTC)
        pivots = detect_pivots(candles)
        highs = [pivot for pivot in pivots if pivot.kind == "high"]
        lows = [pivot for pivot in pivots if pivot.kind == "low"]
        higher_highs = sum(
            1 for idx in range(1, len(highs)) if highs[idx].price > highs[idx - 1].price
        )
        lower_highs = sum(
            1 for idx in range(1, len(highs)) if highs[idx].price < highs[idx - 1].price
        )
        higher_lows = sum(1 for idx in range(1, len(lows)) if lows[idx].price > lows[idx - 1].price)
        lower_lows = sum(1 for idx in range(1, len(lows)) if lows[idx].price < lows[idx - 1].price)
        trend_sequence = clamp(
            (higher_highs + higher_lows - lower_highs - lower_lows) / max(len(pivots), 1), -1.0, 1.0
        )
        close_values = [to_float(candle.close) for candle in candles[-8:]]
        range_size = max(close_values) - min(close_values) if close_values else 0.0
        break_strength = (
            0.0
            if len(close_values) < 2
            else clamp((close_values[-1] - close_values[0]) / max(range_size, 1.0), -1.0, 1.0)
        )
        direction_score = clamp(0.65 * trend_sequence + 0.35 * break_strength, -1.0, 1.0)
        confidence = clamp(
            0.40 + min(len(pivots), 10) * 0.04 + abs(direction_score) * 0.20, 0.05, 0.95
        )
        quality = clamp(
            0.45 + self._symmetry_score(pivots) * 0.20 + self._invalidation_room(candles) * 0.35,
            0.10,
            1.0,
        )
        freshness = self._freshness(
            timeframe, pivots[-1].ts if pivots else generated_at, generated_at
        )
        bias = direction_from_score(direction_score)
        top_reasons = self._top_reasons(
            bias, higher_highs, higher_lows, lower_highs, lower_lows, break_strength
        )
        score = ScoreBundle(
            system="swing",
            direction=bias,
            direction_score=direction_score,
            confidence=confidence,
            quality=quality,
            freshness=freshness,
            evidence_count=max(len(pivots), 1),
            top_reasons=top_reasons,
            conflict_flags=["swing_range"] if abs(direction_score) < 0.12 else [],
            metadata={
                "regime_hint": "trend" if abs(direction_score) >= 0.35 else "balance",
                "pivot_count": len(pivots),
            },
        )
        geometry = []
        if len(pivots) >= 2:
            geometry.append(
                StructureGeometry(
                    geometry_id=build_structure_id("swing", timeframe, "zigzag"),
                    instrument_id=instrument_id,
                    timeframe=timeframe,
                    snapshot_version="pending",
                    system="swing",
                    kind="zigzag",
                    status="confirmed",
                    visible=True,
                    points_json=[
                        {"ts": pivot.ts.isoformat(), "price": pivot.price, "label": pivot.kind}
                        for pivot in pivots[-12:]
                    ],
                    labels_json=["zigzag"],
                    meta_json={"pivot_count": len(pivots)},
                    created_at=generated_at,
                )
            )
        structure_type = (
            "trend_up" if bias == "bullish" else "trend_down" if bias == "bearish" else "range"
        )
        active_items = [
            StructureActiveItem(
                structure_id=build_structure_id("swing", timeframe, "trend"),
                instrument_id=instrument_id,
                timeframe=timeframe,
                snapshot_version="pending",
                system="swing",
                structure_type=structure_type,
                display_name={"bullish": "上升摆动结构", "bearish": "下降摆动结构"}.get(
                    bias, "区间摆动结构"
                ),
                lifecycle_status="confirmed",
                directional_bias=bias,
                confidence=to_decimal(confidence),
                event_ts=generated_at,
                confirmation_ts=generated_at,
                invalidation_ts=None,
                summary=top_reasons[0] if top_reasons else "摆动结构暂无明显方向。",
                reasoning_json=top_reasons,
                key_levels_json={"last_close": close_values[-1] if close_values else 0.0},
                payload_json={"pivot_count": len(pivots)},
                is_active=True,
            )
        ]
        events = [
            StructureEvent(
                event_id=f"evt:{uuid4().hex}",
                instrument_id=instrument_id,
                timeframe=timeframe,
                system="swing",
                event_name=event_name("swing", structure_type, "confirmed"),
                structure_id=active_items[0].structure_id,
                bias=bias,
                status="confirmed",
                confidence=to_decimal(confidence),
                anchor_bar_ts=pivots[-1].ts if pivots else generated_at,
                confirmation_bar_ts=generated_at,
                event_ts=generated_at,
                detection_ts=datetime.now(UTC),
                dedupe_key=build_structure_dedupe_key(
                    "swing",
                    instrument_id,
                    timeframe,
                    structure_type,
                    pivots[-1].kind if pivots else None,
                    isoformat(pivots[-1].ts if pivots else generated_at),
                ),
                payload_json={"top_reasons": top_reasons, "direction_score": direction_score},
            )
        ]
        return DetectionBundle(
            score=score, active_items=active_items, geometry=geometry, events=events
        )

    def _symmetry_score(self, pivots: list[Pivot]) -> float:
        if len(pivots) < 4:
            return 0.55
        distances = [
            abs(pivots[idx].price - pivots[idx - 1].price) for idx in range(1, len(pivots[-6:]))
        ]
        if not distances:
            return 0.55
        avg = safe_mean(distances)
        variance = safe_mean([abs(item - avg) for item in distances])
        return clamp(1.0 - variance / max(avg, 1.0), 0.2, 1.0)

    def _invalidation_room(self, candles: list) -> float:
        if len(candles) < 6:
            return 0.5
        latest = to_float(candles[-1].close)
        recent_lows = min(to_float(candle.low) for candle in candles[-6:])
        recent_highs = max(to_float(candle.high) for candle in candles[-6:])
        room = min(abs(latest - recent_lows), abs(recent_highs - latest))
        width = max(recent_highs - recent_lows, 1.0)
        return clamp(room / width, 0.2, 1.0)

    def _freshness(self, timeframe: str, signal_ts: datetime, latest_ts: datetime) -> float:
        age_hours = max((latest_ts - signal_ts).total_seconds() / 3600.0, 0.0)
        window = self.config.freshness_windows.get(timeframe, 12) * parse_timeframe_hours(timeframe)
        return clamp(1.0 - age_hours / max(window, 1.0), 0.2, 1.0)

    def _top_reasons(
        self,
        bias: str,
        higher_highs: int,
        higher_lows: int,
        lower_highs: int,
        lower_lows: int,
        break_strength: float,
    ) -> list[str]:
        if bias == "bullish":
            return [
                f"更高高点 {higher_highs} 次、更高低点 {higher_lows} 次，摆动序列偏多。",
                "最近一段收盘价格维持在前一轮摆动低点上方。",
                f"突破力度因子为 {break_strength:.2f}，说明上行延续仍占优。",
            ]
        if bias == "bearish":
            return [
                f"更低高点 {lower_highs} 次、更低低点 {lower_lows} 次，摆动序列偏空。",
                "最近收盘没有重新站回前一轮关键高点上方。",
                f"突破力度因子为 {break_strength:.2f}，说明下行延续仍占优。",
            ]
        return [
            "高低点仍在交错，摆动结构更接近震荡或过渡状态。",
            "最近几根 K 线未形成明确 BOS/CHoCH 延续。",
        ]
