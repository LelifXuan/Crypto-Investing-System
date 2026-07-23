from __future__ import annotations

import logging
from dataclasses import dataclass
from datetime import UTC, datetime, timedelta
from typing import Any

from app.cache.shared_query_cache import shared_query_cache
from app.core.config import settings
from app.core.timeframes import normalize_instrument_id, normalize_timeframe_for_cache
from app.repositories.market_repository import MarketRepository
from app.services.btc_derivatives.live_service import btc_derivatives_live_service
from app.services.cache_registry import (
    analysis_cache_key,
    cache_status,
    market_context_cache_key,
)
from app.services.chip_structure import ChipStructureService
from app.services.macro_overview import MacroOverviewService
from app.services.onchain.feature_engine import OnchainFeatureEngine
from app.services.strategy_unified.contracts import payload_hash
from app.services.strategy_unified.trade_decision import _next_close_iso

logger = logging.getLogger(__name__)


@dataclass(frozen=True)
class MarketContextSnapshot:
    instrument_id: str
    timeframe: str
    market_data: dict[str, Any]
    indicator_features: dict[str, Any]
    vwap_features: dict[str, Any]
    structure_features: dict[str, Any]
    derivatives_features: dict[str, Any]
    macro_features: dict[str, Any]
    event_features: dict[str, Any]
    onchain_features: dict[str, Any]
    execution_features: dict[str, Any]
    chip_structure: dict[str, Any]
    macro_overview: dict[str, Any]
    chip_features: dict[str, Any]
    data_quality: dict[str, Any]
    freshness_breakdown: dict[str, Any]
    cache_meta: dict[str, Any]


MarketContext = MarketContextSnapshot


