from __future__ import annotations

import logging
from datetime import UTC, datetime
from decimal import Decimal
from typing import Any

from app.core.timeframes import normalize_instrument_id, normalize_timeframe_for_cache
from app.repositories.market_repository import MarketRepository
from app.services.alerts_bundle import AlertsBundleService
from app.services.analysis_bundle import AnalysisBundleService
from app.services.cache_registry import (
    CACHE_SOURCE_VERSION,
    expires_at_for_strategy,
    strategy_bundle_cache_key,
)
from app.services.market_context import MarketContextBuilder
from app.services.monitoring_dashboard import MonitoringDashboardService
from app.services.strategy_signal.config_loader import (
    detect_asset_class,
    detect_mode,
    load_strategy_signal_config,
)
from app.services.strategy_signal.risk_reward import (
    clamp,
    compute_risk_reward,
    risk_reward_score,
    round2,
)
from app.services.strategy_signal.scoring_engine import weighted_score
from app.services.strategy_signal.setup_lifecycle import normalize_direction_metrics
from app.services.technical_risk import build_divergence_risk, score_divergence_for_snapshot

logger = logging.getLogger(__name__)


def _field(item: Any, key: str, default: Any = None) -> Any:
    if item is None:
        return default
    if isinstance(item, dict):
        return item.get(key, default)
    return getattr(item, key, default)


def _decimal(value: Any) -> Decimal | None:
    if value is None or value == "":
        return None
    try:
        return Decimal(str(value))
    except Exception:
        return None


def _num(value: Any, default: float = 0.0) -> float:
    parsed = _decimal(value)
    return float(parsed) if parsed is not None else default


def _last_value(series: dict[str, Any], *keys: str) -> Any:
    for key in keys:
        values = series.get(key)
        if isinstance(values, list) and values:
            latest = values[-1]
            if isinstance(latest, dict):
                return latest.get("value", latest.get("y", latest.get("close")))
            return latest
    return None


def _previous_value(series: dict[str, Any], key: str) -> Any:
    values = series.get(key)
    if isinstance(values, list) and len(values) >= 2:
        previous = values[-2]
        if isinstance(previous, dict):
            return previous.get("value", previous.get("y", previous.get("close")))
        return previous
    return None


def _find_value(payload: Any, *keys: str) -> Any:
    wanted = {key.lower() for key in keys}
    if isinstance(payload, dict):
        for key, value in payload.items():
            if str(key).lower() in wanted:
                return value
        for value in payload.values():
            found = _find_value(value, *keys)
            if found is not None:
                return found
    elif isinstance(payload, list):
        for item in payload:
            found = _find_value(item, *keys)
            if found is not None:
                return found
    return None


def _status_score(*statuses: str | None) -> int:
    score = 100
    for status in statuses:
        if status in {"missing", "error"}:
            score -= 35
        elif status in {"degraded"}:
            score -= 25
        elif status in {"stale", "updating"}:
            score -= 15
    return max(0, min(100, score))


def _build_trend_score(indicators: dict[str, Any]) -> tuple[float, float]:
    """Compute the multi-timeframe trend component from EMA / ADX inputs.

    The audit (T04) found that the same ``direction_metrics`` value was reused
    for trend, structure and regime fields, so any change in chip direction
    was triple-counted. Trend now lives on its own: EMA20/50/200 alignment,
    EMA20 slope, and ADX strength all contribute. Returns ``(bullish, bearish)``
    scores in 0..100.
    """

    ema20 = _num(indicators.get("ema_20"))
    ema50 = _num(indicators.get("ema_50"))
    ema200 = _num(indicators.get("ema_200"))
    ema20_prev = _num(indicators.get("ema_20_prev"), ema20)
    ema20_slope = ema20 - ema20_prev
    adx = _num(indicators.get("adx_14"), 20)

    bullish = 50.0
    bearish = 50.0
    if ema20 and ema50:
        if ema20 > ema50:
            bullish += 15.0
            bearish -= 10.0
        elif ema20 < ema50:
            bearish += 15.0
            bullish -= 10.0
    if ema50 and ema200:
        if ema50 > ema200:
            bullish += 10.0
        elif ema50 < ema200:
            bearish += 10.0
    if ema20_slope > 0:
        bullish += 10.0
    elif ema20_slope < 0:
        bearish += 10.0
    if adx >= 25:
        if bullish > bearish:
            bullish += 10.0
        elif bearish > bullish:
            bearish += 10.0
    vwap_config = load_strategy_signal_config().get("vwap_cost_channel") or {}
    vwap = classify_vwap_cost_channel(indicators, vwap_config)
    if vwap["vwap_bias"] == "bullish":
        bullish += 8.0
        bearish -= 4.0
    elif vwap["vwap_bias"] == "bearish":
        bearish += 8.0
        bullish -= 4.0
    return clamp(bullish), clamp(bearish)


def _compute_vol_compression(
    bb_width: float | None,
    bb_width_ma_90: float | None,
) -> float:
    """Multi-period percentile rank: current BB-width in 90-day distribution.

    Returns 0-100:
    - 90+ = extreme compression (BB-width < 50% of 90-day MA)
    - 50  = neutral (BB-width near MA)
    - 25  = expansion (BB-width > 1.4 × MA)
    """

    if not bb_width or not bb_width_ma_90 or bb_width_ma_90 <= 0:
        return 50.0
    ratio = bb_width / bb_width_ma_90
    if ratio < 0.5:
        return 90.0
    if ratio < 0.7:
        return 75.0
    if ratio < 0.85:
        return 60.0
    if ratio < 1.15:
        return 50.0
    if ratio < 1.4:
        return 40.0
    return 25.0


