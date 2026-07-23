from __future__ import annotations

import math
from copy import deepcopy
from dataclasses import asdict, dataclass, field
from datetime import datetime, timedelta, timezone
from decimal import ROUND_HALF_UP, Decimal, InvalidOperation
from typing import Any, Mapping, Sequence

from app.services.strategy_signal.config_loader import load_strategy_signal_config

from .contracts import TimeframeNode, as_mapping, first_float, list_floats, node_by_tf

UTC = timezone.utc

# Map of timeframe -> bar duration in hours. Mirrors
# `setup_lifecycle.bar_hours`; kept local so this module remains importable
# without pulling strategy_signal's full surface.
_BAR_HOURS = {
    "15m": 0.25,
    "30m": 0.5,
    "1h": 1,
    "4h": 4,
    "1d": 24,
    "1w": 168,
    "1M": 720,
    "30d": 720,
}


def _bars_to_iso(now: datetime, timeframe: str, bars: int) -> str:
    """Return ISO timestamp ``now + bars * bar_hours(timeframe)``.

    Used to convert a relative "valid for N bars" budget into an absolute
    wall-clock timestamp at decision build time.
    """
    delta_h = bars * _BAR_HOURS.get(timeframe, 1)
    return (now + timedelta(hours=delta_h)).isoformat()


def _next_close_iso(now: datetime, timeframe: str = "4h") -> str:
    """Return the ISO timestamp of the next bar close for ``timeframe``.

    Rounded up to the next bar boundary on the wall clock, so the value is
    stable across renders of the same decision.
    """
    secs = _BAR_HOURS.get(timeframe, 4) * 3600
    boundary = math.ceil(now.timestamp() / secs) * secs
    return datetime.fromtimestamp(boundary, tz=UTC).isoformat()


@dataclass(slots=True)
class TradeDecision:
    side: str
    status: str
    direction_source: str
    setup_timeframe: str
    trigger_timeframe: str
    filter_timeframe: str
    primary_reason: dict[str, str]
    secondary_reasons: list[dict[str, str]] = field(default_factory=list)
    entry_condition: str = ""
    entry_zone: list[float] = field(default_factory=list)
    invalidation: float | None = None
    risk_reward: dict[str, Any] = field(default_factory=dict)
    permission: str = "observe"
    position_cap: str = "observe"
    next_check: str = "next_4h_close"
    recommended_leverage: float = 0.0
    max_leverage: float = 0.0
    leverage_status: str = "blocked"
    leverage_reason: str = "当前条件不允许使用杠杆。"
    order_type: str = "NONE"
    order_status: str = "NO_DIRECTION"
    execution_price: float | None = None
    limit_price: float | None = None
    conflict_timeframe: str = ""
    confirmation_timeframe: str = ""
    price_condition: str = ""
    confirmation_condition: str = ""
    activation_conditions: list[str] = field(default_factory=list)
    price_protection: dict[str, Any] = field(default_factory=dict)
    valid_until: str = ""
    valid_until_iso: str = ""
    next_check_at_iso: str = ""
    # V1.7.x: Stale-plan awareness for conditional orders. When the
    # current price has drifted far enough from the planned entry zone
    # that the order cannot realistically trigger in the near term, the
    # frontend needs to surface that fact explicitly instead of letting
    # the plan stay in the table as if it were still actionable.
    plan_distance_pct: float = 0.0
    plan_stale_score: int = 0
    plan_stale_reason: str = ""
    planned_leverage: float = 0.0
    trade_timeframe: str = "4h"
    direction_timeframes: list[str] = field(default_factory=lambda: ["1d", "4h"])
    execution_timeframes: list[str] = field(default_factory=lambda: ["1h", "15m"])
    lifecycle_state: str = "SETUP_DETECTED"
    activated_at: str = ""
    invalidated_at: str = ""
    invalidation_reason: str = ""
    levels_active: bool = True

    def as_dict(self) -> dict[str, Any]:
        return asdict(self)


