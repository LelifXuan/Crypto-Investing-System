from __future__ import annotations

import hashlib
import json
from dataclasses import asdict, dataclass
from datetime import UTC, datetime, timedelta
from typing import Any, Literal

Side = Literal["long", "short"]

TERMINAL_STATES = {
    "TP2_HIT",
    "STOP_HIT",
    "SETUP_EXPIRED",
    "SETUP_INVALIDATED",
    "MOVE_MISSED",
    "INVALID_PLAN_LEVELS",
}

ACTIVE_STATES = {
    "SETUP_DETECTED",
    "WAIT_LOWER_TF_CONFIRMATION",
    "WAIT_PULLBACK_CONFIRMATION",
    "LONG_TRIGGERED",
    "SHORT_TRIGGERED",
    "TREND_FOLLOW_TRIGGERED",
    "BREAKDOWN_TRIGGERED",
    "BREAKOUT_TRIGGERED",
    "TP1_HIT",
}


@dataclass(slots=True)
class PlanLevels:
    side: Side
    entry: float
    stop: float
    tp1: float
    tp2: float
    risk: float
    rr1: float
    rr2: float
    is_valid: bool
    invalid_reason: str | None = None

    def to_dict(self) -> dict[str, Any]:
        return asdict(self)


@dataclass(slots=True)
class GateDiagnostic:
    code: str
    status: Literal["pass", "fail", "warn", "missing"]
    message: str
    current: Any = None
    required: Any = None
    severity: Literal["info", "warning", "block"] = "info"

    def to_dict(self) -> dict[str, Any]:
        return asdict(self)


def utc_now_iso() -> str:
    return datetime.now(UTC).isoformat()


def to_float(value: Any, default: float = 0.0) -> float:
    try:
        if value is None or value == "":
            return default
        parsed = float(value)
    except (TypeError, ValueError):
        return default
    if parsed != parsed or parsed in {float("inf"), float("-inf")}:
        return default
    return parsed


def clamp(value: Any, low: float = 0.0, high: float = 100.0) -> float:
    return max(low, min(high, to_float(value)))


def stable_hash(payload: dict[str, Any], length: int = 10) -> str:
    raw = json.dumps(payload, sort_keys=True, ensure_ascii=False, default=str)
    return hashlib.sha256(raw.encode("utf-8")).hexdigest()[:length]


DirectionScoreScale = Literal["signed", "legacy_0_100"]


def normalize_direction_metrics(
    direction_score: Any,
    *,
    scale: DirectionScoreScale,
) -> dict[str, float]:
    """Convert a single direction score into ``{bullish, bearish, range, raw, scale}``.

    The ``scale`` argument is required and must match the contract the caller
    received from its upstream source. The legacy auto-detection heuristic
    (``0..100 ⇒ legacy``) was removed because it silently flipped
    ``chip_structure.direction_score`` (signed ``-100..100``) into a 100 %
    bearish reading when the value happened to be in ``0..100`` (e.g. ``0``).
    Callers must now declare the contract:

    * ``scale="signed"`` for ``-100..100`` (chip, final_decision, confidence).
    * ``scale="legacy_0_100"`` for ``0..100`` legacy percent scores where
      ``50`` is neutral and ``0/100`` are the bullish/bearish extremes.
    """

    if scale not in {"signed", "legacy_0_100"}:
        raise ValueError(
            "normalize_direction_metrics: scale must be 'signed' or 'legacy_0_100',"
            f" got {scale!r}"
        )
    if scale == "signed":
        default_score = 0.0
    else:
        default_score = 50.0
    score = to_float(direction_score, default_score)
    if scale == "signed":
        signed = max(-100.0, min(100.0, score))
        bullish = clamp(max(signed, 0.0))
        bearish = clamp(max(-signed, 0.0))
        range_score = clamp(100.0 - abs(signed))
        return {
            "bullish": round(bullish, 4),
            "bearish": round(bearish, 4),
            "range": round(range_score, 4),
            "raw": round(signed, 4),
            "scale": "signed",
        }
    if not 0.0 <= score <= 100.0:
        raise ValueError(
            "normalize_direction_metrics: legacy_0_100 scale expects a score in"
            f" 0..100, got {score}"
        )
    bullish = clamp(score)
    bearish = clamp(100.0 - score)
    range_score = clamp(100.0 - abs(score - 50.0) * 2.0)
    return {
        "bullish": round(bullish, 4),
        "bearish": round(bearish, 4),
        "range": round(range_score, 4),
        "raw": round(score, 4),
        "scale": "legacy_0_100",
    }


