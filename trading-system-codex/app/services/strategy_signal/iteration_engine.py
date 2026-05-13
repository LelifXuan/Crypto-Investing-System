from __future__ import annotations

from typing import Any

from app.repositories.market_repository import MarketRepository
from app.services.strategy_signal.review_engine import ReviewEngine


class IterationEngine:
    def __init__(self, repository: MarketRepository) -> None:
        self.repository = repository

    async def list_proposals(
        self,
        instrument_id: str | None = None,
        timeframe: str | None = None,
    ) -> list[dict[str, Any]]:
        review = await ReviewEngine(self.repository).build_review(instrument_id, timeframe, limit=80)
        proposals: list[dict[str, Any]] = []
        if review["total_signals"] == 0:
            return []
        if review["state_counts"].get("CONFLICTED_NO_TRADE", 0) >= 3:
            proposals.append(
                {
                    "proposal_id": "reduce-conflict-threshold-noise",
                    "priority": "medium",
                    "target_module": "scoring_engine",
                    "proposal": "多空冲突信号较多，建议复核结构权重与动量权重是否重复计入。",
                    "evidence_count": review["state_counts"]["CONFLICTED_NO_TRADE"],
                }
            )
        if review["state_counts"].get("RISK_OFF", 0) >= 3:
            proposals.append(
                {
                    "proposal_id": "inspect-risk-gates",
                    "priority": "medium",
                    "target_module": "risk_reward",
                    "proposal": "风险关闭次数较多，建议检查价差、滑点和事件窗口阈值是否过严。",
                    "evidence_count": review["state_counts"]["RISK_OFF"],
                }
            )
        return proposals

