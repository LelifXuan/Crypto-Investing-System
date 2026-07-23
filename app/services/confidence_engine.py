from __future__ import annotations

from app.models.confidence import (
    ConfidenceComponentScore,
    ConfidenceEngineInput,
    ConfidenceEngineReport,
)

COMPONENT_WEIGHTS = {
    "data_quality_score": 0.24,
    "timeframe_alignment_score": 0.22,
    "structure_confirmation_score": 0.18,
    "momentum_volume_score": 0.16,
    "derivatives_micro_score": 0.14,
    "regime_fit_score": 0.06,
}

DIRECTION_LABEL_ZH = {
    "strong_long": "强做多",
    "long": "做多",
    "neutral": "中性",
    "short": "做空",
    "strong_short": "强做空",
}

ACTION_LABEL_ZH = {
    "observe": "观察",
    "wait_for_confirmation": "等待确认",
    "probe": "试仓",
    "normal_trade": "正常交易",
    "add_on_confirmation": "确认加仓",
    "no_trade": "不交易",
    "reduce_or_exit": "减仓或退出",
}

RISK_GATE_LABEL_ZH = {
    "NO_USABLE_CANDLES": "K线数据不足",
    "EXECUTION_SCORE_TOO_LOW": "执行质量过低",
    "SLIPPAGE_HARD_LIMIT": "滑点超限",
    "SPREAD_HARD_LIMIT": "价差超限",
    "PRICE_INDEX_DEVIATION_EXTREME": "价格指数偏离过大",
    "PRICE_MARK_DEVIATION_EXTREME": "标记价格偏离过大",
}

PAIR_WEIGHTS = {
    ("1w", "1d"): 0.35,
    ("1d", "4h"): 0.35,
    ("4h", "1h"): 0.20,
    ("1w", "4h"): 0.10,
}

EVIDENCE_CAPS = {
    "missing": 0.0,
    "proxy_only": 60.0,
    "partially_confirmed": 75.0,
    "confirmed": 100.0,
}
CONFLICT_CAPS = {0: 100.0, 1: 82.0, 2: 60.0, 3: 45.0}
DATA_QUALITY_CAPS = {
    "no_data": 0.0,
    "bad": 35.0,
    "degraded": 55.0,
    "acceptable": 75.0,
    "good": 100.0,
}


