from __future__ import annotations

from .common import (
    SYSTEMS,
    FusionResult,
    ScoreBundle,
    ScoringConfig,
    clamp,
    direction_from_score,
    normalize_weights,
)


class WeightTemplateResolver:

    def __init__(self, config: ScoringConfig) -> None:

        self.config = config



    def resolve(self, timeframe: str, regime: str) -> tuple[str, dict[str, float]]:

        base = dict(self.config.base_weights.get(timeframe, self.config.base_weights["1d"]))

        delta = self.config.regime_deltas.get(regime, self.config.regime_deltas["transition"])

        adjusted = {system: base.get(system, 0.0) + delta.get(system, 0.0) for system in SYSTEMS}

        return regime, normalize_weights(adjusted, self.config.min_weights)





class RegimeClassifier:

    def classify(self, bundles: dict[str, ScoreBundle]) -> str:

        swing = bundles["swing"]

        classic = bundles["classic"]

        profile = bundles["profile"]

        if abs(swing.direction_score) >= 0.45 and profile.metadata.get("balance_score", 0.0) < 0.45:

            return "trend"

        if profile.metadata.get("balance_score", 0.0) >= 0.60 and abs(swing.direction_score) < 0.30:

            return "balance"

        if (

            classic.metadata.get("candidate_weight", 0.0) >= 0.50

            or profile.metadata.get("imbalance", 0.0) >= 0.40

        ):

            return "transition"

        return "trend" if abs(swing.direction_score) >= 0.35 else "balance"





