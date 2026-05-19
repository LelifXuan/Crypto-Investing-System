from __future__ import annotations

from datetime import datetime, timezone
from uuid import uuid4

from .common import (
    DetectionBundle,
    ScoreBundle,
    StructureActiveItem,
    StructureEvent,
    StructureGeometry,
    build_structure_dedupe_key,
    build_structure_id,
    clamp,
    direction_from_score,
    event_name,
    isoformat,
    safe_mean,
    to_decimal,
    to_float,
)

UTC = timezone.utc


class ProfileScorer:
    def detect(self, instrument_id: str, timeframe: str, candles: list) -> DetectionBundle:
        generated_at = candles[-1].ts_open if candles else datetime.now(timezone.utc)
        profile = build_profile(candles, timeframe=timeframe)
        bias = direction_from_score(profile["direction_score"])
        confidence = clamp(0.42 + profile["structure_strength"] * 0.45, 0.08, 0.92)
        quality = clamp(
            0.45 + profile["bucket_quality"] * 0.35 + profile["imbalance"] * 0.20,
            0.10,
            1.0,
        )
        reasons = profile["reasons"]
        score = ScoreBundle(
            system="profile",
            direction=bias,
            direction_score=profile["direction_score"],
            confidence=confidence,
            quality=quality,
            freshness=clamp(profile["freshness"], 0.20, 1.0),
            evidence_count=profile["bucket_count"],
            top_reasons=reasons,
            conflict_flags=["balance_state"] if profile["balance_score"] >= 0.60 else [],
            metadata={
                "regime_hint": "balance"
                if profile["balance_score"] >= 0.60
                else "transition",
                "balance_score": profile["balance_score"],
                "imbalance": profile["imbalance"],
            },
        )
        structure_type = profile["structure_type"]
        structure_id = build_structure_id("profile", timeframe, structure_type)
        active_item = StructureActiveItem(
            structure_id=structure_id,
            instrument_id=instrument_id,
            timeframe=timeframe,
            snapshot_version="pending",
            system="profile",
            structure_type=structure_type,
            display_name=profile["display_name"],
            lifecycle_status="confirmed",
            directional_bias=bias,
            confidence=to_decimal(confidence),
            event_ts=generated_at,
            confirmation_ts=generated_at,
            invalidation_ts=None,
            summary=reasons[0],
            reasoning_json=reasons,
            key_levels_json={"poc": profile["poc"], "vah": profile["vah"], "val": profile["val"]},
            payload_json=profile,
            is_active=True,
        )
        points = _profile_points(candles, generated_at, profile)
        geometry = [
            StructureGeometry(
                geometry_id=build_structure_id("profile", timeframe, "levels"),
                instrument_id=instrument_id,
                timeframe=timeframe,
                snapshot_version="pending",
                system="profile",
                kind="value_area",
                status="confirmed",
                visible=True,
                points_json=points,
                labels_json=["POC", "VAH", "VAL"],
                meta_json={"poc": profile["poc"], "vah": profile["vah"], "val": profile["val"]},
                created_at=generated_at,
            )
        ]
        event = StructureEvent(
            event_id=f"evt:{uuid4().hex}",
            instrument_id=instrument_id,
            timeframe=timeframe,
            system="profile",
            event_name=event_name("profile", profile["event_key"], "confirmed"),
            structure_id=structure_id,
            bias=bias,
            status="confirmed",
            confidence=to_decimal(confidence),
            anchor_bar_ts=generated_at,
            confirmation_bar_ts=generated_at,
            event_ts=generated_at,
            detection_ts=datetime.now(timezone.utc),
            dedupe_key=build_structure_dedupe_key(
                "profile",
                instrument_id,
                timeframe,
                profile["event_key"],
                bias,
                isoformat(profile.get("anchor_ts") or generated_at),
            ),
            payload_json={
                "levels": {"poc": profile["poc"], "vah": profile["vah"], "val": profile["val"]},
                "reasons": reasons,
            },
        )
        return DetectionBundle(
            score=score,
            active_items=[active_item],
            geometry=geometry,
            events=[event],
        )


def _profile_points(candles: list, generated_at: datetime, profile: dict) -> list[dict]:
    start_ts = (
        candles[max(len(candles) - 24, 0)].ts_open.isoformat()
        if candles
        else generated_at.isoformat()
    )
    end_ts = generated_at.isoformat()
    return [
        {"ts": start_ts, "price": profile["poc"], "label": "POC"},
        {"ts": end_ts, "price": profile["poc"], "label": "POC"},
        {"ts": end_ts, "price": profile["vah"], "label": "VAH"},
        {"ts": end_ts, "price": profile["val"], "label": "VAL"},
    ]


def _continuous_value_area(
    buckets: dict[int, float],
    poc_key: int,
    target_volume: float,
) -> set[int]:
    value_keys = {poc_key}
    covered = buckets.get(poc_key, 0.0)
    left = poc_key - 1
    right = poc_key + 1
    while covered < target_volume and (left in buckets or right in buckets):
        left_volume = buckets.get(left, -1.0)
        right_volume = buckets.get(right, -1.0)
        if right_volume >= left_volume:
            if right in buckets:
                value_keys.add(right)
                covered += buckets[right]
            right += 1
        else:
            if left in buckets:
                value_keys.add(left)
                covered += buckets[left]
            left -= 1
    return value_keys