class ConfidenceEngine:
    def evaluate(self, payload: ConfidenceEngineInput) -> ConfidenceEngineReport:
        direction_score = self._clamp(payload.direction_score, -100.0, 100.0)
        direction_label = self._direction_label(direction_score)

        components = {
            "data_quality_score": self._data_quality_component(payload),
            "timeframe_alignment_score": self._timeframe_alignment_component(payload),
            "structure_confirmation_score": self._structure_component(payload),
            "momentum_volume_score": self._momentum_component(payload),
            "derivatives_micro_score": self._derivatives_component(payload),
            "regime_fit_score": self._regime_component(payload),
        }
        raw_confidence = 100.0 * sum(item.weighted for item in components.values())
        execution_score = self._execution_score(payload)
        risk_score = self._risk_score(payload)
        risk_gates, hard_veto_caps = self._risk_gates(payload, execution_score)
        penalties = self._penalties(payload)
        confidence_cap = self._confidence_cap(
            payload,
            execution_score=execution_score,
            hard_veto_caps=hard_veto_caps,
        )
        confidence_score = self._clamp(raw_confidence - penalties["total"], 0.0, confidence_cap)
        hard_veto_triggered = bool(hard_veto_caps) or confidence_cap == 0.0
        recommended_action = self._recommended_action(
            confidence_score=confidence_score,
            execution_score=execution_score,
            risk_score=risk_score,
            conflict_level=payload.conflict_level,
            evidence_quality=payload.evidence_quality,
            hard_veto_triggered=hard_veto_triggered,
            payload=payload,
        )
        position_multiplier = self._position_multiplier(
            confidence_score=confidence_score,
            execution_score=execution_score,
            conflict_level=payload.conflict_level,
            evidence_quality=payload.evidence_quality,
            hard_veto_triggered=hard_veto_triggered,
        )
        explain = self._explain(
            payload=payload,
            components=components,
            penalties=penalties,
            confidence_cap=confidence_cap,
            risk_gates=risk_gates,
            recommended_action=recommended_action,
            direction_label=direction_label,
        )
        return ConfidenceEngineReport(
            direction_score=round(direction_score, 2),
            direction_label=direction_label,
            confidence_score=round(confidence_score, 2),
            confidence_label=self._confidence_label(confidence_score),
            execution_score=round(execution_score, 2),
            execution_label=self._execution_label(execution_score),
            risk_score=round(risk_score, 2),
            risk_label=self._risk_label(risk_score),
            confidence_cap=round(confidence_cap, 2),
            conflict_level=max(0, min(int(payload.conflict_level), 3)),
            evidence_quality=payload.evidence_quality,
            position_multiplier=round(position_multiplier, 2),
            recommended_action=recommended_action,
            explain=explain,
            components=components,
            risk_gates=risk_gates,
            hard_veto_triggered=hard_veto_triggered,
        )

    def _data_quality_component(self, payload: ConfidenceEngineInput) -> ConfidenceComponentScore:
        status = str(payload.data_quality_status or "").lower()
        raw = self._clamp(payload.data_quality_score / 100.0, 0.0, 1.0)
        if status in {"missing", "bad"}:
            raw *= 0.2
        elif status in {"degraded", "fair"}:
            raw *= 0.72
        return ConfidenceComponentScore(
            raw=raw,
            weighted=raw * COMPONENT_WEIGHTS["data_quality_score"],
            detail={"status": status, "score": round(payload.data_quality_score, 2)},
        )

    def _timeframe_alignment_component(
        self, payload: ConfidenceEngineInput
    ) -> ConfidenceComponentScore:
        biases = payload.timeframe_biases
        agreement = 0.0
        details: dict[str, float | str | bool] = {}
        penalties = 0.0
        for (left, right), weight in PAIR_WEIGHTS.items():
            left_bias = biases.get(left, "neutral")
            right_bias = biases.get(right, "neutral")
            pair_score = self._pair_alignment(left_bias, right_bias)
            agreement += pair_score * weight
            details[f"{left}_{right}"] = round(pair_score, 3)
            if left == "1w" and right == "1d" and self._is_opposite(left_bias, right_bias):
                penalties += 0.22
            if left == "1d" and right == "4h" and self._is_opposite(left_bias, right_bias):
                penalties += 0.18
        if abs(payload.direction_score) >= 65:
            agreement += 0.08
        elif abs(payload.direction_score) <= 20:
            agreement -= 0.06
        raw = self._clamp(agreement - penalties, 0.0, 1.0)
        return ConfidenceComponentScore(
            raw=raw,
            weighted=raw * COMPONENT_WEIGHTS["timeframe_alignment_score"],
            detail=details,
        )

    def _structure_component(self, payload: ConfidenceEngineInput) -> ConfidenceComponentScore:
        if not payload.structure.available:
            raw = 0.5
            return ConfidenceComponentScore(
                raw=raw,
                weighted=raw * COMPONENT_WEIGHTS["structure_confirmation_score"],
                detail={"available": False},
            )
        overall_confidence = self._clamp(payload.structure.overall_confidence, 0.0, 1.0)
        direction_agreement = self._clamp(payload.structure.direction_agreement, 0.0, 1.0)
        evidence_density = self._clamp(payload.structure.evidence_density, 0.0, 1.0)
        raw = overall_confidence * 0.5 + direction_agreement * 0.3 + evidence_density * 0.2
        if payload.structure.conflict_state:
            raw -= 0.18
        raw = self._clamp(raw, 0.0, 1.0)
        return ConfidenceComponentScore(
            raw=raw,
            weighted=raw * COMPONENT_WEIGHTS["structure_confirmation_score"],
            detail={
                "available": True,
                "overall_bias": payload.structure.overall_bias,
                "overall_score": round(payload.structure.overall_score, 4),
                "overall_confidence": round(payload.structure.overall_confidence, 4),
                "conflict_state": payload.structure.conflict_state,
            },
        )

    def _momentum_component(self, payload: ConfidenceEngineInput) -> ConfidenceComponentScore:
        direction_sign = 1 if payload.direction_score >= 0 else -1
        adx_component = self._clamp(payload.h4_adx / 35.0, 0.0, 1.0)
        obv_h4 = self._clamp(0.5 + (payload.h4_obv_slope * direction_sign * 2.0), 0.0, 1.0)
        obv_h1 = self._clamp(0.5 + (payload.h1_obv_slope * direction_sign * 2.0), 0.0, 1.0)
        squeeze_component = 0.65 if payload.h4_bb_width <= 0.055 else 0.5
        if payload.breakout_up or payload.breakout_down:
            squeeze_component += 0.12
        if payload.false_breakout or payload.false_breakdown:
            squeeze_component -= 0.22
        raw = self._clamp(
            adx_component * 0.35 + obv_h4 * 0.25 + obv_h1 * 0.20 + squeeze_component * 0.20,
            0.0,
            1.0,
        )
        return ConfidenceComponentScore(
            raw=raw,
            weighted=raw * COMPONENT_WEIGHTS["momentum_volume_score"],
            detail={
                "adx": round(payload.h4_adx, 2),
                "h4_obv_slope": round(payload.h4_obv_slope, 4),
                "h1_obv_slope": round(payload.h1_obv_slope, 4),
            },
        )

    def _derivatives_component(self, payload: ConfidenceEngineInput) -> ConfidenceComponentScore:
        direction_sign = 1 if payload.direction_score >= 0 else -1
        confirmations: list[float] = []
        if payload.cvd_delta is not None:
            confirmations.append(
                self._clamp(0.5 + (payload.cvd_delta / 5000.0) * direction_sign, 0.0, 1.0)
            )
        if payload.open_interest_notional is not None:
            confirmations.append(0.75 if payload.open_interest_notional > 0 else 0.35)
        if payload.depth_liquidity is not None:
            confirmations.append(self._clamp(payload.depth_liquidity / 500000.0, 0.0, 1.0))
        if payload.slippage_bps is not None:
            confirmations.append(self._clamp(1.0 - payload.slippage_bps / 25.0, 0.0, 1.0))
        if payload.spread_bps is not None:
            confirmations.append(self._clamp(1.0 - payload.spread_bps / 18.0, 0.0, 1.0))
        if not confirmations:
            raw = 0.4
        else:
            raw = sum(confirmations) / len(confirmations)
        crowding_penalty = max(abs(payload.funding_zscore or 0.0), abs(payload.basis_zscore or 0.0))
        raw -= min(crowding_penalty / 8.0, 0.18)
        raw = self._clamp(raw, 0.0, 1.0)
        return ConfidenceComponentScore(
            raw=raw,
            weighted=raw * COMPONENT_WEIGHTS["derivatives_micro_score"],
            detail={
                "cvd_delta": round(payload.cvd_delta or 0.0, 2),
                "open_interest_notional": round(payload.open_interest_notional or 0.0, 2),
                "depth_liquidity": round(payload.depth_liquidity or 0.0, 2),
                "slippage_bps": round(payload.slippage_bps or 0.0, 2),
                "spread_bps": round(payload.spread_bps or 0.0, 2),
            },
        )

    def _regime_component(self, payload: ConfidenceEngineInput) -> ConfidenceComponentScore:
        raw = 0.5
        if payload.primary_regime in {
            "bullish_continuation_range",
            "bearish_continuation_range",
            "accumulation_confirmed",
            "distribution_confirmed",
        }:
            raw = 0.82
        elif payload.primary_regime in {"accumulation_proxy", "distribution_proxy"}:
            raw = 0.64
        elif payload.primary_regime in {"false_breakout", "false_breakdown"}:
            raw = 0.42
        elif payload.primary_regime in {"liquidity_drought", "leverage_compression"}:
            raw = 0.35
        if payload.h4_adx >= 25 and payload.primary_regime.endswith("continuation_range"):
            raw += 0.1
        if payload.false_breakout or payload.false_breakdown:
            raw -= 0.12
        raw = self._clamp(raw, 0.0, 1.0)
        return ConfidenceComponentScore(
            raw=raw,
            weighted=raw * COMPONENT_WEIGHTS["regime_fit_score"],
            detail={"primary_regime": payload.primary_regime},
        )

    def _execution_score(self, payload: ConfidenceEngineInput) -> float:
        score = 72.0
        readiness = payload.execution_readiness
        if readiness == "blocked":
            score = 15.0
        elif readiness == "waiting_confirmation":
            score = 48.0
        elif readiness == "early":
            score = 62.0
        elif readiness == "confirmed":
            score = 82.0
        if payload.depth_liquidity is not None:
            if payload.depth_liquidity < 150000:
                score -= 25.0
            elif payload.depth_liquidity < 300000:
                score -= 12.0
        if payload.spread_bps is not None:
            if payload.spread_bps > 25:
                score -= 30.0
            elif payload.spread_bps > 12:
                score -= 12.0
        if payload.slippage_bps is not None:
            if payload.slippage_bps > 35:
                score -= 35.0
            elif payload.slippage_bps > 18:
                score -= 18.0
        for deviation in (
            payload.price_to_mark_deviation_bps,
            payload.price_to_index_deviation_bps,
        ):
            if deviation is None:
                continue
            abs_dev = abs(deviation)
            if abs_dev > 60:
                score -= 35.0
            elif abs_dev > 30:
                score -= 16.0
        return self._clamp(score, 0.0, 100.0)

    def _risk_score(self, payload: ConfidenceEngineInput) -> float:
        score = 18.0
        crowding = max(abs(payload.funding_zscore or 0.0), abs(payload.basis_zscore or 0.0))
        score += min(crowding * 18.0, 40.0)
        if payload.false_breakout or payload.false_breakdown:
            score += 14.0
        if payload.risk_reduce_size:
            score += 18.0
        if payload.risk_pause_trading:
            score += 42.0
        if payload.conflict_level >= 2:
            score += 12.0
        return self._clamp(score, 0.0, 100.0)

    def _risk_gates(
        self, payload: ConfidenceEngineInput, execution_score: float
    ) -> tuple[list[str], list[float]]:
        gates: list[str] = []
        caps: list[float] = []
        if payload.data_quality_score <= 0:
            gates.append("NO_USABLE_CANDLES")
            caps.append(0.0)
        if execution_score < 35:
            gates.append("EXECUTION_SCORE_TOO_LOW")
            caps.append(35.0)
        if payload.slippage_bps is not None and payload.slippage_bps > 35:
            gates.append("SLIPPAGE_HARD_LIMIT")
            caps.append(45.0)
        if payload.spread_bps is not None and payload.spread_bps > 25:
            gates.append("SPREAD_HARD_LIMIT")
            caps.append(45.0)
        if (
            payload.price_to_index_deviation_bps is not None
            and abs(payload.price_to_index_deviation_bps) > 60
        ):
            gates.append("PRICE_INDEX_DEVIATION_EXTREME")
            caps.append(45.0)
        if (
            payload.price_to_mark_deviation_bps is not None
            and abs(payload.price_to_mark_deviation_bps) > 60
        ):
            gates.append("PRICE_MARK_DEVIATION_EXTREME")
            caps.append(45.0)
        return gates, caps

    def _penalties(self, payload: ConfidenceEngineInput) -> dict[str, float]:
        missing_map = {
            "cvd": 8.0,
            "open_interest": 8.0,
            "depth": 10.0,
            "slippage": 10.0,
            "spread": 8.0,
            "funding": 6.0,
            "basis": 6.0,
            "structure_fusion": 8.0,
        }
        missing_penalty = 0.0
        joined = " ".join(payload.missing_inputs).lower()
        for key, penalty in missing_map.items():
            if key in joined:
                missing_penalty += penalty
        if not payload.structure.available:
            missing_penalty += missing_map["structure_fusion"]
        conflict_penalty = {0: 0.0, 1: 5.0, 2: 12.0, 3: 22.0}.get(payload.conflict_level, 22.0)
        abnormal_penalty = 0.0
        if max(abs(payload.funding_zscore or 0.0), abs(payload.basis_zscore or 0.0)) >= 2.2:
            abnormal_penalty += 8.0
        if payload.false_breakout or payload.false_breakdown:
            abnormal_penalty += 8.0
        if payload.structure.available and payload.structure.conflict_state:
            abnormal_penalty += 12.0
        return {
            "missing_inputs": missing_penalty,
            "conflict": conflict_penalty,
            "abnormal_market": abnormal_penalty,
            "total": missing_penalty + conflict_penalty + abnormal_penalty,
        }

    def _confidence_cap(
        self,
        payload: ConfidenceEngineInput,
        *,
        execution_score: float,
        hard_veto_caps: list[float],
    ) -> float:
        caps = [
            EVIDENCE_CAPS.get(payload.evidence_quality, 60.0),
            CONFLICT_CAPS.get(max(0, min(payload.conflict_level, 3)), 45.0),
            self._data_quality_cap(payload),
            self._execution_cap(payload, execution_score),
            self._price_deviation_cap(payload),
            self._missing_group_cap(payload),
        ]
        caps.extend(hard_veto_caps)
        return min(caps) if caps else 100.0

    def _data_quality_cap(self, payload: ConfidenceEngineInput) -> float:
        if payload.data_quality_score <= 0 or payload.state == "missing":
            return DATA_QUALITY_CAPS["no_data"]
        status = str(payload.data_quality_status or "").lower()
        if status in {"bad"}:
            return DATA_QUALITY_CAPS["bad"]
        if status in {"degraded"}:
            return DATA_QUALITY_CAPS["degraded"]
        if status in {"fair", "acceptable"}:
            return DATA_QUALITY_CAPS["acceptable"]
        return DATA_QUALITY_CAPS["good"]

    def _execution_cap(self, payload: ConfidenceEngineInput, execution_score: float) -> float:
        cap = 100.0
        if execution_score < 35:
            cap = min(cap, 35.0)
        elif execution_score < 50:
            cap = min(cap, 50.0)
        if payload.depth_liquidity is not None and payload.depth_liquidity < 200000:
            cap = min(cap, 50.0)
        if payload.spread_bps is not None and payload.spread_bps > 12:
            cap = min(cap, 50.0)
        if payload.slippage_bps is not None and payload.slippage_bps > 18:
            cap = min(cap, 45.0)
        return cap

    def _price_deviation_cap(self, payload: ConfidenceEngineInput) -> float:
        cap = 100.0
        for deviation in (
            payload.price_to_mark_deviation_bps,
            payload.price_to_index_deviation_bps,
        ):
            if deviation is None:
                continue
            deviation = abs(deviation)
            if deviation > 60:
                cap = min(cap, 45.0)
            elif deviation > 30:
                cap = min(cap, 65.0)
        return cap

    def _missing_group_cap(self, payload: ConfidenceEngineInput) -> float:
        major = {
            "cvd": payload.cvd_delta is None,
            "oi": payload.open_interest_notional is None,
            "depth": payload.depth_liquidity is None,
            "slippage": payload.slippage_bps is None,
            "spread": payload.spread_bps is None,
        }
        if all(major.values()):
            return 55.0
        if major["cvd"] and major["oi"]:
            return 65.0
        if not payload.structure.available:
            return 80.0
        return 100.0

    def _recommended_action(
        self,
        *,
        confidence_score: float,
        execution_score: float,
        risk_score: float,
        conflict_level: int,
        evidence_quality: str,
        hard_veto_triggered: bool,
        payload: ConfidenceEngineInput,
    ) -> str:
        if (
            hard_veto_triggered
            or confidence_score < 35
            or execution_score < 35
            or payload.data_quality_score == 0
        ):
            return "no_trade"
        if risk_score >= 80:
            return "reduce_or_exit"
        if 35 <= confidence_score < 50:
            return "observe"
        if 50 <= confidence_score < 65:
            return "wait_for_confirmation"
        if 65 <= confidence_score < 75 and execution_score >= 50 and conflict_level <= 1:
            return "probe"
        if (
            confidence_score >= 82
            and execution_score >= 75
            and conflict_level == 0
            and evidence_quality == "confirmed"
        ):
            return "add_on_confirmation"
        if (
            confidence_score >= 75
            and execution_score >= 70
            and conflict_level <= 1
            and evidence_quality != "proxy_only"
        ):
            return "normal_trade"
        return "wait_for_confirmation"

    def _position_multiplier(
        self,
        *,
        confidence_score: float,
        execution_score: float,
        conflict_level: int,
        evidence_quality: str,
        hard_veto_triggered: bool,
    ) -> float:
        if hard_veto_triggered or confidence_score < 65:
            return 0.0
        if confidence_score < 75:
            return 0.15
        if confidence_score < 82:
            return 0.35
        if confidence_score < 90 and conflict_level <= 1 and execution_score >= 70:
            return 0.6
        if (
            confidence_score >= 90
            and conflict_level == 0
            and execution_score >= 80
            and evidence_quality == "confirmed"
        ):
            return 0.8
        return 0.35

    def _explain(
        self,
        *,
        payload: ConfidenceEngineInput,
        components: dict[str, ConfidenceComponentScore],
        penalties: dict[str, float],
        confidence_cap: float,
        risk_gates: list[str],
        recommended_action: str,
        direction_label: str,
    ) -> list[str]:
        available_components = [
            component.label
            for component in components.values()
            if component.available and component.raw_score is not None
        ]
        component_text = "、".join(available_components[:4]) or "当前可用证据"
        lines = [
            (
                f"方向判断为{DIRECTION_LABEL_ZH.get(direction_label, direction_label)}，"
                f"主要来自{component_text}的综合加权。"
            ),
            (
                f"当前置信上限为 {confidence_cap:.0f}，由证据质量、冲突等级、"
                "执行质量和缺失输入共同限制。"
            ),
        ]
        if penalties["total"] > 0:
            lines.append(
                f"处罚项：缺失输入扣 {penalties['missing_inputs']:.0f}，"
                f"冲突扣 {penalties['conflict']:.0f}，"
                f"异常市场扣 {penalties['abnormal_market']:.0f}。"
            )
        if payload.structure.available and payload.structure.top_reasons:
            lines.append(f"结构侧证据：{payload.structure.top_reasons[0]}")
        if risk_gates:
            gate_text = " ".join(RISK_GATE_LABEL_ZH.get(item, item) for item in risk_gates)
            lines.append(f"风控门禁：{gate_text}")
        action_text = ACTION_LABEL_ZH.get(recommended_action, recommended_action)
        lines.append(f"建议动作：{action_text}")
        return lines

    def _pair_alignment(self, left: str, right: str) -> float:
        if left == right and left != "neutral":
            return 1.0
        if left == "neutral" or right == "neutral":
            return 0.55
        if self._is_opposite(left, right):
            return 0.0
        return 0.35

    @staticmethod
    def _is_opposite(left: str, right: str) -> bool:
        return {left, right} == {"bullish", "bearish"}

    @staticmethod
    def _direction_label(score: float) -> str:
        if score >= 65:
            return "strong_long"
        if score >= 30:
            return "long"
        if score <= -65:
            return "strong_short"
        if score <= -30:
            return "short"
        return "neutral"

    @staticmethod
    def _confidence_label(score: float) -> str:
        if score <= 0:
            return "invalid"
        if score < 35:
            return "low"
        if score < 50:
            return "watch_only"
        if score < 75:
            return "usable"
        if score < 85:
            return "high"
        return "execution_ready"

    @staticmethod
    def _execution_label(score: float) -> str:
        if score < 35:
            return "blocked"
        if score < 50:
            return "poor"
        if score < 70:
            return "acceptable"
        if score < 85:
            return "good"
        return "strong"

    @staticmethod
    def _risk_label(score: float) -> str:
        if score < 30:
            return "normal"
        if score < 60:
            return "elevated"
        if score < 80:
            return "high"
        return "extreme"

    @staticmethod
    def _clamp(value: float, low: float, high: float) -> float:
        return max(low, min(high, value))
