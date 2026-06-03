from __future__ import annotations

from collections.abc import Mapping, Sequence
from dataclasses import asdict, dataclass, field
from math import isfinite
from typing import Any

from app.services.strategy_signal.setup_lifecycle import GateDiagnostic

MODULE_KEYS = (
    "macro",
    "technical_trend",
    "momentum_volume",
    "volatility",
    "structure",
    "event_risk",
)


@dataclass
class SummaryEvidence:
    key: str
    group: str
    score: float
    state: str
    label: str
    impact: str
    reason: str
    watch_points: list[str] = field(default_factory=list)
    raw_values: dict[str, Any] = field(default_factory=dict)

    def to_dict(self) -> dict[str, Any]:
        data = asdict(self)
        data["score"] = round(float(self.score), 2)
        return data


@dataclass
class ModuleScore:
    key: str
    score: float
    state: str
    impact: str
    reason: str
    evidence: list[SummaryEvidence] = field(default_factory=list)
    confidence: float = 0.5

    def to_dict(self) -> dict[str, Any]:
        return {
            "score": round(float(self.score), 2),
            "state": self.state,
            "impact": self.impact,
            "reason": self.reason,
            "confidence": round(float(self.confidence), 2),
            "evidence": [item.to_dict() for item in self.evidence],
        }


class TerminalSummaryEngine:
    WEIGHTS = {
        "technical_trend": 0.30,
        "momentum_volume": 0.20,
        "macro": 0.20,
        "volatility": 0.10,
        "structure": 0.10,
        "event_risk": 0.10,
    }

    def build(
        self,
        *,
        macro_overview: Mapping[str, Any] | None = None,
        technical_observations: Sequence[Mapping[str, Any]] | None = None,
        structure: Mapping[str, Any] | None = None,
        event_risk: Mapping[str, Any] | None = None,
        alerts_bundle: Mapping[str, Any] | None = None,
        strategy_bundle: Mapping[str, Any] | None = None,
        timeframe_snapshots: Mapping[str, Any] | None = None,
    ) -> dict[str, Any]:
        market_context = _market_context(technical_observations or [])
        technical = TechnicalSummaryAdapter().summarize(technical_observations or [])
        modules = {
            **technical,
            "macro": MacroSummaryAdapter().summarize(macro_overview or {}),
            # T08: structure now flows through StructureSummaryAdapter so the
            # monitoring overview reflects the real structure_bundle state
            # instead of permanently rendering "待确认".
            "structure": StructureSummaryAdapter().summarize(structure),
            "event_risk": self._optional_module(
                "event_risk",
                event_risk,
                fallback_state="中性",
                fallback_reason="暂无明确事件冲击，事件风险按中性处理。",
            ),
        }
        global_score = self._weighted_score(modules)
        regime, bias, confidence = self._determine_regime(modules, global_score)
        headline, conflict, implication = self._generate_text(regime, modules, market_context)
        evidence = self._top_evidence(modules)
        watch_points = self._merge_watch_points(
            evidence,
            prefix=self._context_watch_points(market_context, modules),
        )
        decision_brief = self._build_decision_brief(
            base_summary={
                "regime": regime,
                "bias": bias,
                "confidence": confidence,
                "headline": headline,
                "main_conflict": conflict,
                "strategy_implication": implication,
                "watch_points": watch_points,
                "module_scores": {key: modules[key].to_dict() for key in MODULE_KEYS},
                "bullish_reversal_conditions": [
                    "收复 EMA20 或 VWAP50 并站稳",
                    "MACD 柱值连续收敛或转正",
                    "RSI 修复至 40-50 区间",
                    "成交量配合价格上行",
                ],
                "bearish_continuation_conditions": [
                    "价格持续低于 EMA20/EMA50",
                    "-DI 维持高于 +DI",
                    "跌破前低并伴随成交放大",
                    "MACD 柱值继续负向扩张",
                ],
            },
            alerts_bundle=alerts_bundle or {},
            strategy_bundle=strategy_bundle or {},
            timeframe_snapshots=timeframe_snapshots or {},
            structure=structure or {},
        )
        return {
            "regime": regime,
            "bias": bias,
            "confidence": confidence,
            "headline": headline,
            "module_scores": {key: modules[key].to_dict() for key in MODULE_KEYS},
            "main_conflict": conflict,
            "strategy_implication": implication,
            "watch_points": watch_points,
            "bullish_reversal_conditions": [
                "收复 EMA20 或 VWAP50 并站稳",
                "MACD 柱值连续收敛或转正",
                "RSI 修复至 40-50 区间",
                "成交量配合价格上行",
            ],
            "bearish_continuation_conditions": [
                "价格持续低于 EMA20/EMA50",
                "-DI 维持高于 +DI",
                "跌破前低并伴随成交放大",
                "MACD 柱值继续负向扩张",
            ],
            "evidence": [item.to_dict() for item in evidence],
            "decision_brief": decision_brief,
        }

    def _build_decision_brief(
        self,
        *,
        base_summary: Mapping[str, Any],
        alerts_bundle: Mapping[str, Any],
        strategy_bundle: Mapping[str, Any],
        timeframe_snapshots: Mapping[str, Any],
        structure: Mapping[str, Any],
    ) -> dict[str, Any]:
        """Build the monitoring overview decision brief.

        T09 audit fix: the rows are now ``market_situation`` (rich
        headline with per-TF breakdown), ``mtf_breakdown`` (per-TF
        bullets when timeframes disagree), and ``key_risk`` (top 1-2
        critical invalidation conditions + data gaps). The previous
        ``trading_guidance`` row re-rendered the strategy page and the
        ``risk_invalidation`` row enumerated every chip / divergence /
        structure risk. Both violated the "summary layer, not
        recomputation" principle and have been removed.
        """

        decision = _decision_extract_strategy(strategy_bundle)
        chip = _decision_as_mapping(alerts_bundle.get("chip_structure"))
        divergence = _decision_as_mapping(alerts_bundle.get("divergence_summary"))

        alignment = _decision_source_alignment(
            base_summary=base_summary,
            strategy_decision=decision,
            chip=chip,
            divergence=divergence,
            timeframe_snapshots=timeframe_snapshots,
            structure=structure,
        )

        market_row = _decision_build_market_row(
            base_summary=base_summary,
            chip=chip,
            divergence=divergence,
            timeframe_snapshots=timeframe_snapshots,
            alignment=alignment,
        )
        rows: list[dict[str, Any]] = [market_row]
        mtf_row = _decision_build_mtf_breakdown_row(
            timeframe_snapshots=timeframe_snapshots,
            alignment=alignment,
        )
        if mtf_row is not None:
            rows.append(mtf_row)
        rows.append(
            _decision_build_key_risk_row(
                base_summary=base_summary,
                decision=decision,
                chip=chip,
                divergence=divergence,
                structure=structure,
                alignment=alignment,
            )
        )

        return {
            "version": "monitoring_decision_brief_v1",
            "source_alignment": alignment,
            "rows": rows,
        }

    def _weighted_score(self, modules: Mapping[str, ModuleScore]) -> float:
        total = 0.0
        weight_sum = 0.0
        for key, weight in self.WEIGHTS.items():
            module = modules.get(key)
            if module is None:
                continue
            effective_weight = weight * max(0.25, module.confidence)
            total += module.score * effective_weight
            weight_sum += effective_weight
        return total / weight_sum if weight_sum else 50.0

    def _determine_regime(
        self,
        modules: Mapping[str, ModuleScore],
        global_score: float,
    ) -> tuple[str, str, int]:
        trend = modules["technical_trend"].score
        momentum = modules["momentum_volume"].score
        macro = modules["macro"].score
        volatility = modules["volatility"]
        bearish_trend = trend <= 42
        bullish_trend = trend >= 58
        macro_tight = macro <= 45
        macro_loose = macro >= 58
        momentum_bearish = momentum <= 42
        momentum_bullish = momentum >= 58
        high_execution_risk = volatility.impact == "execution_risk"

        if high_execution_risk and 35 <= global_score <= 65:
            regime = "高波动风险"
        elif bearish_trend and momentum_bearish and volatility.score <= 45:
            regime = "空头加速"
        elif bearish_trend and (momentum_bearish or macro_tight):
            regime = "弱势下行"
        elif bearish_trend:
            regime = "弱势震荡"
        elif bullish_trend and momentum_bullish and not macro_tight:
            regime = "强趋势偏多"
        elif bullish_trend and macro_loose:
            regime = "温和偏多"
        elif macro_loose and not bearish_trend:
            regime = "多头修复"
        else:
            regime = "中性震荡"

        bias = "偏多" if global_score >= 58 else "偏空" if global_score <= 42 else "中性"
        confidence = int(round(min(88, max(35, abs(global_score - 50) * 1.6 + 50))))
        if bearish_trend and macro_tight:
            confidence = min(90, confidence + 6)
        if bullish_trend and macro_tight:
            confidence = max(45, confidence - 6)
        return regime, bias, confidence

    def _generate_text(
        self,
        regime: str,
        modules: Mapping[str, ModuleScore],
        market_context: Mapping[str, Any] | None = None,
    ) -> tuple[str, str, str]:
        contextual = self._generate_contextual_text(regime, modules, market_context or {})
        if contextual is not None:
            return contextual
        macro = modules["macro"]
        trend = modules["technical_trend"]
        momentum = modules["momentum_volume"]
        if regime == "弱势下行":
            return (
                f"当前判定为弱势下行结构。技术趋势处于{trend.state}，动量成交处于{momentum.state}，宏观环境处于{macro.state}，空头方向有效但执行质量需要边界确认。",
                "趋势端空头占优，宏观背景提供压力；波动与成交若未形成加速确认，追空质量仍按一般处理。",
                "优先等待反抽失败或跌破确认，摘要只用于环境判断，具体交易参数由策略模块独立处理。",
            )
        if regime == "空头加速":
            return (
                "当前判定为空头加速阶段。趋势、动量与波动端同步指向下行延续，空头方向具备较强确认。",
                "空头趋势与波动扩张一致，主要风险是低位追空后的急反抽，而不是方向证据不足。",
                "反弹失败或跌破确认后的空头计划优先级较高，但仍需由策略页独立处理仓位和止损。",
            )
        if regime == "弱势震荡":
            return (
                f"当前判定为弱势震荡结构。技术趋势处于{trend.state}，但动量、波动或宏观尚未形成一致加速确认。",
                "空头方向占优但延续质量不足，市场更容易出现反复拉扯。",
                "优先等待反抽失败、区间下沿跌破或动量重新扩张后再评估策略触发质量。",
            )
        if regime == "温和偏多":
            if macro.score <= 45:
                return (
                    "当前判定为技术偏多但宏观压制仍在。价格结构出现修复，风险偏好尚未同步改善。",
                    "技术短线强于宏观背景，多头持续性需要成交、资金流和关键均线站稳确认。",
                    "可以观察回踩不破后的多头计划，但不直接上调为强趋势偏多。",
                )
            return (
                "当前判定为温和偏多结构。价格结构偏强，趋势端具备修复基础。",
                "多头占优但尚未达到强趋势确认，后续需要观察动量与成交是否继续配合。",
                "优先观察回踩关键均线后的承接质量。",
            )
        if regime == "强趋势偏多":
            return (
                "当前判定为多头结构占优。价格、趋势、动量与风险背景形成正向共振。",
                "多头趋势与动量确认一致，主要风险来自过热和拥挤交易。",
                "多头计划可以保留，但应跟踪过热、资金费率和关键均线失守风险。",
            )
        if regime == "高波动风险":
            return (
                "当前判定为高波动风险环境。方向信号需要让位于执行质量和仓位控制。",
                "波动风险抬升会放大假突破、滑点与止损不确定性。",
                "降低追单优先级，等待波动回落或关键位确认后再评估计划。",
            )
        if regime == "多头修复":
            return (
                "当前判定为多头修复阶段。宏观或动量条件改善，但价格结构尚未完成强趋势确认。",
                "修复信号已经出现，趋势端仍需要 EMA、VWAP 与成交确认。",
                "不急于追多，优先观察 EMA20、EMA50 与 VWAP50 的收复情况。",
            )
        return (
            "当前维持中性震荡结构。多空模块分歧明显，价格方向尚未完成确认。",
            "宏观、技术、动量或波动之间缺少一致性，信号质量不足。",
            "降低方向性预设，等待关键均线、VWAP 或结构边界给出确认。",
        )

    def _generate_contextual_text(
        self,
        regime: str,
        modules: Mapping[str, ModuleScore],
        market_context: Mapping[str, Any],
    ) -> tuple[str, str, str] | None:
        label = str(market_context.get("label") or "BTC 日线")
        change_pct = market_context.get("close_change_pct")
        close = market_context.get("close")
        trend = modules["technical_trend"]
        momentum = modules["momentum_volume"]
        macro = modules["macro"]
        volatility = modules["volatility"]
        bearish_trend = trend.score <= 42
        bullish_trend = trend.score >= 58
        sharp_drop = _is_number(change_pct) and float(change_pct) <= -3.0
        sharp_rebound = _is_number(change_pct) and float(change_pct) >= 3.0
        close_text = f"，最新收盘约 {float(close):,.0f}" if _is_number(close) else ""

        if sharp_drop and bearish_trend:
            headline = (
                f"{label}刚经历急跌{close_text}，当前仍处于{regime}。"
                "这不是简单的中性震荡，而是急跌后的偏空结构与反抽风险并存。"
            )
            conflict = (
                f"趋势端为{trend.state}，动量端为{momentum.state}，宏观环境为{macro.state}。"
                "空头方向仍占优，但低位追空的执行质量下降；RSI低位和急跌后的反抽容易制造假突破。"
            )
            implication = (
                "场景优先级应按 BTC 日线连续性排序：低位追空质量偏低；等待反弹至 EMA20/VWAP50 "
                "附近失败后的顺势空头评估更清晰；若继续放量跌破前低，则再评估空头延续质量。"
                "DCA、梭哈现货和左侧摸底开多都不应被视为当前主场景，只适合作为极低权重观察；"
                "右侧开多需要先看到收复 EMA20/VWAP50、RSI 回到 40-50 区间并有成交确认。"
            )
            return headline, conflict, implication

        if bearish_trend:
            headline = (
                f"{label}维持偏空结构{close_text}，价格仍未完成方向修复。"
                "摘要按 BTC 日线趋势连续性评估，而不是按孤立指标投票。"
            )
            conflict = (
                f"趋势端为{trend.state}，动量端为{momentum.state}，波动端为{volatility.state}。"
                "偏空结构有效，但是否适合追空取决于反弹失败、前低跌破和成交放大是否出现。"
            )
            implication = (
                "优先观察反弹开空或跌破确认两类顺势情形；左侧摸底和DCA需要等待超卖修复、"
                "下跌动能收敛以及关键均线/VWAP收复，不宜仅因价格下跌就上调权重。"
            )
            return headline, conflict, implication

        if sharp_rebound and bullish_trend:
            headline = (
                f"{label}出现强反弹并进入偏多结构{close_text}，需要区分右侧确认和短线过热。"
            )
            conflict = (
                f"趋势端为{trend.state}，动量端为{momentum.state}，宏观环境为{macro.state}。"
                "多头修复占优，但追高质量仍取决于回踩不破和成交承接。"
            )
            implication = (
                "右侧开多场景需要回踩 EMA20/VWAP50 不破或突破后放量延续；"
                "DCA和现货加仓更适合在回踩确认后评估，避免把单日反弹误判为趋势完全恢复。"
            )
            return headline, conflict, implication

        if bullish_trend:
            headline = f"{label}维持偏多修复结构{close_text}，但仍需看回踩承接和宏观环境配合。"
            conflict = (
                f"趋势端为{trend.state}，动量端为{momentum.state}，宏观环境为{macro.state}。"
                "多头方向更清晰，但持续性需要成交和均线支撑验证。"
            )
            implication = (
                "右侧交易优先观察回踩 EMA20/VWAP50 后的承接质量；"
                "若跌回关键均线下方，则多头计划降级为等待修复。"
            )
            return headline, conflict, implication

        return None

    def _top_evidence(
        self,
        modules: Mapping[str, ModuleScore],
        limit: int = 6,
    ) -> list[SummaryEvidence]:
        evidence: list[SummaryEvidence] = []
        for module in modules.values():
            evidence.extend(module.evidence)
        evidence.sort(key=lambda item: abs(item.score - 50), reverse=True)
        return evidence[:limit]

    def _merge_watch_points(
        self,
        evidence: Sequence[SummaryEvidence],
        limit: int = 6,
        prefix: Sequence[str] | None = None,
    ) -> list[str]:
        seen: set[str] = set()
        result: list[str] = []
        for point in prefix or []:
            if point and point not in seen:
                result.append(point)
                seen.add(point)
            if len(result) >= limit:
                return result
        for item in evidence:
            for point in item.watch_points:
                if point and point not in seen:
                    result.append(point)
                    seen.add(point)
                if len(result) >= limit:
                    return result
        return result or ["等待宏观、技术与结构数据刷新后重新判断。"]

    def _context_watch_points(
        self,
        market_context: Mapping[str, Any],
        modules: Mapping[str, ModuleScore],
    ) -> list[str]:
        change_pct = market_context.get("close_change_pct")
        trend = modules["technical_trend"]
        momentum = modules["momentum_volume"]
        bearish_trend = trend.score <= 42
        bullish_trend = trend.score >= 58
        sharp_drop = _is_number(change_pct) and float(change_pct) <= -3.0
        points: list[str] = []
        if sharp_drop and bearish_trend:
            points.extend(
                [
                    "低位追空是否被反抽风险抵消",
                    "反弹至 EMA20/VWAP50 后是否再次失败",
                    "是否放量跌破急跌后的前低",
                    "右侧开多是否先收复 EMA20/VWAP50",
                    "DCA/左侧摸底是否仍缺少动能收敛证据",
                ]
            )
        elif bearish_trend:
            points.extend(
                [
                    "反弹开空是否比直接追空更有执行质量",
                    "前低跌破是否获得成交确认",
                    "RSI/MACD 是否出现空头动能收敛",
                ]
            )
        elif bullish_trend:
            points.extend(
                [
                    "回踩 EMA20/VWAP50 是否不破",
                    "右侧开多是否获得成交确认",
                    "宏观环境是否继续压制风险偏好",
                ]
            )
        if momentum.impact == "execution_risk":
            points.append("动量极值是否引发反抽或追单滑点风险")
        return points

    def _optional_module(
        self,
        key: str,
        data: Mapping[str, Any] | None,
        *,
        fallback_state: str,
        fallback_reason: str,
    ) -> ModuleScore:
        if not data:
            return ModuleScore(key, 50, fallback_state, "neutral", fallback_reason, [], 0.35)
        score = _num(data.get("score"), 50.0)
        state = str(data.get("state") or data.get("label") or _state_from_score(score))
        reason = str(data.get("reason") or fallback_reason)
        evidence = SummaryEvidence(
            key,
            key,
            score,
            state,
            state,
            _score_to_impact(score),
            reason,
            list(data.get("watch_points") or []),
            dict(data),
        )
        return ModuleScore(
            key,
            score,
            state,
            _score_to_impact(score),
            reason,
            [evidence],
            _bounded_confidence(data.get("confidence"), 0.5),
        )