class MarketContextBuilder:
    """Light request-level context used by decision services.

    It deliberately reuses the existing page/cache services instead of adding
    a new datastore. More consumers can attach to this context incrementally.
    """

    def __init__(self, repository: MarketRepository) -> None:
        self.repository = repository

    async def get_context(
        self,
        instrument_id: str,
        timeframe: str,
        *,
        cache_only: bool = True,
    ) -> MarketContextSnapshot:
        del cache_only
        instrument_id = normalize_instrument_id(instrument_id)
        timeframe = normalize_timeframe_for_cache(timeframe)
        cache_key = market_context_cache_key(instrument_id, timeframe)
        ttl = settings.shared_query_cache_seconds

        async def producer() -> dict[str, Any]:
            now = datetime.now(UTC)
            dependencies: dict[str, dict[str, Any]] = {}
            sources: list[str] = []
            indicator_features: dict[str, Any] = {}
            vwap_features: dict[str, Any] = {}
            analysis_mark: dict[str, Any] = {}
            analysis_limits = {
                "1h": 720,
                "4h": 480,
                "1d": 420,
                "1w": 260,
                "30d": 180,
            }
            analysis_limit = analysis_limits.get(timeframe, 420)
            try:
                analysis_cache = await self.repository.get_page_snapshot_cache(
                    analysis_cache_key(instrument_id, timeframe, analysis_limit)
                )
                analysis_payload = (
                    dict(analysis_cache.payload_json or {}) if analysis_cache else {}
                )
                analysis_mark = dict(analysis_payload.get("mark") or {})
                indicator_features, vwap_features = self._technical_features(
                    analysis_payload
                )
                analysis_ts = self._parse_ts(
                    getattr(analysis_cache, "source_updated_at", None)
                    or getattr(analysis_cache, "data_ts", None)
                )
                dependencies["technical_indicators"] = self._dependency_meta(
                    "indicators",
                    cache_state=(
                        cache_status(analysis_cache)
                        if analysis_cache is not None and indicator_features
                        else "missing"
                    ),
                    source_updated_at=analysis_ts,
                    timeframe=timeframe,
                    snapshot_payload=analysis_payload,
                )
            except Exception as exc:
                logger.warning("market_context_technical_cache_failed: %s", exc)
                dependencies["technical_indicators"] = self._dependency_meta(
                    "indicators", cache_state="missing", source_updated_at=None
                )
            sources.append("technical_indicators")
            chip: dict[str, Any] = {
                "instrument_id": instrument_id,
                "timeframe": timeframe,
                "state": "missing",
                "state_label": "筹码结构暂时不可用",
                "state_reason": "上游数据缺失，策略将依赖其他维度。",
                "evidence_quality": "missing",
                "direction_score": 0.0,
                "execution_score": 0.0,
                "components": {},
                "evidence": [],
                "missing_inputs": ["chip_structure"],
            }
            try:
                chip = await ChipStructureService(self.repository).analyze(instrument_id, timeframe)
            except Exception as exc:
                dependencies["chip_structure"] = self._dependency_meta(
                    "chip_structure",
                    cache_state="missing",
                    source_updated_at=None,
                )
                logger.warning("chip_structure_analyze_failed: %s", exc, exc_info=True)
            else:
                dependencies["chip_structure"] = self._dependency_meta(
                    "chip_structure",
                    cache_state="fresh",
                    source_updated_at=now,
                    timeframe=timeframe,
                    snapshot_payload=chip,
                )
            sources.append("chip_structure")
            macro_payload: dict[str, Any] = {}
            try:
                macro = await MacroOverviewService(self.repository).build_overview()
                macro_payload = macro.model_dump(mode="json")
            except Exception as exc:
                logger.warning("macro_overview_build_failed: %s", exc, exc_info=True)
                macro_payload = {"regime_key": None, "operation_bias": None, "total_score": None}
            macro_ts = self._parse_ts(
                macro_payload.get("generated_at")
                or macro_payload.get("snapshot_at")
                or macro_payload.get("source_updated_at")
            ) or now
            dependencies["macro"] = self._dependency_meta(
                "macro",
                cache_state="fresh" if macro_payload.get("regime_key") else "missing",
                source_updated_at=macro_ts,
                timeframe="1d",
                snapshot_payload=macro_payload,
            )
            sources.append("macro")
            derivatives_features: dict[str, Any] = {
                "key_levels_axis": {
                    "status": "data_insufficient",
                    "summary": "BTC 衍生品关键价位缓存暂不可用。",
                }
            }
            try:
                derivatives_dashboard = await btc_derivatives_live_service.dashboard(force=False)
                derivatives_ts = self._parse_ts(
                    getattr(derivatives_dashboard, "data_timestamp", None)
                )
                joint = dict(
                    getattr(derivatives_dashboard, "joint_analysis", None) or {}
                )
                options = dict(getattr(derivatives_dashboard, "options", None) or {})
                walls = dict(options.get("walls") or {})
                max_pain = dict(options.get("max_pain") or {})
                hedge = dict(getattr(derivatives_dashboard, "hedge_context", None) or {})
                derivatives_features = {
                    "joint_analysis": joint,
                    "options_metrics": dict(options.get("metrics", {}) or {}),
                    "key_levels_axis": dict(
                        joint.get("derivatives_axes", {}).get("key_levels_axis", {})
                    ),
                    "snapshot_state": derivatives_dashboard.snapshot_state,
                    "data_timestamp": derivatives_dashboard.data_timestamp,
                    "funding_state": joint.get("funding_state"),
                    "oi_state": joint.get("price_oi_state"),
                    "skew_state": joint.get("skew_state"),
                    "basis_state": joint.get("basis_state"),
                    "hedge_cost_state": joint.get("hedge_cost_state"),
                    "wall_movement": joint.get("wall_movement"),
                    "max_pain_movement": joint.get("max_pain_movement"),
                    "data_quality_status": joint.get("data_quality_status"),
                    "call_wall_strike": walls.get("call_wall_strike"),
                    "put_wall_strike": walls.get("put_wall_strike"),
                    "max_pain_strike": max_pain.get("strike"),
                    "spot_price": hedge.get("spot_price"),
                    "skew_25d": dict(options.get("metrics", {}).get("skew_25d", {}) or {}),
                    "put_call_ratios": dict(
                        options.get("metrics", {}).get("put_call_ratios", {}) or {}
                    ),
                    "protection_cost_regime": dict(
                        joint.get("protection_cost_regime", {}) or {}
                    ),
                }
                derivatives_state = (
                    "fresh"
                    if getattr(derivatives_dashboard, "snapshot_state", "") == "live"
                    else getattr(derivatives_dashboard, "snapshot_state", None) or "degraded"
                )
                dependencies["btc_derivatives"] = self._dependency_meta(
                    "btc_derivatives",
                    cache_state=derivatives_state,
                    source_updated_at=derivatives_ts,
                    timeframe="30m",
                    snapshot_payload=derivatives_features,
                )
                sources.append("btc_derivatives")
            except Exception:
                derivatives_features = {
                    "key_levels_axis": {
                        "status": "data_insufficient",
                        "summary": "BTC 衍生品关键价位缓存暂不可用。",
                    },
                    "funding_state": None,
                    "oi_state": None,
                    "skew_state": None,
                    "basis_state": None,
                    "hedge_cost_state": None,
                    "wall_movement": None,
                    "max_pain_movement": None,
                    "data_quality_status": "missing",
                    "call_wall_strike": None,
                    "put_wall_strike": None,
                    "max_pain_strike": None,
                    "spot_price": None,
                    "skew_25d": {},
                    "put_call_ratios": {},
                }
                dependencies["btc_derivatives"] = self._dependency_meta(
                    "btc_derivatives",
                    cache_state="missing",
                    source_updated_at=None,
                )
                sources.append("btc_derivatives")
            try:
                onchain_read = await OnchainFeatureEngine(self.repository).build(now=now)
            except Exception as exc:
                logger.warning("onchain_feature_build_failed: %s", exc, exc_info=True)
                from app.services.onchain.feature_engine import OnchainFeatureRead
                onchain_read = OnchainFeatureRead(
                    features={"metrics": {}, "data_status": "missing"},
                    dependency={
                        "source_page": "onchain",
                        "cache_state": "missing",
                        "freshness_state": "missing",
                        "source_updated_at": None,
                        "source_age_seconds": None,
                    },
                )
            dependencies["onchain"] = onchain_read.dependency
            sources.append("onchain")
            cache_meta = self._cache_meta(sources, dependencies)
            return {
                "instrument_id": instrument_id,
                "timeframe": timeframe,
                "market_data": {
                    "current_price": (
                        analysis_mark.get("mark_price")
                        or chip.get("components", {}).get("latest_close")
                    ),
                    "price_as_of": analysis_mark.get("ts_event"),
                    "price_source": analysis_mark.get("source") or "analysis_bundle",
                    "price_change_pct": chip.get("components", {}).get("price_change_pct"),
                    "execution_score": chip.get("execution_score"),
                    "execution_label": chip.get("execution_label"),
                    "direction_score": chip.get("direction_score"),
                    "direction_label": chip.get("direction_label"),
                    "weekly_context": chip.get("weekly_context"),
                    "daily_bias": chip.get("daily_bias"),
                    "primary_regime": chip.get("primary_regime"),
                    "primary_regime_label": chip.get("primary_regime_label"),
                },
                "indicator_features": indicator_features,
                "vwap_features": vwap_features,
                "structure_features": chip.get("components", {}).get("structure_overall") or {},
                "derivatives_features": derivatives_features,
                "macro_features": {
                    "regime_key": macro_payload.get("regime_key"),
                    "operation_bias": macro_payload.get("operation_bias"),
                    "total_score": macro_payload.get("total_score"),
                },
                "event_features": {
                    "event_window_state": macro_payload.get("event_window_state"),
                    "event_window_status": macro_payload.get("event_window_status"),
                    "next_check_time": _next_close_iso(datetime.now(UTC), timeframe),
                },
                "onchain_features": {
                    **dict(onchain_read.features),
                    "metrics_flat": {
                        key: payload.get("value")
                        for key, payload in (
                            onchain_read.features.get("metrics") or {}
                        ).items()
                        if isinstance(payload, dict)
                    },
                },
                "execution_features": {
                    "execution_score": chip.get("execution_score"),
                    "execution_label": chip.get("execution_label"),
                },
                "chip_structure": chip,
                "macro_overview": macro_payload,
                "chip_features": {
                    "evidence_quality": chip.get("evidence_quality"),
                    "evidence_quality_label": chip.get("evidence_quality_label"),
                    "primary_regime": chip.get("primary_regime"),
                    "primary_regime_label": chip.get("primary_regime_label"),
                    "secondary_regime": chip.get("secondary_regime"),
                    "weekly_context": chip.get("weekly_context"),
                    "daily_bias": chip.get("daily_bias"),
                    "h4_structure": chip.get("h4_structure"),
                    "h1_confirmation": chip.get("h1_confirmation"),
                    "execution_score": chip.get("execution_score"),
                    "execution_label": chip.get("execution_label"),
                    "risk_score": chip.get("risk_score"),
                    "risk_label": chip.get("risk_label"),
                    "missing_inputs": list(chip.get("missing_inputs") or []),
                    "evidence": list(chip.get("evidence") or []),
                    "components": dict(chip.get("components") or {}),
                    "timeframes": list(chip.get("timeframes") or []),
                    "state": chip.get("state"),
                    "state_label": chip.get("state_label"),
                    "state_reason": chip.get("state_reason"),
                },
                "data_quality": {
                    "chip_evidence_quality": chip.get("evidence_quality"),
                    "macro_confidence": macro_payload.get("confidence"),
                    "dependencies": dependencies,
                },
                "freshness_breakdown": {
                    name: {
                        "cache_state": meta.get("cache_state"),
                        "freshness_state": meta.get("freshness_state"),
                        "source_updated_at": meta.get("source_updated_at"),
                        "source_age_seconds": meta.get("source_age_seconds"),
                    }
                    for name, meta in dependencies.items()
                },
                "cache_meta": cache_meta,
            }

        payload = await shared_query_cache.get_or_set(cache_key, ttl, producer)
        return MarketContextSnapshot(
            instrument_id=str(payload.get("instrument_id") or instrument_id),
            timeframe=str(payload.get("timeframe") or timeframe),
            market_data=dict(payload.get("market_data") or {}),
            indicator_features=dict(payload.get("indicator_features") or {}),
            vwap_features=dict(payload.get("vwap_features") or {}),
            structure_features=dict(payload.get("structure_features") or {}),
            derivatives_features=dict(payload.get("derivatives_features") or {}),
            macro_features=dict(payload.get("macro_features") or {}),
            event_features=dict(payload.get("event_features") or {}),
            onchain_features=dict(payload.get("onchain_features") or {}),
            execution_features=dict(payload.get("execution_features") or {}),
            chip_structure=dict(payload.get("chip_structure") or {}),
            macro_overview=dict(payload.get("macro_overview") or {}),
            chip_features=dict(payload.get("chip_features") or {}),
            data_quality=dict(payload.get("data_quality") or {}),
            freshness_breakdown=dict(payload.get("freshness_breakdown") or {}),
            cache_meta=dict(payload.get("cache_meta") or {}),
        )

    @staticmethod
    def _parse_ts(value: Any) -> datetime | None:
        if value is None:
            return None
        if isinstance(value, datetime):
            return value if value.tzinfo else value.replace(tzinfo=UTC)
        try:
            parsed = datetime.fromisoformat(str(value).replace("Z", "+00:00"))
            return parsed if parsed.tzinfo else parsed.replace(tzinfo=UTC)
        except ValueError:
            return None

    @classmethod
    def _technical_features(
        cls, payload: dict[str, Any]
    ) -> tuple[dict[str, Any], dict[str, Any]]:
        core = dict(payload.get("core_indicator_series") or {})
        secondary = dict(payload.get("secondary_indicator_series") or {})
        def latest(source: dict[str, Any], *keys: str) -> float | None:
            return cls._latest_series_value(source, *keys)
        features = {
            "ema_20": latest(core, "ema_20"),
            "ema_50": latest(core, "ema_50"),
            "ema_200": latest(core, "ema_200"),
            "rsi_14": latest(core, "rsi_14"),
            "macd_hist": latest(core, "macd_hist"),
            "atr_14": latest(core, "atr_14"),
            "natr_14": latest(core, "natr_14"),
            "adx_14": latest(secondary, "adx_14"),
            "bb_width": latest(secondary, "bbands_width", "boll_width"),
            "percent_b": latest(secondary, "percent_b"),
            "obv_slope": latest(secondary, "obv_slope"),
            "rsi_14_percentile": cls._series_percentile(core, "rsi_14"),
            "macd_hist_percentile": cls._series_percentile(core, "macd_hist"),
            "bb_width_percentile": cls._series_percentile(
                secondary, "bbands_width", "boll_width"
            ),
            "natr_14_percentile": cls._series_percentile(core, "natr_14"),
            "rsi_14_change": cls._series_change(core, "rsi_14"),
            "macd_hist_change": cls._series_change(core, "macd_hist"),
            "history_points": max(
                len(cls._series_values(core, "rsi_14")),
                len(cls._series_values(core, "macd_hist")),
                len(cls._series_values(secondary, "bbands_width", "boll_width")),
            ),
        }
        vwap = {
            "vwap_short": latest(secondary, "vwap_short", "vwap_50"),
            "vwap_long": latest(secondary, "vwap_long", "vwap_100"),
            "price_vs_vwap_short_pct": latest(
                secondary, "price_vs_vwap_short_pct"
            ),
            "price_vs_vwap_long_pct": latest(
                secondary, "price_vs_vwap_long_pct"
            ),
            "vwap_spread_pct": latest(secondary, "vwap_spread_pct"),
            "vwap_slope_short_10": latest(
                secondary, "vwap_slope_short_10", "vwap_slope_10"
            ),
            "vwap_slope_long_10": latest(secondary, "vwap_slope_long_10"),
        }
        return (
            {key: value for key, value in features.items() if value is not None},
            {key: value for key, value in vwap.items() if value is not None},
        )

    @staticmethod
    def _latest_series_value(source: dict[str, Any], *keys: str) -> Any:
        for key in keys:
            value = source.get(key)
            values = value.get("values") if isinstance(value, dict) else value
            if isinstance(values, list):
                for item in reversed(values):
                    if item is not None:
                        return item
            elif values is not None:
                return values
        return None

    @staticmethod
    def _series_values(source: dict[str, Any], *keys: str) -> list[float]:
        for key in keys:
            raw = source.get(key)
            values = raw.get("values") if isinstance(raw, dict) else raw
            if isinstance(values, list):
                return [
                    float(item)
                    for item in values
                    if isinstance(item, (int, float))
                ]
        return []

    @classmethod
    def _series_percentile(cls, source: dict[str, Any], *keys: str) -> float | None:
        values = cls._series_values(source, *keys)
        if len(values) < 20:
            return None
        latest = values[-1]
        less = sum(value < latest for value in values)
        equal = sum(value == latest for value in values)
        return round((less + 0.5 * equal) / len(values), 6)

    @classmethod
    def _series_change(cls, source: dict[str, Any], *keys: str) -> float | None:
        values = cls._series_values(source, *keys)
        if len(values) < 2:
            return None
        return round(values[-1] - values[-2], 8)

    @staticmethod
    def _dependency_meta(
        source_page: str,
        *,
        cache_state: str,
        source_updated_at: datetime | None,
        timeframe: str | None = None,
        snapshot_payload: dict[str, Any] | None = None,
    ) -> dict[str, Any]:
        now = datetime.now(UTC)
        age_seconds = (
            max(0, int((now - source_updated_at).total_seconds()))
            if source_updated_at is not None
            else None
        )
        freshness_state = "fresh" if cache_state in {"fresh", "ready", "live"} else cache_state
        duration = {
            "15m": timedelta(minutes=15),
            "30m": timedelta(minutes=30),
            "1h": timedelta(hours=1),
            "4h": timedelta(hours=4),
            "1d": timedelta(days=1),
            "1w": timedelta(days=7),
            "30d": timedelta(days=30),
        }.get(str(timeframe or ""), timedelta(minutes=30))
        grace = {
            "15m": timedelta(minutes=3),
            "30m": timedelta(minutes=5),
            "1h": timedelta(minutes=10),
            "4h": timedelta(minutes=30),
            "1d": timedelta(hours=2),
            "1w": timedelta(hours=12),
            "30d": timedelta(days=2),
        }.get(str(timeframe or ""), timedelta(minutes=5))
        expires_at = source_updated_at + duration + grace if source_updated_at else None
        if expires_at is not None and expires_at < now:
            freshness_state = "stale" if cache_state != "missing" else "missing"
        identity = {
            "source_page": source_page,
            "timeframe": timeframe,
            "source_updated_at": source_updated_at.isoformat() if source_updated_at else None,
            "payload": snapshot_payload or {},
        }
        return {
            "source_page": source_page,
            "cache_state": "fresh" if cache_state == "live" else cache_state,
            "freshness_state": freshness_state,
            "source_updated_at": source_updated_at.isoformat() if source_updated_at else None,
            "source_age_seconds": age_seconds,
            "expires_at": expires_at.isoformat() if expires_at else None,
            "snapshot_id": f"{source_page}:{payload_hash(identity)[:16]}",
        }

    @staticmethod
    def _cache_meta(sources: list[str], dependencies: dict[str, dict[str, Any]]) -> dict[str, Any]:
        states = [item.get("cache_state") for item in dependencies.values()]
        if not states:
            cache_state = "missing"
        elif all(state in {"fresh", "ready"} for state in states):
            cache_state = "fresh"
        elif any(state == "missing" for state in states):
            cache_state = "degraded"
        else:
            cache_state = "usable_stale"
        ages = [
            item.get("source_age_seconds")
            for item in dependencies.values()
            if item.get("source_age_seconds") is not None
        ]
        return {
            "source": "market_context_builder",
            "cache_key_version": "v1",
            "sources": sources,
            "cache_state": cache_state,
            "freshness_state": "fresh" if cache_state == "fresh" else cache_state,
            "source_age_seconds": max(ages) if ages else None,
            "dependencies": dependencies,
        }
