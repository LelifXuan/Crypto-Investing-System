# ruff: noqa: E501
"""Leverage sizing engine for the unified AI strategy.

Why this module exists
----------------------
The legacy decision policy (``TradeDecisionEngine._leverage_policy``) only
handed out three buckets: 0x / 3x / 5x, driven by setup alignment and risk
downgrades. That silently assumes every plan can tolerate the same margin
impact, which is false: a plan whose stop sits 0.4% from entry liquidates at
3x on the first adverse wiggle, while a plan with a 4% stop barely notices 5x.

This engine answers two questions per candidate plan, using only values the
unified pipeline already owns:

1. **Given stop distance, per-trade risk budget and ATR, what leverage range
   keeps the position alive?** A stop that is further than ``100 / L``
   (the cross-margin liquidation distance at leverage L, in percent) means
   the maintenance margin call fires *before* the protective stop can fill.
   The liquidation buffer below gates such choices down or to zero.
2. **What is the single "optimal" leverage inside that safe range?** We pick
   the highest leverage whose stop-loss margin impact stays within the
   per-trade risk budget. The budget is expressed as *"if the stop fills,
   at most X% of the allocated margin is lost"* (default 15%): the rest of
   the margin stays behind as excursion buffer, fees and funding headroom.
   This is intentionally conservative: it maximises capital efficiency only
   inside the survival envelope, never by widening the envelope.

Money/precision rules (AGENTS.md §三)
-------------------------------------
All percentages arrive as floats from the strategy stack (stop distance %,
ATR %, risk budgets). Money math itself (risk_amount / reward_amount) already
lives in ``TradeDecisionEngine._planned_risk_reward`` with Decimal; this
module rounds its *leverage outputs* to integers because the UI-facing
recommendation only uses whole leverage steps, while the internals keep full
float precision for the buffer math. No float is ever stored as money:
outputs are leverage multiples + informational margin-impact percents, never
amounts. Position sizing against equity (capital_pct) stays separate: this
module answers "how much leverage can this stop geometry support", not
"how much equity to risk".

Inputs
------
- ``stop_distance_pct``: |entry - stop| / entry * 100. Must be > 0.
- ``atr_pct``: normalised ATR (natr_14) in percent. Optional; when missing the
  ATR-based buffer check is skipped (fail-open on that single gate, recorded
  in ``reasons``).
- ``risk_budget_pct``: max margin impact the trader accepts if the stop
  fills, in percent of *allocated margin* (``stop_distance_pct * L``).
  Default 15.0.
- ``liquidation_buffer_min_pct``: minimum headroom between the stop and the
  approximate liquidation price. Default 1.5 (= ``liquidation_buffer_block_pct``).
- ``hard_cap``: upstream platform cap (legacy plan ``max_leverage``,
  clamped to [0, 5] by the decision policy). The recommendation never
  exceeds it.
- ``atr_buffer_min_pct``: minimum headroom between a one-ATR adverse move
  and liquidation. Default 0.0 (ATR excursion is reported, not gating,
  unless the caller raises it).

Outputs (``LeverageRecommendation.as_dict()``)
----------------------------------------------
- ``recommended_leverage`` / ``max_leverage``: integers in [0, hard_cap].
- ``leverage_status``: one of ``blocked`` | ``risk_adjusted`` |
  ``full_alignment`` — same vocabulary as the legacy policy so the frontend
  needs no new label mapping.
- ``leverage_reason``: one-line Chinese explanation naming the binding
  constraint (stop too tight / ATR buffer / risk budget / hard cap).
- ``leverage_detail``: audit dict with per-leverage rows
  (``stop_margin_impact_pct``, ``one_atr_margin_impact_pct``,
  ``liquidation_buffer_pct``, ``allowed`` flag) for the drawer table, plus
  the resolved ``optimal`` / ``max_allowed`` / ``binding_constraint``.
"""

from __future__ import annotations

from dataclasses import dataclass, field
from typing import Any, Mapping, Sequence

CANDIDATE_LEVERAGES: tuple[int, ...] = (1, 2, 3, 5)

# Default: if the stop fills, lose at most 15% of the allocated margin.
# At 5x that means the stop sits ≤ 3% from entry (0.6% price move × 5);
# at 3x it allows ≤ 5%. Tighter stops force the recommendation down, which
# is exactly the behaviour the user asked for ("不同杠杆下的止损完全不一样").
_DEFAULT_RISK_BUDGET_PCT = 15.0
_DEFAULT_LIQ_BUFFER_MIN_PCT = 1.5
_DEFAULT_ATR_BUFFER_MIN_PCT = 0.0


def _num(value: Any, default: float = 0.0) -> float:
    try:
        number = float(value)
    except (TypeError, ValueError):
        return default
    if number != number or number in (float("inf"), float("-inf")):
        return default
    return number