class MacroSummaryAdapter:
    def summarize(self, macro: Mapping[str, Any]) -> ModuleScore:
        if not macro:
            reason = "宏观输入不足，当前仅按中性背景降级展示。"
            return ModuleScore("macro", 50, "宏观暂不可用", "unknown", reason, [], 0.25)
        score = _num(macro.get("total_score") or macro.get("score"), 50.0)
        completeness = (
            macro.get("data_completeness")
            if isinstance(macro.get("data_completeness"), Mapping)
            else {}
        )
        valid = int(_num(completeness.get("effective_count"), 0))
        total = int(_num(completeness.get("total_count"), 0))
        missing = max(total - valid, 0)
        stale = sum(
            int(_num(layer.get("stale_count"), 0)) for layer in _iter_dicts(macro.get("layers"))
        )
        confidence = 0.75
        if total > 0:
            confidence -= min(0.35, (missing / total) * 0.25 + (stale / total) * 0.15)
        if total and valid < max(3, total * 0.5):
            confidence = min(confidence, 0.42)

        if score >= 65:
            state, impact, reason = (
                "宽松/风险偏好支持",
                "risk_support",
                "宏观环境对风险资产相对友好，流动性或增长条件提供支撑。",
            )
        elif score >= 55:
            state, impact, reason = (
                "中性偏暖",
                "mild_bullish",
                "宏观环境略偏友好，但仍需要技术与资金流确认。",
            )
        elif score > 45:
            state, impact, reason = (
                "宏观中性",
                "neutral",
                "宏观环境未形成明确方向压力，风险资产主要由技术结构和资金行为驱动。",
            )
        elif score > 35:
            state, impact, reason = (
                "温和偏紧",
                "risk_pressure",
                "宏观环境温和偏紧，风险偏好缺乏明显修复。",
            )
        else:
            state, impact, reason = (
                "明显偏紧",
                "bearish",
                "宏观环境明显压制风险资产，需要降低趋势延续和仓位假设。",
            )
        if total and valid < max(3, total * 0.5):
            reason += " 当前宏观有效输入不足，结论置信度已下调。"

        evidence = SummaryEvidence(
            "macro_overview",
            "macro",
            score,
            state,
            str(macro.get("score_band") or state),
            impact,
            reason,
            ["利率与美元是否回落", "信用利差是否收敛", "跨资产风险偏好是否修复"],
            {
                "valid_count": valid,
                "total_count": total,
                "missing_count": missing,
                "stale_count": stale,
            },
        )
        return ModuleScore("macro", score, state, impact, reason, [evidence], max(0.25, confidence))