def _compute_setup_probability(
    long_score: float,
    short_score: float,
    setup_ready: bool,
    conflict_score: float,
    base_prior: float = 0.45,
) -> float:
    """Bayesian posterior: P(win | setup, regime) = prior × Π(likelihoods) / Z.

    Returns 0-1 win probability.
    """
    likelihoods: list[float] = []
    if max(long_score, short_score) > 60:
        likelihoods.append(1.4)
    if setup_ready:
        likelihoods.append(1.5)
    if conflict_score < 30:
        likelihoods.append(1.3)
    if max(long_score, short_score) > 75:
        likelihoods.append(1.6)
    if conflict_score > 70:
        likelihoods.append(0.6)
    if max(long_score, short_score) < 50:
        likelihoods.append(0.5)
    posterior = base_prior
    for lik in likelihoods:
        posterior *= lik
    return clamp(posterior, 0.01, 0.99)


def classify_vwap_cost_channel(
    features: dict[str, Any], config: dict[str, Any] | None = None
) -> dict[str, Any]:
    config = config or {}
    close = _num(features.get("close") or features.get("current_price"))
    vwap_short = _num(features.get("vwap_short") or features.get("vwap_50"))
    vwap_long = _num(features.get("vwap_long") or features.get("vwap_100"))
    short_slope = _num(features.get("vwap_slope_short_10") or features.get("vwap_slope_10"))
    long_slope = _num(features.get("vwap_slope_long_10"))
    price_buffer = float(config.get("price_buffer", 0.01))
    spread_buffer = float(config.get("spread_buffer", 0.005))
    if not close or not vwap_short or not vwap_long:
        return {
            "vwap_regime": "data_unavailable",
            "vwap_bias": "neutral",
            "vwap_confidence": 0,
            "price_position": "unknown",
            "risk_note": "VWAP 成本通道数据不足，仅保留中性过滤。",
        }
    above = close > vwap_long * (1 + price_buffer)
    below = close < vwap_long * (1 - price_buffer)
    short_above_long = vwap_short > vwap_long * (1 + spread_buffer)
    short_below_long = vwap_short < vwap_long * (1 - spread_buffer)
    slopes_up = short_slope >= 0 and long_slope >= 0
    slopes_down = short_slope <= 0 and long_slope <= 0
    price_position = "inside_channel"
    if above:
        price_position = "above_channel"
    elif below:
        price_position = "below_channel"
    if above and short_above_long and slopes_up:
        regime = "bull_trend"
        bias = "bullish"
        confidence = 75
        note = "价格有效站上长期 VWAP，短期成本高于长期成本且斜率确认。"
    elif below and short_below_long and slopes_down:
        regime = "bear_trend"
        bias = "bearish"
        confidence = 75
        note = "价格有效跌破长期 VWAP，短期成本低于长期成本且斜率确认。"
    elif short_above_long != above or short_below_long != below:
        regime = "cost_disagreement"
        bias = "neutral"
        confidence = 40
        note = "价格位置与 VWAP 成本结构不一致，按分歧处理。"
    elif above or below:
        regime = "mean_reversion_risk"
        bias = "neutral"
        confidence = 45
        note = "价格偏离成本通道但缺少斜率或价差确认，避免直接当作趋势触发。"
    else:
        regime = "neutral"
        bias = "neutral"
        confidence = 50
        note = "价格仍在 VWAP 成本缓冲区内。"
    return {
        "vwap_regime": regime,
        "vwap_bias": bias,
        "vwap_confidence": confidence,
        "price_position": price_position,
        "risk_note": note,
    }


def _build_structure_score(structure_overall: dict[str, Any]) -> tuple[float, float]:
    """Compute the structure component from BOS / swing / value area.

    Pulled out of the direction-metrics piggyback (T04). The structure page
    already publishes ``bias_score`` (or ``bullish_score``) on its overall
    payload; fall back to the ``bias`` label when the numeric score is
    missing. Returns ``(bullish, bearish)``.
    """

    bias_score = _num(
        structure_overall.get("bias_score")
        or structure_overall.get("bullish_score")
        or structure_overall.get("overall_score")
        or structure_overall.get("score")
    )
    if bias_score:
        return clamp(bias_score), clamp(100.0 - bias_score)
    bias = str(
        structure_overall.get("bias")
        or structure_overall.get("overall_bias")
        or structure_overall.get("direction")
        or ""
    ).lower()
    if bias in {"bullish", "long", "up", "strong_bullish"}:
        return 70.0, 30.0
    if bias in {"bearish", "short", "down", "strong_bearish"}:
        return 30.0, 70.0
    if bias in {"weak_bullish", "slightly_bullish", "neutral_bullish"}:
        return 60.0, 40.0
    if bias in {"weak_bearish", "slightly_bearish", "neutral_bearish"}:
        return 40.0, 60.0
    return 50.0, 50.0


def _build_regime_fit(structure_overall: dict[str, Any], regime: str | None) -> tuple[float, float, float]:
    """Compute the regime-fit component from the market regime classification.

    Pulled out of the direction-metrics piggyback (T04). Trend regimes
    reward either side symmetrically (both long and short can fit);
    balance / transition regimes penalize both directions. ``range_structure``
    is the inverse of the strongest directional fit and is used by the
    neutral-weight scorer.
    """

    regime_value = str(regime or structure_overall.get("regime") or "").lower()
    if regime_value in {"trend", "trending"}:
        return 65.0, 65.0, 35.0
    if regime_value in {"balance", "range", "ranging"}:
        return 35.0, 35.0, 80.0
    if regime_value in {"transition", "shock"}:
        return 40.0, 40.0, 60.0
    return 50.0, 50.0, 50.0