def stop_distance_pct(entry: Any, stop: Any) -> float:
    """Return |entry - stop| / entry * 100, or 0.0 when unusable."""
    entry_f = _num(entry, 0.0)
    stop_f = _num(stop, 0.0)
    if entry_f <= 0 or stop_f <= 0:
        return 0.0
    return abs(entry_f - stop_f) / abs(entry_f) * 100.0


@dataclass(slots=True)
class LeverageLevel:
    leverage: int
    stop_margin_impact_pct: float
    one_atr_margin_impact_pct: float | None
    liquidation_buffer_pct: float
    allowed: bool
    block_reason: str = ""


@dataclass(slots=True)
class LeverageRecommendation:
    recommended_leverage: int
    max_leverage: int
    leverage_status: str
    leverage_reason: str
    binding_constraint: str = ""
    levels: list[LeverageLevel] = field(default_factory=list)

    def as_dict(self) -> dict[str, Any]:
        return {
            "recommended_leverage": self.recommended_leverage,
            "max_leverage": self.max_leverage,
            "leverage_status": self.leverage_status,
            "leverage_reason": self.leverage_reason,
            "binding_constraint": self.binding_constraint,
            "leverage_detail": {
                "optimal": self.recommended_leverage,
                "max_allowed": self.max_leverage,
                "binding_constraint": self.binding_constraint,
                "levels": [
                    {
                        "leverage": level.leverage,
                        "stop_margin_impact_pct": round(level.stop_margin_impact_pct, 4),
                        "one_atr_margin_impact_pct": (
                            None
                            if level.one_atr_margin_impact_pct is None
                            else round(level.one_atr_margin_impact_pct, 4)
                        ),
                        "liquidation_buffer_pct": round(level.liquidation_buffer_pct, 4),
                        "allowed": level.allowed,
                        "block_reason": level.block_reason,
                    }
                    for level in self.levels
                ],
            },
        }


