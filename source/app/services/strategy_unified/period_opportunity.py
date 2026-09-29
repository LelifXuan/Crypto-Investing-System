"""Independent trade decisions for the three matrix trading horizons.

Each decision is anchored to its own setup candle.  The next lower candle
supplies execution levels; a neutral higher horizon never erases a valid
shorter-horizon direction.  Missing/invalid levels never grant an order.
"""

from __future__ import annotations

from decimal import Decimal, InvalidOperation
from typing import Any, Mapping, Sequence

from app.services.strategy_signal.config_loader import load_strategy_signal_config

from .contracts import TimeframeNode
from .leverage_sizing import evaluate_leverage

EXECUTION_TIMEFRAME = {"1w": "1d", "1d": "4h", "4h": "1h"}
HIGHER_TIMEFRAME = {"1w": "1M", "1d": "1w", "4h": "1d"}
HORIZON_LEVERAGE_CAP = {"1w": 2, "1d": 3, "4h": 5}
ATR_TARGET_MULTIPLE = Decimal("1.5")


def _price(value: Any) -> Decimal | None:
    if value is None or isinstance(value, bool):
        return None
    try:
        result = Decimal(str(value))
    except (InvalidOperation, TypeError, ValueError):
        return None
    return result if result.is_finite() and result > 0 else None


def _plan(bundle: Mapping[str, Any], side: str) -> Mapping[str, Any]:
    decision = bundle.get("decision") or {}
    if not isinstance(decision, Mapping):
        return {}
    key = "long_plan" if side == "LONG" else "short_plan"
    directional = decision.get(key) or {}
    if isinstance(directional, Mapping) and directional:
        return directional
    primary = decision.get("primary_strategy") or {}
    if isinstance(primary, Mapping) and str(primary.get("direction", "")).upper() == side:
        return primary
    return {}


def _triggered(bundle: Mapping[str, Any], plan: Mapping[str, Any]) -> bool:
    """The execution candle must have an active trigger, not just the same bias."""
    decision = bundle.get("decision") or {}
    state = (
        str(decision.get("strategy_state") or "").upper() if isinstance(decision, Mapping) else ""
    )
    triggered_states = {
        "LONG_TRIGGERED",
        "SHORT_TRIGGERED",
        "BREAKOUT_TRIGGERED",
        "BREAKDOWN_TRIGGERED",
        "TREND_FOLLOW_TRIGGERED",
    }
    capital = _price(plan.get("capital_pct"))
    return state in triggered_states and capital is not None


def _target(plan: Mapping[str, Any]) -> Decimal | None:
    target = _price(plan.get("take_profit_1"))
    if target is not None:
        return target
    rows = plan.get("take_profit") or []
    if isinstance(rows, list) and rows:
        first = rows[0]
        return _price(first.get("price") if isinstance(first, Mapping) else first)
    return None


def _atr_pct(bundle: Mapping[str, Any]) -> Decimal | None:
    snapshot = bundle.get("snapshot") or {}
    if not isinstance(snapshot, Mapping):
        snapshot = {}
    return _price(snapshot.get("atr_pct") or bundle.get("atr_pct"))


def _display_price(value: Decimal | None) -> str | None:
    if value is None:
        return None
    return format(value.quantize(Decimal("0.00000001")).normalize(), "f")


