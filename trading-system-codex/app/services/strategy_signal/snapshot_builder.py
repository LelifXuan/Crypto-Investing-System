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
        # Only mark the lower timeframe as missing when a trigger timeframe is
        # configured AND we have evidence the data is actually short. The
        # data quality score already aggregates analysis/alerts/monitoring
        # cache states, so a score below 60 implies the dependency is too
        # degraded to use the lower timeframe for execution triggers.
        lower_tf_missing = lower_tf_required and data_quality_score < 60
        ema20 = _num(indicators.get("ema_20"))
        ema20_prev = _num(indicators.get("ema_20_prev"), ema20)
        ema20_slope = ema20 - ema20_prev
        atr_pct = _num(indicators.get("natr_14")) or (atr / price * 100 if price else 0)
        atr_expansion_score = max(0, min(100, atr_pct * 12))
        volume_confirmation = max(0, min(100, 50 + _num(indicators.get("obv_slope")) * 80))
        missing_inputs = list(dict.fromkeys(derivatives.get("missing_inputs") or []))
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
                "mtf_trend_bullish": direction_metrics["bullish"],
                "mtf_trend_bearish": direction_metrics["bearish"],
                "bullish_structure": direction_metrics["bullish"],
                "bearish_structure": direction_metrics["bearish"],
                "range_structure": direction_metrics["range"],
                "regime_fit_long": direction_metrics["bullish"],
                "regime_fit_short": direction_metrics["bearish"],
                "bullish_momentum": 50 + max(0, rsi - 50) * 1.3 + max(0, macd - macd_prev) * 3,
                "bearish_momentum": 50 + max(0, 50 - rsi) * 1.3 + max(0, macd_prev - macd) * 3,
                "bullish_flow": 50 + max(0, cvd) * 20 + max(0, oi_change) * 250,
                "bearish_flow": 50 + max(0, -cvd) * 20 + max(0, -oi_change) * 250,
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
