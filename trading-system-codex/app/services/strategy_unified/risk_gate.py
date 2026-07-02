# ruff: noqa: E501
from __future__ import annotations

from typing import Any, Mapping, Sequence

from .contracts import DATA_BLOCK_MISSING_CORE_COUNT, MarketDimension, RiskAlert, TimeframeNode


class UnifiedRiskGateEngine:
    def build(
        self,
        nodes: Sequence[TimeframeNode],
        market_dimensions: Mapping[str, MarketDimension],
    ) -> list[RiskAlert]:
        alerts: list[RiskAlert] = []
        missing_core = [
            node.timeframe
            for node in nodes
            if node.timeframe in {"1M", "1w", "1d", "4h"}
            and self._is_missing(node)
            and not self._has_usable_node(node)
        ]
        if len(missing_core) >= DATA_BLOCK_MISSING_CORE_COUNT:
            alerts.append(
                RiskAlert(
                    "data",
                    "blocker",
                    "核心周期数据缺失",
                    f"核心策略输入不可用：{', '.join(missing_core)}。",
                    "刷新统一市场上下文与策略栈后再输出主动计划。",
                    ["strategic", "tactical"],
                    "UnifiedDataLoader",
                )
            )
        elif missing_core:
            alerts.append(
                RiskAlert(
                    "data",
                    "warning",
                    "部分周期数据缺失",
                    f"部分核心策略输入不可用：{', '.join(missing_core)}。",
                    "不要把缺失周期作为执行依据；保持条件权限。",
                    ["strategic", "tactical"],
                    "UnifiedDataLoader",
                )
            )

        macro = market_dimensions.get("macro_regime")
        if macro and macro.state == "EVENT_LOCKED":
            alerts.append(
                RiskAlert(
                    "event",
                    "blocker",
                    "高影响事件窗口",
                    "宏观事件窗口激活，新增高杠杆入场被锁定。",
                    "等待事件落地并确认 1 根 4H 收盘后再升级权限。",
                    ["tactical", "execution"],
                    "MacroRegimeEngine",
                )
            )
        derivatives = market_dimensions.get("derivatives_regime")
        if derivatives and str(derivatives.state).lower() in {
            "data_missing",
            "missing",
            "degraded",
            "data_insufficient",
        }:
            alerts.append(
                RiskAlert(
                    "derivatives",
                    "warning",
                    "衍生品确认降级",
                    "资金费率、持仓量、期权墙或 Max Pain 输入不完整。",
                    "衍生品数据恢复前短期计划保持条件权限，或由价格结构独立确认。",
                    ["tactical", "execution"],
                    "DerivativesRegimeEngine",
                )
            )
        onchain = market_dimensions.get("onchain_regime")
        if onchain and onchain.state == "ONCHAIN_UPSTREAM_MISSING":
            alerts.append(
                RiskAlert(
                    "data",
                    "info",
                    "链上数据缺失",
                    "链上输入不可用，已从强方向判断中排除。",
                    "链上维度仅作观察项。",
                    ["strategic"],
                    "OnchainRegimeEngine",
                )
            )
        return alerts

    @staticmethod
    def _is_missing(node: TimeframeNode) -> bool:
        return bool(
            node.raw_status.get("legacy_status") in {"missing", "error"}
            or node.raw_status.get("cache_state") in {"missing", "error", "updating"}
            or node.freshness in {"missing", "error"}
        )

    @staticmethod
    def _has_usable_node(node: TimeframeNode) -> bool:
        return bool(
            set(node.source_modules) & {"MarketContextBuilder", "StrategySignalService"}
            and node.raw_status.get("cache_state") in {"computed", "refreshed", "context_fallback", "fresh"}
            and (node.long_score > 0 or node.short_score > 0)
        )


def group_risk_alerts(alerts: Sequence[RiskAlert]) -> dict[str, list[dict[str, Any]]]:
    groups: dict[str, list[dict[str, Any]]] = {
        "strategic": [],
        "tactical": [],
        "execution": [],
        "data": [],
        "event": [],
    }
    seen_by_group: dict[str, set[str]] = {key: set() for key in groups}
    for alert in alerts:
        payload = alert.as_dict()
        if alert.category in {"data", "event"}:
            _append_unique(groups, seen_by_group, alert.category, payload)
        for horizon in alert.affected_horizons:
            _append_unique(groups, seen_by_group, horizon, payload)
    return groups


def _append_unique(
    groups: dict[str, list[dict[str, Any]]],
    seen_by_group: dict[str, set[str]],
    group: str,
    payload: dict[str, Any],
) -> None:
    key = str(payload.get("key") or payload.get("id") or repr(payload))
    seen = seen_by_group.setdefault(group, set())
    if key in seen:
        return
    groups.setdefault(group, []).append(payload)
    seen.add(key)