class StructureSummaryAdapter:
    """Translate the structure page / strategy.structure_overall into a ModuleScore.

    T08 audit fix: the audit found that the monitoring overview's structure
    module always rendered ``待确认`` because the monitoring payload never
    carried a ``structure`` key. This adapter consumes the
    ``structure_bundle`` page cache (or the ``strategy.structure_overall``
    fallback) and emits a ModuleScore that matches the rest of the
    engine's modules. The score, state and impact are derived from the
    structure regime and bias; the reason is the suggested action the
    structure page recommends.
    """

    _REGIME_TO_STATE: dict[str, tuple[str, str]] = {
        "trend": ("趋势结构", "neutral"),
        "trending": ("趋势结构", "neutral"),
        "balance": ("区间结构", "neutral"),
        "range": ("区间结构", "neutral"),
        "ranging": ("区间结构", "neutral"),
        "transition": ("结构切换", "warning"),
        "shock": ("结构冲击", "warning"),
        "accumulation_proxy": ("积累倾向", "mild_bullish"),
        "accumulation_confirmed": ("积累确认", "bullish"),
        "distribution_proxy": ("派发倾向", "mild_bearish"),
        "distribution_confirmed": ("派发确认", "bearish"),
    }

    _BIAS_TO_IMPACT: dict[str, str] = {
        "bullish": "bullish",
        "long": "bullish",
        "up": "bullish",
        "bearish": "bearish",
        "short": "bearish",
        "down": "bearish",
        "neutral": "neutral",
    }

    def summarize(self, structure: Mapping[str, Any] | None) -> ModuleScore:
        if not structure:
            return ModuleScore(
                "structure",
                50.0,
                "待确认",
                "neutral",
                "结构形态输入不足，等待关键支撑、阻力和形态确认。",
                [],
                0.35,
            )
        regime = str(
            structure.get("regime")
            or structure.get("state")
            or ""
        ).lower()
        bias = str(
            structure.get("bias")
            or structure.get("overall_bias")
            or structure.get("direction")
            or ""
        ).lower()
        base_score = _num(structure.get("score"))
        if base_score is None:
            bias_score = _num(structure.get("bias_score"))
            if bias_score is None:
                bias_score = _num(structure.get("bullish_score"))
            base_score = bias_score if bias_score is not None else 50.0
        if not 0 <= base_score <= 100:
            base_score = max(0.0, min(100.0, base_score))
        state_default, impact_default = self._REGIME_TO_STATE.get(
            regime, (structure.get("state") or "形态待确认", "neutral")
        )
        if regime and regime not in self._REGIME_TO_STATE and structure.get("state"):
            state_default = str(structure.get("state"))
        if bias:
            impact = self._BIAS_TO_IMPACT.get(bias, impact_default)
        else:
            impact = impact_default
        if bias == "bullish" or bias == "long":
            score = max(base_score, 60.0)
        elif bias == "bearish" or bias == "short":
            score = min(base_score, 40.0)
        else:
            score = base_score
        if impact == "bullish":
            score = max(score, 55.0)
        elif impact == "bearish":
            score = min(score, 45.0)
        reason = str(
            structure.get("reason")
            or structure.get("summary")
            or structure.get("suggested_action")
            or structure.get("mode")
            or ""
        )
        if not reason:
            if regime in {"trend", "trending"}:
                reason = "趋势结构形成，方向由趋势模板权重决定。"
            elif regime in {"balance", "range", "ranging"}:
                reason = "区间结构，方向需等待区间边界突破或失效。"
            elif regime in {"transition", "shock"}:
                reason = "结构切换窗口，方向不明确，等待新结构定型。"
            else:
                reason = "结构形态输入不足，等待关键支撑、阻力和形态确认。"
        watch_points = list(structure.get("watch_points") or [])
        if not watch_points:
            if regime in {"trend", "trending"}:
                watch_points = ["结构边界是否守住", "趋势模板权重是否变化"]
            elif regime in {"balance", "range", "ranging"}:
                watch_points = ["区间边界是否被突破", "突破是否伴随成交放大"]
            elif regime in {"transition", "shock"}:
                watch_points = ["新结构方向是否明确", "切换期间是否出现假突破"]
            else:
                watch_points = ["关键支撑阻力是否被测试", "结构边界是否给出方向"]
        evidence = SummaryEvidence(
            "structure_bundle",
            "structure",
            float(score),
            state_default,
            str(structure.get("label") or state_default),
            impact,
            reason,
            watch_points,
            {
                "regime": regime,
                "bias": bias,
                "source": structure.get("source") or "structure_bundle",
            },
        )
        confidence = _bounded_confidence(
            structure.get("confidence"),
            0.7 if regime in self._REGIME_TO_STATE else 0.4,
        )
        return ModuleScore(
            "structure",
            float(score),
            state_default,
            impact,
            reason,
            [evidence],
            confidence,
        )


class TechnicalSummaryAdapter:
    TREND_KEYS = {
        "ema_20",
        "ema_50",
        "ema_200",
        "ema_structure",
        "vwap_50",
        "vwap_100",
        "vwap_spread_pct",
        "vwap_slope_10",
    }
    MOMENTUM_KEYS = {"rsi_14", "macd_hist", "obv", "volume", "kdj_j", "cci_20"}
    VOLATILITY_KEYS = {
        "atr_14",
        "natr_14",
        "bbands",
        "bbands_width",
        "percent_b",
        "adx_14",
        "plus_di",
        "minus_di",
        "adx_direction",
    }

    def _summarize_legacy(
        self, observations: Sequence[Mapping[str, Any]]
    ) -> dict[str, ModuleScore]:
        trend = [item for item in observations if _key(item) in self.TREND_KEYS]
        momentum = [item for item in observations if _key(item) in self.MOMENTUM_KEYS]
        volatility = [item for item in observations if _key(item) in self.VOLATILITY_KEYS]
        return {
            "technical_trend": self._module(
                "technical_trend", trend, "趋势输入不足，等待 EMA/VWAP 数据刷新。"
            ),
            "momentum_volume": self._module(
                "momentum_volume", momentum, "动量与成交输入不足，等待 RSI/MACD/OBV 数据刷新。"
            ),
            "volatility": self._volatility_module(volatility),
        }

    def _module(
        self, key: str, items: Sequence[Mapping[str, Any]], fallback_reason: str
    ) -> ModuleScore:
        evidence = [self._evidence_from_observation(item, key) for item in items]
        evidence = [item for item in evidence if item is not None]
        if not evidence:
            return ModuleScore(key, 50, "数据不足", "unknown", fallback_reason, [], 0.25)
        score = _avg([item.score for item in evidence])
        reason = "；".join(item.reason for item in evidence[:2])
        return ModuleScore(
            key,
            score,
            _state_from_score(score),
            _score_to_impact(score),
            reason,
            evidence,
            min(0.9, 0.35 + 0.12 * len(evidence)),
        )

    def _volatility_module(self, items: Sequence[Mapping[str, Any]]) -> ModuleScore:
        evidence = [self._volatility_evidence(item) for item in items]
        evidence = [item for item in evidence if item is not None]
        if not evidence:
            return ModuleScore(
                "volatility",
                50,
                "数据不足",
                "unknown",
                "波动输入不足，等待 ATR/BOLL/DMI 数据刷新。",
                [],
                0.25,
            )
        risk_items = [item for item in evidence if item.impact == "execution_risk"]
        score = _avg([item.score for item in evidence])
        if risk_items:
            state = "高波动执行风险"
            impact = "execution_risk"
            reason = "；".join(item.reason for item in risk_items[:2])
        else:
            state = "中性波动"
            impact = "neutral"
            reason = "；".join(item.reason for item in evidence[:2])
        return ModuleScore(
            "volatility",
            score,
            state,
            impact,
            reason,
            evidence,
            min(0.9, 0.35 + 0.12 * len(evidence)),
        )

    def _evidence_from_observation(
        self,
        item: Mapping[str, Any],
        group: str,
    ) -> SummaryEvidence | None:
        key = _key(item)
        value = _num(
            item.get("value_num") if item.get("value_num") is not None else item.get("value"), 0.0
        )
        state = str(item.get("signal_state") or item.get("signal") or "neutral")
        label = str(item.get("signal_label") or item.get("label") or key)
        tone = str(item.get("tone") or "")
        score, impact = _state_score_and_impact(key, state, tone, value)
        reason = _clean_reason(item) or _default_reason(key, label, state)
        return SummaryEvidence(
            key,
            group,
            score,
            state,
            label,
            impact,
            reason,
            _watch_points_for(key, state),
            {"value": value, "signal_state": state, "tone": tone},
        )

    def _volatility_evidence(self, item: Mapping[str, Any]) -> SummaryEvidence | None:
        evidence = self._evidence_from_observation(item, "volatility")
        if evidence is None:
            return None
        key = evidence.key
        value = _num(
            item.get("value_num") if item.get("value_num") is not None else item.get("value"), 0.0
        )
        state = evidence.state
        if key in {"atr_14", "natr_14", "bbands", "bbands_width"}:
            if key == "natr_14" and value >= 3.5:
                evidence.score = 42
                evidence.impact = "execution_risk"
                evidence.state = "high_volatility"
                evidence.label = evidence.label or "波动偏高"
                evidence.reason = "NATR 处于偏高区间，方向信号需要降低追单和仓位假设。"
            elif key in {"bbands", "bbands_width"} and state in {"compressed", "neutral"}:
                evidence.score = 50
                evidence.impact = "neutral"
                evidence.reason = "BOLL 波动状态用于判断执行质量，不直接判定多空方向。"
            else:
                evidence.score = 52
                evidence.impact = "neutral"
        if key in {"adx_14", "plus_di", "minus_di", "adx_direction"}:
            evidence.impact = (
                "neutral" if evidence.impact in {"bullish", "bearish"} else evidence.impact
            )
            evidence.reason = "ADX/DMI 用于确认趋势方向和强度，ADX 不单独决定多空。"
        return evidence

    def summarize(self, observations: Sequence[Mapping[str, Any]]) -> dict[str, ModuleScore]:
        snapshot = _technical_snapshot(observations)
        trend = self._trend_module(snapshot)
        momentum = self._momentum_module(snapshot)
        volatility = self._volatility_module_from_snapshot(snapshot)
        if trend is None:
            trend_items = [item for item in observations if _key(item) in self.TREND_KEYS]
            trend = self._module(
                "technical_trend", trend_items, "趋势输入不足，等待 EMA/VWAP 数据刷新。"
            )
        if momentum is None:
            momentum_items = [item for item in observations if _key(item) in self.MOMENTUM_KEYS]
            momentum = self._module(
                "momentum_volume",
                momentum_items,
                "动量与成交输入不足，等待 RSI/MACD/OBV 数据刷新。",
            )
        if volatility is None:
            volatility_items = [item for item in observations if _key(item) in self.VOLATILITY_KEYS]
            volatility = self._volatility_module(volatility_items)
        return {
            "technical_trend": trend,
            "momentum_volume": momentum,
            "volatility": volatility,
        }

    def _trend_module(self, snapshot: Mapping[str, Any]) -> ModuleScore | None:
        close = snapshot.get("close")
        ema20 = snapshot.get("ema_20")
        ema50 = snapshot.get("ema_50")
        ema200 = snapshot.get("ema_200")
        evidence: list[SummaryEvidence] = []
        scores: list[float] = []
        if all(_is_number(value) for value in (close, ema20, ema50, ema200)):
            close_f = float(close)
            ema20_f = float(ema20)
            ema50_f = float(ema50)
            ema200_f = float(ema200)
            if close_f < ema20_f < ema50_f < ema200_f:
                score, state, impact, label = 24, "空头排列", "bearish", "EMA空头排列"
                reason = "价格位于 EMA20/EMA50/EMA200 下方，均线呈空头排列。"
            elif close_f > ema20_f > ema50_f > ema200_f:
                score, state, impact, label = 76, "多头排列", "bullish", "EMA多头排列"
                reason = "价格位于 EMA20/EMA50/EMA200 上方，均线呈多头排列。"
            elif close_f < ema50_f and close_f < ema200_f:
                score, state, impact, label = 34, "均线压制", "mild_bearish", "EMA压制"
                reason = "价格低于 EMA50 与 EMA200，中长期均线对价格形成压制。"
            elif close_f > ema50_f and close_f > ema200_f:
                score, state, impact, label = 64, "均线支撑", "mild_bullish", "EMA支撑"
                reason = "价格站上 EMA50 与 EMA200，中长期结构具备修复基础。"
            else:
                score, state, impact, label = 50, "均线分歧", "neutral", "EMA分歧"
                reason = "价格处于关键 EMA 之间，趋势结构分歧，等待方向确认。"
            evidence.append(
                SummaryEvidence(
                    "ema_alignment",
                    "technical_trend",
                    score,
                    state,
                    label,
                    impact,
                    reason,
                    ["价格能否收复 EMA20", "EMA20/EMA50 斜率是否同步转向"],
                    {
                        "close": close_f,
                        "ema_20": ema20_f,
                        "ema_50": ema50_f,
                        "ema_200": ema200_f,
                    },
                )
            )
            scores.append(score)

        vwap_score = self._vwap_score(snapshot)
        if vwap_score is not None:
            score, state, impact, reason = vwap_score
            evidence.append(
                SummaryEvidence(
                    "vwap_position",
                    "technical_trend",
                    score,
                    state,
                    state,
                    impact,
                    reason,
                    ["价格能否站上 VWAP50", "VWAP 乖离是否扩大"],
                    {
                        "close": close,
                        "vwap_50": snapshot.get("vwap_50"),
                        "vwap_100": snapshot.get("vwap_100"),
                        "vwap_spread_pct": snapshot.get("vwap_spread_pct"),
                    },
                )
            )
            scores.append(score)

        if not evidence:
            return None
        score = _avg(scores)
        reason = "；".join(item.reason for item in evidence[:2])
        return ModuleScore(
            "technical_trend",
            score,
            _state_from_score(score),
            _score_to_impact(score),
            reason,
            evidence,
            min(0.9, 0.45 + 0.15 * len(evidence)),
        )

    def _vwap_score(self, snapshot: Mapping[str, Any]) -> tuple[float, str, str, str] | None:
        close = snapshot.get("close")
        vwap50 = snapshot.get("vwap_50")
        vwap100 = snapshot.get("vwap_100")
        spread = snapshot.get("vwap_spread_pct")
        if _is_number(spread):
            spread_f = float(spread)
            if spread_f <= -0.5:
                return 36, "VWAP压制", "mild_bearish", "VWAP 价差偏空，成交均价结构压制价格。"
            if spread_f >= 0.5:
                return 64, "VWAP支撑", "mild_bullish", "VWAP 价差偏多，成交均价结构支撑价格。"
            return 50, "VWAP附近", "neutral", "价格接近 VWAP 区域，方向优势不明显。"
        if not _is_number(close):
            return None
        refs = [float(value) for value in (vwap50, vwap100) if _is_number(value)]
        if not refs:
            return None
        close_f = float(close)
        avg_vwap = sum(refs) / len(refs)
        deviation = (close_f - avg_vwap) / max(close_f, 1e-9) * 100
        if deviation <= -1.5:
            return 34, "VWAP压制", "mild_bearish", "价格位于主要 VWAP 下方，成交均价结构形成压制。"
        if deviation >= 1.5:
            return 66, "VWAP支撑", "mild_bullish", "价格位于主要 VWAP 上方，成交均价结构形成支撑。"
        return 50, "VWAP附近", "neutral", "价格接近主要 VWAP，方向优势不明显。"

    def _momentum_module(self, snapshot: Mapping[str, Any]) -> ModuleScore | None:
        evidence: list[SummaryEvidence] = []
        scores: list[float] = []
        rsi = snapshot.get("rsi_14")
        if _is_number(rsi):
            rsi_f = float(rsi)
            if rsi_f >= 70:
                score, state, impact = 58, "RSI过热", "execution_risk"
                reason = "RSI 进入过热区，多头动量强，但追高性价比下降。"
            elif rsi_f >= 60:
                score, state, impact = 70, "动量偏强", "bullish"
                reason = "RSI 位于强势区间，多头动量占优。"
            elif rsi_f >= 55:
                score, state, impact = 60, "温和偏多", "mild_bullish"
                reason = "RSI 高于中轴，多头动量略占优。"
            elif rsi_f > 45:
                score, state, impact = 50, "动量中性", "neutral"
                reason = "RSI 位于中性区间，动量方向未充分展开。"
            elif rsi_f > 30:
                score, state, impact = 38, "动量偏弱", "mild_bearish"
                reason = "RSI 低于中轴，空头动量占优。"
            else:
                score, state, impact = 42, "超卖反抽风险", "execution_risk"
                reason = "RSI 进入超卖区，空头动量偏弱但低位追空风险升高。"
            evidence.append(
                SummaryEvidence(
                    "rsi_14",
                    "momentum_volume",
                    score,
                    state,
                    state,
                    impact,
                    reason,
                    ["RSI 是否修复至 40 上方", "是否出现动量背离"],
                    {"rsi_14": rsi_f},
                )
            )
            scores.append(score)

        macd = snapshot.get("macd_hist")
        if _is_number(macd):
            macd_f = float(macd)
            if macd_f > 0:
                score, state, impact = 62, "MACD偏多", "mild_bullish"
                reason = "MACD 柱值位于正区间，动量结构偏多。"
            elif macd_f < 0:
                score, state, impact = 38, "MACD偏空", "mild_bearish"
                reason = "MACD 柱值位于负区间，动量结构偏空。"
            else:
                score, state, impact = 50, "MACD中性", "neutral"
                reason = "MACD 柱值接近零轴，动量方向不明确。"
            evidence.append(
                SummaryEvidence(
                    "macd_hist",
                    "momentum_volume",
                    score,
                    state,
                    state,
                    impact,
                    reason,
                    ["MACD 柱值是否连续收敛", "MACD 是否回到零轴上方"],
                    {"macd_hist": macd_f},
                )
            )
            scores.append(score)

        if snapshot.get("obv") is not None or snapshot.get("volume") is not None:
            evidence.append(
                SummaryEvidence(
                    "obv_volume",
                    "momentum_volume",
                    50,
                    "成交中性",
                    "成交中性",
                    "neutral",
                    "成交与资金流暂未提供明确方向确认。",
                    ["成交是否配合突破/跌破", "OBV 是否同步创新高/新低"],
                    {"obv": snapshot.get("obv"), "volume": snapshot.get("volume")},
                )
            )
            scores.append(50)

        if not evidence:
            return None
        directional_scores = [item.score for item in evidence if item.impact != "execution_risk"]
        score = _avg(directional_scores or scores)
        if any(item.impact == "execution_risk" for item in evidence) and score < 50:
            score = max(score, 42)
        reason = "；".join(item.reason for item in evidence[:2])
        return ModuleScore(
            "momentum_volume",
            score,
            _state_from_score(score),
            _score_to_impact(score),
            reason,
            evidence,
            min(0.9, 0.4 + 0.12 * len(evidence)),
        )

    def _volatility_module_from_snapshot(self, snapshot: Mapping[str, Any]) -> ModuleScore | None:
        evidence: list[SummaryEvidence] = []
        scores: list[float] = []
        natr = snapshot.get("natr_14")
        atr = snapshot.get("atr_14")
        close = snapshot.get("close")
        if not _is_number(natr) and _is_number(atr) and _is_number(close) and float(close) > 0:
            natr = float(atr) / float(close) * 100
        if _is_number(natr):
            natr_f = float(natr)
            if natr_f >= 5:
                score, state, impact = 42, "高波动执行风险", "execution_risk"
                reason = "NATR 处于高位，方向信号需要降低追单和仓位假设。"
            elif natr_f <= 1:
                score, state, impact = 50, "波动压缩", "neutral"
                reason = "波动压缩，方向信号尚未充分释放。"
            else:
                score, state, impact = 52, "中性波动", "neutral"
                reason = "波动处于中性区间，尚未形成极端执行风险。"
            evidence.append(
                SummaryEvidence(
                    "natr_14",
                    "volatility",
                    score,
                    state,
                    state,
                    impact,
                    reason,
                    ["ATR/NATR 是否进入扩张", "BOLL 宽度是否放大"],
                    {"natr_14": natr_f},
                )
            )
            scores.append(score)

        adx = snapshot.get("adx_14")
        plus_di = snapshot.get("plus_di")
        minus_di = snapshot.get("minus_di")
        if _is_number(adx):
            if _is_number(plus_di) and _is_number(minus_di):
                plus_f = float(plus_di)
                minus_f = float(minus_di)
                if float(adx) >= 25 and minus_f > plus_f + 3:
                    state = "DMI空头确认"
                    reason = "ADX 进入趋势有效区，且 -DI 高于 +DI，空头方向获得确认。"
                    score = 42
                elif float(adx) >= 25 and plus_f > minus_f + 3:
                    state = "DMI多头确认"
                    reason = "ADX 进入趋势有效区，且 +DI 高于 -DI，多头方向获得确认。"
                    score = 58
                else:
                    state = "DMI方向待确认"
                    reason = "ADX/DMI 尚未形成清晰方向优势。"
                    score = 50
            else:
                state = "ADX方向待确认"
                reason = "ADX 只判断趋势强度；缺少 +DI/-DI 时不判断方向。"
                score = 50
            evidence.append(
                SummaryEvidence(
                    "dmi_adx",
                    "volatility",
                    score,
                    state,
                    state,
                    "neutral",
                    reason,
                    ["ADX 是否持续高于 25", "+DI/-DI 是否继续拉开"],
                    {"adx_14": adx, "plus_di": plus_di, "minus_di": minus_di},
                )
            )
            scores.append(score)

        if not evidence:
            return None
        risk_items = [item for item in evidence if item.impact == "execution_risk"]
        impact = "execution_risk" if risk_items else "neutral"
        state = "高波动执行风险" if risk_items else "中性波动"
        reason = "；".join(item.reason for item in (risk_items or evidence)[:2])
        return ModuleScore(
            "volatility",
            _avg(scores),
            state,
            impact,
            reason,
            evidence,
            min(0.9, 0.4 + 0.12 * len(evidence)),
        )


