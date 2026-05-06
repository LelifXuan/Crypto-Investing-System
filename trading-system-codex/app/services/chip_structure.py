from __future__ import annotations

from dataclasses import dataclass
from datetime import UTC, datetime
from decimal import Decimal
from typing import Any

from app.models.confidence import ConfidenceEngineInput, StructureConfidenceInput
from app.quant.indicators import adx_wilder_series, bbands_series, ema_series, obv_series
from app.repositories.market_repository import MarketRepository
from app.schemas.market import CandleRead
from app.services.chip_structure_decision_policy import (
    decide_chip_structure_action,
    suppress_futures_allocation,
)
from app.services.confidence_engine import ConfidenceEngine
from app.services.data_quality import DataQualityAssessment, DataQualityMonitor
from app.services.indicator_matrix import IndicatorMatrixService
from app.services.market_data_bundle import MarketDataBundleService
from app.services.risk import RiskEngine, RiskInput
from app.services.structure.profile import build_profile

PRIMARY_TIMEFRAMES = ("1w", "1d", "4h", "1h")
TIMEFRAME_LABELS = {"1w": "1W", "1d": "1D", "4h": "4H", "1h": "1H"}
STATIC_MISSING_INPUTS = (
    "未接入未平仓量（OI）链路",
    "未接入多空比链路",
    "未接入 CVD / Delta 链路",
    "未接入盘口深度链路",
    "未接入 spread / slippage 链路",
    "当前仅有基于 OHLCV 的 volume profile 近似结果",
)
MICROSTRUCTURE_KEYS = (
    "cvd_delta",
    "open_interest_notional",
    "depth_liquidity",
    "slippage_bps",
)


@dataclass(slots=True)
class TimeframeSnapshot:
    timeframe: str
    label: str
    candles: list[Any]
    quality: DataQualityAssessment
    close: float
    profile: dict[str, Any]
    ema20: float
    ema50: float
    ema200: float
    adx: float
    bb_width: float
    bb_percent_b: float
    obv_slope: float
    range_position: str
    bias: str
    summary: str
    evidence: list[str]
    breakout_up: bool = False
    breakout_down: bool = False
    false_breakout: bool = False
    false_breakdown: bool = False


@dataclass(slots=True)
class ChipStructureContext:
    instrument_id: str
    timeframe: str
    snapshots: dict[str, TimeframeSnapshot]
    observations: dict[str, float | None]
    missing_inputs: list[str]
    evidence_quality: str