def normalize_plan_levels(
    side: Side,
    entry: Any,
    stop: Any,
    tp1: Any,
    tp2: Any,
    current_price: Any | None = None,
    atr: Any | None = None,
    *,
    min_rr: float = 1.0,
    allow_repair: bool = True,
) -> dict[str, Any]:
    entry_f = to_float(entry)
    stop_f = to_float(stop)
    tp1_f = to_float(tp1)
    tp2_f = to_float(tp2)
    price_f = to_float(current_price, entry_f)
    atr_f = max(to_float(atr, abs(price_f) * 0.02), abs(price_f) * 0.002, 1e-9)

    if not entry_f or not stop_f or not tp1_f or not tp2_f:
        return PlanLevels(
            side, entry_f, stop_f, tp1_f, tp2_f, 0, 0, 0, False, "missing entry/stop/tp"
        ).to_dict()

    if allow_repair:
        if side == "long":
            if stop_f >= entry_f:
                stop_f = entry_f - atr_f * 1.6
            tp1_f, tp2_f = sorted([tp1_f, tp2_f])
            if tp1_f <= entry_f:
                tp1_f = entry_f + atr_f * 2.0
            if tp2_f <= tp1_f:
                tp2_f = max(tp1_f + atr_f * 1.2, entry_f + atr_f * 3.2)
        else:
            if stop_f <= entry_f:
                stop_f = entry_f + atr_f * 1.6
            tp1_f, tp2_f = sorted([tp1_f, tp2_f], reverse=True)
            if tp1_f >= entry_f:
                tp1_f = entry_f - atr_f * 2.0
            if tp2_f >= tp1_f:
                tp2_f = min(tp1_f - atr_f * 1.2, entry_f - atr_f * 3.2)

    if side == "long":
        is_valid = stop_f < entry_f < tp1_f < tp2_f
        risk = entry_f - stop_f
        rr1 = (tp1_f - entry_f) / max(risk, 1e-9)
        rr2 = (tp2_f - entry_f) / max(risk, 1e-9)
        reason = None if is_valid else "long plan requires stop < entry < tp1 < tp2"
    else:
        is_valid = stop_f > entry_f > tp1_f > tp2_f
        risk = stop_f - entry_f
        rr1 = (entry_f - tp1_f) / max(risk, 1e-9)
        rr2 = (entry_f - tp2_f) / max(risk, 1e-9)
        reason = None if is_valid else "short plan requires stop > entry > tp1 > tp2"

    if is_valid and rr1 < min_rr:
        is_valid = False
        reason = f"risk reward {rr1:.2f} is below minimum {min_rr:.2f}"

    return PlanLevels(
        side=side,
        entry=round(entry_f, 8),
        stop=round(stop_f, 8),
        tp1=round(tp1_f, 8),
        tp2=round(tp2_f, 8),
        risk=round(max(risk, 0.0), 8),
        rr1=round(rr1, 4),
        rr2=round(rr2, 4),
        is_valid=is_valid,
        invalid_reason=reason,
    ).to_dict()


def build_setup_id(
    instrument_id: str,
    timeframe: str,
    side: Side,
    levels: dict[str, Any],
    created_at: str | None = None,
) -> str:
    day = (created_at or utc_now_iso())[:10].replace("-", "")
    digest = stable_hash(
        {"instrument_id": instrument_id, "timeframe": timeframe, "side": side, "levels": levels}
    )
    return f"setup:{instrument_id}:{timeframe}:{side}:{day}:{digest}"


