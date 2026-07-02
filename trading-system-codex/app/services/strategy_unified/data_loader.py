# ruff: noqa: E501
from __future__ import annotations

from typing import Any, Mapping

from app.core.timeframes import normalize_instrument_id, normalize_timeframe_for_cache
from app.repositories.market_repository import MarketRepository
from app.services.market_context import MarketContextBuilder
from app.services.strategy_signal.service import StrategySignalService

from .contracts import TIMEFRAME_SPECS, first_float, get_value, nested, to_float, uniq


class UnifiedDataLoader:
    def __init__(self, repository: MarketRepository) -> None:
        self.repository = repository
        self.context_builder = MarketContextBuilder(repository)
        self.strategy_service = StrategySignalService(repository)

    async def load(self, instrument_id: str, *, force: bool = False) -> dict[str, Any]:
        instrument = normalize_instrument_id(instrument_id)
        contexts: dict[str, Any] = {}
        bundles: dict[str, dict[str, Any]] = {}
        resolved_states: list[str] = []

        for spec in TIMEFRAME_SPECS:
            cache_tf = normalize_timeframe_for_cache(spec.cache)
            try:
                contexts[spec.logical] = await self.context_builder.get_context(
                    instrument,
                    cache_tf,
                    cache_only=not force,
                )
            except Exception as exc:
                contexts[spec.logical] = {
                    "timeframe": cache_tf,
                    "error": str(exc),
                    "cache_meta": {"cache_state": "missing"},
                }

            bundle = await self._load_bundle(
                instrument,
                cache_tf,
                contexts[spec.logical],
                force=force,
            )
            bundles[spec.logical] = bundle
            resolved_states.append(str(bundle.get("cache_state") or bundle.get("status") or "unknown"))

        return {
            "instrument_id": instrument,
            "contexts": contexts,
            "bundles": bundles,
            "refresh_state": self._refresh_state(force, resolved_states),
            "refresh_limitations": self._refresh_limitations(force, resolved_states),
        }

    async def _load_bundle(
        self,
        instrument: str,
        timeframe: str,
        context: Any,
        *,
        force: bool,
    ) -> dict[str, Any]:
        try:
            cached = await self.strategy_service.get_bundle(
                instrument,
                timeframe,
                enqueue_refresh=not force,
            )
        except Exception as exc:
            cached = self._missing_bundle(instrument, timeframe, error=str(exc))

        if not force and not self._bundle_requires_compute(cached):
            return cached

        try:
            if hasattr(self.strategy_service, "build_bundle_uncached"):
                computed = await self.strategy_service.build_bundle_uncached(
                    instrument,
                    timeframe,
                )
                return self._mark_computed(computed, state="computed")
        except Exception as exc:
            if not self._bundle_requires_compute(cached):
                return cached
            fallback = self._context_fallback_bundle(
                instrument,
                timeframe,
                context,
                source_error=str(exc),
            )
            if fallback is not None:
                return fallback
            cached = dict(cached)
            cached.setdefault("compute_error", str(exc))
            return cached

        fallback = self._context_fallback_bundle(instrument, timeframe, context)
        return fallback if fallback is not None else cached

    @staticmethod
    def _bundle_requires_compute(bundle: Mapping[str, Any]) -> bool:
        status = str(bundle.get("status") or "").lower()
        cache_state = str(bundle.get("cache_state") or "").lower()
        freshness_state = str(bundle.get("freshness_state") or "").lower()
        decision = bundle.get("decision")
        missing_state = {"", "missing", "error", "updating", "stale", "expired"}
        return (
            status in missing_state
            or cache_state in missing_state
            or freshness_state in {"missing", "error", "expired"}
            or not isinstance(decision, Mapping)
            or not decision
        )

    @staticmethod
    def _mark_computed(bundle: Mapping[str, Any], *, state: str) -> dict[str, Any]:
        payload = dict(bundle)
        payload["status"] = "ready"
        payload["cache_state"] = state
        payload["freshness_state"] = payload.get("freshness_state") or "fresh"
        payload["refresh_enqueued"] = False
        payload["source_modules"] = uniq([*(payload.get("source_modules") or []), "StrategySignalService"])
        return payload

    @staticmethod
    def _missing_bundle(instrument: str, timeframe: str, *, error: str | None = None) -> dict[str, Any]:
        payload = {
            "instrument_id": instrument,
            "timeframe": timeframe,
            "status": "missing",
            "cache_state": "missing",
            "freshness_state": "missing",
            "decision": {},
        }
        if error:
            payload["error"] = error
        return payload

    def _context_fallback_bundle(
        self,
        instrument: str,
        timeframe: str,
        context: Any,
        *,
        source_error: str | None = None,
    ) -> dict[str, Any] | None:
        structure = get_value(context, "structure_features") or {}
        indicators = get_value(context, "indicator_features") or {}
        execution = get_value(context, "execution_features") or {}
        macro = get_value(context, "macro_features") or {}
        long_score = first_float(
            nested(structure, "long_score"),
            nested(indicators, "long_score"),
            nested(execution, "long_score"),
        )
        short_score = first_float(
            nested(structure, "short_score"),
            nested(indicators, "short_score"),
            nested(execution, "short_score"),
        )
        direction = str(
            nested(structure, "direction")
            or nested(indicators, "direction")
            or nested(structure, "bias")
            or nested(indicators, "bias")
            or ""
        ).upper()
        if long_score is None and short_score is None and not direction:
            inferred = self._infer_scores_from_structure(structure)
            if inferred is None:
                inferred = self._infer_scores_from_context(timeframe, macro, execution)
            if inferred is not None:
                direction, long_score, short_score, confidence_hint = inferred
            else:
                confidence_hint = None
        else:
            confidence_hint = None
        if long_score is None and short_score is None and not direction:
            return None
        if long_score is None:
            long_score = 64.0 if direction == "LONG" else 38.0 if direction == "SHORT" else 50.0
        if short_score is None:
            short_score = 64.0 if direction == "SHORT" else 38.0 if direction == "LONG" else 50.0
        confidence = first_float(
            nested(structure, "confidence"),
            nested(indicators, "confidence"),
            confidence_hint,
            nested(execution, "execution_score"),
            52,
        )
        support = first_float(nested(structure, "key_support"), nested(structure, "support"))
        resistance = first_float(nested(structure, "key_resistance"), nested(structure, "resistance"))
        state = str(
            nested(structure, "structure_state")
            or nested(structure, "state")
            or nested(structure, "regime")
            or ("CONTEXT_" + direction if direction else "CONTEXT_READY")
        )
        plan_direction = "long" if to_float(long_score) >= to_float(short_score) else "short"
        decision = {
            "strategy_state": state,
            "strategy_bias": plan_direction,
            "long_score": round(to_float(long_score), 2),
            "short_score": round(to_float(short_score), 2),
            "neutral_score": max(0, round(100 - max(to_float(long_score), to_float(short_score)), 2)),
            "direction_confidence": round(to_float(confidence), 2),
            "confidence_score": round(to_float(confidence), 2),
            "primary_strategy": {
                "direction": plan_direction,
                "entry_zone": [value for value in (support, resistance) if value is not None],
                "support": support,
                "resistance": resistance,
                "entry_condition": "market context fallback",
                "strategy_logic": "Unified strategy used MarketContextBuilder because legacy strategy bundle was unavailable.",
            },
            "explain": [
                "Market context fallback supplied usable structure scores.",
                f"{timeframe} context state={state}",
            ],
            "source_modules": ["MarketContextBuilder"],
        }
        payload = {
            "instrument_id": instrument,
            "timeframe": timeframe,
            "status": "ready",
            "cache_state": "context_fallback",
            "freshness_state": str(
                nested(context, "cache_meta", "freshness_state")
                or nested(context, "cache_meta", "cache_state")
                or "fresh"
            ),
            "current_price": first_float(
                get_value(context, "current_price"),
                nested(context, "market_data", "current_price"),
                nested(context, "market_data", "close"),
            ),
            "decision": decision,
            "source_modules": ["MarketContextBuilder"],
            "refresh_enqueued": False,
        }
        if source_error:
            payload["legacy_compute_error"] = source_error
        return payload

    @staticmethod
    def _infer_scores_from_structure(structure: Any) -> tuple[str, float, float, float] | None:
        structure_score = first_float(
            nested(structure, "overall_score"),
            nested(structure, "score"),
        )
        if structure_score is None:
            return None
        bias = str(nested(structure, "overall_bias") or nested(structure, "dominant_side") or "").lower()
        confidence_raw = first_float(
            nested(structure, "overall_confidence"),
            nested(structure, "confidence"),
            0.55,
        )
        confidence = confidence_raw * 100 if confidence_raw <= 1.0 else confidence_raw
        if abs(structure_score) < 0.12 or bias in {"uncertain", "neutral", "balance"}:
            long_score = 50 + max(0.0, structure_score) * 40
            short_score = 50 + max(0.0, -structure_score) * 40
            return ("NEUTRAL", round(long_score, 2), round(short_score, 2), min(65.0, confidence))
        if structure_score > 0 or bias == "bullish":
            return ("LONG", round(52 + abs(structure_score) * 36, 2), round(48 - abs(structure_score) * 24, 2), min(72.0, confidence))
        return ("SHORT", round(48 - abs(structure_score) * 24, 2), round(52 + abs(structure_score) * 36, 2), min(72.0, confidence))

    @staticmethod
    def _infer_scores_from_context(
        timeframe: str,
        macro: Any,
        execution: Any,
    ) -> tuple[str, float, float, float] | None:
        macro_score = first_float(nested(macro, "total_score"), nested(macro, "score"))
        macro_bias = str(nested(macro, "operation_bias") or nested(macro, "regime_key") or "").lower()
        if timeframe in {"30d", "1w"} and macro_score is not None:
            if macro_score >= 58 or macro_bias in {"bullish", "risk_on", "supportive"}:
                return ("LONG", min(72.0, max(58.0, macro_score)), max(28.0, 100.0 - macro_score), min(68.0, macro_score))
            if macro_score <= 42 or macro_bias in {"bearish", "risk_off", "defensive"}:
                return ("SHORT", max(28.0, macro_score), min(72.0, 100.0 - macro_score), min(68.0, 100.0 - macro_score))
        execution_score = first_float(nested(execution, "execution_score"))
        if timeframe == "15m" and execution_score is not None:
            if execution_score >= 65:
                return ("LONG", min(66.0, execution_score), 42.0, min(60.0, execution_score))
            if execution_score <= 35:
                return ("SHORT", 42.0, min(66.0, 100.0 - execution_score), min(60.0, 100.0 - execution_score))
            return ("NEUTRAL", 50.0, 50.0, min(52.0, max(40.0, execution_score)))
        return None

    @staticmethod
    def _refresh_state(force: bool, states: list[str]) -> str:
        if force:
            return "requested"
        if any(state in {"computed", "refreshed"} for state in states):
            return "computed"
        if any(state == "context_fallback" for state in states):
            return "computed_with_context_fallback"
        return "cache_only"

    @staticmethod
    def _refresh_limitations(force: bool, states: list[str]) -> list[str]:
        limitations: list[str] = []
        if force:
            limitations.append("force=true requested six-timeframe strategy refresh before synthesis.")
        else:
            limitations.append("Unified strategy reads cache first and computes missing strategy bundles synchronously.")
        if any(state == "context_fallback" for state in states):
            limitations.append("Some timeframes used MarketContextBuilder fallback because legacy strategy bundles were unavailable.")
        if any(state in {"missing", "error", "updating"} for state in states):
            limitations.append("Some timeframes still have missing or errored strategy inputs and are treated as degraded.")
        return limitations