class ChipStructureService:
    def __init__(self, repository: MarketRepository) -> None:
        self.repository = repository
        self.market_data = MarketDataBundleService(repository)
        self.indicator_matrix = IndicatorMatrixService(repository)
        self.quality_monitor = DataQualityMonitor()
        self.risk_engine = RiskEngine()
        self.confidence_engine = ConfidenceEngine()

    async def analyze(self, instrument_id: str, timeframe: str) -> dict[str, Any]:
        context = await self._build_context(instrument_id, timeframe)
        snapshots = context.snapshots
        missing_inputs = list(context.missing_inputs)

        if not any(snapshot.quality.can_analyze for snapshot in snapshots.values()):
            return self._missing_payload(context)

        weekly = snapshots["1w"]
        daily = snapshots["1d"]
        h4 = snapshots["4h"]
        h1 = snapshots["1h"]

        funding_rate = context.observations.get("funding_rate")
        funding_zscore = context.observations.get("funding_rate_zscore")
        basis_rate = context.observations.get("basis_rate")
        basis_zscore = context.observations.get("basis_rate_zscore")
        cvd_delta = context.observations.get("cvd_delta")
        oi_notional = context.observations.get("open_interest_notional")

        primary_regime, secondary_regime = self._select_regimes(
            weekly=weekly,
            daily=daily,
            h4=h4,
            h1=h1,
            funding_rate=funding_rate,
            funding_zscore=funding_zscore,
            basis_rate=basis_rate,
            basis_zscore=basis_zscore,
            cvd_delta=cvd_delta,
            oi_notional=oi_notional,
            evidence_quality=context.evidence_quality,
        )
        direction_score = self._direction_score(
            weekly,
            daily,
            h4,
            h1,
            funding_rate,
            basis_rate,
            cvd_delta=cvd_delta,
            oi_notional=oi_notional,
        )
        conflict_level = self._conflict_level(weekly, daily, h4, h1, funding_zscore, basis_zscore)
        data_quality = self._aggregate_quality(snapshots, missing_inputs)

        risk_assessment = self.risk_engine.assess(
            RiskInput(
                entry_price=Decimal(str(max(h1.close, 1.0))),
                equity=Decimal("100000"),
                requested_notional=Decimal("100000"),
                current_total_exposure=Decimal("0"),
                data_quality_ok=data_quality["status"] != "missing",
                highs=[Decimal(str(candle.high)) for candle in h1.candles[-80:]],
                lows=[Decimal(str(candle.low)) for candle in h1.candles[-80:]],
                closes=[Decimal(str(candle.close)) for candle in h1.candles[-80:]],
            )
        )

        state = self._state(data_quality, missing_inputs, risk_assessment)
        state_label = self._state_label(data_quality, missing_inputs, risk_assessment)
        state_reason = self._state_reason(data_quality, missing_inputs, risk_assessment)
        execution_readiness = self._execution_readiness(
            h4, h1, conflict_level, state, risk_assessment
        )
        structure_signal = await self._latest_structure_signal(instrument_id, context.timeframe)
        confidence_report = self.confidence_engine.evaluate(
            ConfidenceEngineInput(
                instrument_id=instrument_id,
                timeframe=context.timeframe,
                data_quality_status=data_quality["status"],
                data_quality_score=float(data_quality["score"]),
                missing_inputs=missing_inputs,
                evidence_quality=context.evidence_quality,
                conflict_level=conflict_level,
                state=state,
                direction_score=direction_score,
                timeframe_biases={
                    "1w": weekly.bias,
                    "1d": daily.bias,
                    "4h": h4.bias,
                    "1h": h1.bias,
                },
                primary_regime=primary_regime,
                h4_adx=h4.adx,
                h4_bb_width=h4.bb_width,
                h1_bb_width=h1.bb_width,
                h4_obv_slope=h4.obv_slope,
                h1_obv_slope=h1.obv_slope,
                breakout_up=h4.breakout_up or h1.breakout_up,
                breakout_down=h4.breakout_down or h1.breakout_down,
                false_breakout=h4.false_breakout or h1.false_breakout,
                false_breakdown=h4.false_breakdown or h1.false_breakdown,
                funding_rate=funding_rate,
                funding_zscore=funding_zscore,
                basis_rate=basis_rate,
                basis_zscore=basis_zscore,
                cvd_delta=cvd_delta,
                open_interest_notional=oi_notional,
                depth_liquidity=context.observations.get("depth_liquidity"),
                spread_bps=context.observations.get("spread_bps"),
                slippage_bps=context.observations.get("slippage_bps"),
                price_to_mark_deviation_bps=context.observations.get("price_to_mark_deviation_bps"),
                price_to_index_deviation_bps=context.observations.get(
                    "price_to_index_deviation_bps"
                ),
                execution_readiness=execution_readiness,
                risk_pause_trading=risk_assessment.pause_trading,
                risk_reduce_size=risk_assessment.reduce_size,
                structure=structure_signal,
            )
        )
        risk_notes = self._risk_notes(
            h4=h4,
            h1=h1,
            funding_zscore=funding_zscore,
            basis_zscore=basis_zscore,
            missing_inputs=missing_inputs,
            quality=data_quality,
            risk_assessment=risk_assessment,
        )

        recommended_action = self._legacy_recommended_action(
            confidence_report.recommended_action,
            primary_regime=primary_regime,
            direction_score=direction_score,
            conflict_level=conflict_level,
            state=state,
        )
        position_multiplier = confidence_report.position_multiplier
        direction_permission = self._direction_permission(weekly, daily)
        capital = self._capital_allocation(
            recommended_action=recommended_action,
            confidence_score=confidence_report.confidence_score,
            conflict_level=conflict_level,
            state=state,
            direction_permission=direction_permission,
            execution_readiness=execution_readiness,
            risk_assessment=risk_assessment,
            weekly=weekly,
            daily=daily,
            h4=h4,
        )

        if risk_assessment.pause_trading:
            recommended_action = "risk_off"
            position_multiplier = 0.0
            capital = self._zero_capital_plan(
                "当前风控 veto 生效，现货、合约和试探仓都建议暂不参与。"
            )

        futures_decision = decide_chip_structure_action(
            direction_score=confidence_report.direction_score,
            confidence_score=confidence_report.confidence_score,
            execution_score=confidence_report.execution_score,
            risk_score=confidence_report.risk_score,
            risk_label=confidence_report.risk_label,
            primary_state=primary_regime,
            secondary_scenario=secondary_regime,
            recommended_action=recommended_action,
            execution_readiness=execution_readiness,
            higher_timeframe_conflict=(direction_permission == "mixed" or conflict_level >= 2),
            data_state="available" if state == "ready" else state,
            evidence_quality=context.evidence_quality,
        )
        capital = suppress_futures_allocation(capital, futures_decision)
        if (
            not futures_decision.allow_futures_long
            and capital["total_max_pct"] <= 10
            and recommended_action in {"normal_trade", "add_on_confirmation", "probe"}
        ):
            recommended_action = "wait_confirmation" if state == "ready" else "observe_only"

        confirmation = self._confirmation_requirements(primary_regime)
        invalidation = self._invalidation_conditions(primary_regime)
        evidence = self._build_evidence(
            weekly=weekly,
            daily=daily,
            h4=h4,
            h1=h1,
            funding_rate=funding_rate,
            funding_zscore=funding_zscore,
            basis_rate=basis_rate,
            basis_zscore=basis_zscore,
            direction_score=direction_score,
            confidence_score=confidence_report.confidence_score,
        )

        return {
            "instrument_id": instrument_id,
            "timeframe": context.timeframe,
            "state": state,
            "state_label": state_label,
            "state_reason": state_reason,
            "primary_regime": primary_regime,
            "secondary_regime": secondary_regime,
            "evidence_quality": context.evidence_quality,
            "weekly_context": weekly.summary,
            "daily_bias": daily.summary,
            "h4_structure": h4.summary,
            "h1_confirmation": h1.summary,
            "direction_score": confidence_report.direction_score,
            "direction_label": confidence_report.direction_label,
            "confidence_score": confidence_report.confidence_score,
            "confidence_label": confidence_report.confidence_label,
            "execution_score": confidence_report.execution_score,
            "execution_label": confidence_report.execution_label,
            "state_confidence_label": futures_decision.state_confidence_label,
            "execution_quality_label": futures_decision.execution_quality_label,
            "entry_trigger_label": futures_decision.entry_trigger_label,
            "risk_score": confidence_report.risk_score,
            "risk_label": confidence_report.risk_label,
            "confidence_cap": confidence_report.confidence_cap,
            "conflict_level": confidence_report.conflict_level,
            "position_multiplier": round(position_multiplier, 2),
            "capital_allocation_pct_min": capital["total_min_pct"],
            "capital_allocation_pct_max": capital["total_max_pct"],
            "capital_allocation_label": capital["total_label"],
            "position_sizing_reason": capital["reason"],
            "spot_allocation_pct_min": capital["spot_min_pct"],
            "spot_allocation_pct_max": capital["spot_max_pct"],
            "futures_allocation_pct_min": capital["futures_min_pct"],
            "futures_allocation_pct_max": capital["futures_max_pct"],
            "probe_position_pct_max": capital["probe_max_pct"],
            "spot_allocation_label": capital["spot_label"],
            "futures_allocation_label": capital["futures_label"],
            "probe_position_label": capital["probe_label"],
            "allocation_reason": capital["allocation_reason"],
            "direction_permission": direction_permission,
            "capital_ceiling_pct": capital["ceiling_pct"],
            "execution_readiness": execution_readiness,
            "recommended_action": recommended_action,
            "recommended_action_v2": confidence_report.recommended_action,
            "entry_confirmation_required": confirmation,
            "invalidation_conditions": invalidation,
            "risk_notes": list(dict.fromkeys(risk_notes)),
            "data_quality": data_quality,
            "missing_inputs": list(dict.fromkeys(missing_inputs)),
            "evidence": evidence,
            "risk_gates": confidence_report.risk_gates,
            **futures_decision.payload(),
            "components": confidence_report.component_payload(),
            "explain": confidence_report.explain,
            "timeframes": [self._timeframe_payload(item) for item in (weekly, daily, h4, h1)],
            "generated_at": datetime.now(UTC),
        }

    async def _build_context(self, instrument_id: str, timeframe: str) -> ChipStructureContext:
        normalized_timeframe = self._normalize_timeframe(timeframe)
        snapshots = {
            current_tf: await self._build_timeframe_snapshot(instrument_id, current_tf)
            for current_tf in PRIMARY_TIMEFRAMES
        }
        observations = await self._latest_observations(
            instrument_id,
            (
                "funding_rate",
                "funding_rate_zscore",
                "basis_rate",
                "basis_rate_zscore",
                *MICROSTRUCTURE_KEYS,
                "spread_bps",
                "price_to_mark_deviation_bps",
                "price_to_index_deviation_bps",
            ),
        )
        missing_inputs = self._dynamic_missing_inputs(observations)
        if observations.get("funding_rate") is None:
            missing_inputs.append("Funding Rate 尚未同步")
        if observations.get("funding_rate_zscore") is None:
            missing_inputs.append("Funding Rate Z-Score 尚未同步")
        if observations.get("basis_rate") is None:
            missing_inputs.append("Basis Rate 尚未同步")
        if observations.get("basis_rate_zscore") is None:
            missing_inputs.append("Basis Rate Z-Score 尚未同步")
        return ChipStructureContext(
            instrument_id=instrument_id,
            timeframe=normalized_timeframe,
            snapshots=snapshots,
            observations=observations,
            missing_inputs=missing_inputs,
            evidence_quality=self._evidence_quality(observations),
        )

    async def _build_timeframe_snapshot(
        self, instrument_id: str, timeframe: str
    ) -> TimeframeSnapshot:
        market_bundle = await self.market_data.get_bundle(
            instrument_id=instrument_id,
            timeframe=timeframe,
            limit=220,
            allow_stale=True,
            refresh=False,
        )
        candles = [
            CandleRead.model_validate(item)
            for item in market_bundle.get("candles", [])
        ]
        matrix: dict[str, Any] = {}
        if candles:
            try:
                matrix = await self.indicator_matrix.get_matrix(
                    instrument_id=instrument_id,
                    timeframe=timeframe,
                    limit=220,
                )
            except Exception:
                matrix = {}
        series = matrix.get("series", {}) if isinstance(matrix, dict) else {}
        quality = self.quality_monitor.assess_candles(
            candles,
            expected_min_points=80 if timeframe in {"4h", "1h"} else 40,
            stale_after_seconds=int(self._timeframe_hours(timeframe) * 60 * 60 * 4),
        )
        if not candles:
            return TimeframeSnapshot(
                timeframe=timeframe,
                label=TIMEFRAME_LABELS[timeframe],
                candles=[],
                quality=quality,
                close=0.0,
                profile=build_profile([], timeframe=timeframe),
                ema20=0.0,
                ema50=0.0,
                ema200=0.0,
                adx=0.0,
                bb_width=0.0,
                bb_percent_b=0.0,
                obv_slope=0.0,
                range_position="missing",
                bias="neutral",
                summary=f"{TIMEFRAME_LABELS[timeframe]} 暂无可用 K 线样本。",
                evidence=["当前周期缺少足够 K 线，无法确认筹码区间。"],
            )

        closes = [Decimal(str(candle.close)) for candle in candles]
        highs = [Decimal(str(candle.high)) for candle in candles]
        lows = [Decimal(str(candle.low)) for candle in candles]
        volumes = [Decimal(str(candle.volume)) for candle in candles]

        profile = build_profile(candles, timeframe=timeframe)
        ema20 = self._series_latest(series.get("ema_20"), ema_series(closes, 20).value)
        ema50 = self._series_latest(series.get("ema_50"), ema_series(closes, 50).value)
        ema200 = self._series_latest(series.get("ema_200"), ema_series(closes, 200).value)
        adx = self._series_latest(
            series.get("adx_14"),
            adx_wilder_series(highs, lows, closes, 14)["adx"].value,
        )
        bb = bbands_series(closes, 20, Decimal("2"))

        latest_close = float(closes[-1]) if closes else 0.0
        vah = float(profile.get("vah") or 0.0)
        val = float(profile.get("val") or 0.0)
        poc = float(profile.get("poc") or 0.0)
        range_position = self._range_position(latest_close, vah, val, poc)

        breakout_up = latest_close > vah and len(closes) >= 2 and float(closes[-2]) <= vah
        breakout_down = latest_close < val and len(closes) >= 2 and float(closes[-2]) >= val
        recent_closes = [float(item) for item in closes[-6:]]
        prior_closes = recent_closes[:-1]
        false_breakout = (
            len(recent_closes) >= 3
            and any(close > vah for close in prior_closes)
            and latest_close < vah
        )
        false_breakdown = (
            len(recent_closes) >= 3
            and any(close < val for close in prior_closes)
            and latest_close > val
        )

        directional = float(profile.get("direction_score") or 0.0)
        ema_bias = 1.0 if latest_close >= ema50 else -1.0
        bias_score = directional + (0.18 * ema_bias)
        if ema20 >= ema50 >= ema200:
            bias_score += 0.12
        elif ema20 <= ema50 <= ema200:
            bias_score -= 0.12
        if breakout_up:
            bias_score += 0.18
        if breakout_down:
            bias_score -= 0.18
        if false_breakout:
            bias_score -= 0.14
        if false_breakdown:
            bias_score += 0.14

        if bias_score >= 0.22:
            bias = "bullish"
        elif bias_score <= -0.22:
            bias = "bearish"
        else:
            bias = "neutral"

        bb_width = self._series_latest(series.get("bbands_width"), bb.bandwidth.value)
        bb_percent_b = self._series_latest(series.get("percent_b"), bb.percent_b.value)
        obv_slope = self._series_slope(
            series.get("obv"),
            fallback=obv_series(closes, volumes).series,
        )

        summary = self._timeframe_summary(
            label=TIMEFRAME_LABELS[timeframe],
            bias=bias,
            range_position=range_position,
            breakout_up=breakout_up,
            breakout_down=breakout_down,
            false_breakout=false_breakout,
            false_breakdown=false_breakdown,
        )

        balance_score = self._fmt(profile.get("balance_score") or 0.0, 2)
        bb_percent_text = self._fmt(bb_percent_b, 2)
        evidence = [
            f"POC {self._fmt(poc)}，VAH {self._fmt(vah)}，VAL {self._fmt(val)}。",
            f"价格位于{self._range_position_label(range_position)}，平衡得分 {balance_score}。",
            f"EMA20/50/200 = {self._fmt(ema20)} / {self._fmt(ema50)} / {self._fmt(ema200)}。",
            f"ADX {self._fmt(adx, 1)}，BB 宽度 {self._fmt(bb_width, 3)}，%B {bb_percent_text}。",
        ]

        return TimeframeSnapshot(
            timeframe=timeframe,
            label=TIMEFRAME_LABELS[timeframe],
            candles=candles,
            quality=quality,
            close=latest_close,
            profile=profile,
            ema20=ema20,
            ema50=ema50,
            ema200=ema200,
            adx=adx,
            bb_width=bb_width,
            bb_percent_b=bb_percent_b,
            obv_slope=obv_slope,
            range_position=range_position,
            bias=bias,
            summary=summary,
            evidence=evidence,
            breakout_up=breakout_up,
            breakout_down=breakout_down,
            false_breakout=false_breakout,
            false_breakdown=false_breakdown,
        )

    @staticmethod
    def _series_latest(series: Any, fallback: Any) -> float:
        if isinstance(series, list):
            for value in reversed(series):
                if value is not None:
                    try:
                        return float(value)
                    except (TypeError, ValueError):
                        continue
        try:
            return float(fallback)
        except (TypeError, ValueError):
            return 0.0

    @staticmethod
    def _series_slope(series: Any, fallback: Any) -> float:
        values = series if isinstance(series, list) else fallback
        recent = []
        for item in list(values or [])[-5:]:
            if item is None:
                continue
            try:
                recent.append(float(item))
            except (TypeError, ValueError):
                continue
        if len(recent) < 2:
            return 0.0
        return (recent[-1] - recent[0]) / max(abs(recent[0]), 1.0)

    async def _latest_observations(
        self, instrument_id: str, indicator_keys: tuple[str, ...]
    ) -> dict[str, float | None]:
        observations = await self.repository.list_indicator_observations(
            instrument_id=instrument_id,
            category="technical",
            limit=64,
        )
        latest_map: dict[str, Any] = {}
        for item in observations:
            key = getattr(item, "indicator_key", None)
            if key not in indicator_keys:
                continue
            previous = latest_map.get(key)
            if previous is None or item.observation_ts > previous.observation_ts:
                latest_map[key] = item
        return {
            key: float(latest_map[key].value_num)
            if key in latest_map and latest_map[key].value_num is not None
            else None
            for key in indicator_keys
        }

    async def _latest_structure_signal(
        self, instrument_id: str, timeframe: str
    ) -> StructureConfidenceInput:
        if not hasattr(self.repository, "get_latest_structure_snapshot"):
            return StructureConfidenceInput()
        snapshot = await self.repository.get_latest_structure_snapshot(instrument_id, timeframe)
        if snapshot is None:
            return StructureConfidenceInput()
        if not hasattr(self.repository, "list_structure_system_judgements"):
            diagnostics = getattr(snapshot, "diagnostics_json", {}) or {}
            return StructureConfidenceInput(
                available=True,
                overall_score=float(snapshot.overall_score or 0.0),
                overall_confidence=float(snapshot.overall_confidence or 0.0),
                overall_bias=str(snapshot.overall_bias or "neutral"),
                conflict_state=bool(snapshot.conflict_state),
                evidence_density=min(
                    len(getattr(snapshot, "top_reasons_json", []) or []) / 6.0,
                    1.0,
                ),
                direction_agreement=1.0 if not bool(snapshot.conflict_state) else 0.5,
                suggested_action=diagnostics.get("suggested_action"),
                top_reasons=list(getattr(snapshot, "top_reasons_json", []) or []),
            )
        diagnostics = getattr(snapshot, "diagnostics_json", {}) or {}
        judgements = await self.repository.list_structure_system_judgements(
            instrument_id,
            timeframe,
            snapshot.snapshot_version,
        )
        aligned = 0
        evidence_points = 0
        for item in judgements:
            if item.bias == snapshot.overall_bias and item.bias not in {"neutral", "uncertain"}:
                aligned += 1
            evidence_points += len(getattr(item, "drivers_json", []) or [])
            evidence_points += len(getattr(item, "active_structures_json", []) or [])
        direction_agreement = aligned / max(len(judgements), 1)
        evidence_density = min(
            (evidence_points + len(getattr(snapshot, "top_reasons_json", []) or [])) / 12.0,
            1.0,
        )
        return StructureConfidenceInput(
            available=True,
            overall_score=float(snapshot.overall_score or 0.0),
            overall_confidence=float(snapshot.overall_confidence or 0.0),
            overall_bias=str(snapshot.overall_bias or "neutral"),
            conflict_state=bool(snapshot.conflict_state),
            evidence_density=evidence_density,
            direction_agreement=direction_agreement,
            suggested_action=diagnostics.get("suggested_action"),
            top_reasons=list(getattr(snapshot, "top_reasons_json", []) or []),
        )

    def _select_regimes(
        self,
        *,
        weekly: TimeframeSnapshot,
        daily: TimeframeSnapshot,
        h4: TimeframeSnapshot,
        h1: TimeframeSnapshot,
        funding_rate: float | None,
        funding_zscore: float | None,
        basis_rate: float | None,
        basis_zscore: float | None,
        cvd_delta: float | None,
        oi_notional: float | None,
        evidence_quality: str,
    ) -> tuple[str, str]:
        if any(item.false_breakout for item in (h4, h1)):
            return "false_breakout", "balanced_auction"
        if any(item.false_breakdown for item in (h4, h1)):
            return "false_breakdown", "balanced_auction"
        if h4.bb_width < 0.045 and daily.bb_width < 0.055 and abs(funding_zscore or 0.0) >= 1.2:
            return "leverage_compression", "balanced_auction"
        if (
            h4.quality.status in {"missing", "bad"}
            or sum("volume_sparse" in item.quality.issues for item in (daily, h4, h1)) >= 2
        ):
            return "liquidity_drought", "balanced_auction"
        if (
            daily.range_position in {"lower_half", "near_val"}
            and h4.bias == "bullish"
            and weekly.bias != "bearish"
        ):
            if (
                evidence_quality == "confirmed"
                and (cvd_delta or 0.0) > 0
                and (oi_notional or 0.0) > 0
            ):
                return "accumulation_confirmed", "balanced_auction"
            return "accumulation_proxy", "balanced_auction"
        if (
            daily.range_position in {"upper_half", "near_vah"}
            and h4.bias == "bearish"
            and weekly.bias != "bullish"
        ):
            if (
                evidence_quality == "confirmed"
                and (cvd_delta or 0.0) < 0
                and (oi_notional or 0.0) > 0
            ):
                return "distribution_confirmed", "balanced_auction"
            return "distribution_proxy", "balanced_auction"
        if weekly.bias == daily.bias == h4.bias == "bullish" and h1.bias != "bearish":
            return "bullish_continuation_range", "balanced_auction"
        if weekly.bias == daily.bias == h4.bias == "bearish" and h1.bias != "bullish":
            return "bearish_continuation_range", "balanced_auction"
        if daily.range_position == "balanced" and h4.range_position == "balanced":
            return (
                "balanced_auction",
                "liquidity_drought" if h1.bb_width < 0.035 else "accumulation_candidate",
            )
        if (funding_rate or 0.0) > 0 and (basis_rate or 0.0) > 0 and daily.bias == "bearish":
            return "distribution_candidate", "leverage_compression"
        return "balanced_auction", "liquidity_drought"

    def _direction_score(
        self,
        weekly: TimeframeSnapshot,
        daily: TimeframeSnapshot,
        h4: TimeframeSnapshot,
        h1: TimeframeSnapshot,
        funding_rate: float | None,
        basis_rate: float | None,
        cvd_delta: float | None = None,
        oi_notional: float | None = None,
    ) -> float:
        directional = (
            self._bias_value(weekly.bias) * 26
            + self._bias_value(daily.bias) * 30
            + self._bias_value(h4.bias) * 28
            + self._bias_value(h1.bias) * 16
        )
        flow_adjust = 0.0
        if cvd_delta is not None:
            flow_adjust += max(min(cvd_delta / 1000.0, 12), -12)
        if oi_notional is not None and oi_notional > 0 and h4.bias == h1.bias != "neutral":
            flow_adjust += 4
        breakout_adjust = 0.0
        if any(item.breakout_up for item in (h4, h1)):
            breakout_adjust += 8
        if any(item.breakout_down for item in (h4, h1)):
            breakout_adjust -= 8
        if any(item.false_breakout for item in (h4, h1)):
            breakout_adjust -= 10
        if any(item.false_breakdown for item in (h4, h1)):
            breakout_adjust += 10
        crowding_adjust = 0.0
        if funding_rate is not None:
            crowding_adjust -= max(min(funding_rate * 160, 10), -10)
        if basis_rate is not None:
            crowding_adjust -= max(min(basis_rate * 120, 8), -8)
        score = directional + flow_adjust + breakout_adjust + crowding_adjust
        return max(min(score, 100.0), -100.0)

    def _confidence_score(
        self, snapshots: dict[str, TimeframeSnapshot], missing_inputs: list[str]
    ) -> float:
        quality_score = sum(item.quality.data_quality_score for item in snapshots.values()) / max(
            len(snapshots), 1
        )
        alignment = sum(
            1
            for item in snapshots.values()
            if item.bias == snapshots["4h"].bias and item.bias != "neutral"
        )
        confidence = quality_score * 0.52 + alignment * 10 + snapshots["4h"].adx * 0.35
        confidence -= min(len(set(missing_inputs)) * 2.8, 18)
        return max(min(confidence, 100.0), 8.0)

    def _conflict_level(
        self,
        weekly: TimeframeSnapshot,
        daily: TimeframeSnapshot,
        h4: TimeframeSnapshot,
        h1: TimeframeSnapshot,
        funding_zscore: float | None,
        basis_zscore: float | None,
    ) -> int:
        level = 0
        if weekly.bias != "neutral" and daily.bias != "neutral" and weekly.bias != daily.bias:
            level += 1
        if daily.bias != "neutral" and h4.bias != "neutral" and daily.bias != h4.bias:
            level += 1
        if h4.bias != "neutral" and h1.bias != "neutral" and h4.bias != h1.bias:
            level += 1
        if abs(funding_zscore or 0.0) >= 1.6 or abs(basis_zscore or 0.0) >= 1.6:
            level += 1
        return min(level, 3)

    def _aggregate_quality(
        self, snapshots: dict[str, TimeframeSnapshot], missing_inputs: list[str]
    ) -> dict[str, Any]:
        assessments = [item.quality for item in snapshots.values()]
        score = round(
            sum(item.data_quality_score for item in assessments) / max(len(assessments), 1), 2
        )
        issues = list(dict.fromkeys(issue for item in assessments for issue in item.issues))
        if all(item.status == "missing" for item in assessments):
            status = "missing"
        elif any(item.status in {"bad", "missing"} for item in assessments) or missing_inputs:
            status = "degraded"
        elif any(item.status == "fair" for item in assessments):
            status = "fair"
        else:
            status = "good"
        return {
            "status": status,
            "score": score,
            "issues": issues + [f"missing:{item}" for item in missing_inputs[:5]],
            "can_analyze": all(item.can_analyze for item in assessments),
            "can_alert": all(item.can_alert for item in assessments) and not missing_inputs,
        }

    def _state(self, quality: dict[str, Any], missing_inputs: list[str], risk_assessment) -> str:
        if quality["status"] == "missing":
            return "missing"
        if (
            risk_assessment.pause_trading
            or risk_assessment.reduce_size
            or missing_inputs
            or quality["status"] in {"degraded", "bad", "fair"}
        ):
            return "degraded"
        return "ready"

    def _state_label(
        self, quality: dict[str, Any], missing_inputs: list[str], risk_assessment
    ) -> str:
        if quality["status"] == "missing":
            return "无法判断"
        if self._has_liquidity_restriction(risk_assessment):
            return "流动性不足"
        if risk_assessment.pause_trading or risk_assessment.reduce_size:
            return "风险受限"
        if self._has_missing_micro_inputs(missing_inputs):
            return "信息缺失"
        if quality["status"] in {"degraded", "bad", "fair"}:
            return "数据不完整"
        return "可用"

    def _state_reason(
        self, quality: dict[str, Any], missing_inputs: list[str], risk_assessment
    ) -> str:
        if quality["status"] == "missing":
            return "当前关键周期 K 线不足，无法形成有效的筹码结构判断。"
        if self._has_liquidity_restriction(risk_assessment):
            return "盘口深度或可执行流动性不足，即使方向存在，也不适合正常规模参与。"
        if risk_assessment.pause_trading:
            return "当前风控条件不满足，建议先暂停参与，等待风险约束解除。"
        if risk_assessment.reduce_size:
            return "当前存在风控或波动率约束，仍可分析，但参与规模需要明显受限。"
        if self._has_missing_micro_inputs(missing_inputs):
            return "当前结果主要基于 K 线、近似 profile 与衍生品基础指标，缺少部分微观结构输入。"
        if quality["status"] in {"degraded", "bad", "fair"}:
            return "当前数据完整度一般，结论可参考，但不宜作为高置信度执行依据。"
        return "当前多周期结构与数据质量可用于正常观察和执行规划。"

    def _risk_notes(
        self,
        *,
        h4: TimeframeSnapshot,
        h1: TimeframeSnapshot,
        funding_zscore: float | None,
        basis_zscore: float | None,
        missing_inputs: list[str],
        quality: dict[str, Any],
        risk_assessment,
    ) -> list[str]:
        notes: list[str] = []
        if h4.false_breakout or h1.false_breakout:
            notes.append("近期存在上破后回落，需要警惕假突破。")
        if h4.false_breakdown or h1.false_breakdown:
            notes.append("近期存在下破后收回，需要警惕假跌破。")
        if abs(funding_zscore or 0.0) >= 1.6:
            notes.append("Funding 偏离明显，杠杆情绪可能放大反向波动。")
        if abs(basis_zscore or 0.0) >= 1.6:
            notes.append("Basis 偏离明显，期限结构可能扭曲当前方向判断。")
        if h4.bb_width < 0.04 and h1.bb_width < 0.035:
            notes.append("波动处于压缩阶段，等待突破确认比提前押注更稳妥。")
        if quality["status"] in {"degraded", "bad", "fair"}:
            notes.append("当前数据完整度一般，应以保守仓位参与。")
        if missing_inputs:
            notes.append("缺失部分微观结构输入，建议降低对单一结论的依赖。")
        notes.extend(risk_assessment.reasons or [])
        return list(dict.fromkeys(notes)) or ["当前未发现额外高等级风险。"]

    def _recommended_action(
        self, primary_regime: str, direction_score: float, conflict_level: int, state: str
    ) -> str:
        if state == "missing":
            return "risk_off"
        if state == "degraded" and conflict_level >= 2:
            return "observe_only"
        if primary_regime == "false_breakout":
            return "breakdown_watch"
        if primary_regime == "false_breakdown":
            return "breakout_watch"
        if primary_regime == "leverage_compression":
            return "wait_confirmation"
        if primary_regime == "liquidity_drought":
            return "observe_only"
        if primary_regime in {
            "accumulation_candidate",
            "accumulation_proxy",
            "accumulation_confirmed",
        }:
            return "range_long_bias"
        if primary_regime in {
            "distribution_candidate",
            "distribution_proxy",
            "distribution_confirmed",
        }:
            return "range_short_bias"
        if primary_regime == "bullish_continuation_range":
            return "breakout_watch" if direction_score >= 45 else "wait_confirmation"
        if primary_regime == "bearish_continuation_range":
            return "breakdown_watch" if direction_score <= -45 else "wait_confirmation"
        return "wait_confirmation"

    def _legacy_recommended_action(
        self,
        action_v2: str,
        *,
        primary_regime: str,
        direction_score: float,
        conflict_level: int,
        state: str,
    ) -> str:
        fallback = self._recommended_action(primary_regime, direction_score, conflict_level, state)
        mapped = {
            "no_trade": "risk_off" if state == "missing" else fallback,
            "observe": "observe_only",
            "wait_for_confirmation": "wait_confirmation",
            "probe": "wait_confirmation",
            "normal_trade": fallback,
            "add_on_confirmation": fallback,
            "reduce_or_exit": "observe_only",
        }
        return mapped.get(action_v2, fallback)

    def _position_multiplier(
        self, confidence_score: float, conflict_level: int, state: str
    ) -> float:
        if state == "missing":
            return 0.0
        base = 0.35 + max(min((confidence_score - 40) / 100, 0.55), 0.0)
        if state == "degraded":
            base *= 0.72
        base -= conflict_level * 0.12
        return max(min(base, 1.0), 0.0)

    def _direction_permission(self, weekly: TimeframeSnapshot, daily: TimeframeSnapshot) -> str:
        if weekly.bias == daily.bias == "bullish":
            return "long_preferred"
        if weekly.bias == daily.bias == "bearish":
            return "short_preferred"
        if weekly.bias == "neutral" and daily.bias == "neutral":
            return "range_only"
        return "mixed"

    def _execution_readiness(
        self,
        h4: TimeframeSnapshot,
        h1: TimeframeSnapshot,
        conflict_level: int,
        state: str,
        risk_assessment,
    ) -> str:
        if state == "missing" or risk_assessment.pause_trading:
            return "blocked"
        if conflict_level >= 2 or h1.bias == "neutral":
            return "waiting_confirmation"
        if h4.bias == h1.bias and h4.bias != "neutral":
            return "confirmed"
        return "early"

    def _capital_allocation(
        self,
        *,
        recommended_action: str,
        confidence_score: float,
        conflict_level: int,
        state: str,
        direction_permission: str,
        execution_readiness: str,
        risk_assessment,
        weekly: TimeframeSnapshot,
        daily: TimeframeSnapshot,
        h4: TimeframeSnapshot,
    ) -> dict[str, Any]:
        base_ranges = {
            "risk_off": (0, 0),
            "observe_only": (0, 5),
            "wait_confirmation": (0, 10),
            "range_long_bias": (10, 20),
            "range_short_bias": (10, 20),
            "breakout_watch": (5, 15),
            "breakdown_watch": (5, 15),
            "reduce_size": (5, 10),
        }
        minimum, maximum = base_ranges.get(recommended_action, (0, 10))

        if recommended_action == "risk_off":
            return self._zero_capital_plan(
                "当前优先级为风险规避，现货、合约和试探仓都建议暂不参与。"
            )
        if recommended_action in {"observe_only", "wait_confirmation"}:
            maximum = min(maximum, 5 if recommended_action == "observe_only" else 10)
            total_label = f"0% - {maximum}%" if maximum else "0%"
            reason = (
                "当前建议仅观察，合约仓位保持 0，等待结构与微观数据补齐。"
                if recommended_action == "observe_only"
                else "当前仍需确认，合约仓位保持 0，只允许很小规模现货或试探观察。"
            )
            return {
                "total_min_pct": 0.0,
                "total_max_pct": float(maximum),
                "total_label": total_label,
                "reason": reason,
                "spot_min_pct": 0.0,
                "spot_max_pct": float(maximum),
                "futures_min_pct": 0.0,
                "futures_max_pct": 0.0,
                "probe_max_pct": float(min(3, maximum)),
                "spot_label": self._pct_range_label(0.0, float(maximum)),
                "futures_label": "0%",
                "probe_label": f"{min(3, maximum):.0f}%",
                "allocation_reason": reason,
                "ceiling_pct": float(maximum),
            }

        if (
            confidence_score >= 72
            and conflict_level == 0
            and weekly.bias == daily.bias == h4.bias != "neutral"
        ):
            maximum = max(maximum, 35)
            minimum = max(minimum, 20)
        if conflict_level >= 2:
            maximum = min(maximum, 5)
            minimum = 0
        if direction_permission == "mixed":
            maximum = min(maximum, 10)
            minimum = 0
        if execution_readiness == "waiting_confirmation":
            maximum = min(maximum, 10)
            minimum = 0
        if state == "degraded":
            maximum = min(maximum, 15)
        if risk_assessment.reduce_size:
            maximum = min(maximum, 10)
        if risk_assessment.pause_trading or state == "missing":
            return self._zero_capital_plan(
                "当前风险或数据条件不满足，现货、合约和试探仓都建议暂不参与。"
            )

        total_label = f"{minimum}% - {maximum}%" if minimum != maximum else f"{maximum}%"
        ceiling_pct = float(maximum)

        if maximum == 0:
            allocation_reason = "当前以风险控制为先，总资本建议暂不参与。"
        elif maximum <= 5:
            allocation_reason = "当前更适合轻仓观察，等待 1H 与 4H 再次共振后再考虑放大仓位。"
        elif maximum <= 10:
            allocation_reason = "当前仍需确认，建议只用小额试探仓验证结构是否延续。"
        elif maximum <= 20:
            allocation_reason = "当前可按偏向参与，但仍应保留明显缓冲，不宜一次性加满。"
        else:
            allocation_reason = "当前多周期共振较强，可提升参与比例，但仍需按失效条件执行风控。"

        if (
            recommended_action in {"range_short_bias", "breakdown_watch"}
            or direction_permission == "short_preferred"
        ):
            spot_min = 0.0
            spot_max = float(min(maximum, 5))
            futures_min = float(max(minimum, 5))
            futures_max = float(maximum)
        elif direction_permission == "range_only":
            spot_min = 0.0
            spot_max = float(min(maximum, 10))
            futures_min = 0.0
            futures_max = float(min(maximum, 8))
        else:
            spot_min = float(minimum)
            spot_max = float(round(maximum * 0.7, 1))
            futures_min = (
                0.0 if execution_readiness != "confirmed" else float(round(minimum * 0.25, 1))
            )
            futures_max = float(
                round(maximum * (0.5 if execution_readiness == "confirmed" else 0.35), 1)
            )

        if state == "degraded" or conflict_level >= 2:
            futures_max = float(min(futures_max, 8))
            spot_max = float(min(spot_max, 12))

        probe_max = (
            0.0
            if maximum == 0
            else float(min(5 if execution_readiness != "confirmed" else 8, maximum))
        )

        spot_label = self._pct_range_label(spot_min, spot_max)
        futures_label = self._pct_range_label(futures_min, futures_max)
        probe_label = f"{probe_max:.0f}%"

        return {
            "total_min_pct": float(minimum),
            "total_max_pct": float(maximum),
            "total_label": total_label,
            "reason": allocation_reason,
            "spot_min_pct": spot_min,
            "spot_max_pct": spot_max,
            "futures_min_pct": futures_min,
            "futures_max_pct": futures_max,
            "probe_max_pct": probe_max,
            "spot_label": spot_label,
            "futures_label": futures_label,
            "probe_label": probe_label,
            "allocation_reason": allocation_reason,
            "ceiling_pct": ceiling_pct,
        }

    def _confirmation_requirements(self, primary_regime: str) -> list[str]:
        if primary_regime in {
            "accumulation_candidate",
            "bullish_continuation_range",
            "false_breakdown",
        }:
            return [
                "1H 收盘重新站稳 POC 或 VAH 上方。",
                "4H 不再回到 value area 下半区。",
            ]
        if primary_regime in {
            "distribution_candidate",
            "bearish_continuation_range",
            "false_breakout",
        }:
            return [
                "1H 收盘跌回 POC 或 VAL 下方。",
                "4H 持续停留在 value area 下半区。",
            ]
        if primary_regime == "leverage_compression":
            return ["等待 1H 波动放大并出现方向性收盘确认。"]
        return ["等待 1H 与 4H 方向重新共振。"]

    def _invalidation_conditions(self, primary_regime: str) -> list[str]:
        if primary_regime in {
            "accumulation_candidate",
            "bullish_continuation_range",
            "false_breakdown",
        }:
            return [
                "1H 再次有效跌破 VAL。",
                "4H POC 明显下移且 ADX 失速。",
            ]
        if primary_regime in {
            "distribution_candidate",
            "bearish_continuation_range",
            "false_breakout",
        }:
            return [
                "1H 再次有效站回 VAH。",
                "4H POC 明显上移且空头压制消失。",
            ]
        return ["价格重新回到平衡区中央，且 1H / 4H 不再给出方向确认。"]

    def _build_evidence(
        self,
        *,
        weekly: TimeframeSnapshot,
        daily: TimeframeSnapshot,
        h4: TimeframeSnapshot,
        h1: TimeframeSnapshot,
        funding_rate: float | None,
        funding_zscore: float | None,
        basis_rate: float | None,
        basis_zscore: float | None,
        direction_score: float,
        confidence_score: float,
    ) -> list[dict[str, str]]:
        daily_range_label = self._range_position_label(daily.range_position)
        h4_range_label = self._range_position_label(h4.range_position)
        daily_direction_score = self._fmt(daily.profile.get("direction_score") or 0.0, 2)
        h4_direction_score = self._fmt(h4.profile.get("direction_score") or 0.0, 2)
        weekly_quality_score = self._fmt(weekly.quality.data_quality_score, 0)
        h1_quality_score = self._fmt(h1.quality.data_quality_score, 0)
        return [
            {
                "key": "value_area",
                "label": "区间位置",
                "value": f"1D {daily_range_label} / 4H {h4_range_label}",
                "impact": self._direction_impact(direction_score),
                "summary": "日线与 4H 所处的 value area 位置决定当前更偏承接还是派发。",
            },
            {
                "key": "poc_shift",
                "label": "POC 漂移",
                "value": f"1D {daily_direction_score} / 4H {h4_direction_score}",
                "impact": "bullish"
                if daily.bias == "bullish" and h4.bias == "bullish"
                else "bearish"
                if daily.bias == "bearish" and h4.bias == "bearish"
                else "neutral",
                "summary": "POC 与平衡区重心变化用于识别区间承接、派发与轮动方向。",
            },
            {
                "key": "derivatives",
                "label": "衍生品拥挤度",
                "value": f"Funding {self._fmt(funding_rate, 4)} / Basis {self._fmt(basis_rate, 4)}",
                "impact": "risk"
                if abs(funding_zscore or 0.0) >= 1.5 or abs(basis_zscore or 0.0) >= 1.5
                else "neutral",
                "summary": "Funding 与 Basis 用于识别 crowding 是否正在扭曲当前结构。",
            },
            {
                "key": "volatility",
                "label": "波动与挤压",
                "value": (
                    f"4H BB宽度 {self._fmt(h4.bb_width, 3)} / "
                    f"1H BB宽度 {self._fmt(h1.bb_width, 3)}"
                ),
                "impact": "filter" if h4.bb_width < 0.04 and h1.bb_width < 0.035 else "neutral",
                "summary": "波动压缩有利于等待突破确认，但也会提高假突破风险。",
            },
            {
                "key": "quality",
                "label": "数据质量",
                "value": (
                    f"置信度 {self._fmt(confidence_score, 0)} / "
                    f"数据质量 {weekly_quality_score}~{h1_quality_score}"
                ),
                "impact": "risk"
                if min(weekly.quality.data_quality_score, h1.quality.data_quality_score) < 60
                else "neutral",
                "summary": "当前结论受多周期数据完整度与缺失输入数量影响。",
            },
        ]

    def _timeframe_payload(self, snapshot: TimeframeSnapshot) -> dict[str, Any]:
        return {
            "timeframe": snapshot.label,
            "regime": snapshot.bias,
            "bias": snapshot.bias,
            "range_position": snapshot.range_position,
            "summary": snapshot.summary,
            "confidence_score": round(snapshot.quality.data_quality_score, 2),
            "status": snapshot.quality.status,
            "evidence": snapshot.evidence,
        }

    def _missing_payload(self, context: ChipStructureContext) -> dict[str, Any]:
        capital = self._zero_capital_plan("当前无法形成有效结构判断，总资本建议暂不参与。")
        return {
            "instrument_id": context.instrument_id,
            "timeframe": context.timeframe,
            "state": "missing",
            "state_label": "无法判断",
            "state_reason": "当前关键周期 K 线不足，筹码结构模块只能返回缺失状态。",
            "primary_regime": "balanced_auction",
            "secondary_regime": "liquidity_drought",
            "evidence_quality": context.evidence_quality,
            "weekly_context": "周线暂无足够 K 线样本。",
            "daily_bias": "日线暂无足够 K 线样本。",
            "h4_structure": "4H 暂无足够 K 线样本。",
            "h1_confirmation": "1H 暂无足够确认数据。",
            "direction_score": 0.0,
            "direction_label": "neutral",
            "confidence_score": 0.0,
            "confidence_label": "invalid",
            "execution_score": 0.0,
            "execution_label": "blocked",
            "state_confidence_label": "状态置信无效",
            "execution_quality_label": "盘口执行阻塞",
            "entry_trigger_label": "交易触发阻塞",
            "risk_score": 100.0,
            "risk_label": "extreme",
            "confidence_cap": 0.0,
            "conflict_level": 3,
            "position_multiplier": 0.0,
            "capital_allocation_pct_min": 0.0,
            "capital_allocation_pct_max": 0.0,
            "capital_allocation_label": "0%",
            "position_sizing_reason": capital["reason"],
            "spot_allocation_pct_min": 0.0,
            "spot_allocation_pct_max": 0.0,
            "futures_allocation_pct_min": 0.0,
            "futures_allocation_pct_max": 0.0,
            "probe_position_pct_max": 0.0,
            "spot_allocation_label": "0%",
            "futures_allocation_label": "0%",
            "probe_position_label": "0%",
            "allocation_reason": capital["allocation_reason"],
            "direction_permission": "blocked",
            "capital_ceiling_pct": 0.0,
            "execution_readiness": "blocked",
            "recommended_action": "risk_off",
            "recommended_action_v2": "no_trade",
            "entry_confirmation_required": ["先补齐关键周期 K 线与监控指标。"],
            "invalidation_conditions": ["数据补齐前不应使用该结论。"],
            "risk_notes": ["当前缺少足够数据，筹码结构模块进入只读缺失状态。"]
            + context.missing_inputs,
            "data_quality": {
                "status": "missing",
                "score": 0.0,
                "issues": ["candles_missing"],
                "can_analyze": False,
                "can_alert": False,
            },
            "missing_inputs": context.missing_inputs,
            "evidence": [],
            "risk_gates": ["NO_USABLE_CANDLES"],
            "allow_futures_long": False,
            "futures_gate_checks": [],
            "failed_gate_reasons": ["当前缺少可分析 K 线，所有合约开多门槛默认失败。"],
            "why_no_futures_long": "当前不建议开多合约，因为缺少可分析 K 线和关键输入。",
            "components": {},
            "explain": ["缺少可用 K 线，置信度被压制为 0，当前仅返回缺失状态。"],
            "timeframes": [
                self._timeframe_payload(snapshot) for snapshot in context.snapshots.values()
            ],
            "generated_at": datetime.now(UTC),
        }

    def _timeframe_summary(
        self,
        *,
        label: str,
        bias: str,
        range_position: str,
        breakout_up: bool,
        breakout_down: bool,
        false_breakout: bool,
        false_breakdown: bool,
    ) -> str:
        if false_breakout:
            return f"{label} 出现上破后重新跌回区间，偏向假突破。"
        if false_breakdown:
            return f"{label} 出现下破后重新收回区间，偏向假跌破。"
        if breakout_up:
            return f"{label} 正在尝试站上 value area 上沿。"
        if breakout_down:
            return f"{label} 正在尝试跌破 value area 下沿。"
        tone = {"bullish": "偏多", "bearish": "偏空"}.get(bias, "中性")
        return f"{label} 处于{self._range_position_label(range_position)}，当前结构{tone}。"

    def _range_position(self, close: float, vah: float, val: float, poc: float) -> str:
        midpoint = (vah + val) / 2 if vah or val else poc
        if close > vah:
            return "above_vah"
        if close < val:
            return "below_val"
        if abs(close - poc) <= max((vah - val) * 0.12, 1.0):
            return "balanced"
        if close >= midpoint:
            return "upper_half" if close < vah - max((vah - val) * 0.12, 1.0) else "near_vah"
        return "lower_half" if close > val + max((vah - val) * 0.12, 1.0) else "near_val"

    def _range_position_label(self, value: str) -> str:
        labels = {
            "above_vah": "VAH 上方",
            "below_val": "VAL 下方",
            "balanced": "POC 附近",
            "upper_half": "value area 上半区",
            "lower_half": "value area 下半区",
            "near_vah": "区间上沿附近",
            "near_val": "区间下沿附近",
            "missing": "缺失",
        }
        return labels.get(value, value)

    def _bias_value(self, value: str) -> int:
        return {"bullish": 1, "bearish": -1}.get(value, 0)

    def _range_value(self, value: str) -> int:
        mapping = {
            "above_vah": 1,
            "upper_half": 1,
            "near_vah": 1,
            "balanced": 0,
            "lower_half": -1,
            "near_val": -1,
            "below_val": -1,
        }
        return mapping.get(value, 0)

    def _dynamic_missing_inputs(self, observations: dict[str, float | None]) -> list[str]:
        labels = {
            "open_interest_notional": "OI 尚未同步",
            "cvd_delta": "CVD / Delta 尚未同步",
            "depth_liquidity": "depth 尚未同步",
            "slippage_bps": "slippage / spread 尚未同步",
        }
        return [
            label
            for key, label in labels.items()
            if observations.get(key) is None
        ]

    def _evidence_quality(self, observations: dict[str, float | None]) -> str:
        available = sum(1 for key in MICROSTRUCTURE_KEYS if observations.get(key) is not None)
        has_funding = observations.get("funding_rate") is not None
        if available == len(MICROSTRUCTURE_KEYS) and has_funding:
            return "confirmed"
        if available >= 2 or (available >= 1 and has_funding):
            return "partially_confirmed"
        return "proxy_only"

    def _normalize_timeframe(self, timeframe: str) -> str:
        return str(timeframe or "1h").lower()

    def _timeframe_hours(self, timeframe: str) -> float:
        return {"1h": 1.0, "4h": 4.0, "1d": 24.0, "1w": 168.0}.get(timeframe, 1.0)

    def _fmt(self, value: float | Decimal | None, digits: int = 2) -> str:
        if value is None:
            return "-"
        return f"{float(value):,.{digits}f}"

    def _has_missing_micro_inputs(self, missing_inputs: list[str]) -> bool:
        return any(
            any(token in item for token in ("OI", "CVD", "depth", "slippage", "spread"))
            for item in missing_inputs
        )

    def _has_liquidity_restriction(self, risk_assessment) -> bool:
        return any(
            "流动性" in reason or "可执行" in reason for reason in (risk_assessment.reasons or [])
        )

    def _direction_impact(self, direction_score: float) -> str:
        if direction_score >= 30:
            return "bullish"
        if direction_score >= 10:
            return "bullish_soft"
        if direction_score <= -30:
            return "bearish"
        if direction_score <= -10:
            return "bearish_soft"
        return "neutral"

    def _pct_range_label(self, minimum: float, maximum: float) -> str:
        if maximum <= 0:
            return "0%"
        if round(minimum, 1) == round(maximum, 1):
            return f"{maximum:.0f}%"
        return f"{minimum:.0f}% - {maximum:.0f}%"

    def _zero_capital_plan(self, reason: str) -> dict[str, Any]:
        return {
            "total_min_pct": 0.0,
            "total_max_pct": 0.0,
            "total_label": "0%",
            "reason": reason,
            "spot_min_pct": 0.0,
            "spot_max_pct": 0.0,
            "futures_min_pct": 0.0,
            "futures_max_pct": 0.0,
            "probe_max_pct": 0.0,
            "spot_label": "0%",
            "futures_label": "0%",
            "probe_label": "0%",
            "allocation_reason": reason,
            "ceiling_pct": 0.0,
        }
