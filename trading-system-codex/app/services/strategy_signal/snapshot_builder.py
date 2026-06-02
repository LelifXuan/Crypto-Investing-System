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
from app.services.monitoring_dashboard import MonitoringDashboardService
from app.services.strategy_signal.config_loader import load_strategy_signal_config
from app.services.strategy_signal.risk_reward import clamp
from app.services.strategy_signal.setup_lifecycle import normalize_direction_metrics

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
    return clamp(bullish), clamp(bearish)


def _build_structure_score(structure_overall: dict[str, Any]) -> tuple[float, float]:
    """Compute the structure component from BOS / swing / value area.

    Pulled out of the direction-metrics piggyback (T04). The structure page
    already publishes ``bias_score`` (or ``bullish_score``) on its overall
    payload; fall back to the ``bias`` label when the numeric score is
    missing. Returns ``(bullish, bearish)``.
    """

    bias_score = _num(structure_overall.get("bias_score"))
    if not bias_score:
        bias_score = _num(structure_overall.get("bullish_score"))
    if bias_score:
        return clamp(bias_score), clamp(100.0 - bias_score)
    bias = str(
        structure_overall.get("bias")
        or structure_overall.get("overall_bias")
        or structure_overall.get("direction")
        or ""
    ).lower()
    if bias in {"bullish", "long", "up"}:
        return 70.0, 30.0
    if bias in {"bearish", "short", "down"}:
        return 30.0, 70.0
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


