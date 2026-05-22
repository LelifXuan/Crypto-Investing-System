from __future__ import annotations

from typing import Any


def number(value: Any, default: float = 0.0) -> float:
    try:
        if value is None or value == "":
            return default
        output = float(value)
    except (TypeError, ValueError):
        return default
    if output != output or output in {float("inf"), float("-inf")}:
        return default
    return output


def clamp(value: Any, low: float = 0.0, high: float = 100.0) -> float:
    return max(low, min(high, number(value)))


def round2(value: Any) -> float:
    return round(number(value), 2)


def risk_reward_score(rr: float | None) -> float:
    if rr is None or rr <= 0:
        return 0
    if rr < 1:
        return 20
    if rr < 1.5:
        return 40
    if rr < 2:
        return 60
    if rr < 3:
        return 80
    return 90


def risk_reward_label(rr: float | None) -> str:
    if rr is None or rr <= 0:
        return "缺少入场、止损或目标价，暂不能评估盈亏比"
    if rr < 1:
        return "盈亏比低于 1，不值得交易"
    if rr < 1.5:
        return "盈亏比较弱，只适合观察"
    if rr < 2:
        return "盈亏比可观察，仍需等待确认"
    if rr < 3:
        return "盈亏比合格"
    return "盈亏比优秀，但仍需确认目标是否现实"


def compute_risk_reward(
    direction: str, entry: float | None, stop: float | None, tp1: float | None
) -> float | None:
    if not entry or not stop or not tp1:
        return None
    if direction == "long" and entry > stop:
        return (tp1 - entry) / max(entry - stop, 1e-9)
    if direction == "short" and stop > entry:
        return (entry - tp1) / max(stop - entry, 1e-9)
    return None