class StructureFusionEngine:

    def __init__(self, config: ScoringConfig) -> None:

        self.config = config

        self.weight_resolver = WeightTemplateResolver(config)

        self.regime_classifier = RegimeClassifier()



    def fuse(self, timeframe: str, bundles: dict[str, ScoreBundle]) -> FusionResult:

        regime = self.regime_classifier.classify(bundles)

        weight_template, weights = self.weight_resolver.resolve(timeframe, regime)

        contributions = {

            system: weights[system] * bundle.effective_score for system, bundle in bundles.items()

        }

        overall_score = sum(contributions.values())

        agreement = self._agreement_score(bundles)

        conflict_state = self._conflict_state(bundles)

        if conflict_state:

            overall_score = self._apply_conflict_cap(overall_score, bundles)

        overall_bias = self._map_bias(overall_score, bundles, agreement, conflict_state)

        weighted_confidences = [weights[name] * bundles[name].confidence for name in SYSTEMS]

        density = clamp(sum(bundle.evidence_count for bundle in bundles.values()) / 12.0, 0.0, 1.0)

        overall_confidence = clamp(

            0.55 * sum(weighted_confidences) + 0.25 * agreement + 0.20 * density, 0.0, 1.0

        )

        primary = []

        opposing = []

        top_reasons = []

        for system in sorted(SYSTEMS, key=lambda item: abs(contributions[item]), reverse=True):

            bundle = bundles[system]

            if contributions[system] >= 0:

                primary.extend(bundle.top_reasons[:2])

            else:

                opposing.extend(bundle.top_reasons[:2])

            top_reasons.extend(bundle.top_reasons[:2])

        return FusionResult(

            overall_bias=overall_bias,

            overall_score=clamp(overall_score, -1.0, 1.0),

            overall_confidence=overall_confidence,

            evidence_density=density,

            regime=regime,

            weight_template=weight_template,

            weights=weights,

            contribution_breakdown=contributions,

            conflict_state=conflict_state,

            conflict_type=self._conflict_type(bundles, regime, conflict_state),

            dominant_side=self._dominant_side(bundles),

            opposing_side=self._opposing_side(bundles),

            meaning=self._conflict_meaning(bundles, regime, conflict_state),

            risk=self._risk_message(bundles, regime, conflict_state),

            need_confirmation=self._need_confirmation(bundles, regime, conflict_state),

            invalidation=self._invalidation_hint(bundles, regime, conflict_state),

            suggested_mode=self._suggested_mode(bundles, regime, conflict_state),

            suggested_action=self._suggested_action(bundles, regime, conflict_state),

            primary_drivers=primary[:4],

            opposing_factors=opposing[:4],

            top_reasons=top_reasons[:6],

        )



    def _agreement_score(self, bundles: dict[str, ScoreBundle]) -> float:

        directions = [

            direction_from_score(bundle.effective_score)

            for bundle in bundles.values()

            if abs(bundle.effective_score) >= 0.08

        ]

        if not directions:

            return 0.0

        dominant = max(

            directions.count("bullish"), directions.count("bearish"), directions.count("neutral")

        )

        return clamp(dominant / max(len(directions), 1), 0.0, 1.0)



    def _conflict_state(self, bundles: dict[str, ScoreBundle]) -> bool:

        strong = [

            (name, bundle)

            for name, bundle in bundles.items()

            if abs(bundle.effective_score) >= 0.18

        ]

        bullish = [name for name, bundle in strong if bundle.effective_score > 0]

        bearish = [name for name, bundle in strong if bundle.effective_score < 0]

        return bool(bullish and bearish)



    def _apply_conflict_cap(self, overall_score: float, bundles: dict[str, ScoreBundle]) -> float:

        swing = bundles["swing"].effective_score

        classic = bundles["classic"].effective_score

        profile = bundles["profile"].effective_score

        if swing >= 0.22 and classic <= -0.18 and abs(profile) < 0.10:

            return min(overall_score, 0.34)

        if swing <= -0.22 and classic >= 0.18 and abs(profile) < 0.10:

            return max(overall_score, -0.34)

        return overall_score * 0.68



    def _support_count(self, bundles: dict[str, ScoreBundle], direction: str) -> int:

        return sum(

            1

            for bundle in bundles.values()

            if bundle.direction == direction and abs(bundle.effective_score) >= 0.08

        )



    def _map_bias(

        self,

        overall_score: float,

        bundles: dict[str, ScoreBundle],

        agreement: float,

        conflict_state: bool,

    ) -> str:

        if all(abs(bundle.effective_score) < 0.08 for bundle in bundles.values()):

            return "no_clear_structure"

        bullish_support = self._support_count(bundles, "bullish")

        bearish_support = self._support_count(bundles, "bearish")

        if (
            not bullish_support
            and not bearish_support
            and all(bundle.direction == "neutral" for bundle in bundles.values())
            and abs(overall_score) < 0.20
        ):
            return "neutral"

        if conflict_state and abs(overall_score) < 0.20:

            return "uncertain"

        if overall_score >= self.config.bullish_threshold:

            if bullish_support >= 2 and agreement >= 0.67 and not conflict_state:

                return "bullish"

            return "weak_bullish"

        if overall_score >= self.config.weak_bullish_threshold:

            if bullish_support >= 1:

                return "weak_bullish"

            return "uncertain"

        if overall_score <= self.config.bearish_threshold:

            if bearish_support >= 2 and agreement >= 0.67 and not conflict_state:

                return "bearish"

            return "weak_bearish"

        if overall_score <= self.config.weak_bearish_threshold:

            if bearish_support >= 1:

                return "weak_bearish"

            return "uncertain"

        if bullish_support and not bearish_support and overall_score > 0.08:

            return "weak_bullish"

        if bearish_support and not bullish_support and overall_score < -0.08:

            return "weak_bearish"

        if agreement >= 0.67 and abs(overall_score) < 0.10:

            return "neutral"

        return "uncertain"



    def _dominant_side(self, bundles: dict[str, ScoreBundle]) -> str | None:

        scored = sorted(bundles.values(), key=lambda item: abs(item.effective_score), reverse=True)

        if not scored or abs(scored[0].effective_score) < 0.08:

            return None

        return scored[0].direction



    def _opposing_side(self, bundles: dict[str, ScoreBundle]) -> str | None:

        dominant = self._dominant_side(bundles)

        if dominant is None:

            return None

        for bundle in sorted(

            bundles.values(), key=lambda item: abs(item.effective_score), reverse=True

        ):

            if (

                bundle.direction not in {dominant, "neutral"}

                and abs(bundle.effective_score) >= 0.08

            ):

                return bundle.direction

        return None



    def _conflict_type(

        self, bundles: dict[str, ScoreBundle], regime: str, conflict_state: bool

    ) -> str | None:

        if any(bundle.metadata.get("risk_veto") for bundle in bundles.values()):

            return "risk_veto_conflict"

        if not conflict_state:

            if regime == "transition":

                return "timeframe_conflict"

            return None

        swing = bundles["swing"]

        classic = bundles["classic"]

        profile = bundles["profile"]

        if (

            swing.direction != classic.direction

            and abs(swing.effective_score) >= 0.18

            and abs(classic.effective_score) >= 0.18

        ):

            return "system_conflict"

        if any(

            flag == "momentum_divergence" for flag in classic.conflict_flags + swing.conflict_flags

        ):

            return "momentum_divergence"

        if (

            profile.metadata.get("balance_score", 0.0) >= 0.55

            and swing.direction != profile.direction

        ):

            return "volume_conflict"

        if profile.metadata.get("imbalance", 0.0) >= 0.40 and regime == "transition":

            return "volatility_conflict"

        if any(flag == "crowding" for flag in profile.conflict_flags):

            return "derivatives_crowding_conflict"

        return "system_conflict"



    def _conflict_meaning(

        self, bundles: dict[str, ScoreBundle], regime: str, conflict_state: bool

    ) -> str | None:

        conflict_type = self._conflict_type(bundles, regime, conflict_state)

        if conflict_type == "system_conflict":

            return "多套分析系统方向不一致，需更多确认信号。"

        if conflict_type == "timeframe_conflict":

            return "多周期方向分歧，等待高周期与低周期统一。"

        if conflict_type == "momentum_divergence":

            return "价格与动量出现背离，趋势可靠性降低。"

        if conflict_type == "volume_conflict":

            return "成交量未能确认价格方向，量价关系不匹配。"

        if conflict_type == "volatility_conflict":

            return "波动较高且方向不明，交易环境不确定。"

        if conflict_type == "derivatives_crowding_conflict":

            return "衍生品仓位拥挤，反转风险上升。"

        if conflict_type == "risk_veto_conflict":

            return "风险门禁已触发，当前不可交易。"

        return None



    def _need_confirmation(

        self, bundles: dict[str, ScoreBundle], regime: str, conflict_state: bool

    ) -> str | None:

        if (

            not conflict_state

            and regime != "transition"

            and not any(bundle.metadata.get("risk_veto") for bundle in bundles.values())

        ):

            return None

        return "当前方向需要额外确认信号后再入场。"



    def _invalidation_hint(

        self, bundles: dict[str, ScoreBundle], regime: str, conflict_state: bool

    ) -> str | None:

        if (

            not conflict_state

            and regime != "transition"

            and not any(bundle.metadata.get("risk_veto") for bundle in bundles.values())

        ):

            return None

        dominant = self._dominant_side(bundles)

        if dominant == "bullish":

            return "若价格跌破最近结构低点，多头结构失效。"

        if dominant == "bearish":

            return "若价格突破最近结构高点，空头结构失效。"

        return "若无后续确认或价格反向突破关键位，结构可能失效。"



    def _suggested_mode(

        self, bundles: dict[str, ScoreBundle], regime: str, conflict_state: bool

    ) -> str | None:

        if any(bundle.metadata.get("risk_veto") for bundle in bundles.values()):

            return "风险关闭 / 暂停交易"

        if conflict_state:

            return "观望 / 等待 / 仅观察"

        if regime == "transition":

            return "可等待确认后酌情轻仓"

        return "正常模式"



    def _risk_message(

        self, bundles: dict[str, ScoreBundle], regime: str, conflict_state: bool

    ) -> str | None:

        conflict_type = self._conflict_type(bundles, regime, conflict_state)

        if conflict_type == "risk_veto_conflict":

            return "多个风险门禁已触发，系统建议暂停交易。"

        if conflict_type == "volatility_conflict":

            return "波动较高且方向不明，交易环境不确定。"

        if conflict_type == "derivatives_crowding_conflict":

            return "衍生品市场过度拥挤，反转概率偏高。"

        if conflict_state:

            return "分析系统存在内部矛盾，信号可靠度下降。"

        if regime == "transition":

            return "市场处于过渡期，方向尚未明确。"

        return None



    def _suggested_action(

        self, bundles: dict[str, ScoreBundle], regime: str, conflict_state: bool

    ) -> str | None:

        if any(bundle.metadata.get("risk_veto") for bundle in bundles.values()):

            return "暂停所有新开仓，等待风险解除后再评估。"

        if conflict_state:

            return "建议观望，等待各分析系统达成方向共识。"

        if regime == "transition":

            return "可等待确认后逐步分批建仓。"

        dominant = self._dominant_side(bundles)

        if dominant == "bullish":

            return "可考虑回调做多，注意控制仓位。"

        if dominant == "bearish":

            return "可考虑反弹做空，注意控制仓位。"

        return "方向不明确，建议观望或小额试仓。"