def build_frozen_setup(
    *,
    instrument_id: str,
    timeframe: str,
    side: Side,
    levels: dict[str, Any],
    entry_mode: str,
    snapshot: dict[str, Any],
    valid_bars: int = 10,
) -> dict[str, Any]:
    created = datetime.now(UTC)
    bar_hours = {"1h": 1, "4h": 4, "1d": 24, "1w": 168, "30d": 720, "1M": 720}
    hours = max(valid_bars * bar_hours.get(timeframe, 1), 1)
    valid_until = created + timedelta(hours=hours)
    setup_id = build_setup_id(instrument_id, timeframe, side, levels, created.isoformat())
    return {
        "setup_id": setup_id,
        "setup_version": "v1.7",
        "instrument_id": instrument_id,
        "timeframe": timeframe,
        "direction": side,
        "entry_mode": entry_mode,
        "created_at": created.isoformat(),
        "valid_until": valid_until.isoformat(),
        "entry_price": levels["entry"],
        "stop_price": levels["stop"],
        "take_profit_1": levels["tp1"],
        "take_profit_2": levels["tp2"],
        "risk": levels["risk"],
        "rr1": levels["rr1"],
        "rr2": levels["rr2"],
        "invalidation_level": levels["stop"],
        "initial_snapshot_hash": stable_hash(snapshot),
        "last_lifecycle_state": "SETUP_DETECTED",
    }


def _parse_dt(value: Any) -> datetime | None:
    if not value:
        return None
    if isinstance(value, datetime):
        return value if value.tzinfo else value.replace(tzinfo=UTC)
    try:
        parsed = datetime.fromisoformat(str(value).replace("Z", "+00:00"))
        return parsed if parsed.tzinfo else parsed.replace(tzinfo=UTC)
    except ValueError:
        return None


def evaluate_setup_lifecycle(
    setup: dict[str, Any], snapshot: dict[str, Any], config: dict[str, Any] | None = None
) -> dict[str, Any]:
    cfg = config or {}
    thresholds = cfg.get("thresholds", {})
    side = str(setup.get("direction") or setup.get("side") or "").lower()
    if side not in {"long", "short"}:
        return {
            "state": "SETUP_INVALIDATED",
            "reason": "setup direction is missing or invalid",
            "is_terminal": True,
        }

    price = to_float(snapshot.get("current_price") or snapshot.get("price", {}).get("current"))
    atr = max(to_float(snapshot.get("atr_14"), price * 0.02), price * 0.002, 1e-9)
    entry = to_float(setup.get("entry_price") or setup.get("entry_price_frozen"))
    stop = to_float(setup.get("stop_price") or setup.get("stop_price_frozen"))
    tp1 = to_float(setup.get("take_profit_1") or setup.get("take_profit_1_frozen"))
    tp2 = to_float(setup.get("take_profit_2") or setup.get("take_profit_2_frozen"))
    risk = to_float(setup.get("risk"), abs(entry - stop)) or abs(entry - stop)

    levels = normalize_plan_levels(
        side, entry, stop, tp1, tp2, price, atr, min_rr=0.1, allow_repair=False
    )
    if not levels["is_valid"]:
        return {
            "state": "INVALID_PLAN_LEVELS",
            "reason": levels["invalid_reason"],
            "is_terminal": True,
            "levels": levels,
        }

    valid_until = _parse_dt(setup.get("valid_until"))
    if valid_until and datetime.now(UTC) > valid_until:
        return {
            "state": "SETUP_EXPIRED",
            "reason": "setup valid_until has passed",
            "is_terminal": True,
            "levels": levels,
        }

    missed_r = to_float(thresholds.get("missed_move_r_multiple"), 1.0)
    missed_atr = to_float(thresholds.get("missed_move_atr_multiple"), 1.5)
    tolerance = to_float(thresholds.get("tp_hit_tolerance_atr"), 0.1) * atr

    if side == "long":
        favorable = price - entry
        adverse_stop = price <= stop
        tp2_hit = price >= tp2 - tolerance
        tp1_hit = price >= tp1 - tolerance
        moved_beyond_tp1 = price >= tp1
    else:
        favorable = entry - price
        adverse_stop = price >= stop
        tp2_hit = price <= tp2 + tolerance
        tp1_hit = price <= tp1 + tolerance
        moved_beyond_tp1 = price <= tp1

    if adverse_stop:
        return {
            "state": "STOP_HIT",
            "reason": "current price has touched setup stop/invalidation",
            "is_terminal": True,
            "levels": levels,
        }
    if tp2_hit:
        return {
            "state": "TP2_HIT",
            "reason": "current price has touched second target",
            "is_terminal": True,
            "levels": levels,
        }
    if tp1_hit:
        return {
            "state": "TP1_HIT",
            "reason": "current price has touched first target",
            "is_terminal": False,
            "levels": levels,
        }

    moved_r = favorable / max(risk, 1e-9)
    moved_atr = favorable / max(atr, 1e-9)
    if moved_beyond_tp1 or moved_r >= missed_r or moved_atr >= missed_atr:
        return {
            "state": "MOVE_MISSED",
            "reason": "price has already moved too far from frozen entry",
            "is_terminal": True,
            "levels": levels,
            "moved_r": round(moved_r, 4),
            "moved_atr": round(moved_atr, 4),
        }

    return {
        "state": setup.get("last_lifecycle_state") or "SETUP_DETECTED",
        "reason": "setup remains active",
        "is_terminal": False,
        "levels": levels,
        "moved_r": round(moved_r, 4),
        "moved_atr": round(moved_atr, 4),
    }