class TradeDecisionEngine:
    """Resolve one auditable 1D -> 4H -> 1H -> 15M execution chain."""

    def build(
        self,
        *,
        nodes: Sequence[TimeframeNode],
        bundles: Mapping[str, Mapping[str, Any]],
        risk_alerts: Sequence[Any],
        position_cap: str,
        next_check: str | None,
    ) -> TradeDecision:
        # Anchor all relative budgets (valid_until, next_check) to a single
        # wall-clock moment so the absolute timestamps agree with the relative
        # semantics inside this build.
        now_iso_dt = datetime.now(UTC)
        next_check_at_iso = (
            next_check
            if next_check and "T" in str(next_check)
            else _next_close_iso(now_iso_dt, "4h")
        )
        daily = node_by_tf(nodes, "1d")
        h4 = node_by_tf(nodes, "4h")
        h1 = node_by_tf(nodes, "1h")
        m15 = node_by_tf(nodes, "15m")
        warnings = [
            item for item in risk_alerts if str(getattr(item, "severity", "")).lower() == "warning"
        ]
        blockers = [
            item for item in risk_alerts if str(getattr(item, "severity", "")).lower() == "blocker"
        ]
        if blockers:
            primary = self._reason(
                "RISK_GATE_BLOCKED", str(getattr(blockers[0], "message", "风险门禁已触发。"))
            )
            secondary = [
                self._reason("RISK_GATE_DETAIL", str(getattr(item, "action", "等待风险解除。")))
                for item in blockers[1:]
            ]
            return self._decision(
                side="NONE",
                status="BLOCKED",
                primary=primary,
                secondary=secondary,
                permission="no_trade",
                position_cap="no_trade",
                next_check=next_check,
                next_check_at_iso=next_check_at_iso,
            )

        if daily is None or daily.freshness in {"missing", "error"}:
            return self._decision(
                side="NONE",
                status="BLOCKED",
                primary=self._reason("DAILY_DATA_UNAVAILABLE", "日线数据不足，无法建立方向许可。"),
                permission="no_trade",
                position_cap="no_trade",
                next_check=next_check,
                next_check_at_iso=next_check_at_iso,
            )
        if daily.direction not in {"LONG", "SHORT"}:
            return self._decision(
                side="NONE",
                status="NO_DIRECTION",
                primary=self._reason(
                    "DAILY_DIRECTION_UNCONFIRMED", "日线处于区间状态或转换阶段，尚未形成交易方向。"
                ),
                permission="observe",
                position_cap="observe",
                next_check=next_check,
                next_check_at_iso=next_check_at_iso,
            )

        side = daily.direction
        plans = self._legacy_plans(bundles, side)
        plan = plans[0] if plans else {}
        declared_caps = [
            cap
            for candidate in plans
            if (cap := first_float(candidate.get("max_leverage"))) is not None and cap > 0
        ]
        # Older cached plans either omitted max_leverage or serialized its new default as 0.
        # A valid directional plan therefore inherits the platform hard cap during migration;
        # the decision policy below still tightens it to 0/3/5 from setup and risk state.
        legacy_cap = max(declared_caps) if declared_caps else (5.0 if plans else 0.0)
        threshold = float(
            load_strategy_signal_config().get("thresholds", {}).get("min_rr_trade", 1.5)
        )
        entry_zone = list_floats(plan.get("entry_zone") or plan.get("entry_price_range"))
        invalidation = first_float(
            plan.get("stop_price"), plan.get("stop_loss"), daily.invalidation
        )
        entry_condition = str(
            plan.get("entry_condition") or plan.get("entry_logic") or self._default_entry(side)
        )
        current_price = first_float(
            m15.current_price if m15 else None,
            h1.current_price if h1 else None,
            h4.current_price if h4 else None,
            daily.current_price,
        )
        targets = self._take_profit_targets(plan)
        rr_payload = self._planned_risk_reward(
            side=side,
            entry_zone=entry_zone,
            fallback_entry=first_float(
                plan.get("entry_price"), plan.get("reference_price"), current_price
            ),
            stop=invalidation,
            targets=targets,
            threshold=threshold,
        )
        rr = first_float(rr_payload.get("value"))
        thresholds = load_strategy_signal_config().get("thresholds", {})
        price_protection = self._price_protection(plan, thresholds)
        common = {
            "entry_condition": entry_condition,
            "entry_zone": entry_zone,
            "invalidation": invalidation,
            "risk_reward": rr_payload,
            "position_cap": position_cap,
            "next_check": next_check,
            "next_check_at_iso": next_check_at_iso,
            "upstream_max_leverage": legacy_cap,
            "risk_downgraded": bool(warnings) or position_cap == "reduced",
            "execution_price": current_price,
            "price_protection": price_protection,
        }

        lifecycle_state = str(
            plan.get("lifecycle_state") or plan.get("state") or "SETUP_DETECTED"
        ).upper()
        active_states = {
            "LONG_TRIGGERED",
            "SHORT_TRIGGERED",
            "TREND_FOLLOW_TRIGGERED",
            "BREAKDOWN_TRIGGERED",
            "BREAKOUT_TRIGGERED",
            "TP1_HIT",
        }
        if self._invalidation_crossed(side, current_price, invalidation):
            stopped = lifecycle_state in active_states
            terminal_state = "STOP_HIT" if stopped else "SETUP_INVALIDATED"
            reason = (
                "已激活计划的实时价格越过止损位。"
                if stopped
                else "候选计划尚未入场，实时价格已越过失效位；旧计划禁止继续执行。"
            )
            return self._decision(
                side=side,
                status=terminal_state,
                primary=self._reason(terminal_state, reason),
                permission="no_trade",
                order_type="NONE",
                order_status="STOP_HIT" if stopped else "INVALIDATED",
                lifecycle_state=terminal_state,
                invalidated_at=now_iso_dt.isoformat(),
                invalidation_reason=reason,
                levels_active=False,
                **common,
            )

        if not rr_payload.get("valid"):
            return self._decision(
                side=side,
                status="INVALID_PLAN_LEVELS",
                primary=self._reason(
                    "INVALID_PLAN_LEVELS",
                    "入场、止损或止盈价位缺失或几何关系无效，计划已阻止执行。",
                ),
                permission="no_trade",
                order_type="NONE",
                order_status="BLOCKED",
                lifecycle_state="INVALID_PLAN_LEVELS",
                invalidation_reason=str(rr_payload.get("invalid_reason") or "invalid_levels"),
                levels_active=False,
                **common,
            )

        # Reward/risk is a plan-level admission gate, independent of whether
        # lower timeframes have aligned yet.  A geometrically complete plan
        # below the configured minimum must never remain an active candidate.
        if rr is not None and rr < threshold:
            return self._decision(
                side=side,
                status="BLOCKED",
                primary=self._reason(
                    "RISK_REWARD_BELOW_THRESHOLD",
                    f"当前盈亏比 {rr:.2f} 低于执行门槛 {threshold:.2f}。",
                ),
                secondary=[
                    self._reason(
                        "SETUP_DIRECTION_VALID",
                        "方向条件可继续观察，但该组入场、止损和止盈价位不具备执行资格。",
                    )
                ],
                permission="no_trade",
                order_type="NONE",
                order_status="BLOCKED",
                invalidation_reason="risk_reward_below_minimum",
                levels_active=False,
                **common,
            )

        if h4 is None or h4.freshness in {"missing", "error"}:
            return self._decision(
                side=side,
                status="BLOCKED",
                primary=self._reason(
                    "FOUR_HOUR_DATA_UNAVAILABLE", "4H 数据不足，不能建立最低交易级别判断。"
                ),
                permission="no_trade",
                order_type="NONE",
                order_status="BLOCKED",
                **common,
            )
        if h4.direction != side or self._is_transition(h4):
            direction = "多头" if side == "LONG" else "空头"
            return self._decision(
                side=side,
                status="WAIT_SETUP",
                primary=self._reason(
                    "WAIT_FOUR_HOUR_ALIGNMENT",
                    f"日线保留{direction}方向许可，但4H尚未同向；等待4H恢复后再评估入场。",
                ),
                permission="observe",
                order_type="NONE",
                order_status="WAIT_SETUP",
                conflict_timeframe="",
                confirmation_timeframe="4h",
                filter_timeframe="1h",
                confirmation_condition=self._confirmation_condition(side, "4h", "1h"),
                **common,
            )

        chain = [("1h", h1), ("15m", m15)]
        for index, (timeframe, node) in enumerate(chain):
            if node is None or node.freshness in {"missing", "error"}:
                return self._decision(
                    side=side,
                    status="BLOCKED",
                    primary=self._reason(
                        "EXECUTION_DATA_UNAVAILABLE",
                        f"{timeframe.upper()} 数据不足，不能生成订单计划。",
                    ),
                    permission="no_trade",
                    order_type="NONE",
                    order_status="BLOCKED",
                    **common,
                )
            transition = self._is_transition(node)
            if node.direction != side or transition:
                zone = entry_zone or self._conditional_zone(node, side)
                limit_price = sum(zone) / len(zone) if zone else None
                in_zone = self._in_zone(current_price, zone)
                next_tf = chain[index + 1][0] if index + 1 < len(chain) else ""
                order_status = "WAIT_CONFIRMATION" if in_zone else "WAIT_PRICE"
                price_condition = self._price_condition(side, zone)
                confirmation_condition = self._confirmation_condition(side, timeframe, next_tf)
                # V1.7.x: surface how far current price is from the entry
                # zone so the UI can warn when a "conditional limit" plan
                # has drifted out of realistic trigger range.
                plan_distance_pct, plan_stale_score, plan_stale_reason = (
                    self._plan_distance_and_staleness(
                        side, current_price, zone, "CONDITIONAL_LIMIT"
                    )
                )
                return self._decision(
                    side=side,
                    status="WAIT_TRIGGER",
                    primary=self._reason(
                        "WAIT_RECURSIVE_CONFIRMATION",
                        f"{timeframe.upper()} 尚未与日线方向一致，"
                        "等待价格进入候选区并完成顺势反转确认。",
                    ),
                    permission="conditional",
                    order_type="CONDITIONAL_LIMIT",
                    order_status=order_status,
                    limit_price=limit_price,
                    conflict_timeframe=timeframe,
                    confirmation_timeframe=timeframe,
                    filter_timeframe=next_tf,
                    price_condition=price_condition,
                    confirmation_condition=confirmation_condition,
                    activation_conditions=[price_condition, confirmation_condition],
                    planned_leverage=min(3.0, legacy_cap),
                    valid_until=(
                        f"{timeframe}:"
                        f"{int(thresholds.get('setup_valid_bars', {}).get(timeframe, 20))}_bars"
                    ),
                    valid_until_iso=_bars_to_iso(
                        now_iso_dt,
                        timeframe,
                        int(thresholds.get("setup_valid_bars", {}).get(timeframe, 20)),
                    ),
                    entry_zone=zone,
                    plan_distance_pct=plan_distance_pct,
                    plan_stale_score=plan_stale_score,
                    plan_stale_reason=plan_stale_reason,
                    **{key: value for key, value in common.items() if key != "entry_zone"},
                )

        market_rr = self._market_risk_reward(
            side,
            current_price,
            invalidation,
            targets[0] if targets else None,
        )
        if market_rr is not None:
            rr = market_rr
            rr_payload.update(
                value=rr,
                evaluable=True,
                passed=rr >= threshold,
                label="合格" if rr >= threshold else "低于门槛",
            )
        if rr is not None and rr < threshold:
            return self._decision(
                side=side,
                status="BLOCKED",
                primary=self._reason(
                    "MARKET_RISK_REWARD_BELOW_THRESHOLD",
                    f"按现价计算的盈亏比 {rr:.2f} 低于执行门槛 {threshold:.2f}。",
                ),
                permission="no_trade",
                order_type="NONE",
                order_status="BLOCKED",
                invalidation_reason="risk_reward_below_minimum",
                levels_active=False,
                **common,
            )
        if rr is None:
            return self._decision(
                side=side,
                status="BLOCKED",
                primary=self._reason(
                    "RISK_REWARD_UNAVAILABLE", "按现价无法计算盈亏比，不能执行市价单。"
                ),
                permission="observe",
                order_type="NONE",
                order_status="BLOCKED",
                **common,
            )
        if not price_protection["passed"]:
            return self._decision(
                side=side,
                status="BLOCKED",
                primary=self._reason(
                    "MARKET_PRICE_PROTECTION_FAILED", price_protection["reason"]
                ),
                permission="observe",
                order_type="NONE",
                order_status="BLOCKED",
                **common,
            )

        return self._decision(
            side=side,
            status="READY",
            primary=self._reason(
                "EXECUTION_READY", f"日线、4H 与 1H 已形成{self._side_cn(side)}执行链。"
            ),
            secondary=[]
            if rr is not None
            else [self._reason("RISK_REWARD_UNAVAILABLE", "执行前仍需补齐盈亏比。")],
            permission="conditional" if rr is None else "allow",
            order_type="MARKET",
            order_status="READY",
            **common,
        )

    @staticmethod
    def _reason(code: str, message: str) -> dict[str, str]:
        return {"code": code, "message": message}

    def _decision(
        self,
        *,
        side: str,
        status: str,
        primary: dict[str, str],
        secondary: list[dict[str, str]] | None = None,
        permission: str,
        position_cap: str,
        next_check: str | None,
        next_check_at_iso: str = "",
        entry_condition: str = "",
        entry_zone: list[float] | None = None,
        invalidation: float | None = None,
        risk_reward: dict[str, Any] | None = None,
        upstream_max_leverage: float = 0.0,
        risk_downgraded: bool = False,
        order_type: str = "NONE",
        order_status: str = "NO_DIRECTION",
        execution_price: float | None = None,
        limit_price: float | None = None,
        conflict_timeframe: str = "",
        confirmation_timeframe: str = "",
        filter_timeframe: str = "15m",
        price_condition: str = "",
        confirmation_condition: str = "",
        activation_conditions: list[str] | None = None,
        price_protection: dict[str, Any] | None = None,
        valid_until: str = "",
        valid_until_iso: str = "",
        plan_distance_pct: float = 0.0,
        plan_stale_score: int = 0,
        plan_stale_reason: str = "",
        planned_leverage: float = 0.0,
        lifecycle_state: str = "SETUP_DETECTED",
        activated_at: str = "",
        invalidated_at: str = "",
        invalidation_reason: str = "",
        levels_active: bool = True,
    ) -> TradeDecision:
        leverage = self._leverage_policy(
            status=status,
            permission=permission,
            position_cap=position_cap,
            risk_reward=risk_reward or {},
            upstream_max=upstream_max_leverage,
            risk_downgraded=risk_downgraded,
        )
        if order_type == "CONDITIONAL_LIMIT":
            leverage = {
                "recommended_leverage": 0.0,
                "max_leverage": 0.0,
                "leverage_status": "planned",
                "leverage_reason": "条件尚未同时满足；当前不使用杠杆，激活后按计划上限执行。",
            }
        return TradeDecision(
            side=side,
            status=status,
            direction_source="1d+4h" if side != "NONE" else "",
            setup_timeframe="4h",
            trigger_timeframe="1h",
            primary_reason=primary,
            secondary_reasons=secondary or [],
            entry_condition=entry_condition,
            entry_zone=entry_zone or [],
            invalidation=invalidation,
            risk_reward=risk_reward
            or {
                "value": None,
                "evaluable": False,
                "passed": False,
                "label": "计划价位不完整",
                "basis": "planned_entry",
                "entry_price_used": None,
                "risk_amount": None,
                "reward_amount": None,
                "tp1_ratio": None,
                "tp2_ratio": None,
                "minimum_required": float(
                    load_strategy_signal_config()
                    .get("thresholds", {})
                    .get("min_rr_trade", 1.5)
                ),
                "valid": False,
                "invalid_reason": "missing_plan_levels",
                "formula": "reward_amount / risk_amount",
            },
            permission=permission,
            position_cap=position_cap,
            next_check=next_check or "next_4h_close",
            next_check_at_iso=next_check_at_iso,
            order_type=order_type,
            order_status=order_status,
            execution_price=execution_price,
            limit_price=limit_price,
            conflict_timeframe=conflict_timeframe,
            confirmation_timeframe=confirmation_timeframe,
            filter_timeframe=filter_timeframe,
            price_condition=price_condition,
            confirmation_condition=confirmation_condition,
            activation_conditions=activation_conditions or [],
            price_protection=price_protection or {},
            valid_until=valid_until,
            valid_until_iso=valid_until_iso,
            plan_distance_pct=plan_distance_pct,
            plan_stale_score=plan_stale_score,
            plan_stale_reason=plan_stale_reason,
            planned_leverage=planned_leverage,
            lifecycle_state=lifecycle_state,
            activated_at=activated_at,
            invalidated_at=invalidated_at,
            invalidation_reason=invalidation_reason,
            levels_active=levels_active,
            **leverage,
        )

    @staticmethod
    def _leverage_policy(
        *,
        status: str,
        permission: str,
        position_cap: str,
        risk_reward: Mapping[str, Any],
        upstream_max: float,
        risk_downgraded: bool,
    ) -> dict[str, Any]:
        hard_cap = max(0.0, min(5.0, float(upstream_max or 0.0)))
        if permission == "no_trade" or status in {
            "BLOCKED",
            "NO_DIRECTION",
            "WAIT_SETUP",
            "WAIT_TRIGGER",
        }:
            return {
                "recommended_leverage": 0.0,
                "max_leverage": 0.0,
                "leverage_status": "blocked",
                "leverage_reason": "方向、形态或风险门禁尚未允许杠杆交易。",
            }
        full_alignment = (
            status == "READY"
            and permission == "allow"
            and position_cap == "standard"
            and risk_reward.get("passed") is True
            and not risk_downgraded
        )
        target = 5.0 if full_alignment else 3.0
        cap = min(target, hard_cap)
        if cap <= 0:
            return {
                "recommended_leverage": 0.0,
                "max_leverage": 0.0,
                "leverage_status": "unavailable",
                "leverage_reason": "上游计划尚未给出可用杠杆上限。",
            }
        return {
            "recommended_leverage": cap,
            "max_leverage": cap,
            "leverage_status": "full_alignment" if full_alignment and cap >= 5 else "risk_adjusted",
            "leverage_reason": (
                "1D、4H、1H同向，15M过滤通过，盈亏比达标且无风险降级。"
                if full_alignment and cap >= 5
                else "当前计划可执行，但按风险状态限制在3倍以内。"
            ),
        }

    @staticmethod
    def _is_transition(node: TimeframeNode) -> bool:
        state = f"{node.structure_state} {node.state} {node.timeframe_state}".upper()
        return any(token in state for token in ("TRANSITION", "CONVERT", "转换", "转折"))

    @staticmethod
    def _conditional_zone(node: TimeframeNode, side: str) -> list[float]:
        anchor = node.key_support if side == "LONG" else node.key_resistance
        if anchor is None or anchor <= 0:
            return []
        return [round(anchor * 0.998, 2), round(anchor * 1.002, 2)]

    @staticmethod
    def _in_zone(price: float | None, zone: Sequence[float]) -> bool:
        return price is not None and bool(zone) and min(zone) <= price <= max(zone)

    @staticmethod
    def _plan_distance_and_staleness(
        side: str,
        current_price: float | None,
        zone: Sequence[float],
        order_type: str,
    ) -> tuple[float, int, str]:
        """Compute (distance_pct, stale_score 0-100, reason) for a
        conditional limit plan relative to the live price.

        * ``distance_pct`` — signed % gap from current_price to the
          *closer* edge of the zone (positive = price must travel
          *toward* the zone to trigger). For SHORT plans, price must
          drop back to the zone; for LONG plans, price must rally up.
        * ``stale_score`` — 0 / 50 / 100. 50 = "warning, the user should
          notice the gap". 100 = effectively unreachable without a
          regime change, surface as 已过期 / 等待重新评估.
        * ``reason`` — short Chinese label shown in the trigger row.

        Thresholds: ±1.5% is "warning", ≥3.0% is "stale" (zone isn't
        really reachable inside the planned validity window without an
        unlikely move against the current trend).
        """
        if order_type != "CONDITIONAL_LIMIT" or not zone or current_price is None:
            return 0.0, 0, ""
        if not all(isinstance(value, (int, float)) and math.isfinite(value) for value in zone):
            return 0.0, 0, ""
        min_zone = min(zone)
        max_zone = max(zone)
        if min_zone <= current_price <= max_zone:
            # Already inside the zone — gap is 0 in the right direction.
            return 0.0, 0, ""
        # Direction of travel needed for the plan to trigger:
        # SHORT = price must come down to the zone from above → gap to
        # max_zone. LONG = price must rally up to the zone from below →
        # gap to min_zone.
        if side == "SHORT" or side == "BEARISH":
            target = max_zone
        else:
            target = min_zone
        gap = abs(target - current_price)
        distance_pct = round(gap / current_price * 100, 2) if current_price else 0.0
        if distance_pct >= 3.0:
            return distance_pct, 100, "已远离入场区，等待主趋势重新对齐"
        if distance_pct >= 1.5:
            return distance_pct, 50, "价格需先顺趋势运行"
        return distance_pct, 0, ""

    @staticmethod
    def _price_condition(side: str, zone: Sequence[float]) -> str:
        if not zone:
            return "等待关键价格区域生成"
        action = "回踩" if side == "LONG" else "反弹"
        return f"价格{action}进入 {min(zone):.2f}–{max(zone):.2f}"

    @staticmethod
    def _confirmation_condition(side: str, timeframe: str, filter_timeframe: str) -> str:
        direction = "多头" if side == "LONG" else "空头"
        filter_copy = f"，且 {filter_timeframe.upper()} 过滤通过" if filter_timeframe else ""
        return f"{timeframe.upper()} 恢复{direction}结构并收盘确认{filter_copy}"

    @staticmethod
    def _market_risk_reward(
        side: str,
        price: float | None,
        stop: float | None,
        target: float | None,
    ) -> float | None:
        if price is None or stop is None or target is None:
            return None
        risk = price - stop if side == "LONG" else stop - price
        reward = target - price if side == "LONG" else price - target
        if risk <= 0 or reward <= 0:
            return None
        return round(reward / risk, 4)

    @staticmethod
    def _invalidation_crossed(
        side: str, price: float | None, stop: float | None
    ) -> bool:
        if price is None or stop is None:
            return False
        return price <= stop if side == "LONG" else price >= stop

    @staticmethod
    def _take_profit_targets(plan: Mapping[str, Any]) -> list[float]:
        targets = list_floats(
            [
                plan.get("take_profit_1"),
                plan.get("take_profit_2"),
                plan.get("take_profit")
                if not isinstance(plan.get("take_profit"), (list, tuple))
                else None,
            ]
        )
        rows = plan.get("take_profit")
        if isinstance(rows, Sequence) and not isinstance(rows, (str, bytes)):
            targets.extend(
                value
                for row in rows
                if isinstance(row, Mapping)
                and (value := first_float(row.get("price"), row.get("value")))
                is not None
            )
        return list(dict.fromkeys(targets))

    @classmethod
    def _planned_risk_reward(
        cls,
        *,
        side: str,
        entry_zone: Sequence[float],
        fallback_entry: float | None,
        stop: float | None,
        targets: Sequence[float],
        threshold: float,
    ) -> dict[str, Any]:
        """Calculate plan R:R from the least favourable fill in an entry zone."""
        valid_zone = [
            value
            for raw in entry_zone
            if (value := cls._as_decimal(raw)) is not None
        ]
        if valid_zone:
            entry = max(valid_zone) if side == "LONG" else min(valid_zone)
            basis = "conservative_entry_zone_edge"
        else:
            entry = cls._as_decimal(fallback_entry)
            basis = "planned_entry"
        stop_decimal = cls._as_decimal(stop)
        tp1 = cls._as_decimal(targets[0]) if targets else None
        tp2 = cls._as_decimal(targets[1]) if len(targets) > 1 else None
        risk = (
            entry - stop_decimal
            if side == "LONG" and entry is not None and stop_decimal is not None
            else stop_decimal - entry
            if entry is not None and stop_decimal is not None
            else None
        )
        reward = (
            tp1 - entry
            if side == "LONG" and entry is not None and tp1 is not None
            else entry - tp1
            if entry is not None and tp1 is not None
            else None
        )
        reward_2 = (
            tp2 - entry
            if side == "LONG" and entry is not None and tp2 is not None
            else entry - tp2
            if entry is not None and tp2 is not None
            else None
        )
        valid = bool(risk is not None and reward is not None and risk > 0 and reward > 0)
        tp1_rr_decimal = (
            (reward / risk).quantize(Decimal("0.00000001"), rounding=ROUND_HALF_UP)
            if valid and reward is not None and risk is not None
            else None
        )
        tp2_rr_decimal = (
            (reward_2 / risk).quantize(Decimal("0.00000001"), rounding=ROUND_HALF_UP)
            if risk is not None and risk > 0 and reward_2 is not None and reward_2 > 0
            else None
        )
        tp1_rr = float(tp1_rr_decimal) if tp1_rr_decimal is not None else None
        if entry is None:
            invalid_reason = "missing_entry"
        elif stop_decimal is None:
            invalid_reason = "missing_stop"
        elif tp1 is None:
            invalid_reason = "missing_take_profit_1"
        elif not valid:
            invalid_reason = "invalid_price_geometry"
        else:
            invalid_reason = ""
        return {
            "value": tp1_rr,
            "threshold": threshold,
            "evaluable": valid,
            "passed": valid and tp1_rr >= threshold,
            "label": (
                "合格"
                if valid and tp1_rr >= threshold
                else "低于门槛"
                if valid
                else "计划价位无效"
            ),
            "basis": basis,
            "entry_price_used": cls._decimal_string(entry),
            "risk_amount": cls._decimal_string(risk),
            "reward_amount": cls._decimal_string(reward),
            "tp1_ratio": cls._decimal_string(tp1_rr_decimal),
            "tp2_ratio": cls._decimal_string(tp2_rr_decimal),
            "minimum_required": threshold,
            "valid": valid,
            "invalid_reason": invalid_reason,
            "formula": "reward_amount / risk_amount",
        }

    @staticmethod
    def _as_decimal(value: Any) -> Decimal | None:
        if value is None or value == "":
            return None
        try:
            decimal = Decimal(str(value))
        except (InvalidOperation, ValueError, TypeError):
            return None
        return decimal if decimal.is_finite() else None

    @staticmethod
    def _decimal_string(value: Decimal | None) -> str | None:
        if value is None:
            return None
        return format(value.normalize(), "f")

    @staticmethod
    def _price_protection(plan: Mapping[str, Any], thresholds: Mapping[str, Any]) -> dict[str, Any]:
        execution = as_mapping(plan.get("execution_quality"))
        chase = first_float(
            plan.get("chase_distance_atr"), execution.get("chase_distance_atr")
        )
        spread = first_float(plan.get("spread_bps"), execution.get("spread_bps"))
        slippage = first_float(plan.get("slippage_bps"), execution.get("slippage_bps"))
        limits = {
            "chase_distance_atr": float(thresholds.get("chase_max_distance_atr", 1.5)),
            "spread_bps": float(thresholds.get("spread_hard_limit_bps", 25)),
            "slippage_bps": float(thresholds.get("slippage_hard_limit_bps", 40)),
        }
        values = {
            "chase_distance_atr": chase,
            "spread_bps": spread,
            "slippage_bps": slippage,
        }
        missing = [key for key, value in values.items() if value is None]
        failed = [
            key for key, value in values.items() if value is not None and value > limits[key]
        ]
        if missing:
            reason = f"缺少市价保护数据：{', '.join(missing)}。"
        elif failed:
            reason = f"市价保护未通过：{', '.join(failed)} 超出上限。"
        else:
            reason = "追价距离、点差和滑点均在允许范围内。"
        return {
            "passed": not missing and not failed,
            "values": values,
            "limits": limits,
            "reason": reason,
        }

    @staticmethod
    def _legacy_plan(bundles: Mapping[str, Mapping[str, Any]], side: str) -> dict[str, Any]:
        plans = TradeDecisionEngine._legacy_plans(bundles, side)
        return plans[0] if plans else {}

    @staticmethod
    def _legacy_plans(
        bundles: Mapping[str, Mapping[str, Any]], side: str
    ) -> list[dict[str, Any]]:
        plan_key = "short_plan" if side == "SHORT" else "long_plan"
        plans: list[dict[str, Any]] = []
        for timeframe in ("4h", "1d", "1h"):
            decision = as_mapping(as_mapping(bundles.get(timeframe)).get("decision"))
            directional = as_mapping(decision.get(plan_key))
            primary = as_mapping(decision.get("primary_strategy"))
            if directional:
                plans.append(directional)
            if primary and primary != directional:
                plans.append(primary)
        return plans

    @staticmethod
    def _side_cn(side: str) -> str:
        return "顺势做空" if side == "SHORT" else "顺势做多"

    @staticmethod
    def _default_entry(side: str) -> str:
        return (
            "等待 4H 反抽失败或支撑破位，并由 1H 确认。"
            if side == "SHORT"
            else "等待 4H 回踩企稳或阻力突破，并由 1H 确认。"
        )


