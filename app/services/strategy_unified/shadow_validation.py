from __future__ import annotations

from datetime import UTC, datetime
from decimal import ROUND_HALF_UP, Decimal
from typing import Any

from app.db.models.market import StrategyDecision, StrategyDecisionOutcome
from app.repositories.market_repository import MarketRepository

RETURN_WINDOWS = (1, 3, 6, 12, 24)
ROUND_TRIP_COST = Decimal("0.001")


class ShadowValidationService:
    """Evaluate active and shadow decisions using candles strictly after creation."""

    def __init__(self, repository: MarketRepository) -> None:
        self.repository = repository

    async def update_outcomes(
        self, instrument_id: str = "btc-usdt-perp", *, limit: int = 2000
    ) -> dict[str, int]:
        decisions = await self.repository.list_strategy_decisions(
            instrument_id=instrument_id,
            timeframe="4h",
            limit=limit,
        )
        existing = await self.repository.list_strategy_decision_outcomes(
            decision_ids=[item.decision_id for item in decisions],
            limit=limit,
        )
        completed = {item.decision_id for item in existing}
        created = 0
        pending = 0
        for decision in decisions:
            if decision.decision_id in completed:
                continue
            outcome = await self._outcome_for(decision)
            if outcome is None:
                pending += 1
                continue
            await self.repository.add_strategy_decision_outcome(outcome)
            created += 1
        return {"created": created, "pending": pending, "total": len(decisions)}

    async def _outcome_for(
        self, decision: StrategyDecision
    ) -> StrategyDecisionOutcome | None:
        direction = str(decision.direction or "").upper()
        entry = decision.current_price
        if direction not in {"LONG", "SHORT"} or entry is None or entry <= 0:
            return None
        candles = await self.repository.list_candles_filtered(
            instrument_id=decision.instrument_id,
            timeframe=decision.timeframe,
            from_ts=decision.decision_ts,
            ascending=True,
            limit=64,
        )
        future = [
            candle
            for candle in candles
            if getattr(candle, "ts_open", decision.decision_ts) > decision.decision_ts
        ]
        if len(future) < max(RETURN_WINDOWS):
            return None
        side = Decimal("1") if direction == "LONG" else Decimal("-1")
        returns: dict[int, Decimal] = {}
        highs: list[Decimal] = []
        lows: list[Decimal] = []
        for window in RETURN_WINDOWS:
            close = Decimal(str(future[window - 1].close))
            returns[window] = ((close - entry) / entry * side).quantize(
                Decimal("0.00000001"), rounding=ROUND_HALF_UP
            )
        for candle in future[: max(RETURN_WINDOWS)]:
            highs.append(Decimal(str(candle.high)))
            lows.append(Decimal(str(candle.low)))
        if direction == "LONG":
            mfe = max((high - entry) / entry for high in highs)
            mae = min((low - entry) / entry for low in lows)
        else:
            mfe = max((entry - low) / entry for low in lows)
            mae = min((entry - high) / entry for high in highs)
        six_bar_net = returns[6] - ROUND_TRIP_COST
        return StrategyDecisionOutcome(
            decision_id=decision.decision_id,
            bars_1_return=returns[1],
            bars_3_return=returns[3],
            bars_6_return=returns[6],
            bars_12_return=returns[12],
            bars_24_return=returns[24],
            fee_adjusted_return=six_bar_net,
            slippage_adjusted_return=six_bar_net,
            mfe=mfe.quantize(Decimal("0.00000001"), rounding=ROUND_HALF_UP),
            mae=mae.quantize(Decimal("0.00000001"), rounding=ROUND_HALF_UP),
            stop_hit_first=None,
            take_profit_hit_first=None,
            confirmation_hit=returns[6] > 0,
            invalidation_hit=None,
            review_label="direction_hit" if returns[6] > 0 else "direction_miss",
            attribution_json={
                "evaluation_window": "6x4h",
                "round_trip_cost": str(ROUND_TRIP_COST),
                "no_lookahead": True,
            },
        )

    async def build_report(
        self,
        instrument_id: str = "btc-usdt-perp",
        *,
        update_outcomes: bool = False,
        limit: int = 5000,
    ) -> dict[str, Any]:
        update = (
            await self.update_outcomes(instrument_id, limit=limit)
            if update_outcomes
            else None
        )
        decisions = await self.repository.list_strategy_decisions(
            instrument_id=instrument_id,
            timeframe="4h",
            limit=limit,
        )
        outcomes = await self.repository.list_strategy_decision_outcomes(
            decision_ids=[item.decision_id for item in decisions],
            limit=limit,
        )
        by_id = {item.decision_id: item for item in outcomes}
        modes: dict[str, list[tuple[StrategyDecision, StrategyDecisionOutcome]]] = {
            "active": [],
            "shadow": [],
        }
        safety_results: list[bool] = []
        for decision in decisions:
            payload = decision.payload_json or {}
            mode = str(payload.get("evaluation_mode") or "")
            safety = payload.get("safety_gate_passed")
            if isinstance(safety, bool):
                safety_results.append(safety)
            outcome = by_id.get(decision.decision_id)
            if mode in modes and outcome is not None:
                modes[mode].append((decision, outcome))
        metrics = {mode: self._metrics(rows) for mode, rows in modes.items()}
        all_dates = [item.decision_ts for item in decisions]
        coverage_days = (
            (max(all_dates) - min(all_dates)).total_seconds() / 86400
            if len(all_dates) >= 2
            else 0.0
        )
        safety_rate = (
            sum(safety_results) / len(safety_results) if safety_results else 0.0
        )
        active = metrics["active"]
        shadow = metrics["shadow"]
        comparisons = {
            "hit_rate_not_worse": shadow["direction_hit_rate"] >= active["direction_hit_rate"],
            "brier_not_worse": shadow["brier_score"] <= active["brier_score"],
            "expected_return_not_worse": (
                shadow["net_expected_return"] >= active["net_expected_return"]
            ),
            "drawdown_not_worse": shadow["max_drawdown"] <= active["max_drawdown"],
            "reversals_within_limit": shadow["reversal_count"] <= active["reversal_count"] * 1.1,
        }
        gates = {
            "history_90_days": coverage_days >= 90,
            "shadow_30_days": coverage_days >= 30,
            "shadow_120_decisions": shadow["evaluated_decisions"] >= 120,
            "safety_gate_100pct": bool(safety_results) and safety_rate == 1.0,
            **comparisons,
        }
        return {
            "instrument_id": instrument_id,
            "generated_at": datetime.now(UTC).isoformat(),
            "status": "eligible_for_manual_cutover" if all(gates.values()) else "collecting",
            "cutover_mode": "manual",
            "coverage_days": round(coverage_days, 2),
            "safety_gate_pass_rate": round(safety_rate, 6),
            "metrics": metrics,
            "gates": gates,
            "update": update,
        }

    @staticmethod
    def _metrics(
        rows: list[tuple[StrategyDecision, StrategyDecisionOutcome]],
    ) -> dict[str, Any]:
        if not rows:
            return {
                "evaluated_decisions": 0,
                "direction_hit_rate": 0.0,
                "brier_score": 1.0,
                "net_expected_return": 0.0,
                "max_drawdown": 0.0,
                "reversal_count": 0,
            }
        ordered = sorted(rows, key=lambda item: item[0].decision_ts)
        returns = [Decimal(str(item[1].slippage_adjusted_return or 0)) for item in ordered]
        hits = [Decimal("1") if item > 0 else Decimal("0") for item in returns]
        probabilities = [
            min(Decimal("1"), max(Decimal("0"), Decimal(str(item[0].confidence_score or 50)) / 100))
            for item in ordered
        ]
        brier = sum(
            (probability - hit) ** 2
            for probability, hit in zip(probabilities, hits, strict=True)
        ) / len(hits)
        equity = Decimal("1")
        peak = equity
        max_drawdown = Decimal("0")
        for item in returns:
            equity *= Decimal("1") + item
            peak = max(peak, equity)
            if peak > 0:
                max_drawdown = max(max_drawdown, (peak - equity) / peak)
        directions = [str(item[0].direction or "").upper() for item in ordered]
        reversals = sum(
            current != previous
            for previous, current in zip(directions, directions[1:], strict=False)
            if previous in {"LONG", "SHORT"} and current in {"LONG", "SHORT"}
        )
        return {
            "evaluated_decisions": len(ordered),
            "direction_hit_rate": round(float(sum(hits) / len(hits)), 6),
            "brier_score": round(float(brier), 6),
            "net_expected_return": round(float(sum(returns) / len(returns)), 8),
            "max_drawdown": round(float(max_drawdown), 8),
            "reversal_count": reversals,
        }