def evaluate_leverage(
    *,
    stop_distance_pct: float,
    atr_pct: float | None = None,
    risk_budget_pct: float = _DEFAULT_RISK_BUDGET_PCT,
    liquidation_buffer_min_pct: float = _DEFAULT_LIQ_BUFFER_MIN_PCT,
    atr_buffer_min_pct: float = _DEFAULT_ATR_BUFFER_MIN_PCT,
    hard_cap: float = 5.0,
    candidates: Sequence[int] = CANDIDATE_LEVERAGES,
) -> LeverageRecommendation:
    """Pick the optimal leverage inside the survival envelope.

    Per-leverage margin math (cross-margin approximation, same basis as
    ``snapshot_builder._compute_futures_risk``):

    - ``stop_margin_impact_pct = stop_distance_pct * L`` — margin lost when
      the protective stop fills.
    - ``liquidation_buffer_pct = 100 / L - stop_distance_pct`` — headroom
      between the stop and the approximate liquidation price. Must stay
      >= ``liquidation_buffer_min_pct`` or the stop cannot fill before
      liquidation.
    - ``one_atr_margin_impact_pct = atr_pct * L`` (when ATR is known) — a
      single adverse ATR excursion's margin cost; the ATR buffer is
      ``100 / L - atr_pct`` and must stay >= ``atr_buffer_min_pct``.
    """
    stop_pct = _num(stop_distance_pct, 0.0)
    budget = _num(risk_budget_pct, _DEFAULT_RISK_BUDGET_PCT)
    liq_min = _num(liquidation_buffer_min_pct, _DEFAULT_LIQ_BUFFER_MIN_PCT)
    atr_min = _num(atr_buffer_min_pct, _DEFAULT_ATR_BUFFER_MIN_PCT)
    cap = max(0, min(5, int(_num(hard_cap, 0.0))))
    atr = _num(atr_pct, 0.0) if atr_pct is not None else None

    if stop_pct <= 0:
        return LeverageRecommendation(
            recommended_leverage=0,
            max_leverage=0,
            leverage_status="blocked",
            leverage_reason="缺少有效止损距离，无法评估杠杆安全边界。",
            binding_constraint="missing_stop_distance",
            levels=[],
        )
    if cap <= 0:
        return LeverageRecommendation(
            recommended_leverage=0,
            max_leverage=0,
            leverage_status="blocked",
            leverage_reason="上游计划尚未给出可用杠杆上限。",
            binding_constraint="upstream_cap",
            levels=[],
        )

    levels: list[LeverageLevel] = []
    for lev in candidates:
        lev_int = int(lev)
        if lev_int <= 0 or lev_int > cap:
            continue
        stop_impact = stop_pct * lev_int
        liq_buffer = 100.0 / lev_int - stop_pct
        atr_impact = atr * lev_int if atr is not None else None
        atr_buffer = (100.0 / lev_int - atr) if atr is not None else None
        if stop_impact > budget:
            levels.append(
                LeverageLevel(
                    leverage=lev_int,
                    stop_margin_impact_pct=stop_impact,
                    one_atr_margin_impact_pct=atr_impact,
                    liquidation_buffer_pct=liq_buffer,
                    allowed=False,
                    block_reason=f"止损冲击 {stop_impact:.2f}% 超出单笔风险预算 {budget:.2f}%",
                )
            )
            continue
        if liq_buffer < liq_min:
            levels.append(
                LeverageLevel(
                    leverage=lev_int,
                    stop_margin_impact_pct=stop_impact,
                    one_atr_margin_impact_pct=atr_impact,
                    liquidation_buffer_pct=liq_buffer,
                    allowed=False,
                    block_reason=f"强平缓冲 {liq_buffer:.2f}% 低于最低 {liq_min:.2f}%",
                )
            )
            continue
        if atr is not None and atr_buffer is not None and atr_buffer < atr_min:
            levels.append(
                LeverageLevel(
                    leverage=lev_int,
                    stop_margin_impact_pct=stop_impact,
                    one_atr_margin_impact_pct=atr_impact,
                    liquidation_buffer_pct=liq_buffer,
                    allowed=False,
                    block_reason=f"单根 ATR 回撤缓冲 {atr_buffer:.2f}% 不足",
                )
            )
            continue
        levels.append(
            LeverageLevel(
                leverage=lev_int,
                stop_margin_impact_pct=stop_impact,
                one_atr_margin_impact_pct=atr_impact,
                liquidation_buffer_pct=liq_buffer,
                allowed=True,
            )
        )

    allowed = [level for level in levels if level.allowed]
    if not allowed:
        first_block = levels[0].block_reason if levels else "无可用杠杆档位"
        constraint = "risk_budget" if "风险预算" in first_block else (
            "liquidation_buffer" if "强平缓冲" in first_block else "atr_buffer"
        )
        return LeverageRecommendation(
            recommended_leverage=0,
            max_leverage=0,
            leverage_status="blocked",
            leverage_reason=f"止损距离 {stop_pct:.2f}% 下所有杠杆档位均不安全：{first_block}。",
            binding_constraint=constraint,
            levels=levels,
        )

    optimal = max(allowed, key=lambda item: item.leverage)
    binding = "hard_cap" if optimal.leverage >= cap else "risk_budget"
    if optimal.leverage >= 5:
        status = "full_alignment"
        reason = (
            f"止损距离 {stop_pct:.2f}%，{optimal.leverage}× 下止损冲击 "
            f"{optimal.stop_margin_impact_pct:.2f}%（预算 {budget:.2f}%），"
            f"强平缓冲 {optimal.liquidation_buffer_pct:.2f}%。"
        )
    else:
        status = "risk_adjusted"
        reason = (
            f"止损距离 {stop_pct:.2f}% 限制下最优为 {optimal.leverage}×："
            f"止损冲击 {optimal.stop_margin_impact_pct:.2f}%（预算 {budget:.2f}%），"
            f"强平缓冲 {optimal.liquidation_buffer_pct:.2f}%。"
        )
    return LeverageRecommendation(
        recommended_leverage=optimal.leverage,
        max_leverage=optimal.leverage,
        leverage_status=status,
        leverage_reason=reason,
        binding_constraint=binding,
        levels=levels,
    )


def recommendation_from_plan(
    *,
    entry: Any,
    stop: Any,
    atr_pct: float | None = None,
    risk_budget_pct: float = _DEFAULT_RISK_BUDGET_PCT,
    liquidation_buffer_min_pct: float = _DEFAULT_LIQ_BUFFER_MIN_PCT,
    atr_buffer_min_pct: float = _DEFAULT_ATR_BUFFER_MIN_PCT,
    hard_cap: float = 5.0,
) -> LeverageRecommendation:
    """Convenience wrapper resolving ``stop_distance_pct`` from prices."""
    return evaluate_leverage(
        stop_distance_pct=stop_distance_pct(entry, stop),
        atr_pct=atr_pct,
        risk_budget_pct=risk_budget_pct,
        liquidation_buffer_min_pct=liquidation_buffer_min_pct,
        atr_buffer_min_pct=atr_buffer_min_pct,
        hard_cap=hard_cap,
    )


def sizing_config_from_mapping(config: Mapping[str, Any] | None) -> dict[str, float]:
    """Read tunables from the strategy-signal config ``leverage_sizing`` block."""
    block = dict((config or {}).get("leverage_sizing") or {})
    return {
        "risk_budget_pct": _num(block.get("risk_budget_pct"), _DEFAULT_RISK_BUDGET_PCT),
        "liquidation_buffer_min_pct": _num(
            block.get("liquidation_buffer_min_pct"), _DEFAULT_LIQ_BUFFER_MIN_PCT
        ),
        "atr_buffer_min_pct": _num(
            block.get("atr_buffer_min_pct"), _DEFAULT_ATR_BUFFER_MIN_PCT
        ),
    }