def reconcile_cached_strategy(
    payload: Mapping[str, Any],
    *,
    latest_price: Any,
    price_as_of: str,
    price_source: str,
) -> tuple[dict[str, Any], bool]:
    """Fail closed when a cached candidate plan has crossed invalidation.

    The cached page snapshot may outlive a fast mark-price update. This guard is
    intentionally lightweight and does not attempt to synthesize a new direction;
    it only prevents an invalid candidate from remaining actionable while the
    full unified recompute is queued.
    """
    result = deepcopy(dict(payload or {}))
    result["price_as_of"] = price_as_of
    result["price_source"] = price_source
    latest_decimal = TradeDecisionEngine._as_decimal(latest_price)
    snapshot = result.get("market_decision_snapshot")
    if isinstance(snapshot, dict):
        snapshot.update(
            {
                "price": TradeDecisionEngine._decimal_string(latest_decimal),
                "price_as_of": price_as_of,
                "price_source": price_source,
            }
        )
    latest_float = first_float(latest_price)
    state = result.setdefault("unified_state", {})
    state["current_price"] = latest_float
    decision = result.get("trade_decision")
    if not isinstance(decision, dict):
        return result, False
    decision["execution_price"] = latest_float
    side = str(decision.get("side") or "").upper()
    stop = first_float(decision.get("invalidation"))
    lifecycle = str(decision.get("lifecycle_state") or "SETUP_DETECTED").upper()
    terminal = {
        "SETUP_INVALIDATED",
        "STOP_HIT",
        "TP2_HIT",
        "SETUP_EXPIRED",
        "INVALID_PLAN_LEVELS",
    }
    if side not in {"LONG", "SHORT"} or lifecycle in terminal:
        return result, False
    if not TradeDecisionEngine._invalidation_crossed(side, latest_float, stop):
        return result, False

    active_states = {
        "LONG_TRIGGERED",
        "SHORT_TRIGGERED",
        "TREND_FOLLOW_TRIGGERED",
        "BREAKDOWN_TRIGGERED",
        "BREAKOUT_TRIGGERED",
        "TP1_HIT",
    }
    stopped = lifecycle in active_states
    lifecycle = "STOP_HIT" if stopped else "SETUP_INVALIDATED"
    reason = (
        "已激活计划的实时价格越过止损位。"
        if stopped
        else "候选计划尚未入场，实时价格已越过失效位；旧计划已作废，正在重新推演。"
    )
    decision.update(
        {
            "status": lifecycle,
            "permission": "no_trade",
            "order_type": "NONE",
            "order_status": "STOP_HIT" if stopped else "INVALIDATED",
            "lifecycle_state": lifecycle,
            "invalidated_at": price_as_of,
            "invalidation_reason": reason,
            "primary_reason": {"code": lifecycle, "message": reason},
            "recommended_leverage": 0.0,
            "max_leverage": 0.0,
            "levels_active": False,
        }
    )
    state.update(
        {
            "permission": "no_trade",
            "position_cap": "no_trade",
            "instruction": reason,
        }
    )
    for plan in result.get("trade_plans") or []:
        if not isinstance(plan, dict) or str(plan.get("direction") or "").upper() != side:
            continue
        plan.update(
            {
                "permission": "no_trade",
                "order_type": "NONE",
                "order_status": "INVALIDATED",
                "lifecycle_state": lifecycle,
                "invalidated_at": price_as_of,
                "invalidation_reason": reason,
                "recommended_leverage": 0.0,
                "max_leverage": 0.0,
                "levels_active": False,
            }
        )
    result["recompute_status"] = "enqueued"
    return result, True