def _num(value: Any, default: float = 0.0) -> float:
    try:
        if value is None:
            return default
        parsed = float(value)
        return parsed if isfinite(parsed) else default
    except (TypeError, ValueError):
        return default


def _avg(values: Sequence[float], default: float = 50.0) -> float:
    cleaned = [float(value) for value in values if isfinite(float(value))]
    return sum(cleaned) / len(cleaned) if cleaned else default


def _bounded_confidence(value: Any, default: float) -> float:
    parsed = _num(value, default)
    if parsed > 1:
        parsed = parsed / 100
    return max(0.2, min(0.95, parsed))


def _key(item: Mapping[str, Any]) -> str:
    return str(item.get("indicator_key") or item.get("key") or "").strip().lower()


def _technical_snapshot(observations: Sequence[Mapping[str, Any]]) -> dict[str, Any]:
    snapshot: dict[str, Any] = {}
    for item in observations:
        key = _key(item)
        value = item.get("value_num") if item.get("value_num") is not None else item.get("value")
        if key:
            snapshot[key] = value
        raw_values = item.get("raw_values")
        if isinstance(raw_values, Mapping):
            for raw_key, raw_value in raw_values.items():
                snapshot.setdefault(str(raw_key).strip().lower(), raw_value)
        value_json = item.get("value_json")
        if isinstance(value_json, Mapping):
            for raw_key, raw_value in value_json.items():
                normalized = str(raw_key).strip().lower()
                if normalized in {
                    "close",
                    "ema_20",
                    "ema20",
                    "ema_50",
                    "ema50",
                    "ema_200",
                    "ema200",
                    "vwap_50",
                    "vwap50",
                    "vwap_100",
                    "vwap100",
                    "previous_close",
                    "prev_close",
                    "close_change_pct",
                    "daily_change_pct",
                }:
                    snapshot.setdefault(normalized, raw_value)
    aliases = {
        "ema20": "ema_20",
        "ema50": "ema_50",
        "ema200": "ema_200",
        "vwap50": "vwap_50",
        "vwap100": "vwap_100",
        "rsi14": "rsi_14",
        "adx14": "adx_14",
        "atr14": "atr_14",
        "natr14": "natr_14",
        "prev_close": "previous_close",
        "daily_change_pct": "close_change_pct",
    }
    for source, target in aliases.items():
        if target not in snapshot and source in snapshot:
            snapshot[target] = snapshot[source]
    if "close" not in snapshot:
        for item in observations:
            raw = item.get("value_json")
            if isinstance(raw, Mapping) and raw.get("close") is not None:
                snapshot["close"] = raw.get("close")
                break
    return snapshot


