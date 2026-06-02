from __future__ import annotations

from datetime import datetime, timezone
from typing import Any

from app.repositories.market_repository import MarketRepository
from app.services.chip_structure import ChipStructureService
from app.services.macro_overview import MacroOverviewService

UTC = timezone.utc


class FinalDecisionService:
    def __init__(self, repository: MarketRepository) -> None:
        self.repository = repository

    async def build(self, instrument_id: str, timeframe: str) -> dict[str, Any]:
        chip = await self._chip_payload(instrument_id, timeframe)
        macro_payload = await self._macro_payload()
        macro_bias = self._macro_bias(macro_payload)
        conflicts = self._conflicts(chip, macro_bias)
        action = self._final_action(chip, conflicts)
        direction = self._direction(chip)
        confidence_label = str(chip.get("confidence_label") or "invalid")
        risk_gates = list(chip.get("risk_gates") or [])
        return {
            "instrument_id": instrument_id,
            "timeframe": timeframe,
            "direction": direction,
            "direction_score": chip.get("direction_score", 0.0),
            "direction_label": chip.get("direction_label", "neutral"),
            "confidence_score": chip.get("confidence_score", 0.0),
            "confidence_label": confidence_label,
            "execution_score": chip.get("execution_score", 0.0),
            "execution_label": chip.get("execution_label", "blocked"),
            "risk_score": chip.get("risk_score", 100.0),
            "risk_label": chip.get("risk_label", "extreme"),
            "confidence_cap": chip.get("confidence_cap", 0.0),
            "action": action,
            "recommended_action": chip.get("recommended_action_v2", "no_trade"),
            "legacy_recommended_action": chip.get("recommended_action", "risk_off"),
            "position_multiplier": chip.get("position_multiplier", 0.0),
            "capital_ceiling_pct": chip.get("capital_ceiling_pct", 0.0),
            "evidence_quality": chip.get("evidence_quality", "proxy_only"),
            "conflict_level": chip.get("conflict_level", 3),
            "chip_regime": chip.get("primary_regime"),
            "macro_bias": macro_bias,
            "risk_state": chip.get("state"),
            "risk_gates": risk_gates,
            "conflicts": conflicts,
            "explain": list(chip.get("explain") or []),
            "components": chip.get("components") or {},
            "source": {
                "chip_structure": {
                    "recommended_action": chip.get("recommended_action"),
                    "recommended_action_v2": chip.get("recommended_action_v2"),
                    "direction_score": chip.get("direction_score"),
                    "confidence_score": chip.get("confidence_score"),
                    "confidence_label": chip.get("confidence_label"),
                    "execution_score": chip.get("execution_score"),
                    "risk_score": chip.get("risk_score"),
                },
                "macro": {
                    "status": macro_payload.get("status"),
                    "risk_level": macro_payload.get("risk_level"),
                },
            },
            "generated_at": datetime.now(timezone.utc),
        }

    async def _chip_payload(self, instrument_id: str, timeframe: str) -> dict[str, Any]:
        try:
            return await ChipStructureService(self.repository).analyze(instrument_id, timeframe)
        except Exception as exc:
            return {
                "instrument_id": instrument_id,
                "timeframe": timeframe,
                "state": "unavailable",
                "direction_score": 0.0,
                "direction_label": "neutral",
                "confidence_score": 0.0,
                "confidence_label": "invalid",
                "execution_score": 0.0,
                "execution_label": "blocked",
                "risk_score": 100.0,
                "risk_label": "extreme",
                "confidence_cap": 0.0,
                "recommended_action": "risk_off",
                "recommended_action_v2": "no_trade",
                "position_multiplier": 0.0,
                "capital_ceiling_pct": 0.0,
                "evidence_quality": "proxy_only",
                "conflict_level": 3,
                "risk_gates": ["CHIP_STRUCTURE_UNAVAILABLE"],
                "explain": [f"筹码结构暂不可用，最终决策降级为仅观察：{exc}"],
                "components": {},
            }

    async def _macro_payload(self) -> dict[str, Any]:
        try:
            macro = await MacroOverviewService(self.repository).build_overview()
            return macro.model_dump(mode="json")
        except Exception as exc:
            return {
                "status": "unavailable",
                "risk_level": "unknown",
                "explain": [f"宏观概览暂不可用，已按中性处理：{exc}"],
            }

    def _direction(self, chip: dict[str, Any]) -> str:
        label = str(chip.get("direction_label") or "")
        if label in {"strong_long", "long"}:
            return "long_preferred"
        if label in {"strong_short", "short"}:
            return "short_preferred"
        score = float(chip.get("direction_score") or 0.0)
        if score >= 20:
            return "long_preferred"
        if score <= -20:
            return "short_preferred"
        return "range_or_wait"

    def _macro_bias(self, payload: dict[str, Any]) -> str:
        risk_level = str(payload.get("risk_level") or payload.get("status") or "").lower()
        if risk_level in {"risk_off", "stress", "stressed", "tight"}:
            return "risk_off"
        if risk_level in {"risk_on", "supportive", "loose"}:
            return "supportive"
        return "neutral"

    def _conflicts(self, chip: dict[str, Any], macro_bias: str) -> list[str]:
        conflicts: list[str] = []
        action = str(chip.get("recommended_action_v2") or chip.get("recommended_action") or "")
        allowed_when_macro_risk_off = {
            "observe",
            "no_trade",
            "reduce_or_exit",
            "observe_only",
            "risk_off",
        }
        if macro_bias == "risk_off" and action not in allowed_when_macro_risk_off:
            conflicts.append("macro_risk_off_vs_trade_action")
        if (
            chip.get("state") in {"missing", "unavailable"}
            and chip.get("capital_ceiling_pct", 0) > 10
        ):
            conflicts.append("weak_data_quality_vs_position_size")
        if float(chip.get("risk_score") or 0.0) >= 80:
            conflicts.append("risk_score_extreme")
        return conflicts

    def _final_action(self, chip: dict[str, Any], conflicts: list[str]) -> str:
        action = str(chip.get("recommended_action_v2") or "no_trade")
        if chip.get("state") == "missing":
            return "no_trade"
        if conflicts:
            return "observe"
        return action