def _classify_margin_pressure(impact_pct: float, thresholds: dict[str, Any]) -> str:
    """Map a margin-impact percent to one of ``ok / downsize / small / block``.

    The audit (T06) requires four explicit tiers based on the
    ``one_atr_margin_impact_pct`` (or its equivalent). The thresholds come
    from the ``futures_risk.margin_pressure_thresholds`` config block and
    default to the audit-recommended 20/40/70 levels. A negative impact
    (e.g. short side) is folded to its absolute value.
    """

    impact = abs(float(impact_pct))
    downsize = float(thresholds.get("downsize", 20))
    small = float(thresholds.get("small", 40))
    block = float(thresholds.get("block", 70))
    if impact >= block:
        return "block"
    if impact >= small:
        return "small"
    if impact >= downsize:
        return "downsize"
    return "ok"


def _compute_futures_risk(
    *,
    atr_pct: float,
    entry: float,
    stop: float,
    leverage: float,
    thresholds: dict[str, Any],
    liq_warn_pct: float,
    liq_block_pct: float,
) -> dict[str, Any]:
    """Compute the full futures-margin risk bundle for a trade plan.

    The audit (T06) recommended surfacing the per-trade margin impact
    percentages and a 4-tier pressure verdict so the trading row can
    downgrade its tone and the strategy generator can refuse to grant
    a futures permission when the pressure is in the top tier. All
    numbers are in percent and rounded for readability; the underlying
    raw values are also kept for downstream tuners.
    """

    safe_leverage = max(1.0, float(leverage))
    stop_distance_pct = (
        abs(float(entry) - float(stop)) / max(abs(float(entry)), 1e-9) * 100.0
        if entry
        else 0.0
    )
    one_atr_impact = float(atr_pct) * safe_leverage
    stop_impact = stop_distance_pct * safe_leverage
    # Cross-margin liq buffer approximation: at leverage L, the maximum
    # adverse move before liquidation is 1/L. The buffer is the headroom
    # remaining once the protective stop is hit.
    liquidation_buffer = max(0.0, 100.0 / safe_leverage - stop_distance_pct)
    pressure = _classify_margin_pressure(one_atr_impact, thresholds)
    risk_blocked = pressure == "block" or liquidation_buffer < liq_block_pct
    buffer_warning = (
        "block"
        if liquidation_buffer < liq_block_pct
        else "warn"
        if liquidation_buffer < liq_warn_pct
        else "ok"
    )
    return {
        "atr_pct": round(float(atr_pct), 4),
        "leverage": round(safe_leverage, 2),
        "stop_distance_pct": round(stop_distance_pct, 4),
        "one_atr_margin_impact_pct": round(one_atr_impact, 4),
        "stop_margin_impact_pct": round(stop_impact, 4),
        "liquidation_buffer_pct": round(liquidation_buffer, 4),
        "futures_margin_pressure": pressure,
        "liquidation_buffer_warning": buffer_warning,
        "futures_risk_blocked": risk_blocked,
        "thresholds": {
            "downsize": float(thresholds.get("downsize", 20)),
            "small": float(thresholds.get("small", 40)),
            "block": float(thresholds.get("block", 70)),
        },
    }