def evaluate_lower_tf_trigger(
    side: Side,
    current_snapshot: dict[str, Any],
    lower_snapshot: dict[str, Any] | None,
    config: dict[str, Any] | None = None,
) -> dict[str, Any]:
    cfg = config or {}
    required_tf = (cfg.get("timeframe_mapping") or {}).get(str(current_snapshot.get("timeframe")))
    if required_tf and not lower_snapshot:
        return {
            "ready": False,
            "required_timeframe": required_tf,
            "missing": True,
            "state": "WAIT_LOWER_TF_CONFIRMATION",
            "diagnostics": [
                GateDiagnostic(
                    code="lower_tf_missing",
                    status="missing",
                    message=f"缺少 {required_tf} 次级触发周期数据，不能把方向优势直接升级为入场触发。",
                    severity="warning",
                ).to_dict()
            ],
        }
    return {"ready": False, "required_timeframe": required_tf, "missing": False, "diagnostics": []}


def evaluate_strong_trend_follow(
    side: Side, snapshot: dict[str, Any], config: dict[str, Any] | None = None
) -> dict[str, Any]:
    cfg = config or {}
    thresholds = cfg.get("thresholds", {})
    adx_min = to_float(thresholds.get("strong_trend_adx_min"), 25)
    momentum_min = to_float(thresholds.get("strong_trend_momentum_min"), 60)
    atr_expansion_min = to_float(thresholds.get("strong_trend_atr_expansion_min"), 60)
    flow_min = to_float(thresholds.get("strong_trend_flow_min"), 55)
    max_distance_atr = to_float(thresholds.get("chase_max_distance_atr"), 1.5)

    price = to_float(snapshot.get("current_price") or snapshot.get("price", {}).get("current"))
    atr = max(to_float(snapshot.get("atr_14"), price * 0.02), price * 0.002, 1e-9)
    adx = clamp(snapshot.get("adx_14"))
    atr_expansion = clamp(snapshot.get("atr_expansion_score"))
    if side == "long":
        trend_ok = (
            to_float(snapshot.get("ema_20")) >= to_float(snapshot.get("ema_50"))
            or to_float(snapshot.get("ema20_slope")) > 0
        )
        breakout = bool(
            snapshot.get("breakout_up") or snapshot.get("levels", {}).get("breakout_up")
        )
        momentum = clamp(snapshot.get("bullish_momentum"))
        flow = clamp(
            max(
                to_float(snapshot.get("bullish_flow")),
                to_float(snapshot.get("volume_confirmation")),
            )
        )
        trigger_level = to_float(snapshot.get("long_entry"), price)
        distance_atr = max(0.0, price - trigger_level) / atr
        triggered_state = "BREAKOUT_TRIGGERED" if breakout else "TREND_FOLLOW_TRIGGERED"
    else:
        trend_ok = (
            to_float(snapshot.get("ema_20")) <= to_float(snapshot.get("ema_50"))
            or to_float(snapshot.get("ema20_slope")) < 0
        )
        breakout = bool(
            snapshot.get("breakout_down") or snapshot.get("levels", {}).get("breakout_down")
        )
        momentum = clamp(snapshot.get("bearish_momentum"))
        flow = clamp(
            max(
                to_float(snapshot.get("bearish_flow")),
                to_float(snapshot.get("volume_confirmation")),
            )
        )
        trigger_level = to_float(snapshot.get("short_entry"), price)
        distance_atr = max(0.0, trigger_level - price) / atr
        triggered_state = "BREAKDOWN_TRIGGERED" if breakout else "TREND_FOLLOW_TRIGGERED"

    diagnostics = [
        GateDiagnostic(
            "strong_trend_adx",
            "pass" if adx >= adx_min else "fail",
            "ADX 趋势强度",
            round(adx, 2),
            adx_min,
        ).to_dict(),
        GateDiagnostic(
            "strong_trend_ema", "pass" if trend_ok else "fail", "EMA 方向一致", trend_ok, True
        ).to_dict(),
        GateDiagnostic(
            "strong_trend_momentum",
            "pass" if momentum >= momentum_min else "fail",
            "动量强度",
            round(momentum, 2),
            momentum_min,
        ).to_dict(),
        GateDiagnostic(
            "strong_trend_atr",
            "pass" if atr_expansion >= atr_expansion_min else "fail",
            "ATR 扩张",
            round(atr_expansion, 2),
            atr_expansion_min,
        ).to_dict(),
        GateDiagnostic(
            "strong_trend_flow",
            "pass" if flow >= flow_min else "warn",
            "成交/资金流确认",
            round(flow, 2),
            flow_min,
            "warning" if flow < flow_min else "info",
        ).to_dict(),
        GateDiagnostic(
            "chase_distance",
            "pass" if distance_atr <= max_distance_atr else "warn",
            "追单距离",
            round(distance_atr, 4),
            max_distance_atr,
            "warning" if distance_atr > max_distance_atr else "info",
        ).to_dict(),
    ]
    strong = (
        adx >= adx_min
        and trend_ok
        and momentum >= momentum_min
        and atr_expansion >= atr_expansion_min
    )
    if not strong:
        return {
            "ready": False,
            "state": None,
            "entry_mode": None,
            "distance_atr": round(distance_atr, 4),
            "diagnostics": diagnostics,
        }
    if distance_atr > max_distance_atr:
        return {
            "ready": False,
            "state": "WAIT_RETEST_AFTER_MISSED_MOVE",
            "entry_mode": "strong_trend_chase",
            "distance_atr": round(distance_atr, 4),
            "diagnostics": diagnostics,
            "reason": "强趋势成立，但当前价格离触发位过远，等待反抽/回踩更稳妥。",
        }
    return {
        "ready": True,
        "state": triggered_state,
        "entry_mode": "strong_trend_chase"
        if not breakout
        else ("breakout_follow" if side == "long" else "breakdown_follow"),
        "distance_atr": round(distance_atr, 4),
        "diagnostics": diagnostics,
    }