def build_profile(
    candles: list,
    *,
    timeframe: str = "1h",
    tick_size: float | None = None,
    bucket_bps: float = 5.0,
) -> dict:
    if not candles:
        return _empty_profile()
    lookback = {"1h": 168, "4h": 120, "1d": 90, "1w": 52, "30d": 52}.get(timeframe, 168)
    sample = candles[-lookback:]
    prices = [to_float(candle.close) for candle in sample]
    highs = [to_float(candle.high) for candle in sample]
    lows = [to_float(candle.low) for candle in sample]
    volumes = [max(to_float(candle.volume), 1.0) for candle in sample]
    price_min = min(lows)
    reference_price = max(safe_mean(prices), 1.0)
    step = max(tick_size or 0.0, reference_price * bucket_bps / 10000.0, 1e-12)
    buckets: dict[int, float] = {}
    for high, low, volume in zip(highs, lows, volumes, strict=False):
        start_key = int((min(high, low) - price_min) / step)
        end_key = int((max(high, low) - price_min) / step)
        bucket_count = max(end_key - start_key + 1, 1)
        volume_share = volume / bucket_count
        for key in range(start_key, end_key + 1):
            buckets[key] = buckets.get(key, 0.0) + volume_share
    ordered = sorted(buckets.items(), key=lambda item: item[1], reverse=True)
    poc_key = ordered[0][0] if ordered else 0
    total_volume = sum(buckets.values()) or 1.0
    value_keys = _continuous_value_area(buckets, poc_key, total_volume * 0.70)
    poc = price_min + (poc_key + 0.5) * step
    vah = price_min + (max(value_keys) + 1) * step
    val = price_min + min(value_keys) * step
    latest_close = prices[-1]
    midpoint = max(len(sample) // 2, 1)
    early_poc = safe_mean(prices[:midpoint])
    late_poc = safe_mean(prices[midpoint:])
    poc_shift = clamp((late_poc - early_poc) / max(step * 3, 1.0), -1.0, 1.0)
    direction_score, event_key, structure_type, display_name, reasons = _profile_state(
        latest_close,
        vah,
        val,
        poc,
        poc_shift,
    )
    width = max(vah - val, 1.0)
    balance_score = clamp(1.0 - abs(latest_close - poc) / width, 0.0, 1.0)
    return {
        "poc": poc,
        "vah": vah,
        "val": val,
        "direction_score": clamp(direction_score, -1.0, 1.0),
        "balance_score": balance_score,
        "bucket_count": len(buckets),
        "bucket_quality": clamp(len(buckets) / 8.0, 0.30, 1.0),
        "structure_strength": clamp(abs(direction_score) + abs(poc_shift) * 0.5, 0.20, 1.0),
        "imbalance": abs(poc_shift),
        "freshness": 0.90,
        "structure_type": structure_type,
        "display_name": display_name,
        "event_key": event_key,
        "reasons": reasons,
    }


def _empty_profile() -> dict:
    return {
        "poc": 0.0,
        "vah": 0.0,
        "val": 0.0,
        "direction_score": 0.0,
        "balance_score": 0.0,
        "bucket_count": 0,
        "bucket_quality": 0.0,
        "structure_strength": 0.0,
        "imbalance": 0.0,
        "freshness": 0.5,
        "structure_type": "value_area_balance",
        "display_name": "成交量轮廓平衡",
        "event_key": "hvn_acceptance",
        "reasons": ["缺少 OHLCV 样本，成交量轮廓只能输出占位结果。"],
    }


def _profile_state(
    latest_close: float,
    vah: float,
    val: float,
    poc: float,
    poc_shift: float,
) -> tuple[float, str, str, str, list[str]]:
    poc_threshold = 0.02
    if latest_close > vah:
        return (
            0.55 + max(poc_shift, 0.0) * 0.20,
            "acceptance_above_vah",
            "acceptance_above_vah",
            "价值区上方接受",
            [
                "价格收在 VAH 上方，市场正在尝试接受更高价值区。",
                _poc_reason("上行解释力", poc_shift, poc_threshold),
            ],
        )
    if latest_close < val:
        return (
            -0.55 + min(poc_shift, 0.0) * 0.20,
            "acceptance_below_val",
            "acceptance_below_val",
            "价值区下方接受",
            [
                "价格收在 VAL 下方，市场正在尝试接受更低价值区。",
                _poc_reason("下行解释力", poc_shift, poc_threshold),
            ],
        )
    if latest_close >= poc:
        return (
            0.24 + max(poc_shift, 0.0) * 0.18,
            "hvn_acceptance",
            "value_area_balance",
            "价值区上半部平衡",
            [
                "价格位于价值区内部且靠近 POC 上方，偏向平衡偏多。",
                "仍需突破 VAH 才能确认上行扩展。",
            ],
        )
    return (
        -0.24 + min(poc_shift, 0.0) * 0.18,
        "lvn_rejection",
        "value_area_balance",
        "价值区下半部平衡",
        ["价格位于价值区内部且靠近 POC 下方，偏向平衡偏空。", "仍需跌破 VAL 才能确认下行扩展。"],
    )


def _poc_reason(label: str, shift: float, threshold: float) -> str:
    if shift > threshold:
        return f"POC 已上移，{label}得到成交密集区迁移支持。"
    if shift < -threshold:
        return f"POC 下移，与{label}形成矛盾，上行解释力降级。"
    return "POC 暂未明显迁移，价值区突破仍需更多成交确认。"
