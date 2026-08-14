"""Gold Workbench decision service — policy read + decision derivation.

The gold-allocation page aggregates three independent sources into one
decision: the user's portfolio policy (``gold_policy_versions``), the
XAUT proxy market state (price / drawdown / indicators), and macro
scenarios. This module owns the policy side: it reads the latest
versioned policy and execution history, then derives the
``strategic_allocation`` / ``base_dca`` / ``dip_add`` blocks that
gold_v5.js renders.

All money amounts are Decimal end-to-end (AGENTS.md §三: no float for
money); stringified only at the payload boundary for JSON portability.
"""
from __future__ import annotations

from datetime import date, datetime, time, timezone
from decimal import Decimal
from typing import Any

from sqlalchemy import desc, select
from sqlalchemy.ext.asyncio import AsyncSession

from app.db.models.market import GoldExecutionEvent, GoldPolicyVersion


def decimal_string(value: Decimal | None) -> str | None:
    """Stable JSON-safe Decimal serialization (no scientific notation)."""
    return format(value, "f") if value is not None else None


class GoldPolicyRepository:
    """Read-side repository for versioned gold policy + execution events."""

    def __init__(self, session: AsyncSession) -> None:
        self.session = session

    async def latest(self, tenant_id: str, user_id: str) -> GoldPolicyVersion | None:
        result = await self.session.execute(
            select(GoldPolicyVersion)
            .where(
                GoldPolicyVersion.tenant_id == tenant_id,
                GoldPolicyVersion.user_id == user_id,
            )
            .order_by(desc(GoldPolicyVersion.version))
            .limit(1)
        )
        return result.scalar_one_or_none()

    async def execution_state(self, tenant_id: str, user_id: str) -> dict[str, Any]:
        """Derive ``executed_today`` / ``last_dip_add_date`` from append-only events.

        ``executed_today`` is true when a BASE_DCA_EXECUTED event exists with
        ``executed_at`` on the current UTC day; ``last_dip_add_date`` is the
        most recent DIP_ADD_EXECUTED date (cooldown is computed against it).
        """
        utc_today = datetime.now(timezone.utc).date()
        day_start = datetime.combine(utc_today, time.min, tzinfo=timezone.utc)
        rows = await self.session.execute(
            select(GoldExecutionEvent)
            .where(
                GoldExecutionEvent.tenant_id == tenant_id,
                GoldExecutionEvent.user_id == user_id,
            )
            .order_by(desc(GoldExecutionEvent.executed_at))
            .limit(200)
        )
        events = list(rows.scalars())

        def as_utc(value: datetime) -> datetime:
            if value.tzinfo is None:
                return value.replace(tzinfo=timezone.utc)
            return value.astimezone(timezone.utc)

        return {
            "executed_today": any(
                event.event_type == "BASE_DCA_EXECUTED"
                and as_utc(event.executed_at) >= day_start
                for event in events
            ),
            "last_dip_add_date": next(
                (
                    as_utc(event.executed_at).date()
                    for event in events
                    if event.event_type == "DIP_ADD_EXECUTED"
                ),
                None,
            ),
        }


def policy_dict(model: GoldPolicyVersion) -> dict[str, Any]:
    return {
        "policy_id": model.policy_id,
        "version": model.version,
        "base_currency": model.base_currency,
        "portfolio_total": decimal_string(model.portfolio_total),
        "gold_current_value": decimal_string(model.gold_current_value),
        "available_cash": decimal_string(model.available_cash),
        "target_min": decimal_string(model.target_min),
        "target_max": decimal_string(model.target_max),
        "base_dca_amount": decimal_string(model.base_dca_amount),
        "fixed_dip_add_amount": decimal_string(model.fixed_dip_add_amount),
        "cooldown_days": model.cooldown_days,
        "quote_max_age_seconds": model.quote_max_age_seconds,
        "confirmations_required": model.confirmations_required,
        "drawdown_threshold": decimal_string(model.drawdown_threshold),
        "pause_base_when_overweight": model.pause_base_when_overweight,
        "created_at": model.created_at,
    }