def apply_lifecycle_to_decision(
    decision: dict[str, Any], setup: dict[str, Any], lifecycle: dict[str, Any]
) -> dict[str, Any]:
    output = dict(decision)
    state = lifecycle.get("state") or output.get("strategy_state")
    side = setup.get("direction") or output.get("strategy_bias") or "neutral"
    output["strategy_state"] = state
    output["strategy_state_label"] = state
    output["strategy_bias"] = side
    output["dominant_direction"] = side
    output["setup_lifecycle"] = lifecycle
    output["active_setup"] = setup
    output["entry_mode"] = setup.get("entry_mode")
    primary_key = "long_plan" if side == "long" else "short_plan"
    primary = dict(output.get(primary_key) or output.get("primary_strategy") or {})
    primary.update(
        {
            "setup_id": setup.get("setup_id"),
            "entry_mode": setup.get("entry_mode"),
            "entry_price": setup.get("entry_price"),
            "entry_zone": [
                round(to_float(setup.get("entry_price")) * 0.998, 2),
                round(to_float(setup.get("entry_price")) * 1.002, 2),
            ],
            "entry_price_range": [
                round(to_float(setup.get("entry_price")) * 0.998, 2),
                round(to_float(setup.get("entry_price")) * 1.002, 2),
            ],
            "stop_price": setup.get("stop_price"),
            "take_profit_1": setup.get("take_profit_1"),
            "take_profit_2": setup.get("take_profit_2"),
            "risk_reward_ratio": setup.get("rr1"),
            "is_frozen_setup": True,
            "lifecycle_state": state,
        }
    )
    output[primary_key] = primary
    output["primary_strategy"] = primary
    return output