def _market_context(observations: Sequence[Mapping[str, Any]]) -> dict[str, Any]:
    snapshot = _technical_snapshot(observations)
    instrument_id = "btc-usdt-perp"
    timeframe = "1d"
    for item in observations:
        raw_instrument = item.get("instrument_id") or item.get("symbol") or item.get("asset_code")
        raw_timeframe = item.get("timeframe")
        if raw_instrument:
            instrument_id = str(raw_instrument)
        if raw_timeframe:
            timeframe = str(raw_timeframe)
        if raw_instrument or raw_timeframe:
            break
    close = snapshot.get("close")
    previous_close = snapshot.get("previous_close")
    change_pct = snapshot.get("close_change_pct")
    if not _is_number(change_pct) and _is_number(close) and _is_number(previous_close):
        previous = float(previous_close)
        if previous != 0:
            change_pct = (float(close) - previous) / previous * 100
    instrument_label = "BTC" if "btc" in instrument_id.lower() else instrument_id.upper()
    timeframe_label = "日线" if timeframe.lower() in {"1d", "d", "day", "daily"} else timeframe
    return {
        "instrument_id": instrument_id,
        "timeframe": timeframe,
        "label": f"{instrument_label} {timeframe_label}",
        "close": close,
        "previous_close": previous_close,
        "close_change_pct": change_pct,
    }


def _is_number(value: Any) -> bool:
    try:
        return value is not None and isfinite(float(value))
    except (TypeError, ValueError):
        return False


def _iter_dicts(value: Any) -> list[Mapping[str, Any]]:
    if not isinstance(value, list):
        return []
    return [item for item in value if isinstance(item, Mapping)]


def _state_score_and_impact(key: str, state: str, tone: str, value: float) -> tuple[float, str]:
    normalized = state.lower()
    tone = tone.lower()
    if key == "rsi_14" and normalized in {"risk_cold", "oversold"}:
        return 42, "execution_risk"
    if (
        normalized in {"strong_bullish", "bullish", "positive_hist", "breakout_up"}
        or tone == "bullish"
    ):
        return (74 if normalized.startswith("strong") else 62), "bullish"
    if (
        normalized in {"strong_bearish", "bearish", "negative_hist", "breakout_down"}
        or tone == "bearish"
    ):
        return (26 if normalized.startswith("strong") else 38), "bearish"
    if normalized in {"risk_hot", "event", "high_volatility"} or tone == "event":
        return 45, "execution_risk"
    if normalized in {"neutral_bullish", "weak_bullish", "strong"}:
        return 58, "mild_bullish"
    if normalized in {"neutral_bearish", "weak_bearish", "weak"}:
        return 42, "mild_bearish"
    return 50, "neutral"


def _state_from_score(score: float) -> str:
    if score >= 72:
        return "明确偏多"
    if score >= 58:
        return "温和偏多"
    if score <= 28:
        return "明确偏空"
    if score <= 42:
        return "温和偏空"
    return "中性"


def _score_to_impact(score: float) -> str:
    if score >= 70:
        return "bullish"
    if score >= 58:
        return "mild_bullish"
    if score <= 30:
        return "bearish"
    if score <= 42:
        return "mild_bearish"
    return "neutral"


def _clean_reason(item: Mapping[str, Any]) -> str:
    for key in ("comment", "rule", "hint", "reason"):
        value = item.get(key)
        if value:
            return str(value)
    return ""


def _default_reason(key: str, label: str, state: str) -> str:
    if key.startswith("ema") or key.startswith("vwap"):
        return f"{label} 反映当前价格相对均线或成交均价的位置。"
    if key == "rsi_14":
        return "RSI 用于判断动量强弱；低于 30 时按反抽风险处理，不直接判多。"
    if key == "macd_hist":
        return "MACD 柱值用于判断动量延续或收敛。"
    if key in {"atr_14", "natr_14", "bbands_width"}:
        return "波动指标用于判断执行质量和追单风险，不直接判定多空。"
    return f"{label} 当前状态为 {state}。"


def _watch_points_for(key: str, state: str) -> list[str]:
    if key.startswith("ema"):
        return ["价格能否收复 EMA20", "EMA20/EMA50 斜率是否同步转向"]
    if key.startswith("vwap"):
        return ["价格能否站上 VWAP50", "VWAP 乖离是否扩大"]
    if key == "rsi_14":
        return ["RSI 是否修复至 40 上方", "是否出现动量背离"]
    if key == "macd_hist":
        return ["MACD 柱值是否连续收敛", "MACD 是否回到零轴上方"]
    if key in {"adx_14", "adx_direction", "plus_di", "minus_di"}:
        return ["ADX 是否持续高于 25", "+DI/-DI 是否继续拉开"]
    if key in {"atr_14", "natr_14", "bbands", "bbands_width"}:
        return ["ATR/NATR 是否进入扩张", "BOLL 宽度是否放大"]
    return []


# ---------------------------------------------------------------------------
# Decision brief helpers
# ---------------------------------------------------------------------------
# These helpers support ``TerminalSummaryEngine._build_decision_brief`` and
# are intentionally pure functions: no I/O, no network, no database. They
# tolerate partially available cache payloads by accepting loose mappings and
# falling back to neutral placeholders. The terminal summary is still
# computed by the main engine, so adding decision_brief never replaces the
# existing keys; downstream UI and tests that read regime/bias/confidence
# keep working unchanged.

_DECISION_DIRECTION_BEARISH = (
    "bear", "bearish", "short", "空", "偏空", "看空", "下行",
    "risk_pressure", "mild_bearish", "strong_bearish", "soft_bearish",
    "中性偏空", "风险升温", "卖压", "negative_hist", "breakout_down",
)
_DECISION_DIRECTION_BULLISH = (
    "bull", "bullish", "long", "多", "偏多", "看多", "上行",
    "risk_on", "risk_support", "mild_bullish", "strong_bullish",
    "soft_bullish", "中性偏多", "风险缓和", "买压", "positive_hist",
    "breakout_up",
)
_DECISION_DIRECTION_NEUTRAL = (
    "neutral", "中性", "震荡", "wait", "observe", "观望", "待确认",
    "sideways", "event_wait", "inactive", "not_triggered",
)


def _decision_direction(value: Any) -> str | None:
    """Map a wide range of tokens to ``bullish``/``bearish``/``neutral``."""

    if value is None:
        return None
    text = str(value).strip().lower()
    if not text:
        return None
    if any(token in text for token in _DECISION_DIRECTION_BEARISH):
        return "bearish"
    if any(token in text for token in _DECISION_DIRECTION_BULLISH):
        return "bullish"
    if any(token in text for token in _DECISION_DIRECTION_NEUTRAL):
        return "neutral"
    return None


def _decision_zh_direction(direction: str | None) -> str:
    return {"bullish": "多", "bearish": "空", "neutral": "中性"}.get(direction or "", "中性")


def _decision_as_mapping(value: Any) -> Mapping[str, Any]:
    return value if isinstance(value, Mapping) else {}


def _decision_as_list(value: Any) -> list[Any]:
    if value is None:
        return []
    if isinstance(value, list):
        return value
    if isinstance(value, tuple):
        return list(value)
    return [value]


def _decision_first_present(mapping: Mapping[str, Any], *keys: str) -> Any:
    for key in keys:
        if key in mapping and mapping[key] not in (None, "", [], {}):
            return mapping[key]
    return None


def _decision_text(value: Any, fallback: str = "") -> str:
    if value is None:
        return fallback
    if isinstance(value, (dict, list, tuple)):
        return str(value)
    text = str(value).strip()
    return text if text else fallback


def _decision_dedupe_text(items: Sequence[Any], limit: int | None = None) -> list[str]:
    seen: set[str] = set()
    out: list[str] = []
    for item in items or []:
        text = _decision_text(item)
        if not text or text in seen:
            continue
        seen.add(text)
        out.append(text)
        if limit is not None and len(out) >= limit:
            break
    return out


def _decision_collect_named_items(
    mapping: Mapping[str, Any], keys: Sequence[str]
) -> list[Any]:
    items: list[Any] = []
    for key in keys:
        if key not in mapping:
            continue
        value = mapping[key]
        if isinstance(value, list):
            items.extend(value)
        elif value not in (None, "", {}):
            items.append(value)
    return items


def _decision_extract_strategy(bundle: Mapping[str, Any]) -> Mapping[str, Any]:
    """Pull the actual strategy decision block from a strategy bundle payload."""

    if not bundle:
        return {}
    for key in ("decision", "strategy_decision", "payload", "result"):
        value = bundle.get(key)
        if isinstance(value, Mapping) and value:
            return value
    return bundle


def _decision_append_direction(
    out: list[tuple[str, str]], name: str, value: Any
) -> None:
    direction = _decision_direction(value)
    if direction:
        out.append((name, direction))


def _decision_timeframe_directions(
    timeframe_snapshots: Mapping[str, Any],
) -> list[tuple[str, str]]:
    out: list[tuple[str, str]] = []
    for timeframe, payload in timeframe_snapshots.items():
        mapping = _decision_as_mapping(payload)
        direction = _decision_direction(
            _decision_first_present(
                mapping, "bias", "direction", "trend", "final_direction", "state"
            )
        )
        if direction:
            out.append((f"analysis.{timeframe}", direction))
    return out


def _decision_source_alignment(
    *,
    base_summary: Mapping[str, Any],
    strategy_decision: Mapping[str, Any],
    chip: Mapping[str, Any],
    divergence: Mapping[str, Any],
    timeframe_snapshots: Mapping[str, Any],
    structure: Mapping[str, Any],
) -> dict[str, Any]:
    alignment: dict[str, Any] = {
        "primary_sources": [],
        "timeframes": [],
        "consistency": "degraded",
        "conflicts": [],
        "missing_sources": [],
        "matrix": [],
    }

    if timeframe_snapshots:
        alignment["primary_sources"].append("analysis_bundle")
        alignment["timeframes"].extend(str(key) for key in timeframe_snapshots.keys())
    else:
        alignment["missing_sources"].append("analysis_bundle.4h_1d_1w")

    if chip or divergence:
        alignment["primary_sources"].append("alerts_bundle")
    else:
        alignment["missing_sources"].append("alerts_bundle")

    if strategy_decision:
        alignment["primary_sources"].append("strategy_bundle")
    else:
        alignment["missing_sources"].append("strategy_bundle")

    if structure:
        alignment["primary_sources"].append("structure_bundle")
    else:
        alignment["missing_sources"].append("structure_bundle")

    directions: list[tuple[str, str]] = []
    _decision_append_direction(
        directions, "terminal_summary", base_summary.get("bias")
    )
    _decision_append_direction(
        directions,
        "strategy.decision",
        _decision_first_present(
            strategy_decision, "strategy_bias", "bias", "direction"
        ),
    )
    _decision_append_direction(
        directions,
        "alerts.chip_structure",
        _decision_first_present(
            chip, "direction", "direction_label", "bias", "signal"
        ),
    )
    div_direction_value = _decision_first_present(
        divergence, "direction", "direction_label", "bias", "signal"
    )
    if not div_direction_value:
        # DivergenceService emits ``overall.tone`` rather than ``direction``;
        # fall back to the nested block so cross-page comparison still works.
        overall = _decision_as_mapping(divergence.get("overall"))
        div_direction_value = _decision_first_present(
            overall, "tone", "direction", "title"
        )
    _decision_append_direction(directions, "alerts.divergence_summary", div_direction_value)
    directions.extend(_decision_timeframe_directions(timeframe_snapshots))

    positive = [name for name, direction in directions if direction == "bullish"]
    negative = [name for name, direction in directions if direction == "bearish"]

    if positive and negative:
        alignment["consistency"] = "conflict"
        alignment["conflicts"].append(
            "方向证据冲突：偏多来源=" + "、".join(positive) + "；偏空来源=" + "、".join(negative)
        )
    elif alignment["missing_sources"]:
        alignment["consistency"] = "degraded"
    elif directions and not (positive or negative):
        alignment["consistency"] = "mixed"
    elif directions:
        alignment["consistency"] = "aligned"

    tf_dirs = _decision_timeframe_directions(timeframe_snapshots)
    if len(set(direction for _, direction in tf_dirs)) > 1:
        alignment["consistency"] = "conflict"
        alignment["conflicts"].append(
            "4h/1d/1w 多周期方向不一致，交易准入需要降级为等待确认。"
        )

    alignment["primary_sources"] = _decision_dedupe_text(
        alignment["primary_sources"], limit=8
    )
    alignment["timeframes"] = _decision_dedupe_text(
        alignment["timeframes"], limit=8
    )
    alignment["conflicts"] = _decision_dedupe_text(
        alignment["conflicts"], limit=8
    )
    alignment["missing_sources"] = _decision_dedupe_text(
        alignment["missing_sources"], limit=8
    )
    alignment["matrix"] = _decision_conflict_matrix(
        base_summary=base_summary,
        strategy_decision=strategy_decision,
        chip=chip,
        divergence=divergence,
        timeframe_snapshots=timeframe_snapshots,
    )
    return alignment


