from __future__ import annotations

from datetime import UTC, datetime

from app.schemas.structure import StructureDiagnosticsRead

from .common import STRUCTURE_DETECTOR_VERSION, FusionResult


def bundle_status_message(cache_state: str) -> str:
    if cache_state == "missing":
        return "当前仅返回缓存结果：尚未生成结构快照，请手动刷新后再查看结构分析。"
    if cache_state == "stale":
        return "当前显示的是缓存快照，结构结果已落后于最新价格，请按需手动刷新。"
    return "当前显示的是缓存快照结果。"


def empty_diagnostics() -> StructureDiagnosticsRead:
    return StructureDiagnosticsRead(
        detector_version=STRUCTURE_DETECTOR_VERSION,
        compute_mode="snapshot",
        candles_loaded=0,
        profile_precision="ohlcv_approx",
        geometry_count=0,
        event_count=0,
        alert_count=0,
        latest_event_name=None,
        generated_at=datetime.now(UTC),
        notes=["当前还没有可用的结构快照。"],
    )


def build_diagnostics_payload(
    candles: list,
    geometry: list,
    events: list,
    alerts: list,
    generated_at: datetime,
    fusion: FusionResult,
    quality,
) -> dict:
    return {
        "compute_mode": "bounded_recompute_lite",
        "candles_loaded": len(candles),
        "profile_precision": "ohlcv_approx",
        "geometry_count": len(geometry),
        "event_count": len(events),
        "alert_count": len(alerts),
        "latest_event_name": events[0].event_name if events else None,
        "generated_at": generated_at.isoformat(),
        "detection_latency_ms": 0,
        "conflict_type": fusion.conflict_type,
        "dominant_side": fusion.dominant_side,
        "opposing_side": fusion.opposing_side,
        "meaning": fusion.meaning,
        "risk": fusion.risk,
        "mode": fusion.suggested_mode,
        "need_confirmation": fusion.need_confirmation,
        "invalidation": fusion.invalidation,
        "suggested_mode": fusion.suggested_mode,
        "suggested_action": fusion.suggested_action,
        "data_quality_score": quality.data_quality_score,
        "data_quality_status": quality.status,
        "data_quality_issues": quality.issues,
        "can_analyze": quality.can_analyze,
        "can_alert": quality.can_alert,
        "notes": [
            "综合判断使用分层加权与市场状态切换模型。",
            f"当前权重模板为 {fusion.weight_template}。",
        ],
    }