def build_period_opportunities(
    instrument_id: str,
    nodes: Sequence[TimeframeNode],
    bundles: Mapping[str, Mapping[str, Any]],
    risk_alerts: Sequence[Any],
) -> dict[str, dict[str, Any]]:
    """Produce three separately governed, stable instrument×period decisions."""
    by_tf = {node.timeframe: node for node in nodes}
    threshold = Decimal(
        str(load_strategy_signal_config().get("thresholds", {}).get("min_rr_trade", 1.5))
    )
    blocked = any(str(getattr(item, "severity", "")).lower() == "blocker" for item in risk_alerts)
    results: dict[str, dict[str, Any]] = {}
    for trade_tf, execution_tf in EXECUTION_TIMEFRAME.items():
        setup = by_tf.get(trade_tf)
        trigger = by_tf.get(execution_tf)
        higher = by_tf.get(HIGHER_TIMEFRAME[trade_tf])
        side = setup.direction if setup and setup.direction in {"LONG", "SHORT"} else "NONE"
        status = (
            "WAIT_DATA" if not setup or setup.freshness in {"missing", "error"} else "NO_DIRECTION"
        )
        reason = f"{trade_tf} 尚未形成交易方向。"
        if side != "NONE":
            status, reason = "WAIT_LEVELS", f"等待 {execution_tf} 生成有效进出场价位。"
        if trigger is None or trigger.freshness in {"missing", "error"}:
            status, reason = "WAIT_DATA", f"{execution_tf} 执行数据尚未就绪。"
        if blocked:
            status, reason = "BLOCKED", "风险门禁已触发，当前周期暂停开仓。"

        execution_bundle = bundles.get(execution_tf) or {}
        setup_bundle = bundles.get(trade_tf) or {}
        execution_plan = _plan(execution_bundle, side) if side != "NONE" else {}
        setup_plan = _plan(setup_bundle, side) if side != "NONE" else {}
        zone_raw = execution_plan.get("entry_zone") or execution_plan.get("entry_price_range") or []
        zone = [_price(value) for value in zone_raw] if isinstance(zone_raw, (list, tuple)) else []
        zone = [value for value in zone if value is not None]
        if not zone:
            entry = _price(execution_plan.get("entry_price"))
            zone = [entry] if entry is not None else []
        # The lower candle selects the entry and first scale-out. The trade
        # horizon owns the invalidation and final objective: using the lower
        # candle's stop for a weekly holding plan would understate its risk.
        execution_stop = _price(execution_plan.get("stop_price") or execution_plan.get("stop_loss"))
        setup_stop = _price(setup_plan.get("stop_price") or setup_plan.get("stop_loss"))
        if setup_stop is None and setup:
            setup_stop = _price(setup.invalidation)
        stop = setup_stop or execution_stop
        stop_source = trade_tf if setup_stop else execution_tf
        first_target = _target(execution_plan)
        horizon_target = _target(setup_plan)
        target_source = "trade_plan"
        if zone and horizon_target is None and setup:
            horizon_target = _price(setup.key_resistance if side == "LONG" else setup.key_support)
            target_source = "observed_structure"
        setup_atr_pct = _atr_pct(setup_bundle)
        if zone and horizon_target is None and setup_atr_pct is not None:
            entry_basis = max(zone) if side == "LONG" else min(zone)
            move = entry_basis * setup_atr_pct * ATR_TARGET_MULTIPLE / Decimal("100")
            horizon_target = entry_basis + move if side == "LONG" else entry_basis - move
            target_source = "atr_projection"
        execution_stop_valid = bool(zone and execution_stop) and (
            (side == "LONG" and execution_stop < min(zone))
            or (side == "SHORT" and execution_stop > max(zone))
        )
        geometry_valid = (
            execution_stop_valid
            and bool(zone and stop and first_target and horizon_target)
            and (
                (
                    side == "LONG"
                    and stop < min(zone)
                    and first_target > max(zone)
                    and horizon_target > first_target
                )
                or (
                    side == "SHORT"
                    and stop > max(zone)
                    and first_target < min(zone)
                    and horizon_target < first_target
                )
            )
        )
        rr: Decimal | None = None
        first_rr: Decimal | None = None
        move_pct: Decimal | None = None
        stop_pct: Decimal | None = None
        if geometry_valid:
            # The adverse edge gives the conservative risk/reward estimate.
            entry = max(zone) if side == "LONG" else min(zone)
            risk = entry - stop if side == "LONG" else stop - entry
            first_reward = first_target - entry if side == "LONG" else entry - first_target
            reward = horizon_target - entry if side == "LONG" else entry - horizon_target
            rr = reward / risk if risk > 0 and reward > 0 else None
            first_rr = first_reward / risk if risk > 0 and first_reward > 0 else None
            move_pct = reward / entry * Decimal("100") if entry > 0 else None
            stop_pct = risk / entry * Decimal("100") if entry > 0 else None
            geometry_valid = rr is not None and rr >= threshold
        leverage = evaluate_leverage(
            stop_distance_pct=float(stop_pct) if geometry_valid and stop_pct else 0.0,
            atr_pct=float(setup_atr_pct) if setup_atr_pct else None,
            hard_cap=HORIZON_LEVERAGE_CAP[trade_tf],
        )
        if side != "NONE" and status == "WAIT_LEVELS" and geometry_valid:
            if (
                trigger
                and trigger.direction == side
                and _triggered(execution_bundle, execution_plan)
            ):
                status, reason = "READY", f"{trade_tf} 方向与 {execution_tf} 执行信号一致。"
            else:
                status, reason = (
                    "WAIT_TRIGGER",
                    f"{trade_tf} 方向已建立，等待 {execution_tf} 同向入场确认。",
                )
        if side != "NONE" and status == "WAIT_LEVELS" and not geometry_valid:
            reason = f"{execution_tf} 执行价位与 {trade_tf} 波动目标未形成有效计划。"
        permission = (
            "allow"
            if status == "READY"
            else "conditional"
            if status == "WAIT_TRIGGER"
            else "observe"
        )
        if (
            higher
            and higher.direction in {"LONG", "SHORT"}
            and higher.direction != side
            and permission == "allow"
        ):
            status = "WAIT_TRIGGER"
            permission = "conditional"
            reason += f" 上级 {higher.timeframe} 方向相反，仓位需收紧。"
        if permission in {"allow", "conditional"} and leverage.recommended_leverage == 0:
            status, permission = "WAIT_RISK", "observe"
            reason = f"{trade_tf} 止损距离超出安全杠杆预算，等待更合适的入场区间。"
        active = permission in {"allow", "conditional"} and geometry_valid
        planned_leverage = leverage.recommended_leverage if active else 0
        results[trade_tf] = {
            "opportunity_id": f"{instrument_id}:{trade_tf}",
            "instrument_id": instrument_id,
            "trade_timeframe": trade_tf,
            "execution_timeframe": execution_tf,
            "higher_timeframe": HIGHER_TIMEFRAME[trade_tf],
            "side": side,
            "status": status,
            "permission": permission,
            "primary_reason": {"code": status, "message": reason},
            "entry_zone": [_display_price(value) for value in zone] if active else [],
            "invalidation_price": _display_price(stop) if active else None,
            "take_profit_1": _display_price(first_target) if active else None,
            "horizon_target": _display_price(horizon_target) if active else None,
            "target_source": target_source,
            "stop_source": stop_source,
            "expected_move_pct": str(move_pct.quantize(Decimal("0.01")))
            if active and move_pct
            else None,
            "stop_distance_pct": str(stop_pct.quantize(Decimal("0.01")))
            if active and stop_pct
            else None,
            "atr_pct": str(setup_atr_pct) if setup_atr_pct else None,
            "risk_reward": {
                "value": str(rr.quantize(Decimal("0.01"))) if rr else None,
                "passed": geometry_valid,
            },
            "first_risk_reward": str(first_rr.quantize(Decimal("0.01"))) if first_rr else None,
            "order_type": "CONDITIONAL_LIMIT" if status == "READY" else "NONE",
            "order_status": "READY" if status == "READY" else "WAIT_TRIGGER" if active else status,
            "levels_active": active,
            "confidence": setup.confidence if setup else 0,
            "setup_evidence": list(setup.evidence) if setup else [],
            "execution_evidence": list(trigger.evidence) if trigger else [],
            "trigger_direction": trigger.direction if trigger else "NONE",
            "higher_direction": higher.direction if higher else "NONE",
            "position_cap": "reduced"
            if permission == "conditional"
            else "standard"
            if active
            else "observe",
            "planned_leverage": planned_leverage,
            "recommended_leverage": planned_leverage if status == "READY" else 0,
            "max_leverage": leverage.max_leverage if active else 0,
            "leverage_reason": leverage.leverage_reason,
            "leverage_detail": leverage.as_dict()["leverage_detail"],
        }
    return results
