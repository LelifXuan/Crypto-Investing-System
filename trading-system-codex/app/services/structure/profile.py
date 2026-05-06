from __future__ import annotations

from datetime import UTC, datetime
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


class ProfileScorer:
    def detect(self, instrument_id: str, timeframe: str, candles: list) -> DetectionBundle:
        generated_at = candles[-1].ts_open if candles else datetime.now(UTC)
        profile = build_profile(candles)
        balance_score = profile["balance_score"]
        direction_score = profile["direction_score"]
        bias = direction_from_score(direction_score)
        confidence = clamp(0.42 + profile["structure_strength"] * 0.45, 0.08, 0.92)
        quality = clamp(
            0.45 + profile["bucket_quality"] * 0.35 + profile["imbalance"] * 0.20, 0.10, 1.0
        )
        freshness = clamp(profile["freshness"], 0.20, 1.0)
        reasons = profile["reasons"]
        score = ScoreBundle(
            system="profile",
            direction=bias,
            direction_score=direction_score,
            confidence=confidence,
            quality=quality,
            freshness=freshness,
            evidence_count=profile["bucket_count"],
            top_reasons=reasons,
            conflict_flags=["balance_state"] if balance_score >= 0.60 else [],
            metadata={
                "regime_hint": "balance" if balance_score >= 0.60 else "transition",
                "balance_score": balance_score,
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
        points = [
            {
                "ts": candles[max(len(candles) - 24, 0)].ts_open.isoformat()
                if candles
                else generated_at.isoformat(),
                "price": profile["poc"],
                "label": "POC",
            },
            {"ts": generated_at.isoformat(), "price": profile["poc"], "label": "POC"},
            {"ts": generated_at.isoformat(), "price": profile["vah"], "label": "VAH"},
            {"ts": generated_at.isoformat(), "price": profile["val"], "label": "VAL"},
        ]
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
        event_key = profile["event_key"]
        event = StructureEvent(
            event_id=f"evt:{uuid4().hex}",
            instrument_id=instrument_id,
            timeframe=timeframe,
            system="profile",
            event_name=event_name("profile", event_key, "confirmed"),
            structure_id=structure_id,
            bias=bias,
            status="confirmed",
            confidence=to_decimal(confidence),
            anchor_bar_ts=generated_at,
            confirmation_bar_ts=generated_at,
            event_ts=generated_at,
            detection_ts=datetime.now(UTC),
            dedupe_key=build_structure_dedupe_key(
                "profile",
                instrument_id,
                timeframe,
                event_key,
                bias,
                isoformat(profile.get("anchor_ts") or generated_at),
            ),
            payload_json={
                "levels": {"poc": profile["poc"], "vah": profile["vah"], "val": profile["val"]},
                "reasons": reasons,
            },
        )
        return DetectionBundle(
            score=score, active_items=[active_item], geometry=geometry, events=[event]
        )


def _continuous_value_area(
    buckets: dict[int, float], poc_key: int, target_volume: float
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
            "display_name": "价值区平衡",
            "event_key": "hvn_acceptance",
            "reasons": ["暂无可用的 OHLCV 样本来构建市场轮廓。"],
        }
    lookback = {"1m": 240, "5m": 240, "15m": 192, "1h": 168, "4h": 120, "1d": 90, "1w": 52}.get(
        timeframe,
        168,
    )
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
    midpoint = len(sample) // 2
    early_poc = safe_mean(prices[:midpoint])
    late_poc = safe_mean(prices[midpoint:])
    poc_shift = clamp((late_poc - early_poc) / max(step * 3, 1.0), -1.0, 1.0)
    if latest_close > vah:
        direction_score = 0.55 + max(poc_shift, 0.0) * 0.20
        event_key = "acceptance_above_vah"
        structure_type = "acceptance_above_vah"
        display_name = "价值区上沿接受"
        reasons = [
            "最新价格已经站上价值区高点，并在其上方建立接受。",
            "近期成交重心仍在上移，POC 迁移支持偏多判断。",
        ]
    elif latest_close < val:
        direction_score = -0.55 + min(poc_shift, 0.0) * 0.20
        event_key = "acceptance_below_val"
        structure_type = "acceptance_below_val"
        display_name = "价值区下沿失守"
        reasons = [
            "最新价格已经跌破价值区低点，并在其下方建立接受。",
            "近期成交重心仍在下移，POC 迁移支持偏空判断。",
        ]
    elif latest_close >= poc:
        direction_score = 0.24 + max(poc_shift, 0.0) * 0.18
        event_key = "hvn_acceptance"
        structure_type = "value_area_balance"
        display_name = "价值区平衡偏多"
        reasons = [
            "价格仍在价值区内部运行，但更靠近价值区上半区。",
            "POC 没有明显下移，说明平衡区内偏多承接仍在。",
        ]
    else:
        direction_score = -0.24 + min(poc_shift, 0.0) * 0.18
        event_key = "lvn_rejection"
        structure_type = "value_area_balance"
        display_name = "价值区平衡偏空"
        reasons = [
            "价格仍在价值区内部运行，但更靠近价值区下半区。",
            "POC 没有明显上移，说明平衡区内偏空压制仍在。",
        ]
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