def _decision_matrix_strength(*values: Any) -> float:
    """Compute evidence_strength for a matrix cell.

    Each value contributes a bounded score; the average of the non-zero
    scores is returned so a single piece of evidence does not by itself
    represent a confident cell.
    """

    scores: list[float] = []
    for value in values:
        if value is None or value == "" or value == {} or value == []:
            continue
        if isinstance(value, bool):
            scores.append(0.7 if value else 0.2)
            continue
        if isinstance(value, (int, float)):
            if 0 <= float(value) <= 1:
                scores.append(max(0.0, min(1.0, float(value))))
            else:
                scores.append(max(0.0, min(1.0, float(value) / 100.0)))
            continue
        text = str(value).strip().lower()
        if not text:
            continue
        if text in {"high", "strong", "fresh", "good", "较高", "ready"}:
            scores.append(0.85)
        elif text in {"medium", "normal", "ok", "degraded", "中等"}:
            scores.append(0.55)
        elif text in {"low", "weak", "stale", "stale_cache", "低", "不足"}:
            scores.append(0.3)
        elif text in {"blocked", "extreme", "invalid"}:
            scores.append(0.2)
        else:
            scores.append(0.6)
    if not scores:
        return 0.0
    return round(sum(scores) / len(scores), 4)


def _decision_conflict_matrix(
    *,
    base_summary: Mapping[str, Any],
    strategy_decision: Mapping[str, Any],
    chip: Mapping[str, Any],
    divergence: Mapping[str, Any],
    timeframe_snapshots: Mapping[str, Any],
) -> list[dict[str, Any]]:
    """Build the six-row multi-period conflict matrix.

    Rows are always in a fixed order so consumers can render them as a
    stable grid:
        1w_trend, 1d_bias, 4h_trigger, chip_structure,
        divergence_summary, strategy_gates
    """

    matrix: list[dict[str, Any]] = []
    for row in _MATRIX_ROW_DEFINITIONS:
        cell = _decision_matrix_row(
            row,
            base_summary=base_summary,
            strategy_decision=strategy_decision,
            chip=chip,
            divergence=divergence,
            timeframe_snapshots=timeframe_snapshots,
        )
        matrix.append(cell)
    return matrix


def _decision_matrix_row(
    row_def: dict[str, Any],
    *,
    base_summary: Mapping[str, Any],
    strategy_decision: Mapping[str, Any],
    chip: Mapping[str, Any],
    divergence: Mapping[str, Any],
    timeframe_snapshots: Mapping[str, Any],
) -> dict[str, Any]:
    key = row_def["key"]
    source = row_def["source"]
    direction = "missing"
    strength_values: list[Any] = []

    if source == "timeframe":
        tf_payload = _decision_as_mapping(timeframe_snapshots.get(row_def["timeframe"]))
        if tf_payload:
            direction_value = _decision_first_present(
                tf_payload, "bias", "direction", "trend", "final_direction", "state"
            )
            direction = _decision_direction(direction_value) or "neutral"
            strength_values = [
                tf_payload.get("confidence"),
                tf_payload.get("score"),
                tf_payload.get("regime"),
            ]
    elif source == "chip_structure":
        if chip:
            direction = _decision_direction(
                _decision_first_present(
                    chip, "direction", "direction_label", "bias", "signal"
                )
            ) or "neutral"
            strength_values = [
                chip.get("confidence_score"),
                chip.get("evidence_quality"),
                chip.get("data_quality"),
            ]
    elif source == "divergence_summary":
        if divergence:
            overall = _decision_as_mapping(divergence.get("overall"))
            tone = _decision_first_present(
                divergence, "direction", "direction_label", "bias", "signal"
            )
            if not tone and overall:
                tone = _decision_first_present(overall, "tone", "title")
            direction = _decision_direction(tone) or "neutral"
            strength_values = [
                overall.get("confidence") if overall else None,
                overall.get("score") if overall else None,
                divergence.get("trend_context"),
            ]
    elif source == "strategy_gates":
        if strategy_decision:
            bias = _decision_first_present(
                strategy_decision, "strategy_bias", "bias", "direction"
            )
            direction = _decision_direction(bias) or "neutral"
            # Only data-quality fields count. State and permission are
            # semantic - "blocked" does not mean weak evidence.
            strength_values = [
                strategy_decision.get("confidence_score"),
                strategy_decision.get("data_quality_score"),
            ]
    elif source == "terminal_summary":
        direction = _decision_direction(base_summary.get("bias")) or "neutral"
        confidence = base_summary.get("confidence")
        if isinstance(confidence, (int, float)):
            strength_values.append(float(confidence) / 100.0)
        else:
            strength_values.append(confidence)

    return {
        "key": key,
        "label": row_def["label"],
        "source": source,
        "timeframe": row_def.get("timeframe"),
        "direction": direction,
        "weight": row_def["weight"],
        "evidence_strength": _decision_matrix_strength(*strength_values),
    }


_MATRIX_ROW_DEFINITIONS: tuple[dict[str, Any], ...] = (
    {
        "key": "1w_trend",
        "label": "1w 趋势",
        "source": "timeframe",
        "timeframe": "1w",
        "weight": 0.18,
    },
    {
        "key": "1d_bias",
        "label": "1d 主战",
        "source": "timeframe",
        "timeframe": "1d",
        "weight": 0.22,
    },
    {
        "key": "4h_trigger",
        "label": "4h 触发",
        "source": "timeframe",
        "timeframe": "4h",
        "weight": 0.18,
    },
    {
        "key": "chip_structure",
        "label": "筹码结构",
        "source": "chip_structure",
        "weight": 0.15,
    },
    {
        "key": "divergence_summary",
        "label": "背离风险",
        "source": "divergence_summary",
        "weight": 0.12,
    },
    {
        "key": "strategy_gates",
        "label": "策略 gates",
        "source": "strategy_gates",
        "weight": 0.15,
    },
)


# Map decision_brief row ``source_refs`` to matrix keys. The mapping
# favours the closest evidence we have on hand. Unrecognised references
# fall back to the strategy_gates row (best-effort) so the row still
# receives an evidence_strength.
_SOURCE_REF_TO_MATRIX_KEY: dict[str, str] = {
    "alerts.chip_structure": "chip_structure",
    "alerts.divergence_summary": "divergence_summary",
    "alerts.final_decision": "strategy_gates",
    "strategy.decision": "strategy_gates",
    "strategy.gates": "strategy_gates",
    "structure.snapshot": "strategy_gates",
    "analysis.1w": "1w_trend",
    "analysis.1d": "1d_bias",
    "analysis.4h": "4h_trigger",
    "analysis.30d": "1w_trend",
    "analysis.1M": "1w_trend",
}

EVIDENCE_STRENGTH_THRESHOLD = 0.5


def _row_evidence_strength(
    source_refs: Sequence[str],
    matrix: Sequence[Mapping[str, Any]],
    base_summary: Mapping[str, Any],
) -> float:
    """Compute the minimum evidence_strength across the row's sources.

    The matrix is the source of truth for per-source strength. ``terminal_summary``
    is a self-referential fallback and never counts as independent evidence,
    so when the only source ref is the terminal summary itself the row is
    treated as having no real evidence (strength 0.0). The same applies when
    source_refs is empty.
    """

    matrix_strengths: list[float] = []
    matrix_index = {
        str(item.get("key")): item for item in matrix if isinstance(item, Mapping)
    }
    for ref in source_refs or []:
        if ref == "terminal_summary":
            continue
        key = _SOURCE_REF_TO_MATRIX_KEY.get(str(ref))
        if key and key in matrix_index:
            strength = matrix_index[key].get("evidence_strength")
            if isinstance(strength, (int, float)):
                matrix_strengths.append(float(strength))
    if matrix_strengths:
        return round(min(matrix_strengths), 4)
    return 0.0


def _apply_evidence_strength(row: dict[str, Any], strength: float) -> dict[str, Any]:
    """Attach evidence_strength to a row and demote tone/summary when low.

    When the strength is below ``EVIDENCE_STRENGTH_THRESHOLD`` the row is
    treated as advisory only: the tone becomes ``warning`` and the summary
    is prefixed with an explicit uncertainty note so the user never reads
    a directional verdict that is not actually supported by the data.
    """

    row["evidence_strength"] = round(float(strength), 4)
    if strength < EVIDENCE_STRENGTH_THRESHOLD:
        row["tone"] = "warning"
        prefix = f"证据强度 {int(strength * 100)}%，结论置信度有限。"
        existing = str(row.get("summary") or "")
        if not existing.startswith(prefix):
            row["summary"] = prefix + existing
    return row


def _decision_describe_timeframes(timeframe_snapshots: Mapping[str, Any]) -> str:
    if not timeframe_snapshots:
        return ""
    parts: list[str] = []
    for timeframe, payload in timeframe_snapshots.items():
        mapping = _decision_as_mapping(payload)
        direction = _decision_direction(
            _decision_first_present(
                mapping, "bias", "direction", "trend", "final_direction", "state"
            )
        )
        confidence = _decision_first_present(mapping, "confidence", "score")
        if direction:
            parts.append(f"{timeframe} 偏{_decision_zh_direction(direction)}")
        elif confidence is not None:
            parts.append(f"{timeframe} 评分 {confidence}")
        else:
            parts.append(f"{timeframe} 已有快照但方向未明")
    return "多周期状态：" + "；".join(parts) + "。"


# Ordered list of supported timeframes so the per-TF breakdown always reads
# high → low (1w → 1d → 4h). Anything not in this list is appended in the
# iteration order to keep the breakdown deterministic.
_TF_DISPLAY_ORDER: tuple[str, ...] = ("1w", "1d", "4h", "1h", "15m")


def _decision_format_mtf_breakdown(
    timeframe_snapshots: Mapping[str, Any],
    *,
    include_scores: bool = True,
) -> str:
    """T09: per-TF breakdown with score labels, sorted high→low.

    Replaces the old "4h/1d/1w 多周期方向不一致..." single-line. The user
    wants to see exactly which TFs are bullish and which are bearish so
    they can decide based on their own trading horizon. Example output:
    ``1w 偏多(score 62) / 1d 偏空(score 35) / 4h 偏空(score 28)``.
    Falls back to a coarser ``1w 偏多 / 1d 偏空 / 4h 偏空`` when scores are
    missing, and to a single dash when no snapshot is present.
    """

    if not timeframe_snapshots:
        return ""

    items: list[tuple[str, str, str | None]] = []
    seen: set[str] = set()
    for tf in _TF_DISPLAY_ORDER:
        if tf in timeframe_snapshots:
            seen.add(tf)
            mapping = _decision_as_mapping(timeframe_snapshots.get(tf))
            direction = _decision_direction(
                _decision_first_present(
                    mapping, "bias", "direction", "trend", "final_direction", "state"
                )
            )
            if direction:
                score = _decision_first_present(mapping, "score", "confidence")
                items.append((tf, _decision_zh_direction(direction), score))
            else:
                items.append((tf, "方向未明", _decision_first_present(mapping, "score")))
    for tf in timeframe_snapshots:
        if tf in seen:
            continue
        mapping = _decision_as_mapping(timeframe_snapshots.get(tf))
        direction = _decision_direction(
            _decision_first_present(
                mapping, "bias", "direction", "trend", "final_direction", "state"
            )
        )
        if direction:
            items.append((tf, _decision_zh_direction(direction), None))
        else:
            items.append((tf, "方向未明", None))

    if not items:
        return ""
    parts: list[str] = []
    for tf, label, score in items:
        if include_scores and score is not None:
            try:
                score_str = f"score {int(round(float(score)))}"
            except (TypeError, ValueError):
                score_str = f"score {score}"
            parts.append(f"{tf} 偏{label}({score_str})")
        else:
            parts.append(f"{tf} 偏{label}")
    return " / ".join(parts)


