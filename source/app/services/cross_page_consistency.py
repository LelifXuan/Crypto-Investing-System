"""Resolve the monitoring headline from the published strategy decision.

The technical summary remains evidence. The global direction must be the
backend's canonical daily decision, so pages never publish rival verdicts.
"""

from __future__ import annotations

from collections.abc import Mapping
from datetime import UTC, datetime, timedelta
from typing import Any

MAX_PUBLICATION_SKEW = timedelta(hours=6)


def _utc(value: datetime | str | None) -> datetime | None:
    if isinstance(value, str):
        try:
            value = datetime.fromisoformat(value.replace("Z", "+00:00"))
        except ValueError:
            return None
    if not isinstance(value, datetime):
        return None
    return value.replace(tzinfo=UTC) if value.tzinfo is None else value.astimezone(UTC)


def _direction(value: Any) -> str | None:
    text = str(value or "").strip().upper()
    if text in {"LONG", "BULLISH", "偏多", "做多"}:
        return "LONG"
    if text in {"SHORT", "BEARISH", "偏空", "做空"}:
        return "SHORT"
    if text in {"WAIT", "NEUTRAL", "NONE", "中性", "等待"}:
        return "WAIT"
    return None


def _timeframe_node(payload: Mapping[str, Any], timeframe: str) -> Mapping[str, Any]:
    stack = payload.get("timeframe_stack")
    if isinstance(stack, list):
        for item in stack:
            if isinstance(item, Mapping) and item.get("timeframe") == timeframe:
                return item
    elif isinstance(stack, Mapping):
        item = stack.get(timeframe)
        if isinstance(item, Mapping):
            return item
    return {}


def compare_published_conclusions(
    monitoring_summary: Mapping[str, Any] | None,
    unified_strategy: Mapping[str, Any] | None,
    *,
    instrument_id: str,
    timeframe: str,
    monitoring_snapshot_at: datetime | str | None,
    strategy_snapshot_at: datetime | str | None,
    monitoring_cache_state: str,
    strategy_cache_state: str,
) -> dict[str, Any]:
    """Return one auditable cross-page verdict for the same instrument/timeframe.

    Stale or widely separated publications cannot prove a directional
    contradiction. A 4h move against an aligned daily view is recorded as a
    horizon divergence, separate from a same-timeframe conflict.
    """
    summary = monitoring_summary if isinstance(monitoring_summary, Mapping) else {}
    strategy = unified_strategy if isinstance(unified_strategy, Mapping) else {}
    monitor_at = _utc(monitoring_snapshot_at)
    strategy_at = _utc(strategy_snapshot_at)
    monitor_direction = _direction(summary.get("technical_bias") or summary.get("bias"))
    node = _timeframe_node(strategy, timeframe)
    strategy_direction = _direction(node.get("direction"))
    trade = strategy.get("trade_decision")
    trade = trade if isinstance(trade, Mapping) else {}
    lower_node = _timeframe_node(strategy, "4h") if timeframe == "1d" else {}
    lower_direction = _direction(lower_node.get("direction"))
    result: dict[str, Any] = {
        "status": "unavailable",
        "instrument_id": instrument_id,
        "timeframe": timeframe,
        "monitoring_direction": monitor_direction,
        "strategy_direction": strategy_direction,
        "strategy_confidence": node.get("confidence"),
        "lower_timeframe_direction": lower_direction,
        "canonical_side": _direction(trade.get("side")),
        "canonical_permission": trade.get("permission"),
        "monitoring_snapshot_at": monitor_at.isoformat() if monitor_at else None,
        "strategy_snapshot_at": strategy_at.isoformat() if strategy_at else None,
        "strategy_snapshot_id": strategy.get("snapshot_key"),
        "message": "监控与统一策略的同周期快照尚未齐备，跨页方向待核验。",
    }
    if not summary or not strategy or not monitor_at or not strategy_at:
        return result
    if (
        monitoring_cache_state != "fresh"
        or strategy_cache_state != "fresh"
        or abs(monitor_at - strategy_at) > MAX_PUBLICATION_SKEW
    ):
        result["status"] = "stale_sources"
        result["message"] = "监控与统一策略快照不同步，暂不作跨页方向结论。"
        return result
    if (
        not monitor_direction
        or not strategy_direction
        or str(node.get("freshness") or "").lower() not in {"fresh", "ready", "live"}
    ):
        return result
    if (
        monitor_direction in {"LONG", "SHORT"}
        and strategy_direction in {"LONG", "SHORT"}
        and monitor_direction != strategy_direction
    ):
        result["status"] = "conflict"
        monitor_label = "偏多" if monitor_direction == "LONG" else "偏空"
        strategy_label = "做多" if strategy_direction == "LONG" else "做空"
        result["message"] = (
            f"{instrument_id} {timeframe} 监控技术面{monitor_label}，"
            f"同周期统一策略却为{strategy_label}；"
            "两页方向冲突，暂停全局方向性结论。"
        )
        return result
    if (
        timeframe == "1d"
        and lower_direction in {"LONG", "SHORT"}
        and lower_direction != strategy_direction
    ):
        result["status"] = "timeframe_divergence"
        result["message"] = (
            f"{instrument_id} 日线与 4H 策略方向分歧；日线趋势不能直接充当短周期交易许可。"
        )
        return result
    if monitor_direction == "WAIT" or strategy_direction == "WAIT":
        result["status"] = "unconfirmed"
        result["message"] = "监控技术面与统一策略尚未形成同周期方向共识，等待确认。"
        return result
    result["status"] = "aligned"
    result["message"] = "监控技术面与统一策略同周期方向一致；交易权限仍以统一策略为准。"
    return result


