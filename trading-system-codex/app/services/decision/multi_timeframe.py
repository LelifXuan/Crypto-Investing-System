from __future__ import annotations

from dataclasses import dataclass, field


@dataclass(slots=True)
class TimeframeSignal:
    timeframe: str
    bias: str
    confidence: float = 0.0
    risk: str | None = None


@dataclass(slots=True)
class MultiTimeframeDecisionResult:
    mode: str
    confirmation: str
    invalidation: str
    suggested_action: str
    evidence: list[str] = field(default_factory=list)


class MultiTimeframeDecisionEngine:
    def decide(
        self, signals: list[TimeframeSignal], *, risk_veto: bool = False
    ) -> MultiTimeframeDecisionResult:
        by_tf = {signal.timeframe: signal for signal in signals}
        monthly = by_tf.get("1M")
        weekly = by_tf.get("1w")
        daily = by_tf.get("1d")
        four_hour = by_tf.get("4h")
        one_hour = by_tf.get("1h")
        evidence = [
            f"{signal.timeframe}:{signal.bias}:{signal.confidence:.2f}" for signal in signals
        ]

        if risk_veto:
            return MultiTimeframeDecisionResult(
                mode="risk_off",
                confirmation="等待风险条件解除后再恢复方向判断。",
                invalidation="若风险过滤继续生效，则保持观望。",
                suggested_action="暂停主动开仓，只保留风险管理动作。",
                evidence=evidence,
            )
        if (
            daily
            and daily.bias.startswith("bull")
            and one_hour
            and one_hour.bias.startswith("bear")
        ):
            return MultiTimeframeDecisionResult(
                mode="wait_pullback_long",
                confirmation="等待 1h 回调结束并重新站回短线结构确认位。",
                invalidation="若 1d 主导低点被跌破，则多头过滤失效。",
                suggested_action="不追涨，优先等待顺大周期方向的回踩机会。",
                evidence=evidence,
            )
        if (
            daily
            and daily.bias.startswith("bear")
            and one_hour
            and one_hour.bias.startswith("bull")
        ):
            return MultiTimeframeDecisionResult(
                mode="wait_rebound_short",
                confirmation="等待 1h 反弹衰竭并重新出现空头确认。",
                invalidation="若 1d 主导高点被重新站回，则空头过滤失效。",
                suggested_action="不抄底，优先等待顺大周期方向的反弹做空机会。",
                evidence=evidence,
            )
        if (
            daily
            and daily.bias in {"neutral", "uncertain", "no_clear_structure"}
            and four_hour
            and four_hour.bias.startswith("bull")
        ):
            return MultiTimeframeDecisionResult(
                mode="breakout_watch",
                confirmation="等待 4h 突破被 1d 收盘确认。",
                invalidation="若突破区重新失守，则突破观察失效。",
                suggested_action="以观察名单管理为主，不在震荡区内过早重仓。",
                evidence=evidence,
            )
        if (
            daily
            and daily.bias in {"neutral", "uncertain", "no_clear_structure"}
            and four_hour
            and four_hour.bias.startswith("bear")
        ):
            return MultiTimeframeDecisionResult(
                mode="breakdown_watch",
                confirmation="等待 4h 跌破被 1d 收盘确认。",
                invalidation="若跌破区重新收回，则跌破观察失效。",
                suggested_action="以观察名单管理为主，等待确认后再扩张仓位。",
                evidence=evidence,
            )
        dominant = next(
            (
                signal
                for signal in [daily, weekly, monthly, four_hour, one_hour]
                if signal and signal.bias.startswith("bull")
            ),
            None,
        )
        if dominant:
            return MultiTimeframeDecisionResult(
                mode="long_only",
                confirmation="继续保持高低周期同向确认。",
                invalidation="若主导周期关键低点失守，则多头模式失效。",
                suggested_action="只保留顺势多头机会，逆势信号降级为观察。",
                evidence=evidence,
            )
        dominant = next(
            (
                signal
                for signal in [daily, weekly, monthly, four_hour, one_hour]
                if signal and signal.bias.startswith("bear")
            ),
            None,
        )
        if dominant:
            return MultiTimeframeDecisionResult(
                mode="short_only",
                confirmation="继续保持高低周期同向确认。",
                invalidation="若主导周期关键高点被重新站回，则空头模式失效。",
                suggested_action="只保留顺势空头机会，逆势信号降级为观察。",
                evidence=evidence,
            )
        return MultiTimeframeDecisionResult(
            mode="range_only",
            confirmation="等待方向突破出现再升级模式。",
            invalidation="若高低周期重新形成同向结构，则震荡模式结束。",
            suggested_action="优先区间交易与观望，不做激进趋势跟随。",
            evidence=evidence,
        )