def _decision_mtf_has_conflict(
    timeframe_snapshots: Mapping[str, Any],
) -> bool:
    """Return True when the per-TF directions are not unanimous."""
    if not timeframe_snapshots:
        return False
    directions: set[str] = set()
    for payload in timeframe_snapshots.values():
        mapping = _decision_as_mapping(payload)
        direction = _decision_direction(
            _decision_first_present(
                mapping, "bias", "direction", "trend", "final_direction", "state"
            )
        )
        if direction:
            directions.add(direction)
    return len(directions) > 1


def _decision_describe_chip(chip: Mapping[str, Any]) -> str:
    if not chip:
        return ""
    regime = _decision_first_present(chip, "regime", "state", "structure_state", "title")
    direction = _decision_direction(
        _decision_first_present(
            chip, "direction", "direction_label", "bias", "signal"
        )
    )
    pressure = _decision_first_present(
        chip, "pressure", "pressure_label", "risk_level", "execution_label"
    )
    parts: list[str] = []
    if regime:
        parts.append(f"筹码结构={_decision_text(regime)}")
    if direction:
        parts.append(f"方向偏{_decision_zh_direction(direction)}")
    if pressure:
        parts.append(f"压力={_decision_text(pressure)}")
    return "筹码结构提示：" + "，".join(parts) + "。" if parts else ""


def _decision_describe_divergence(divergence: Mapping[str, Any]) -> str:
    if not divergence:
        return ""
    state = _decision_first_present(divergence, "state", "status", "summary", "title")
    overall = _decision_as_mapping(divergence.get("overall"))
    if not state and overall:
        state = _decision_first_present(overall, "title", "message", "tone")
    direction = _decision_direction(
        _decision_first_present(
            divergence, "direction", "direction_label", "bias", "signal"
        )
    )
    if not direction and overall:
        direction = _decision_direction(
            _decision_first_present(overall, "tone", "title")
        )
    risk = _decision_first_present(
        divergence, "risk_level", "risk", "severity"
    )
    if not risk and overall:
        risk = _decision_first_present(overall, "signal_kind", "confidence")
    parts: list[str] = []
    if state:
        parts.append(f"状态={_decision_text(state)}")
    if direction:
        parts.append(f"方向偏{_decision_zh_direction(direction)}")
    if risk:
        parts.append(f"风险={_decision_text(risk)}")
    return "背离风险提示：" + "，".join(parts) + "。" if parts else ""


def _decision_describe_trigger(trigger: Mapping[str, Any]) -> str:
    if not trigger:
        return ""
    label = _decision_first_present(
        trigger, "label", "title", "name", "condition"
    )
    price = _decision_first_present(
        trigger, "price", "level", "trigger_price"
    )
    timeframe = _decision_first_present(trigger, "timeframe", "tf")
    parts: list[str] = []
    if timeframe:
        parts.append(f"周期={_decision_text(timeframe)}")
    if label:
        parts.append(f"条件={_decision_text(label)}")
    if price is not None:
        parts.append(f"价位={_decision_text(price)}")
    return "下一触发器：" + "，".join(parts) + "。" if parts else ""


def _decision_format_trigger(trigger: Any) -> str:
    """Render the strategy's next_trigger for the trading row.

    The audit (T02) found that ``_decision_as_mapping(decision.get('next_trigger'))``
    silently swallowed string and list triggers because the formatter only
    understood dict shapes. The strategy generator can legitimately emit any
    of: a human string, a list of trigger conditions, or a structured dict.
    All three must surface in the trading row.
    """

    if trigger is None or trigger == "" or trigger == [] or trigger == {}:
        return ""
    if isinstance(trigger, str):
        return "下一触发器：" + trigger.strip() + "。"
    if isinstance(trigger, (list, tuple)):
        items = [_decision_text(item) for item in trigger if item not in (None, "")]
        if not items:
            return ""
        return "下一触发器：" + "；".join(items) + "。"
    mapping = _decision_as_mapping(trigger)
    if mapping:
        return _decision_describe_trigger(mapping)
    return "下一触发器：" + _decision_text(trigger) + "。"


_BLOCK_SEVERITIES = {"block", "blocked", "blocking"}
_WARN_SEVERITIES = {"warn", "warning"}
_PASS_STATUSES = {"pass", "ok"}


def _decision_gate_from_any(item: Any) -> GateDiagnostic | None:
    """Normalize a single gate entry into a ``GateDiagnostic``.

    Accepts a ``GateDiagnostic`` instance, a dict with the standard fields,
    a plain string (treated as the message), or ``None`` (skipped). Unknown
    shapes return ``None`` so the caller can filter them out and the row
    never silently renders a half-parsed value.
    """

    if item is None:
        return None
    if isinstance(item, GateDiagnostic):
        return item
    if isinstance(item, Mapping):
        code = str(item.get("code") or item.get("id") or "UNKNOWN_GATE")
        raw_severity = str(
            item.get("severity") or item.get("level") or "info"
        ).lower()
        status = str(item.get("status") or "info").lower()
        message = str(item.get("message") or item.get("reason") or code)
        # Map "warn" / "blocked" / "blocking" to the canonical severity set.
        if raw_severity in _BLOCK_SEVERITIES:
            severity = "block"
        elif raw_severity in _WARN_SEVERITIES:
            severity = "warning"
        elif raw_severity in {"info"}:
            severity = "info"
        else:
            severity = "info"
        return GateDiagnostic(
            code=code,
            status=status if status in {"pass", "fail", "warn", "missing", "info"} else "info",
            message=message,
            current=item.get("current", item.get("value")),
            required=item.get("required", item.get("threshold")),
            severity=severity,
        )
    if isinstance(item, str):
        text = item.strip()
        if not text:
            return None
        lowered = text.lower()
        if lowered in _BLOCK_SEVERITIES:
            return GateDiagnostic(
                code=text, status="fail", message=text, severity="block"
            )
        if lowered in _WARN_SEVERITIES:
            return GateDiagnostic(
                code=text, status="warn", message=text, severity="warning"
            )
        if lowered in _PASS_STATUSES:
            return GateDiagnostic(
                code=text, status="pass", message=text, severity="info"
            )
        return GateDiagnostic(code=text, status="info", message=text, severity="info")
    return None


def _decision_normalize_gates(gates: Any) -> list[GateDiagnostic]:
    """Normalize any gates payload into a list of ``GateDiagnostic``."""

    if gates is None:
        return []
    if isinstance(gates, GateDiagnostic):
        return [gates]
    if isinstance(gates, Mapping):
        if not gates:
            return []
        normalized = _decision_gate_from_any(gates)
        return [normalized] if normalized else []
    if isinstance(gates, (list, tuple, set)):
        output: list[GateDiagnostic] = []
        for item in gates:
            normalized = _decision_gate_from_any(item)
            if normalized is not None:
                output.append(normalized)
        return output
    if isinstance(gates, str):
        normalized = _decision_gate_from_any(gates)
        return [normalized] if normalized else []
    return []


def _decision_format_gate_bullet(gate: GateDiagnostic) -> str:
    """Render one GateDiagnostic as a Chinese sentence fragment."""

    if gate.severity == "block" or gate.status in {"fail", "missing"}:
        prefix = "未通过"
    elif gate.severity == "warning" or gate.status == "warn":
        prefix = "风险提示"
    elif gate.status in _PASS_STATUSES:
        prefix = "已通过"
    else:
        prefix = "门槛"
    body = gate.message or gate.code
    extras: list[str] = []
    if gate.current is not None and gate.current != "":
        extras.append(f"当前 {_decision_text(gate.current)}")
    if gate.required is not None and gate.required != "":
        extras.append(f"要求 {_decision_text(gate.required)}")
    if extras:
        body = body + "（" + "，".join(extras) + "）"
    return f"{prefix}：{body}"


def _decision_format_gates(
    gates: Any, *, limit: int = 4
) -> tuple[list[str], bool, bool]:
    """Render gates for both the trading row and the risk row.

    Returns a tuple of (bullets, has_block, has_warning). Pass / info gates
    are folded (not surfaced as bullets) per the T03 spec; the trading row
    never needs to see gates it has already cleared. ``has_block`` is True
    when at least one gate is severity block or status fail/missing; those
    are the gates the audit found were silently dropped. ``has_warning`` lets
    the trading row downgrade the tone to ``warning`` even when no gate is
    fully blocking.
    """

    normalized = _decision_normalize_gates(gates)
    if not normalized:
        return [], False, False

    def priority(gate: GateDiagnostic) -> int:
        if gate.severity == "block" or gate.status in {"fail", "missing"}:
            return 0
        if gate.severity == "warning" or gate.status == "warn":
            return 1
        return 2

    def is_surfaced(gate: GateDiagnostic) -> bool:
        # Fold pass / info gates; they have already cleared and only add noise.
        if gate.status in _PASS_STATUSES or gate.severity == "info":
            return False
        return True

    surfaced = [gate for gate in normalized if is_surfaced(gate)]
    ordered = sorted(surfaced, key=priority)
    bullets = [_decision_format_gate_bullet(gate) for gate in ordered[:limit]]
    has_block = any(
        gate.severity == "block" or gate.status in {"fail", "missing"}
        for gate in normalized
    )
    has_warning = any(
        gate.severity == "warning" or gate.status == "warn"
        for gate in normalized
    )
    return bullets, has_block, has_warning


def _decision_extract_futures_pressure(decision: Mapping[str, Any]) -> dict[str, Any] | None:
    """Pull the active side's futures margin pressure from the decision bundle.

    The audit (T06) requires the risk row to surface a margin-pressure
    verdict whenever the active side is non-ok. The decision bundle
    embeds the snapshot's ``futures_risk`` payload; we accept both the
    direct dict and the normalized ``primary_strategy`` shape.
    """

    risk = decision.get("futures_risk") or decision.get("primary_strategy", {}).get(
        "futures_risk"
    )
    if not isinstance(risk, Mapping) or not risk:
        return None
    side = decision.get("strategy_bias") or decision.get("dominant_direction")
    if side not in {"long", "short"}:
        sides = [key for key in ("long", "short") if key in risk]
        if not sides:
            return None
        side = sides[0]
    bundle = risk.get(side)
    if not isinstance(bundle, Mapping):
        return None
    return {
        "side": side,
        "level": bundle.get("futures_margin_pressure"),
        "impact_pct": bundle.get("one_atr_margin_impact_pct"),
        "stop_impact_pct": bundle.get("stop_margin_impact_pct"),
        "liquidation_buffer_pct": bundle.get("liquidation_buffer_pct"),
        "leverage": bundle.get("leverage"),
        "atr_pct": bundle.get("atr_pct"),
    }


def _decision_format_futures_pressure(payload: Mapping[str, Any]) -> str:
    """Render a one-line summary of the futures margin pressure verdict."""

    level = str(payload.get("level") or "ok")
    impact = payload.get("impact_pct")
    buffer = payload.get("liquidation_buffer_pct")
    leverage = payload.get("leverage")
    side_label = "做多" if payload.get("side") == "long" else "做空"
    fragments: list[str] = []
    if impact is not None:
        fragments.append(f"one-ATR 影响 {impact}%")
    if buffer is not None:
        fragments.append(f"强平缓冲 {buffer}%")
    if leverage is not None:
        fragments.append(f"{leverage}x 杠杆")
    suffix = "；".join(fragments)
    if level == "block":
        return f"合约保证金压力=block：{side_label}侧合约开仓被拒绝（{suffix}）。"
    if level == "small":
        return f"合约保证金压力偏高：{side_label}侧建议降至最小观察仓（{suffix}）。"
    if level == "downsize":
        return f"合约保证金压力中等：{side_label}侧建议减半仓位（{suffix}）。"
    return ""


