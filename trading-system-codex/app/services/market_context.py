from __future__ import annotations

from dataclasses import dataclass
from datetime import UTC, datetime
from typing import Any

from app.cache.shared_query_cache import shared_query_cache
from app.core.config import settings
from app.core.timeframes import normalize_instrument_id, normalize_timeframe_for_cache
from app.repositories.market_repository import MarketRepository
from app.services.btc_derivatives.live_service import btc_derivatives_live_service
from app.services.cache_registry import market_context_cache_key
from app.services.chip_structure import ChipStructureService
from app.services.macro_overview import MacroOverviewService
from app.services.onchain.feature_engine import OnchainFeatureEngine


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
            chip = await ChipStructureService(self.repository).analyze(instrument_id, timeframe)
            dependencies["chip_structure"] = self._dependency_meta(
                "chip_structure",
                cache_state="fresh",
                source_updated_at=now,
            )
            sources.append("chip_structure")
            macro = await MacroOverviewService(self.repository).build_overview()
            macro_payload = macro.model_dump(mode="json")
            dependencies["macro"] = self._dependency_meta(
                "macro",
                cache_state="fresh" if macro_payload else "missing",
                source_updated_at=self._parse_ts(
                    macro_payload.get("generated_at")
                    or macro_payload.get("snapshot_at")
                    or macro_payload.get("source_updated_at")
                )
                or now,
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
            onchain_read = await OnchainFeatureEngine(self.repository).build(now=now)
            dependencies["onchain"] = onchain_read.dependency
            sources.append("onchain")
            cache_meta = self._cache_meta(sources, dependencies)
            return {
                "instrument_id": instrument_id,
                "timeframe": timeframe,
                "market_data": {
                    "current_price": chip.get("components", {}).get("latest_close"),
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
                "indicator_features": {},
                "vwap_features": {},
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

    @staticmethod
    def _dependency_meta(
        source_page: str,
        *,
        cache_state: str,
        source_updated_at: datetime | None,
    ) -> dict[str, Any]:
        now = datetime.now(UTC)
        age_seconds = (
            max(0, int((now - source_updated_at).total_seconds()))
            if source_updated_at is not None
            else None
        )
        freshness_state = "fresh" if cache_state in {"fresh", "ready", "live"} else cache_state
        return {
            "source_page": source_page,
            "cache_state": "fresh" if cache_state == "live" else cache_state,
            "freshness_state": freshness_state,
            "source_updated_at": source_updated_at.isoformat() if source_updated_at else None,
            "source_age_seconds": age_seconds,
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
