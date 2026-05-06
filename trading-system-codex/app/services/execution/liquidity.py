from __future__ import annotations

from dataclasses import dataclass, field
from decimal import Decimal


@dataclass(slots=True)
class LiquidityAssessment:
    bid_ask_spread: Decimal
    depth: Decimal
    slippage: Decimal
    min_liquidity_ok: bool
    funding_cost: Decimal
    max_executable_size: Decimal
    notes: list[str] = field(default_factory=list)


class ExecutionLiquidityEngine:
    def assess(
        self,
        *,
        bid_ask_spread: Decimal,
        depth: Decimal,
        slippage: Decimal,
        min_depth: Decimal,
        funding_cost: Decimal,
        requested_size: Decimal,
    ) -> LiquidityAssessment:
        notes = []
        if depth < min_depth:
            notes.append("盘口深度不足，建议降仓或放弃执行。")
        if slippage > Decimal("0.003"):
            notes.append("预估滑点偏高，执行质量较差。")
        if funding_cost > Decimal("0.0015"):
            notes.append("资金费率成本偏高，持仓性价比下降。")
        max_executable_size = min(requested_size, depth * Decimal("0.25"))
        return LiquidityAssessment(
            bid_ask_spread=bid_ask_spread,
            depth=depth,
            slippage=slippage,
            min_liquidity_ok=depth >= min_depth,
            funding_cost=funding_cost,
            max_executable_size=max_executable_size,
            notes=notes,
        )