def build_gold_decisions(
    policy: GoldPolicyVersion,
    *,
    quote_age_seconds: int | None,
    drawdown_60d: Decimal | None,
    confirmations_passed: int,
    liquidity_shock: bool,
    executed_today: bool,
    last_dip_add_date: date | None,
) -> dict[str, Any]:
    """Derive the three workbench decision blocks from policy + market inputs.

    Allocation band: gold weight vs ``[target_min, target_max]`` →
    STRATEGIC_UNDERWEIGHT / STRATEGIC_WITHIN_RANGE / STRATEGIC_OVERWEIGHT_NO_SELL
    (overweight never triggers a sell by policy default — only pauses).

    Base DCA status precedence (first match wins):
    invalid amount → stale quote → already executed today → insufficient
    cash → explicit portfolio pause → EXECUTE.

    Dip-add status precedence (first match wins):
    invalid amount → stale quote → cooldown → allocation cap → insufficient
    cash → liquidity shock → drawdown not reached → confirmations not met →
    READY_FIXED_ADD.
    """
    weight = policy.gold_current_value / policy.portfolio_total
    if weight < policy.target_min:
        allocation_state = "STRATEGIC_UNDERWEIGHT"
        gap = policy.portfolio_total * policy.target_min - policy.gold_current_value
    elif weight > policy.target_max:
        allocation_state = "STRATEGIC_OVERWEIGHT_NO_SELL"
        gap = Decimal("0")
    else:
        allocation_state = "STRATEGIC_WITHIN_RANGE"
        gap = Decimal("0")

    base_reasons: list[str] = []
    base_amount = policy.base_dca_amount
    if policy.base_dca_amount <= 0:
        base_status, base_amount = "BLOCKED_INVALID_AMOUNT", Decimal("0")
        base_reasons.append("INVALID_CONFIGURED_AMOUNT")
    elif quote_age_seconds is None or quote_age_seconds > policy.quote_max_age_seconds:
        base_status, base_amount = "BLOCKED_STALE_QUOTE", Decimal("0")
        base_reasons.append("STALE_OR_MISSING_QUOTE")
    elif executed_today:
        base_status, base_amount = "ALREADY_EXECUTED", Decimal("0")
        base_reasons.append("ALREADY_EXECUTED_TODAY")
    elif policy.available_cash is not None and policy.available_cash < policy.base_dca_amount:
        base_status, base_amount = "BLOCKED_INSUFFICIENT_CASH", Decimal("0")
        base_reasons.append("INSUFFICIENT_CASH")
    elif allocation_state == "STRATEGIC_OVERWEIGHT_NO_SELL" and policy.pause_base_when_overweight:
        base_status, base_amount = "PAUSED_BY_EXPLICIT_PORTFOLIO_POLICY", Decimal("0")
        base_reasons.append("EXPLICIT_PORTFOLIO_POLICY_CAP")
    else:
        base_status = "EXECUTE"
        base_reasons.append("BASE_DCA_DUE")

    dip_reasons: list[str] = []
    dip_amount = Decimal("0")
    cooldown_until = (
        date.fromordinal(last_dip_add_date.toordinal() + policy.cooldown_days)
        if last_dip_add_date
        else None
    )
    if policy.fixed_dip_add_amount <= 0:
        dip_status = "BLOCKED_INVALID_FIXED_AMOUNT"
        dip_reasons.append("INVALID_FIXED_DIP_AMOUNT")
    elif quote_age_seconds is None or quote_age_seconds > policy.quote_max_age_seconds:
        dip_status = "BLOCKED_STALE_QUOTE"
        dip_reasons.append("STALE_OR_MISSING_QUOTE")
    elif cooldown_until and datetime.now(timezone.utc).date() < cooldown_until:
        dip_status = "COOLDOWN"
        dip_reasons.append("DIP_ADD_COOLDOWN")
    elif allocation_state == "STRATEGIC_OVERWEIGHT_NO_SELL":
        dip_status = "BLOCKED_OVERWEIGHT"
        dip_reasons.append("ALLOCATION_CAP_REACHED")
    elif policy.available_cash is not None and policy.available_cash < policy.fixed_dip_add_amount:
        dip_status = "BLOCKED_INSUFFICIENT_CASH"
        dip_reasons.append("INSUFFICIENT_CASH")
    elif liquidity_shock:
        dip_status = "BLOCKED_LIQUIDITY_SHOCK"
        dip_reasons.append("LIQUIDITY_SHOCK")
    elif drawdown_60d is None or abs(drawdown_60d) < policy.drawdown_threshold:
        dip_status = "WAIT_DRAWDOWN"
        dip_reasons.append("DRAWDOWN_NOT_REACHED")
    elif confirmations_passed < policy.confirmations_required:
        dip_status = "SETUP_FORMING"
        dip_reasons.append("CONFIRMATIONS_INSUFFICIENT")
    else:
        dip_status = "READY_FIXED_ADD"
        dip_amount = policy.fixed_dip_add_amount
        dip_reasons.append("DIP_ADD_TRIGGERED")

    return {
        "portfolio": {
            "policy_id": policy.policy_id,
            "policy_version": policy.version,
            "base_currency": policy.base_currency,
            "portfolio_total": decimal_string(policy.portfolio_total),
            "gold_current_value": decimal_string(policy.gold_current_value),
            "available_cash": decimal_string(policy.available_cash),
        },
        "strategic_allocation": {
            "allocation_state": allocation_state,
            "current_weight": decimal_string(weight),
            "target_min": decimal_string(policy.target_min),
            "target_max": decimal_string(policy.target_max),
            "gap_amount": decimal_string(gap),
            "no_sell_default": True,
        },
        "base_dca": {
            "status": base_status,
            "amount": decimal_string(base_amount),
            "reason_codes": base_reasons,
            "action_now": (
                f"执行今日基础定投 {decimal_string(base_amount)} {policy.base_currency}。"
                if base_status == "EXECUTE"
                else "今日基础定投不执行；按原因码处理后再评估。"
            ),
        },
        "dip_add": {
            "status": dip_status,
            "mode": "fixed_amount",
            "amount": decimal_string(dip_amount),
            "reason_codes": dip_reasons,
            "confirmations": {
                "passed": confirmations_passed,
                "required": policy.confirmations_required,
            },
            "drawdown_60d": decimal_string(drawdown_60d),
            "drawdown_threshold": decimal_string(policy.drawdown_threshold),
            "cooldown_until": cooldown_until.isoformat() if cooldown_until else None,
            "action_now": (
                f"执行固定黄金坑加仓 {decimal_string(dip_amount)} {policy.base_currency}。"
                if dip_status == "READY_FIXED_ADD"
                else "不执行黄金坑加仓；基础定投按独立状态处理。"
            ),
        },
    }