class StrategySnapshotBuilder:
    """Build market strategy inputs from existing page bundles only."""

    def __init__(self, repository: MarketRepository) -> None:
        self.repository = repository

    async def build(
        self,
        instrument_id: str,
        timeframe: str,
        *,
        dependency_policy: str = "cache_only",
    ) -> dict[str, Any]:
        instrument = normalize_instrument_id(instrument_id)
        tf = normalize_timeframe_for_cache(timeframe)
        cache_only = dependency_policy == "cache_only"
        analysis = await AnalysisBundleService(self.repository).get_bundle(
            instrument, tf, "default"
        )
        alerts = await AlertsBundleService(self.repository).get_bundle(
            instrument,
            tf,
            allow_refresh=not cache_only,
        )
        monitoring = await MonitoringDashboardService(self.repository).get_bundle(
            instrument,
            tf,
            allow_refresh=not cache_only,
        )
        structure_payload = await self._structure_payload(instrument, tf)
        try:
            market_context = await MarketContextBuilder(self.repository).get_context(
                instrument,
                tf,
                cache_only=True,
            )
            market_context_payload = market_context.__dict__
        except Exception as exc:
            logger.debug("strategy market context unavailable: %s", exc)
            market_context_payload = {
                "instrument_id": instrument,
                "timeframe": tf,
                "data_quality": {"dependencies": {"market_context": {"cache_state": "error"}}},
                "cache_meta": {
                    "source": "market_context_builder",
                    "cache_state": "error",
                    "last_error": str(exc),
                },
            }

        analysis_payload = analysis.model_dump(mode="json")
        alerts_payload = alerts.model_dump(mode="json")
        monitoring_payload = monitoring.model_dump(mode="json")
        candles = analysis_payload.get("candles") or structure_payload.get("candles") or []
        mark = analysis_payload.get("mark") or {}
        current_price = _decimal(mark.get("mark_price") or mark.get("price"))
        if current_price is None and candles:
            current_price = _decimal(_field(candles[-1], "close"))

        core = analysis_payload.get("core_indicator_series") or {}
        secondary = analysis_payload.get("secondary_indicator_series") or {}
        final_decision = (
            analysis_payload.get("final_decision") or alerts_payload.get("final_decision") or {}
        )
        technical_risk_payload = alerts_payload.get("technical_risk") or {}
        macro_overview = monitoring_payload.get("macro_overview") or {}
        structure_overall = (
            (structure_payload.get("snapshot") or {}).get("overall")
            or structure_payload.get("overall")
            or {}
        )

        dependency_state = {
            "analysis": analysis_payload.get("cache_state"),
            "alerts": alerts_payload.get("cache_state"),
            "monitoring": monitoring_payload.get("cache_state"),
            "structure": structure_payload.get("cache_state"),
        }
        data_quality_score = _status_score(*dependency_state.values())
        indicators = self._indicators(core, secondary)
        levels = self._levels(structure_payload)
        config = load_strategy_signal_config()
        price = float(current_price) if current_price is not None else 0.0
        if price:
            indicators["close"] = price
        vwap_features = classify_vwap_cost_channel(
            indicators, config.get("vwap_cost_channel") or {}
        )

        direction_score = _num(final_decision.get("direction_score"), 0)
        direction_metrics = normalize_direction_metrics(direction_score, scale="signed")
        execution_score = _num(final_decision.get("execution_score"), 50)
        risk_score = _num(final_decision.get("risk_score"), 50)
        confidence_score = _num(final_decision.get("confidence_score"), 50)
        conflict_level = _num(final_decision.get("conflict_level"), 0)
        atr = max(_num(indicators.get("atr_14"), price * 0.025), price * 0.006) if price else 0
        support = _decimal(levels.get("support_price") or levels.get("val_price"))
        resistance = _decimal(levels.get("resistance_price") or levels.get("vah_price"))
        long_entry = float(support) if support is not None else price * 0.995
        short_entry = float(resistance) if resistance is not None else price * 1.005

        macro_status = macro_overview.get("event_window_status") or "normal"
        macro_bias = (
            macro_overview.get("risk_bias") or macro_overview.get("macro_bias") or "neutral"
        )
        rsi = _num(indicators.get("rsi_14"), 50)
        macd = _num(indicators.get("macd_hist"))
        macd_prev = _num(indicators.get("macd_hist_prev"))
        adx = _num(indicators.get("adx_14"), 20)
        divergence_risk = (technical_risk_payload.get("divergence") or {}) if isinstance(technical_risk_payload, dict) else {}
        if not divergence_risk:
            divergence_risk = build_divergence_risk(
                alerts_payload.get("divergence_summary"),
                strategy_bias=final_decision.get("strategy_bias", "neutral"),
                timeframe=tf,
            )
        divergence_scores = score_divergence_for_snapshot(divergence_risk)
        trigger_tf = (config.get("timeframe_mapping") or {}).get(tf)
        lower_tf_required = bool(trigger_tf)
        # T05 audit fix: actually load the lower timeframe snapshot instead
        # of inferring it from the aggregate data quality score. The data
        # quality heuristic was masking cases where the lower timeframe is
        # perfectly available but the higher timeframe bundle is degraded.
        lower_tf_payload = None
        lower_tf_alignment: dict[str, Any] = {"status": "not_required"}
        if lower_tf_required and trigger_tf:
            lower_tf_payload = await self._load_lower_tf_snapshot(
                instrument=instrument, lower_tf=trigger_tf
            )
            if lower_tf_payload is None:
                lower_tf_missing = True
                lower_tf_alignment = {
                    "status": "missing",
                    "required_timeframe": trigger_tf,
                    "current_timeframe": tf,
                    "message": "缺少次级周期快照，方向优势不能直接升级为入场触发。",
                }
            else:
                lower_tf_missing = False
                lower_tf_alignment = self._compute_lower_tf_alignment(
                    higher_direction=direction_metrics,
                    lower_payload=lower_tf_payload,
                    higher_timeframe=tf,
                    lower_timeframe=trigger_tf,
                )
        else:
            lower_tf_missing = False
        ema20 = _num(indicators.get("ema_20"))
        ema20_prev = _num(indicators.get("ema_20_prev"), ema20)
        ema20_slope = ema20 - ema20_prev
        atr_pct = _num(indicators.get("natr_14")) or (atr / price * 100 if price else 0)
        atr_expansion_score = max(0, min(100, atr_pct * 12))
        volume_confirmation = max(0, min(100, 50 + _num(indicators.get("obv_slope")) * 80))
        missing_inputs: list[str] = []
        futures_risk_config = config.get("futures_risk") or {}
        leverage = _num(futures_risk_config.get("default_leverage"), 10) or 10
        thresholds = futures_risk_config.get("margin_pressure_thresholds") or {}
        liq_warn_pct = _num(futures_risk_config.get("liquidation_buffer_warn_pct"), 3.0)
        liq_block_pct = _num(futures_risk_config.get("liquidation_buffer_block_pct"), 1.5)
        # Compute the futures risk bundle for both sides so the strategy
        # generator and the terminal summary can reason about it.
        futures_risk_long = _compute_futures_risk(
            atr_pct=atr_pct,
            entry=long_entry,
            stop=_num(levels.get("structure_invalid_long"), long_entry - atr * 1.6),
            leverage=leverage,
            thresholds=thresholds,
            liq_warn_pct=liq_warn_pct,
            liq_block_pct=liq_block_pct,
        )
        futures_risk_short = _compute_futures_risk(
            atr_pct=atr_pct,
            entry=short_entry,
            stop=_num(levels.get("structure_invalid_short"), short_entry + atr * 1.6),
            leverage=leverage,
            thresholds=thresholds,
            liq_warn_pct=liq_warn_pct,
            liq_block_pct=liq_block_pct,
        )
        futures_risk_active = {
            "long": futures_risk_long,
            "short": futures_risk_short,
        }
        for key, state in dependency_state.items():
            if state in {"missing", "error", "stale", "updating", "degraded"}:
                missing_inputs.append(f"{key}:{state}")
        missing_input_penalties = self._missing_input_penalties(missing_inputs)

        snapshot: dict[str, Any] = {
            "instrument_id": instrument,
            "symbol": instrument,
            "timeframe": tf,
            "timestamp": datetime.now(UTC).isoformat(),
            "generated_at": datetime.now(UTC).isoformat(),
            "current_price": str(current_price) if current_price is not None else None,
            "data_quality": {
                "score": data_quality_score,
                "statuses": dependency_state,
                "candles_count": len(candles),
            },
            "price": {"current": str(current_price) if current_price is not None else None},
            "indicators": indicators,
            "vwap_features": vwap_features,
            "levels": levels,
            "macro": {"macro_bias": macro_bias, "event_window_status": macro_status},
            "structure": {
                "overall": structure_overall,
                "snapshot": structure_payload.get("snapshot"),
            },
            "final_decision_v12": final_decision,
            "alerts": {
                "events": alerts_payload.get("alert_events", []),
                "divergence_summary": alerts_payload.get("divergence_summary"),
            },
            "technical_risk": {"divergence": divergence_risk},
            "monitoring": monitoring_payload,
            "market_context": market_context_payload,
            "bundle_status": {
                **dependency_state,
            },
            "dependency_state": dependency_state,
            "missing_inputs": missing_inputs,
            "missing_input_penalties": missing_input_penalties,
            "trigger_timeframe": trigger_tf,
            "lower_tf_required": bool(trigger_tf),
            "lower_tf_missing": lower_tf_missing,
            "lower_tf_payload": lower_tf_payload,
            "lower_tf_alignment": lower_tf_alignment,
            "atr_pct": round(atr_pct, 4),
            "futures_risk": futures_risk_active,
            "futures_risk_thresholds": {
                "downsize": _num(thresholds.get("downsize"), 20),
                "small": _num(thresholds.get("small"), 40),
                "block": _num(thresholds.get("block"), 70),
            },
            "default_leverage": leverage,
            "direction_score_raw": direction_score,
            "direction_score_scale": direction_metrics.get("scale"),
            "direction_score_normalized": direction_metrics,
        }
        snapshot.update(
            {
                "candle_completeness": data_quality_score,
                "candle_freshness": data_quality_score,
                "multi_timeframe_availability": 80 if final_decision else 55,
                "macro_event_availability": 100 if macro_status else 60,
                **divergence_scores,
                **self._build_snapshot(
                    features=self._feature_components(
                        indicators=indicators,
                        structure_overall=structure_overall,
                        regime=structure_overall.get("regime"),
                        direction_metrics=direction_metrics,
                        rsi=rsi,
                        macd=macd,
                        macd_prev=macd_prev,
                        adx=adx,
                        long_entry=long_entry,
                        long_stop=_num(
                            levels.get("structure_invalid_long"),
                            long_entry - atr * 1.6,
                        ),
                        long_tp1=(
                            float(resistance)
                            if resistance is not None
                            else price + atr * 2.2
                        ),
                        short_entry=short_entry,
                        short_stop=_num(
                            levels.get("structure_invalid_short"),
                            short_entry + atr * 1.6,
                        ),
                        short_tp1=(
                            float(support)
                            if support is not None
                            else price - atr * 2.2
                        ),
                    ),
                    regime=structure_overall.get("regime"),
                    adx=adx,
                    instrument_id=instrument,
                    timeframe=tf,
                    config=config,
                ),
                "low_volume_confirmation": 50,
                "low_adx": max(0, 60 - adx),
                "volume_proxy_confirmation": volume_confirmation,
                "execution_quality": execution_score,
                "event_risk_score": 85
                if macro_status in {"block", "event_wait", "risk_off"}
                else 20,
                "funding_crowding_score": 0,
                "late_entry_risk_score": risk_score,
                "conflict_score": min(100, conflict_level * 20),
                "long_setup_ready": direction_metrics["bullish"] >= 58,
                "short_setup_ready": direction_metrics["bearish"] >= 58,
                "long_trigger_ready": bool(levels.get("breakout_up")) or confidence_score >= 72,
                "short_trigger_ready": bool(levels.get("breakout_down"))
                or (direction_metrics["bearish"] >= 65 and confidence_score >= 72),
                "long_entry": long_entry,
                "long_stop": _num(levels.get("structure_invalid_long"), long_entry - atr * 1.6),
                "long_tp1": float(resistance) if resistance is not None else price + atr * 2.2,
                "long_tp2": price + atr * 3.6,
                "short_entry": short_entry,
                "short_stop": _num(levels.get("structure_invalid_short"), short_entry + atr * 1.6),
                "short_tp1": float(support) if support is not None else price - atr * 2.2,
                "short_tp2": price - atr * 3.6,
                "market_regime": str(structure_overall.get("regime") or "unknown"),
                "atr_14": indicators.get("atr_14"),
                "adx_14": indicators.get("adx_14"),
                "ema_20": indicators.get("ema_20"),
                "ema_50": indicators.get("ema_50"),
                "ema_200": indicators.get("ema_200"),
                "ema20_slope": ema20_slope,
                "atr_expansion_score": atr_expansion_score,
                "volume_confirmation": volume_confirmation,
                "breakout_up": bool(levels.get("breakout_up")),
                "breakout_down": bool(levels.get("breakout_down")),
                "event_window_status": macro_status,
                "vwap_regime": vwap_features.get("vwap_regime"),
                "vwap_bias": vwap_features.get("vwap_bias"),
                "vwap_confidence": vwap_features.get("vwap_confidence"),
            }
        )
        await self._persist_strategy_cache(instrument, tf, snapshot)
        return snapshot

    async def _persist_strategy_cache(
        self,
        instrument_id: str,
        timeframe: str,
        snapshot: dict[str, Any],
    ) -> None:
        """Best-effort write of the strategy snapshot to PageSnapshotCache.

        The strategy decision is what the monitoring overview decision_brief
        reuses. If the write fails (e.g. transient DB issue), the caller
        still gets the snapshot in memory; the next refresh will retry.
        """

        now = datetime.now(UTC)
        try:
            await self.repository.upsert_page_snapshot_cache(
                cache_key=strategy_bundle_cache_key(instrument_id, timeframe),
                page_type="strategy",
                instrument_id=instrument_id,
                timeframe=timeframe,
                payload_json={"decision": snapshot},
                status="ready",
                cache_state="fresh",
                snapshot_at=now,
                data_ts=now,
                expires_at=expires_at_for_strategy(timeframe, now),
                source_updated_at=now,
                source_version=CACHE_SOURCE_VERSION,
                cost_ms=0,
                meta_json={"source": "strategy_snapshot_builder"},
            )
        except Exception as exc:
            logger.debug("strategy bundle cache write skipped: %s", exc)

    @staticmethod
    def _feature_components(
        *,
        indicators: dict[str, Any],
        structure_overall: dict[str, Any],
        regime: str | None,
        direction_metrics: dict[str, float],
        rsi: float,
        macd: float,
        macd_prev: float,
        adx: float,
        long_entry: float | None = None,
        long_stop: float | None = None,
        long_tp1: float | None = None,
        short_entry: float | None = None,
        short_stop: float | None = None,
        short_tp1: float | None = None,
    ) -> dict[str, float]:
        """Combine strategy features from trend, structure, regime and momentum."""

        trend_bullish, trend_bearish = _build_trend_score(indicators)
        struct_bullish, struct_bearish = _build_structure_score(structure_overall)
        regime_long, regime_short, range_score = _build_regime_fit(structure_overall, regime)
        # Momentum still derives from RSI / MACD; capped to a sensible 0..100
        # band because the audit flagged the previous raw-add formula as
        # able to escape the 0..100 range.
        bullish_momentum = clamp(
            50.0 + max(0.0, rsi - 50.0) * 1.3 + max(0.0, macd - macd_prev) * 3.0
        )
        bearish_momentum = clamp(
            50.0 + max(0.0, 50.0 - rsi) * 1.3 + max(0.0, macd_prev - macd) * 3.0
        )
        # V1.7.4 audit fix: low_directional_spread and *_risk_reward sub-scores
        # are weighted at 0.20 + 0.15 + 0.15 = 0.50 (50%) of the range-mode
        # long/short score in market_strategy_signal_config_v17.json. Without
        # these values the call to ``weighted_score`` falls back to 0 via
        # ``dict.get(key, 0)``, silently zeroing half the range-mode signal.
        # Build them from raw inputs that are always available at the call
        # site and fall back to 50 (neutral) when input data is incomplete.
        bullish_component = direction_metrics.get("bullish", 0.0)
        bearish_component = direction_metrics.get("bearish", 0.0)
        directional_gap = abs(bullish_component - bearish_component)
        low_directional_spread = clamp(100.0 - directional_gap)

        rr_long = compute_risk_reward("long", long_entry, long_stop, long_tp1)
        rr_short = compute_risk_reward("short", short_entry, short_stop, short_tp1)
        long_risk_reward = risk_reward_score(rr_long) if rr_long is not None else 50.0
        short_risk_reward = risk_reward_score(rr_short) if rr_short is not None else 50.0

        # Direction-score kept in the snapshot as a labeled aggregate, not as
        # a re-source for trend/structure/regime (T04).
        features: dict[str, Any] = {
            "mtf_trend_bullish": trend_bullish,
            "mtf_trend_bearish": trend_bearish,
            "mtf_trend_source": "ema+adx+vwap",
            "bullish_structure": struct_bullish,
            "bearish_structure": struct_bearish,
            "structure_source": "structure_overall",
            "regime_fit_long": regime_long,
            "regime_fit_short": regime_short,
            "regime_source": str(regime or structure_overall.get("regime") or "unknown"),
            "range_structure": range_score,
            "bullish_momentum": bullish_momentum,
            "bearish_momentum": bearish_momentum,
            "momentum_source": "rsi+macd",
            "direction_score_aggregate": direction_metrics["bullish"]
            - direction_metrics["bearish"],
            "low_directional_spread": low_directional_spread,
            "long_risk_reward": long_risk_reward,
            "short_risk_reward": short_risk_reward,
            "risk_reward_source": "entries+stops+tps" if (
                rr_long is not None or rr_short is not None
            ) else "neutral_default",
        }
        # V1.7.5: surface vol_compression (bb_width vs bb_width_ma_90 percentile
        # rank) and setup_probability (Bayesian posterior) on the features dict
        # so the transition-mode multiplicative gate and downstream consumers
        # (strategy generator, terminal summary) can read them directly.
        # ``_compute_vol_compression`` falls back to 50 when ``bb_width_ma_90``
        # is missing — same neutral fallback the helper exposes for tests.
        features["vol_compression"] = _compute_vol_compression(
            bb_width=_num(indicators.get("bb_width")),
            bb_width_ma_90=_num(indicators.get("bb_width_ma_90")) or None,
        )
        # Setup-ready proxy mirrors the ``long_setup_ready`` rule applied later
        # in ``build()`` (``direction_metrics.bullish >= 58``). Conflict score
        # is not surfaced through ``_feature_components`` yet, so we fall back
        # to 50 (neutral) — Bayesian posterior with no negative evidence.
        setup_ready = direction_metrics.get("bullish", 0.0) >= 58
        conflict_score = 50.0
        features["setup_ready"] = setup_ready
        features["conflict_score"] = conflict_score
        features["setup_probability"] = _compute_setup_probability(
            long_score=trend_bullish + struct_bullish,
            short_score=trend_bearish + struct_bearish,
            setup_ready=setup_ready,
            conflict_score=conflict_score,
        )
        return features

    @staticmethod
    def _compute_mode_aware_scores(
        feature_dict: dict[str, Any],
        *,
        regime: str | None,
        adx: float | None,
        instrument_id: str | None,
        timeframe: str | None,
        config: dict[str, Any] | None = None,
    ) -> dict[str, Any]:
        """Compute long/short/neutral scores using per-mode weight tables.

        Returns the active ``mode`` (``trend`` | ``range`` | ``transition``)
        plus the asset class, the three weighted scores and a copy of the
        weights that were actually used. The mode detection uses the same
        :func:`detect_mode` / :func:`detect_asset_class` helpers as the rest
        of the pipeline so a given (regime, adx, asset_class, timeframe)
        tuple always maps to the same weight table here and downstream.

        The mode-specific dict is preferred over the flat ``long_weights`` /
        ``short_weights`` block; when no per-mode entry exists for the active
        mode (e.g. ``transition``) the function falls back to the flat
        weights so the system never silently drops a sub-score.
        """

        cfg = config if config is not None else load_strategy_signal_config()
        asset_class = detect_asset_class(instrument_id)
        mode = detect_mode(
            regime=regime,
            adx=adx,
            asset_class=asset_class,
            timeframe=timeframe,
        )
        long_weights_by_mode = cfg.get("long_weights_by_mode") or {}
        long_weights = long_weights_by_mode.get(mode) or cfg.get("long_weights") or {}
        short_weights_by_mode = cfg.get("short_weights_by_mode") or {}
        short_weights = short_weights_by_mode.get(mode) or cfg.get("short_weights") or {}
        neutral_weights = cfg.get("neutral_weights") or {}

        raw_long = weighted_score(feature_dict, long_weights)
        raw_short = weighted_score(feature_dict, short_weights)
        neutral_score = weighted_score(feature_dict, neutral_weights)

        # V1.7.5 transition multiplicative gate: scale the long/short scores
        # by ``vol_compression / 100`` so an extended squeeze (low bb_width
        # relative to its 90-day MA) dampens the directional signal in
        # transition mode where neither trend nor range weights are reliable.
        # Without sufficient volatility compression the gate suppresses both
        # sides symmetrically — neutral_score is left alone because the gate
        # only gates directional commitment, not the do-nothing baseline.
        if mode == "transition":
            vol_compression_score = _num(feature_dict.get("vol_compression"), 50.0)
            vol_factor = clamp(vol_compression_score / 100.0, 0.0, 1.0)
            raw_long = raw_long * vol_factor
            raw_short = raw_short * vol_factor

        return {
            "mode": mode,
            "asset_class": asset_class,
            "long_score": round2(raw_long),
            "short_score": round2(raw_short),
            "neutral_score": round2(neutral_score),
            "long_weights": dict(long_weights),
            "short_weights": dict(short_weights),
        }

    @staticmethod
    def _build_snapshot(
        *,
        features: dict[str, Any],
        regime: str | None,
        adx: float | None,
        instrument_id: str | None,
        timeframe: str | None,
        config: dict[str, Any] | None = None,
    ) -> dict[str, Any]:
        """Build a scored snapshot dict from pre-computed feature values.

        This is the sync helper the public :meth:`build` calls once the
        heavier async dependency fetches have been resolved; it is also the
        test seam used by ``tests/test_strategy_signal_snapshot.py`` so the
        mode-aware weight selection can be exercised without touching the DB.
        """

        scored = StrategySnapshotBuilder._compute_mode_aware_scores(
            features,
            regime=regime,
            adx=adx,
            instrument_id=instrument_id,
            timeframe=timeframe,
            config=config,
        )
        return {
            **features,
            "mode": scored["mode"],
            "asset_class": scored["asset_class"],
            "long_score": scored["long_score"],
            "short_score": scored["short_score"],
            "neutral_score": scored["neutral_score"],
            "long_weights": scored["long_weights"],
            "short_weights": scored["short_weights"],
        }

    @staticmethod
    def _indicators(core: dict[str, Any], secondary: dict[str, Any]) -> dict[str, Any]:
        return {
            "ema_20": _last_value(core, "ema_20"),
            "ema_20_prev": _previous_value(core, "ema_20"),
            "ema_50": _last_value(core, "ema_50"),
            "ema_200": _last_value(core, "ema_200"),
            "rsi_14": _last_value(core, "rsi_14"),
            "macd_hist": _last_value(core, "macd_hist"),
            "macd_hist_prev": _previous_value(core, "macd_hist"),
            "atr_14": _last_value(core, "atr_14"),
            "natr_14": _last_value(core, "natr_14"),
            "adx_14": _last_value(secondary, "adx_14"),
            "bb_width": _last_value(secondary, "bbands_width", "boll_width"),
            "percent_b": _last_value(secondary, "percent_b"),
            "obv": _last_value(secondary, "obv"),
            "obv_slope": _last_value(secondary, "obv_slope"),
            "vwap_short": _last_value(secondary, "vwap_short", "vwap_50"),
            "vwap_long": _last_value(secondary, "vwap_long", "vwap_100"),
            "price_vs_vwap_short_pct": _last_value(secondary, "price_vs_vwap_short_pct"),
            "price_vs_vwap_long_pct": _last_value(secondary, "price_vs_vwap_long_pct"),
            "vwap_spread_pct": _last_value(secondary, "vwap_spread_pct"),
            "vwap_slope_short_10": _last_value(secondary, "vwap_slope_short_10", "vwap_slope_10"),
            "vwap_slope_long_10": _last_value(secondary, "vwap_slope_long_10"),
        }

    @staticmethod
    def _levels(structure_payload: dict[str, Any]) -> dict[str, Any]:
        return {
            "support_price": _find_value(structure_payload, "support_price", "support"),
            "resistance_price": _find_value(structure_payload, "resistance_price", "resistance"),
            "poc_price": _find_value(structure_payload, "poc", "poc_price"),
            "vah_price": _find_value(structure_payload, "vah", "vah_price"),
            "val_price": _find_value(structure_payload, "val", "val_price"),
            "structure_invalid_long": _find_value(
                structure_payload, "structure_invalid_long", "invalid_long", "invalidation_long"
            ),
            "structure_invalid_short": _find_value(
                structure_payload, "structure_invalid_short", "invalid_short", "invalidation_short"
            ),
            "breakout_up": bool(_find_value(structure_payload, "breakout_up", "bos_up")),
            "breakout_down": bool(_find_value(structure_payload, "breakout_down", "bos_down")),
            "false_breakout": bool(_find_value(structure_payload, "false_breakout")),
            "false_breakdown": bool(_find_value(structure_payload, "false_breakdown")),
        }

    @staticmethod
    def _missing_input_penalties(missing_inputs: list[str]) -> list[dict[str, Any]]:
        penalties: list[dict[str, Any]] = []
        joined = " ".join(missing_inputs).lower()
        rules = [
            (
                "structure",
                ("structure:missing", "structure:error", "structure:stale"),
                70,
                "结构快照缺失或滞后，结构贡献上限降至 70。",
            ),
        ]
        for key, tokens, cap, message in rules:
            if any(token in joined for token in tokens):
                penalties.append({"input": key, "cap": cap, "message": message})
        return penalties

    async def _load_lower_tf_snapshot(
        self, *, instrument: str, lower_tf: str
    ) -> dict[str, Any] | None:
        """Load the strategy bundle for the lower trigger timeframe.

        T05 audit fix: the snapshot used to mark ``lower_tf_missing`` whenever
        the aggregate data quality score was below 60, which conflated the
        higher timeframe bundle health with the lower timeframe's own
        availability. The lower timeframe is now read directly from the
        ``strategy_bundle`` page snapshot cache; if it is not there (no
        scheduled refresh has produced it yet) we still return ``None`` so
        the snapshot can mark the trigger as missing.
        """

        cache_key = strategy_bundle_cache_key(instrument, lower_tf)
        try:
            cached = await self.repository.get_page_snapshot_cache(cache_key)
        except Exception as exc:
            logger.debug("lower_tf snapshot cache read failed: %s", exc)
            return None
        if cached is None:
            return None
        payload = getattr(cached, "payload_json", None) or {}
        if not isinstance(payload, dict):
            return None
        decision = payload.get("decision") or {}
        if not isinstance(decision, dict):
            decision = {}
        cache_state = getattr(cached, "cache_state", "unknown")
        return {
            "instrument_id": instrument,
            "timeframe": lower_tf,
            "cache_state": cache_state,
            "snapshot_at": (
                cached.snapshot_at.isoformat()
                if getattr(cached, "snapshot_at", None) is not None
                else None
            ),
            "expires_at": (
                cached.expires_at.isoformat()
                if getattr(cached, "expires_at", None) is not None
                else None
            ),
            "strategy_state": decision.get("strategy_state"),
            "strategy_state_label": decision.get("strategy_state_label"),
            "strategy_bias": decision.get("strategy_bias"),
            "direction_score": decision.get("direction_confidence")
            or decision.get("long_score")
            or decision.get("short_score"),
            "long_score": decision.get("long_score"),
            "short_score": decision.get("short_score"),
            "mtf_trend_bullish": decision.get("mtf_trend_bullish"),
            "mtf_trend_bearish": decision.get("mtf_trend_bearish"),
            "confidence": decision.get("direction_confidence")
            or decision.get("confidence_score"),
            "next_trigger": decision.get("next_trigger"),
            "gates": decision.get("gates"),
        }

    @staticmethod
    def _compute_lower_tf_alignment(
        *,
        higher_direction: dict[str, float],
        lower_payload: dict[str, Any],
        higher_timeframe: str,
        lower_timeframe: str,
    ) -> dict[str, Any]:
        """Compare the higher-timeframe direction against the lower-timeframe snapshot."""

        higher_bullish = float(higher_direction.get("bullish") or 0)
        higher_bearish = float(higher_direction.get("bearish") or 0)
        higher_diff = higher_bullish - higher_bearish
        higher_label = (
            "bullish"
            if higher_diff > 5
            else "bearish"
            if higher_diff < -5
            else "neutral"
        )

        long_score = _num(lower_payload.get("long_score"))
        short_score = _num(lower_payload.get("short_score"))
        lower_diff = long_score - short_score
        lower_label = (
            "bullish"
            if lower_diff > 5
            else "bearish"
            if lower_diff < -5
            else "neutral"
        )
        if higher_label == "neutral" or lower_label == "neutral":
            status = "neutral"
        elif higher_label == lower_label:
            status = "aligned"
        else:
            status = "conflict"

        return {
            "status": status,
            "required_timeframe": lower_timeframe,
            "current_timeframe": higher_timeframe,
            "higher_label": higher_label,
            "lower_label": lower_label,
            "long_score": long_score,
            "short_score": short_score,
            "lower_strategy_state": lower_payload.get("strategy_state"),
            "lower_cache_state": lower_payload.get("cache_state"),
        }

    async def _structure_payload(self, instrument_id: str, timeframe: str) -> dict[str, Any]:
        try:
            from app.services.structure.snapshot_service import StructureSnapshotService

            structure = await StructureSnapshotService(self.repository).get_bundle(
                instrument_id,
                timeframe,
                include_geometry=True,
                candles_limit=220,
            )
            payload = structure.model_dump(mode="json")
            snapshot = payload.get("snapshot")
            if snapshot is None:
                payload["snapshot"] = {"overall": {}}
            if not payload.get("overall"):
                payload["overall"] = {}
            payload.setdefault("candles", [])
            payload.setdefault("diagnostics", {})
            return payload
        except Exception as exc:
            return {
                "instrument_id": instrument_id,
                "timeframe": timeframe,
                "cache_state": "low_confidence",
                "status": "low_confidence",
                "candles": [],
                "snapshot": {"overall": {}},
                "overall": {},
                "diagnostics": {"messages": [f"结构快照暂不可用：{exc}"]},
            }
