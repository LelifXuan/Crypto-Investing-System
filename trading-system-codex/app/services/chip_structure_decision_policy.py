from __future__ import annotations

from dataclasses import dataclass
from typing import Any

BLOCKING_PRIMARY_STATES = {
    "balanced_auction",
    "distribution_candidate",
    "distribution_proxy",
    "distribution_confirmed",
    "bearish_continuation_range",
    "false_breakout",
    "leverage_compression",
    "liquidity_drought",
}

BLOCKING_SECONDARY_SCENARIOS = {
    "distribution_candidate",
    "distribution_proxy",
    "distribution_confirmed",
    "bearish_continuation_range",
    "liquidity_drought",
    "leverage_compression",
}

BLOCKING_RISK_LABELS = {"high", "extreme"}
ALLOWED_EVIDENCE_QUALITY = {"confirmed", "partially_confirmed"}


@dataclass(frozen=True, slots=True)
class GateCheck:
    key: str
    label: str
    passed: bool
    actual: str
    requirement: str

    def as_dict(self) -> dict[str, Any]:
        return {
            "key": self.key,
            "label": self.label,
            "passed": self.passed,
            "actual": self.actual,
            "requirement": self.requirement,
        }


@dataclass(frozen=True, slots=True)
class ChipStructureDecision:
    allow_futures_long: bool
    gate_checks: list[GateCheck]
    failed_gate_reasons: list[str]
    why_no_futures_long: str
    entry_trigger_label: str
    state_confidence_label: str
    execution_quality_label: str
    recommended_action: str

    def payload(self) -> dict[str, Any]:
        return {
            "allow_futures_long": self.allow_futures_long,
            "futures_gate_checks": [item.as_dict() for item in self.gate_checks],
            "failed_gate_reasons": self.failed_gate_reasons,
            "why_no_futures_long": self.why_no_futures_long,
            "entry_trigger_label": self.entry_trigger_label,
            "state_confidence_label": self.state_confidence_label,
            "execution_quality_label": self.execution_quality_label,
        }


def _confidence_label(score: float) -> str:
    if score >= 80:
        return "状态置信很高"
    if score >= 70:
        return "状态置信较高"
    if score >= 55:
        return "状态置信可用"
    if score > 0:
        return "状态仅供观察"
    return "状态置信无效"


def _execution_label(score: float, execution_readiness: str) -> str:
    if execution_readiness == "blocked":
        return "盘口执行阻塞"
    if score >= 80:
        return "盘口执行质量很强"
    if score >= 70:
        return "盘口执行质量良好"
    if score >= 55:
        return "盘口执行质量可接受"
    return "盘口执行质量偏弱"


def _entry_trigger_label(execution_readiness: str, recommended_action: str) -> str:
    if recommended_action in {"risk_off", "no_trade"} or execution_readiness == "blocked":
        return "交易触发阻塞"
    if recommended_action in {"observe_only", "observe"}:
        return "仅观察，未触发入场"
    if recommended_action in {"wait_confirmation", "wait_for_confirmation"}:
        return "等待确认，未触发入场"
    if execution_readiness != "confirmed":
        return "触发未完成"
    return "触发条件可用"


def _check(key: str, label: str, passed: bool, actual: str, requirement: str) -> GateCheck:
    return GateCheck(key=key, label=label, passed=passed, actual=actual, requirement=requirement)


def decide_chip_structure_action(
    *,
    direction_score: float,
    confidence_score: float,
    execution_score: float,
    risk_score: float,
    risk_label: str,
    primary_state: str,
    secondary_scenario: str,
    recommended_action: str,
    execution_readiness: str,
    higher_timeframe_conflict: bool,
    data_state: str,
    evidence_quality: str,
) -> ChipStructureDecision:
    entry_trigger_label = _entry_trigger_label(execution_readiness, recommended_action)
    gate_checks = [
        _check(
            "direction_score",
            "方向分",
            direction_score >= 72,
            f"{direction_score:.0f}",
            "至少 72，且必须偏多",
        ),
        _check(
            "state_confidence_score",
            "状态置信",
            confidence_score >= 70,
            f"{confidence_score:.0f}",
            "至少 70",
        ),
        _check(
            "execution_score",
            "盘口执行质量",
            execution_score >= 70,
            f"{execution_score:.0f}",
            "至少 70",
        ),
        _check("risk_score", "风险分", risk_score <= 30, f"{risk_score:.0f}", "不高于 30"),
        _check(
            "risk_label",
            "风险标签",
            risk_label not in BLOCKING_RISK_LABELS,
            risk_label or "-",
            "不能是 high / extreme",
        ),
        _check(
            "primary_state",
            "主状态",
            primary_state not in BLOCKING_PRIMARY_STATES,
            primary_state or "-",
            "不能是派发、空头、假突破、流动性干涸或杠杆压缩",
        ),
        _check(
            "secondary_scenario",
            "次级情景",
            secondary_scenario not in BLOCKING_SECONDARY_SCENARIOS,
            secondary_scenario or "-",
            "不能出现派发、空头、流动性干涸或杠杆压缩",
        ),
        _check(
            "entry_trigger",
            "交易触发",
            entry_trigger_label == "触发条件可用",
            entry_trigger_label,
            "必须已触发，而不是观察或等待确认",
        ),
        _check(
            "higher_timeframe_conflict",
            "高周期冲突",
            not higher_timeframe_conflict,
            "有冲突" if higher_timeframe_conflict else "无冲突",
            "不能存在 1W/1D 与执行周期方向冲突",
        ),
        _check(
            "data_state",
            "数据状态",
            data_state == "available",
            data_state,
            "必须 available",
        ),
        _check(
            "evidence_quality",
            "证据质量",
            evidence_quality in ALLOWED_EVIDENCE_QUALITY,
            evidence_quality or "-",
            "必须 confirmed 或 partially_confirmed",
        ),
    ]
    failed = [item for item in gate_checks if not item.passed]
    allow = not failed
    reasons = [
        f"{item.label}未达标：当前 {item.actual}，要求 {item.requirement}"
        for item in failed
    ]
    failed_summary = "；".join(reasons[:4])
    why = (
        "全部合约开多门槛通过，允许进入合约仓位评估。"
        if allow
        else "当前不建议开多合约，因为" + (failed_summary + "。" if reasons else "门控信息不完整。")
    )
    return ChipStructureDecision(
        allow_futures_long=allow,
        gate_checks=gate_checks,
        failed_gate_reasons=reasons,
        why_no_futures_long=why,
        entry_trigger_label=entry_trigger_label,
        state_confidence_label=_confidence_label(confidence_score),
        execution_quality_label=_execution_label(execution_score, execution_readiness),
        recommended_action=recommended_action,
    )


def suppress_futures_allocation(
    capital: dict[str, Any],
    decision: ChipStructureDecision,
) -> dict[str, Any]:
    if decision.allow_futures_long:
        return capital
    updated = dict(capital)
    updated["futures_min_pct"] = 0.0
    updated["futures_max_pct"] = 0.0
    updated["futures_label"] = "0%"
    spot_max = float(updated.get("spot_max_pct") or 0.0)
    if spot_max <= 10:
        reason = "当前仅允许现货小仓观察，不建议开合约；等待方向、触发、风险和证据质量同时达标。"
        updated["total_label"] = updated.get("total_label") or "0% - 10%"
    else:
        reason = "当前合约门控未通过，现货仓位需要按原有上限保守执行，合约仓位保持 0%。"
    updated["reason"] = reason
    updated["allocation_reason"] = reason
    return updated