def apply_check_to_monitoring_summary(
    summary: Mapping[str, Any],
    check: Mapping[str, Any],
    unified_strategy: Mapping[str, Any] | None,
) -> dict[str, Any]:
    """Publish one market conclusion while retaining technical evidence."""
    result = dict(summary)
    result["technical_regime"] = summary.get("technical_regime") or summary.get("regime")
    result["technical_bias"] = summary.get("technical_bias") or summary.get("bias")
    result["technical_range_state"] = summary.get("range_state")
    trade = (unified_strategy or {}).get("trade_decision")
    ready = check.get("status") not in {"unavailable", "stale_sources"}
    if isinstance(trade, Mapping) and ready:
        result["trade_decision"] = dict(trade)
    canonical = check.get("strategy_direction") if ready else None
    if canonical not in {"LONG", "SHORT"}:
        result["range_state"] = "NONE"
        result["regime"] = "等待方向确认"
        result["bias"] = "中性"
        result["confidence"] = min(int(result.get("confidence") or 0), 50)
        result["headline"] = "关键周期的策略判断尚未齐备，等待后台更新后给出全局方向。"
        result["trade_decision"] = None
    else:
        result["range_state"] = "NONE"
        result["bias"] = "偏多" if canonical == "LONG" else "偏空"
        timeframe_label = {"1d": "日线", "4h": "4H", "1w": "周线"}.get(
            str(check.get("timeframe")), str(check.get("timeframe") or "当前周期")
        )
        result["regime"] = f"{timeframe_label}{'偏多' if canonical == 'LONG' else '偏空'}"
        try:
            result["confidence"] = round(
                max(0.0, min(100.0, float(check.get("strategy_confidence"))))
            )
        except (TypeError, ValueError):
            result["confidence"] = min(int(result.get("confidence") or 0), 50)
        label = "偏多" if canonical == "LONG" else "偏空"
        reason = trade.get("primary_reason") if isinstance(trade, Mapping) else {}
        reason_text = reason.get("message") if isinstance(reason, Mapping) else None
        symbol = str(check.get("instrument_id") or "BTC").split("-", 1)[0].upper()
        result["headline"] = (
            f"{symbol} {timeframe_label}判断{label}。"
            f"{reason_text or '具体入场条件以统一策略为准。'}"
        )
        result["main_conflict"] = None
        result["strategy_implication"] = reason_text
    brief = dict(result.get("decision_brief") or {})
    rows = [dict(row) for row in brief.get("rows") or []]
    for row in rows:
        if row.get("key") == "market_situation":
            row["summary"] = result["headline"]
    brief["rows"] = rows
    alignment = dict(brief.get("source_alignment") or {})
    alignment["canonical_strategy_snapshot_id"] = check.get("strategy_snapshot_id")
    alignment["consistency"] = "canonical" if canonical in {"LONG", "SHORT"} else "pending"
    alignment["conflicts"] = []
    brief["source_alignment"] = alignment
    result["decision_brief"] = brief
    return result