def _decision_describe_strategy_levels(strategy: Mapping[str, Any]) -> str:
    if not strategy:
        return ""
    levels = _decision_as_mapping(strategy.get("levels")) or strategy
    entry = _decision_first_present(
        levels, "entry", "entry_price", "entry_zone"
    )
    stop = _decision_first_present(
        levels, "stop", "stop_loss", "invalid_price", "invalidation_price"
    )
    take_profit = _decision_first_present(
        levels, "take_profit", "tp", "target", "targets"
    )
    parts: list[str] = []
    if entry is not None:
        parts.append(f"入场参考={_decision_text(entry)}")
    if stop is not None:
        parts.append(f"失效/止损={_decision_text(stop)}")
    if take_profit is not None:
        parts.append(f"止盈/目标={_decision_text(take_profit)}")
    return "策略价位：" + "，".join(parts) + "。" if parts else ""


def _decision_build_market_row(
    *,
    base_summary: Mapping[str, Any],
    chip: Mapping[str, Any],
    divergence: Mapping[str, Any],
    timeframe_snapshots: Mapping[str, Any],
    alignment: Mapping[str, Any],
) -> dict[str, Any]:
    """T09: market_situation row carries the per-TF breakdown in the headline.

    The audit found that the previous headline was a single
    abstract sentence (``当前维持中性震荡结构。多空模块分歧明显...``)
    that hid the per-TF disagreement. When the timeframes conflict we
    now render the actual breakdown so the user can decide based on
    their own trading horizon. The chips and divergence bullets stay
    inline because they are aggregations, not re-computations.
    """

    regime = _decision_text(base_summary.get("regime"), "中性震荡")
    bias = _decision_direction(base_summary.get("bias")) or "neutral"
    confidence = _decision_text(base_summary.get("confidence"), "--")
    mtf_breakdown = _decision_format_mtf_breakdown(
        timeframe_snapshots, include_scores=True
    )

    bullets: list[str] = []
    sources: list[str] = ["terminal_summary"]

    if mtf_breakdown:
        bullets.append("多周期状态：" + mtf_breakdown + "。")
        sources.extend(f"analysis.{tf}" for tf in timeframe_snapshots.keys())

    chip_comment = _decision_describe_chip(chip)
    if chip_comment:
        bullets.append(chip_comment)
        sources.append("alerts.chip_structure")

    div_comment = _decision_describe_divergence(divergence)
    if div_comment:
        bullets.append(div_comment)
        sources.append("alerts.divergence_summary")

    if not bullets:
        bullets.append(
            _decision_text(
                base_summary.get("headline"),
                "关键输入不足，等待宏观、技术与结构数据刷新。",
            )
        )

    consistency = alignment.get("consistency") or "degraded"
    has_mtf_conflict = _decision_mtf_has_conflict(timeframe_snapshots)
    if has_mtf_conflict:
        summary = (
            f"高周期与短周期方向冲突：{mtf_breakdown}。"
            "请按你的交易周期判断。"
        )
        tone = "warning"
    elif consistency == "conflict":
        summary = (
            f"当前为{regime}，但跨页面证据存在冲突，方向结论需要等待确认。"
        )
        tone = "warning"
    elif consistency == "degraded":
        summary = (
            f"当前维持{regime}判断，置信度 {confidence}，但部分页面证据缺失。"
        )
        tone = "warning"
    else:
        summary = (
            f"当前维持{regime}，方向偏{_decision_zh_direction(bias)}，"
            f"置信度 {confidence}。"
        )
        tone = bias

    dedup_sources = _decision_dedupe_text(sources, limit=8)
    row = {
        "key": "market_situation",
        "title": "市场情况",
        "tone": tone,
        "summary": summary,
        "bullets": _decision_dedupe_text(bullets, limit=6),
        "source_refs": dedup_sources,
    }
    strength = _row_evidence_strength(
        dedup_sources, alignment.get("matrix") or [], base_summary
    )
    return _apply_evidence_strength(row, strength)


def _decision_build_mtf_breakdown_row(
    *,
    timeframe_snapshots: Mapping[str, Any],
    alignment: Mapping[str, Any],
) -> dict[str, Any] | None:
    """T09: dedicated row showing the per-TF breakdown in conflict cases.

    The user explicitly asked: "大小周期的多空矛盾可以直接写清楚出来，
    让用户根据自己的交易周期去思考" — so we surface the actual
    high→low per-TF list in its own row whenever the directions
    disagree. When the TFs are aligned, the row is omitted (the
    market_situation summary already says so). When no TF data is
    available, the row is also omitted so we never fabricate.
    """

    if not timeframe_snapshots:
        return None
    if not _decision_mtf_has_conflict(timeframe_snapshots):
        return None
    breakdown = _decision_format_mtf_breakdown(
        timeframe_snapshots, include_scores=True
    )
    if not breakdown:
        return None
    sources = ["terminal_summary"] + [
        f"analysis.{tf}" for tf in timeframe_snapshots.keys()
    ]
    row = {
        "key": "mtf_breakdown",
        "title": "多周期方向",
        "tone": "warning",
        "summary": (
            f"高周期与短周期方向冲突：{breakdown}。"
            "短线交易以 1h/4h 为准，中长线以 1d/1w 为准。"
        ),
        "bullets": [f"具体方向：{breakdown}。"],
        "source_refs": _decision_dedupe_text(sources, limit=8),
    }
    strength = _row_evidence_strength(
        row["source_refs"], alignment.get("matrix") or [], {}
    )
    return _apply_evidence_strength(row, strength)


def _decision_build_trading_row(
    *,
    base_summary: Mapping[str, Any],
    decision: Mapping[str, Any],
    final_decision: Mapping[str, Any],
    alignment: Mapping[str, Any],
) -> dict[str, Any]:
    """Dormant. T09 removed the ``trading_guidance`` row from the
    decision brief because it re-rendered the strategy page in the
    overview and violated the "summary layer, not recomputation"
    principle. This function is kept for backward compatibility with
    tests that import it directly; ``_build_decision_brief`` no longer
    calls it.
    """

    return {
        "key": "trading_guidance_removed_v1_5_2",
        "title": "交易指引（已下线）",
        "tone": "neutral",
        "summary": "交易指引已迁移到 AI 策略页 / 监控总览不再重复呈现。",
        "bullets": [],
        "source_refs": ["terminal_summary.removed"],
    }


def _decision_build_key_risk_row(
    *,
    base_summary: Mapping[str, Any],
    decision: Mapping[str, Any],
    chip: Mapping[str, Any],
    divergence: Mapping[str, Any],
    structure: Mapping[str, Any],
    alignment: Mapping[str, Any],
) -> dict[str, Any]:
    """T09: renamed from ``_decision_build_risk_row``.

    The previous risk row enumerated every chip / divergence / structure
    risk and re-rendered the strategy gates, violating the
    "summary layer, not recomputation" principle. The new row carries
    only the highest-signal items:

    * data gaps from ``source_alignment.missing_sources``
    * the most critical invalidation condition across chip / structure
    * (gated) the futures margin pressure verdict — T10 hides it when
      the strategy has no actionable plan.

    The row is renamed ``key_risk`` so the frontend can no longer rely
    on the old ``risk_invalidation`` key.
    """

    bullets: list[str] = []
    sources: list[str] = []

    for missing in alignment.get("missing_sources") or []:
        bullets.append(f"数据缺口：{missing} 缺失或未刷新。")
        sources.append(f"missing:{missing}")

    # Pick the single most critical invalidation condition across all
    # sources. The audit complained that the old row listed every chip
    # risk note; here we surface one representative line per source
    # so the user has something actionable without a wall of text.
    critical = _decision_pick_critical_invalidation(
        chip=chip,
        divergence=divergence,
        structure=structure,
    )
    if critical:
        bullets.append(f"关键失效：{critical}")
        sources.append(critical.get("source") or "structure.snapshot")

    # T10: surface the futures margin pressure verdict only when the
    # active strategy is actually entering a position. The function
    # returns False for OBSERVE / NO_EDGE / WAIT_* / EVENT_WAIT /
    # RISK_OFF / INVALID_PLAN_LEVELS / terminal states, so the
    # "OBSERVE + 建议减半仓位" contradiction is no longer rendered.
    futures_pressure = _decision_extract_futures_pressure(decision)
    if (
        futures_pressure
        and futures_pressure.get("level") not in {None, "ok"}
        and _decision_should_show_futures_pressure(decision)
    ):
        pressure_line = _decision_format_futures_pressure(futures_pressure)
        if pressure_line:
            bullets.append(pressure_line)
            sources.append("strategy.futures_risk")

    if not bullets:
        bullets.append(
            "若价格重新站回或跌破关键均线、VWAP、结构边界，"
            "或告警中心证据反向确认，则当前判断失效。"
        )
        sources.append("terminal_summary")

    consistency = alignment.get("consistency") or "degraded"
    missing = alignment.get("missing_sources") or []
    if consistency == "aligned" and not missing:
        summary = (
            "当前主要关注关键价位、筹码区和动量背离是否反向确认；"
            "一旦触发即降低或撤销原判断。"
        )
    else:
        summary = (
            "当前判断的主要风险来自数据缺口、跨周期冲突、"
            "筹码/背离反向确认以及策略 gates 未通过。"
        )

    dedup_sources = _decision_dedupe_text(sources, limit=8)
    row = {
        "key": "key_risk",
        "title": "关键失效",
        "tone": "warning",
        "summary": summary,
        "bullets": _decision_dedupe_text(bullets, limit=4),
        "source_refs": dedup_sources,
    }
    strength = _row_evidence_strength(
        dedup_sources, alignment.get("matrix") or [], base_summary
    )
    return _apply_evidence_strength(row, strength)


def _decision_pick_critical_invalidation(
    *,
    chip: Mapping[str, Any],
    divergence: Mapping[str, Any],
    structure: Mapping[str, Any],
) -> dict[str, Any] | None:
    """Pick a single highest-signal invalidation condition.

    The previous code enumerated every chip / divergence / structure
    risk note. The audit asked for a single critical line so the
    overview stays concise. We prefer the chip's first
    ``invalidation_conditions`` entry (it is the most concrete
    price-level condition), then fall back to structure, then
    divergence.
    """

    candidates: list[tuple[int, dict[str, Any]]] = []
    for source, payload in (
        ("alerts.chip_structure", chip),
        ("structure.snapshot", structure),
        ("alerts.divergence_summary", divergence),
    ):
        if not isinstance(payload, Mapping) or not payload:
            continue
        items = _decision_collect_named_items(
            payload,
            ("invalidation_conditions", "invalidation", "watch_points", "risk_points"),
        )
        for item in items[:1]:
            text = _decision_text(item)
            if not text:
                continue
            priority = 0 if "alerts.chip_structure" in source else 1
            candidates.append((priority, {"text": text, "source": source}))
    if not candidates:
        return None
    candidates.sort(key=lambda pair: pair[0])
    return candidates[0][1]


def _decision_build_risk_row(
    *,
    base_summary: Mapping[str, Any],
    decision: Mapping[str, Any],
    chip: Mapping[str, Any],
    divergence: Mapping[str, Any],
    structure: Mapping[str, Any],
    alignment: Mapping[str, Any],
) -> dict[str, Any]:
    """Dormant. T09 renamed the public row to ``key_risk``. Kept so any
    external caller that imports the symbol still works, but the
    overview no longer uses it.
    """

    return _decision_build_key_risk_row(
        base_summary=base_summary,
        decision=decision,
        chip=chip,
        divergence=divergence,
        structure=structure,
        alignment=alignment,
    )