def _build_flow_score(derivatives: dict[str, Any]) -> tuple[float, float]:
    """Compute the money-flow component from CVD / OI change / funding.

    The audit (T04) found that OI was being treated as a raw number while
    CVD is z-scored, and the two were being summed with the same weight
    (250). This routine keeps the OI percent weight, the CVD z-score weight,
    and the funding-z weight separate so the audit can tune them in
    isolation. OI is assumed to be a percent value per the
    ``oi_change_pct`` field name; values in (0, 1) are treated as decimals
    and rescaled to percent.
    """

    cvd = _num(derivatives.get("cvd_norm"))
    oi_raw = _num(derivatives.get("oi_change_pct"))
    # Normalize to percent: oi_change_pct should be a percent (4.0 == 4 %).
    # Decimal sources slip in (< 1) and are silently rescaled.
    oi_change = oi_raw * 100.0 if -1.0 < oi_raw < 1.0 else oi_raw
    funding_z = abs(_num(derivatives.get("funding_zscore")))

    bullish = 50.0 + max(0.0, cvd) * 18.0 + max(0.0, oi_change) * 6.0
    bearish = 50.0 + max(0.0, -cvd) * 18.0 + max(0.0, -oi_change) * 6.0
    # Funding z dilutes both sides: extreme funding often precedes reversals.
    dilution = min(20.0, funding_z * 12.0)
    bullish -= dilution
    bearish -= dilution
    return clamp(bullish), clamp(bearish)


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
        chip = alerts_payload.get("chip_structure") or {}
        contract_snapshot = (
            analysis_payload.get("contract_snapshot")
            or alerts_payload.get("contract_snapshot")
            or {}
        )
        macro_overview = monitoring_payload.get("macro_overview") or {}
        structure_overall = (
            structure_payload.get("snapshot", {}).get("overall")
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
        derivatives = self._derivatives(contract_snapshot, chip)
        config = load_strategy_signal_config()

        direction_score = _num(
            final_decision.get("direction_score") or chip.get("direction_score"), 0
        )
        direction_metrics = normalize_direction_metrics(direction_score, scale="signed")
        execution_score = _num(
            final_decision.get("execution_score") or chip.get("execution_score"), 50
        )
        risk_score = _num(final_decision.get("risk_score") or chip.get("risk_score"), 50)
        confidence_score = _num(
            final_decision.get("confidence_score") or chip.get("confidence_score"), 50
        )
        conflict_level = _num(final_decision.get("conflict_level") or chip.get("conflict_level"), 0)
        price = float(current_price) if current_price is not None else 0.0
        atr = max(_num(indicators.get("atr_14"), price * 0.025), price * 0.006) if price else 0
        support = _decimal(levels.get("support_price") or levels.get("val_price"))
        resistance = _decimal(levels.get("resistance_price") or levels.get("vah_price"))
        long_entry = float(support) if support is not None else price * 0.995
        short_entry = float(resistance) if resistance is not None else price * 1.005

        macro_status = macro_overview.get("event_window_status") or "normal"
        macro_bias = (
            macro_overview.get("risk_bias") or macro_overview.get("macro_bias") or "neutral"
        )
        cvd = _num(derivatives.get("cvd_norm"))
        oi_change = _num(derivatives.get("oi_change_pct"))
        rsi = _num(indicators.get("rsi_14"), 50)
        macd = _num(indicators.get("macd_hist"))
        macd_prev = _num(indicators.get("macd_hist_prev"))
        adx = _num(indicators.get("adx_14"), 20)
        funding_z = abs(_num(derivatives.get("funding_zscore")))
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
        missing_inputs = list(dict.fromkeys(derivatives.get("missing_inputs") or []))
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
            "levels": levels,
            "derivatives_micro": derivatives,
            "macro": {"macro_bias": macro_bias, "event_window_status": macro_status},
            "structure": {
                "overall": structure_overall,
                "chip_structure": chip,
                "snapshot": structure_payload.get("snapshot"),
            },
            "final_decision_v12": final_decision,
            "alerts": {
                "events": alerts_payload.get("alert_events", []),
                "divergence_summary": alerts_payload.get("divergence_summary"),
            },
            "monitoring": monitoring_payload,
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
                "derivatives_data_availability": max(
                    0,
                    100 - min(70, len(missing_inputs) * 10),
                ),
                "orderbook_data_availability": 100
                if derivatives.get("spread_bps") is not None
                else 50,
                "macro_event_availability": 100 if macro_status else 60,
                **self._feature_components(
                    indicators=indicators,
                    structure_overall=structure_overall,
                    regime=structure_overall.get("regime") or chip.get("regime"),
                    derivatives=derivatives,
                    direction_metrics=direction_metrics,
                    rsi=rsi,
                    macd=macd,
                    macd_prev=macd_prev,
                    cvd=cvd,
                    oi_change=oi_change,
                    adx=adx,
                ),
                "low_volume_confirmation": 50,
                "low_adx": max(0, 60 - adx),
                "derivatives_long_confirmation": 50 + max(0, oi_change) * 250,
                "derivatives_short_confirmation": 50 + max(0, -oi_change) * 250,
                "execution_quality": execution_score,
                "depth_score": execution_score,
                "event_risk_score": 85
                if macro_status in {"block", "event_wait", "risk_off"}
                else 20,
                "funding_crowding_score": min(100, funding_z * 35),
                "oi_price_divergence_score": 20,
                "cvd_divergence_score": 20,
                "late_entry_risk_score": risk_score,
                "conflict_score": min(100, conflict_level * 20),
                "spread_bps": derivatives.get("spread_bps") or 0,
                "slippage_bps": derivatives.get("slippage_bps") or 0,
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
                "market_regime": str(
                    structure_overall.get("regime") or chip.get("regime") or "unknown"
                ),
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
        derivatives: dict[str, Any],
        direction_metrics: dict[str, float],
        rsi: float,
        macd: float,
        macd_prev: float,
        cvd: float,
        oi_change: float,
        adx: float,
    ) -> dict[str, float]:
        """Combine the 5 independent feature sources into the snapshot feature row.

        Each feature family now lives in its own helper so the audit (T04)
        can tune weights in isolation and a regression in one family does
        not silently poison the others. The 5 families are:

        * **trend** — EMA 20/50/200 alignment + slope + ADX strength
        * **structure** — BOS / swing / value area from structure page
        * **regime_fit** — market-regime classifier (trend/balance/transition)
        * **momentum** — RSI / MACD histogram (no change in source)
        * **flow** — CVD / OI / funding-z, with explicit unit normalization
        """

        trend_bullish, trend_bearish = _build_trend_score(indicators)
        struct_bullish, struct_bearish = _build_structure_score(structure_overall)
        regime_long, regime_short, range_score = _build_regime_fit(structure_overall, regime)
        flow_bullish, flow_bearish = _build_flow_score(derivatives)
        # Momentum still derives from RSI / MACD; capped to a sensible 0..100
        # band because the audit flagged the previous raw-add formula as
        # able to escape the 0..100 range.
        bullish_momentum = clamp(
            50.0 + max(0.0, rsi - 50.0) * 1.3 + max(0.0, macd - macd_prev) * 3.0
        )
        bearish_momentum = clamp(
            50.0 + max(0.0, 50.0 - rsi) * 1.3 + max(0.0, macd_prev - macd) * 3.0
        )
        # Direction-score kept in the snapshot as a labeled aggregate, not as
        # a re-source for trend/structure/regime (T04).
        return {
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
            "bullish_flow": flow_bullish,
            "bearish_flow": flow_bearish,
            "flow_source": "cvd+oi+funding",
            "derivatives_long_confirmation": flow_bullish,
            "derivatives_short_confirmation": flow_bearish,
            "direction_score_aggregate": direction_metrics["bullish"]
            - direction_metrics["bearish"],
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
    def _derivatives(contract_snapshot: dict[str, Any], chip: dict[str, Any]) -> dict[str, Any]:
        return {
            "funding_zscore": _find_value(
                contract_snapshot, "funding_rate_zscore", "funding_zscore"
            ),
            "basis_zscore": _find_value(contract_snapshot, "basis_rate_zscore", "basis_zscore"),
            "cvd_norm": _find_value(contract_snapshot, "cvd_norm", "cvd_zscore"),
            "oi_change_pct": _find_value(
                contract_snapshot, "oi_change_pct", "open_interest_change_pct"
            ),
            "price_change_pct": _find_value(contract_snapshot, "price_change_pct"),
            "depth_notional": _find_value(contract_snapshot, "depth_notional", "depth_50bps"),
            "spread_bps": _find_value(contract_snapshot, "spread_bps"),
            "slippage_bps": _find_value(contract_snapshot, "buy_slippage_bps", "slippage_bps"),
            "missing_inputs": chip.get("missing_inputs", []),
        }

    @staticmethod
    def _missing_input_penalties(missing_inputs: list[str]) -> list[dict[str, Any]]:
        penalties: list[dict[str, Any]] = []
        joined = " ".join(missing_inputs).lower()
        rules = [
            ("OI", ("oi", "open_interest"), 70, "缺少持仓量数据，衍生品确认分上限降至 70。"),
            ("CVD/Delta", ("cvd", "delta"), 65, "缺少主动买卖流数据，微观结构确认分上限降至 65。"),
            (
                "depth/spread/slippage",
                ("depth", "spread", "slippage"),
                60,
                "缺少盘口深度、价差或滑点数据，执行质量上限降至 60。",
            ),
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
            return structure.model_dump(mode="json")
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
