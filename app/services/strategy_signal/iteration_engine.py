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
        review = await ReviewEngine(self.repository).build_review(
            instrument_id, timeframe, limit=80, update_outcomes=True
        )
        proposals: list[dict[str, Any]] = []
        records = review.get("latest_records", [])
        total = review.get("total_signals", 0)
        if total == 0:
            return []

        proposals.extend(self._check_entry_strictness(records))
        proposals.extend(self._check_trigger_quality(records))
        proposals.extend(self._check_tp_management(records))
        proposals.extend(self._check_confidence_miscalibration(records))
        proposals.extend(self._check_pattern_degradation(records))
        proposals.extend(self._check_ambiguous_hits(records))

        if total < 8:
            proposals.append({
                "proposal_id": "low-sample-warning",
                "priority": "low",
                "proposal_type": "sample_size",
                "target_module": "review_engine",
                "reason": f"仅 {total} 条已保存策略记录，样本量不足，建议持续保存后重新评估。",
                "evidence_count": total,
                "suggested_change": {"action": "keep_saving"},
            })

        return proposals

    def _check_entry_strictness(self, records: list[dict]) -> list[dict[str, Any]]:
        wait_states = {"WAIT_LONG_CONFIRMATION", "WAIT_SHORT_CONFIRMATION",
                       "WAIT_LOWER_TF_CONFIRMATION", "WAIT_PULLBACK_CONFIRMATION"}
        candidates = [
            r for r in records
            if r.get("state") in wait_states
            and (r.get("mfe") or 0) > 0.01
        ]
        if len(candidates) >= 3:
            return [{
                "proposal_id": "entry-trigger-too-strict",
                "priority": "high",
                "proposal_type": "threshold_adjustment",
                "target_module": "strategy_generator/setup_lifecycle",
                "reason": f"最近 {len(candidates)} 条等待确认策略中，MFE 明显为正但未触发入场，入场条件可能过严。",
                "evidence_count": len(candidates),
                "suggested_change": {
                    "rule": "lower_tf_confirmation or pullback_confirm",
                    "change": "建议降低触发确认门槛，或允许价格回踩入场区后触发",
                },
            }]
        return []

    def _check_trigger_quality(self, records: list[dict]) -> list[dict[str, Any]]:
        triggered = [r for r in records if r.get("state") in ("LONG_TRIGGERED", "SHORT_TRIGGERED")]
        sl_first = [r for r in triggered if r.get("stop_hit_first")]
        if len(sl_first) >= 2 and len(triggered) >= 5:
            rate = len(sl_first) / len(triggered) * 100
            return [{
                "proposal_id": "trigger-quality-low",
                "priority": "high",
                "proposal_type": "quality_threshold",
                "target_module": "entry_validation",
                "reason": f"已触发策略中止损先行比例 {rate:.0f}%，触发质量不足，建议提高次级周期确认或盘口执行分阈值。",
                "evidence_count": len(sl_first),
                "suggested_change": {
                    "rule": "execution_score or lower_tf_confirm",
                    "change": "提高 ExecutionScore 最低要求或增加低周期确认条件",
                },
            }]
        return []

    def _check_tp_management(self, records: list[dict]) -> list[dict[str, Any]]:
        tp_then_drawdown = [
            r for r in records
            if r.get("outcome_status") in ("tp1_hit", "tp2_hit")
            and (r.get("mfe") or 0) > (r.get("return_24") or 0) + 0.02
        ]
        if len(tp_then_drawdown) >= 3:
            return [{
                "proposal_id": "take-profit-management",
                "priority": "medium",
                "proposal_type": "exit_rule",
                "target_module": "strategy_generator",
                "reason": f"有 {len(tp_then_drawdown)} 条策略 TP1 命中后出现明显回撤，建议 TP1 后移动止损或分批止盈。",
                "evidence_count": len(tp_then_drawdown),
                "suggested_change": {
                    "rule": "trailing_stop_after_tp1",
                    "change": "TP1 命中后激活追踪止损，锁定已有盈利",
                },
            }]
        return []

    def _check_confidence_miscalibration(self, records: list[dict]) -> list[dict[str, Any]]:
        high_conf = [r for r in records if r.get("confidence_score", 0) >= 70]
        high_conf_fail = [r for r in high_conf if r.get("outcome_status") in ("stop_hit", "move_missed")]
        if len(high_conf_fail) >= 2 and len(high_conf) >= 4:
            return [{
                "proposal_id": "confidence-miscalibration",
                "priority": "medium",
                "proposal_type": "calibration",
                "target_module": "confidence_engine",
                "reason": f"高置信度策略中 {len(high_conf_fail)}/{len(high_conf)} 条结果不达预期，置信度可能需要重新校准。",
                "evidence_count": len(high_conf_fail),
                "suggested_change": {
                    "rule": "confidence_ceiling_lower",
                    "change": "降低高置信度状态的仓位上限或增加额外验证条件",
                },
            }]
        return []

    def _check_pattern_degradation(self, records: list[dict]) -> list[dict[str, Any]]:
        by_state: dict[str, list[dict]] = {}
        for r in records:
            st = r.get("state", "")
            if st:
                by_state.setdefault(st, []).append(r)
        proposals = []
        for state, items in by_state.items():
            if len(items) < 3:
                continue
            sl_rate = sum(1 for r in items if r.get("outcome_status") == "stop_hit") / len(items)
            if sl_rate >= 0.5:
                proposals.append({
                    "proposal_id": f"pattern-degradation-{state.lower()}",
                    "priority": "medium",
                    "proposal_type": "pattern_quality",
                    "target_module": "strategy_generator",
                    "reason": f"状态 {state} 的近 {len(items)} 条策略中止损率 {sl_rate:.0f}%，该形态近期表现不佳，建议降低权重或限制适用市场状态。",
                    "evidence_count": len(items),
                    "suggested_change": {
                        "state": state,
                        "change": "降低该形态权重或增加条件过滤",
                    },
                })
        return proposals

    def _check_ambiguous_hits(self, records: list[dict]) -> list[dict[str, Any]]:
        ambiguous = [r for r in records if r.get("hit_ambiguous")]
        if len(ambiguous) >= 2:
            return [{
                "proposal_id": "need-lower-tf-review",
                "priority": "medium",
                "proposal_type": "data_quality",
                "target_module": "outcome_engine",
                "reason": f"有 {len(ambiguous)} 条策略在同根 K 线内止盈止损均触及，无法判断真实命中顺序，需要更低周期数据。",
                "evidence_count": len(ambiguous),
                "suggested_change": {
                    "rule": "lower_tf_outcome_data",
                    "change": "需要更低周期 K 线数据判断真实命中顺序",
                },
            }]
        return []
