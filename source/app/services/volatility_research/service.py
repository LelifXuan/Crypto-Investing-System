from __future__ import annotations

import hashlib
import json
from datetime import datetime, timedelta, timezone
from decimal import Decimal
from typing import Any

from app.db.models.market import (
    VolatilityFeatureObservation,
    VolatilityResearchSnapshot,
)
from app.repositories.market_repository import MarketRepository
from app.services.data_freshness import TIMEFRAME_SECONDS, normalize_timeframe
from app.services.volatility_research.estimators import (
    OhlcBar,
    atr_natr,
    bipower_and_jump_volatility,
    bollinger_bandwidth,
    empirical_percentile,
    ewma_volatility,
    range_volatility,
    realized_volatility,
    yang_zhang_volatility,
)
from app.services.volatility_research.registry import load_research_registry

UTC = timezone.utc
FORMULA_VERSION = "btc-native-vol-research-v1"


def _decimal_text(value: Decimal | None) -> str | None:
    return format(value, "f") if value is not None else None


def _status_block(reason: str) -> dict[str, Any]:
    return {"status": "data_insufficient", "missing_reason": reason}


def _feature_unit(key: str) -> str:
    if key == "atr_14":
        return "price"
    if key == "natr_14" or key.endswith("percentile"):
        return "percent"
    if key == "bollinger_bandwidth" or key.endswith("ratio"):
        return "decimal_ratio"
    return "annualized_decimal"


class VolatilityResearchService:
    """Builds research-only snapshots without affecting canonical decisions."""

    def __init__(self, repository: MarketRepository) -> None:
        self.repository = repository

    async def build_shadow_snapshot(
        self, instrument_id: str, timeframe: str, *, candle_limit: int = 1200
    ) -> VolatilityResearchSnapshot:
        normalized = normalize_timeframe(timeframe)
        bar_seconds = TIMEFRAME_SECONDS.get(normalized)
        if bar_seconds is None:
            raise ValueError(f"unsupported volatility research timeframe: {timeframe}")
        candles = await self.repository.list_candles(instrument_id, normalized, limit=candle_limit)
        now = datetime.now(UTC)
        candles = sorted(candles, key=lambda item: item.ts_open)
        # A complete OHLC value is not knowable at bar open.  Exclude the live
        # bar and timestamp every derived value at the estimated bar close.
        candles = [
            item
            for item in candles
            if (
                (item.ts_open.replace(tzinfo=UTC) if item.ts_open.tzinfo is None else item.ts_open)
                + timedelta(seconds=bar_seconds)
            )
            <= now
        ]
        if not candles:
            raise ValueError("no candles available for volatility research")
        latest = candles[-1]
        bar_open = latest.ts_open
        if bar_open.tzinfo is None:
            bar_open = bar_open.replace(tzinfo=UTC)
        event_time = bar_open + timedelta(seconds=bar_seconds)
        created_at = latest.created_at or event_time
        if created_at.tzinfo is None:
            created_at = created_at.replace(tzinfo=UTC)
        available_at = max(event_time, min(created_at, now))
        registry = load_research_registry()
        windows = registry["realized_volatility"]["evaluation_windows"]
        bars = [OhlcBar(item.open, item.high, item.low, item.close) for item in candles]
        feature_values: dict[str, tuple[Decimal | None, dict[str, Any]]] = {}

        for label, window in windows.items():
            subset = bars[-int(window):]
            params = {"window": int(window), "bar_seconds": bar_seconds, "annualization": "365d"}
            feature_values[f"rv_close_{label}"] = (
                realized_volatility(subset, bar_seconds), params
            )
            for decay in registry["realized_volatility"]["ewma_decay_candidates"]:
                decimal_decay = Decimal(decay)
                feature_values[f"rv_ewma_{label}_lambda_{decay}"] = (
                    ewma_volatility(subset, bar_seconds, decimal_decay),
                    {**params, "decay": decay},
                )
            for estimator in ("parkinson", "garman_klass", "rogers_satchell", "realized_range"):
                feature_values[f"rv_{estimator}_{label}"] = (
                    range_volatility(subset, bar_seconds, estimator), params
                )
            feature_values[f"rv_yang_zhang_{label}"] = (
                yang_zhang_volatility(subset, bar_seconds), params
            )
            bipower, jump = bipower_and_jump_volatility(subset, bar_seconds)
            feature_values[f"rv_bipower_{label}"] = (bipower, params)
            feature_values[f"rv_jump_{label}"] = (jump, params)

        closes = [item.close for item in bars]
        bb_history: list[Decimal] = []
        bb_window = int(registry["realized_volatility"]["bollinger_window"])
        for index in range(bb_window, len(closes) + 1):
            width = bollinger_bandwidth(closes[:index], bb_window)
            if width is not None:
                bb_history.append(width)
        bb_current = bb_history[-1] if bb_history else None
        bb_percentile = (
            empirical_percentile(bb_history, bb_current) if bb_current is not None else None
        )
        feature_values["bollinger_bandwidth"] = (
            bb_current,
            {"window": bb_window, "stddev_multiplier": "2"},
        )
        feature_values["bollinger_bandwidth_empirical_percentile"] = (
            bb_percentile,
            {"history_points": len(bb_history), "rank_method": "midrank"},
        )

        atr, natr = atr_natr(bars, 14)
        natr_history: list[Decimal] = []
        for index in range(15, len(bars) + 1):
            _, historical_natr = atr_natr(bars[:index], 14)
            if historical_natr is not None:
                natr_history.append(historical_natr)
        feature_values["atr_14"] = (atr, {"window": 14, "variant": "wilder"})
        feature_values["natr_14"] = (
            natr,
            {"window": 14, "formula": "atr/close*100", "variant": "wilder"},
        )
        feature_values["natr_14_empirical_percentile"] = (
            empirical_percentile(natr_history, natr) if natr is not None else None,
            {"history_points": len(natr_history), "rank_method": "midrank"},
        )

        short_rv = feature_values.get("rv_close_short", (None, {}))[0]
        long_rv = feature_values.get("rv_close_long", (None, {}))[0]
        feature_values["rv_short_long_ratio"] = (
            (
                short_rv / long_rv
                if short_rv is not None and long_rv not in {None, Decimal(0)}
                else None
            ),
            {"numerator": "rv_close_short", "denominator": "rv_close_long"},
        )

        digest_payload = {
            "instrument_id": instrument_id,
            "timeframe": normalized,
            "event_time": event_time.isoformat(),
            "formula_version": FORMULA_VERSION,
        }
        digest = hashlib.sha256(
            json.dumps(digest_payload, sort_keys=True).encode("utf-8")
        ).hexdigest()[:24]
        snapshot_id = f"vol-{digest}"
        observations: list[VolatilityFeatureObservation] = []
        serialized_features: dict[str, Any] = {}
        for key, (value, params) in sorted(feature_values.items()):
            parameter_set_id = hashlib.sha256(
                json.dumps(params, sort_keys=True).encode("utf-8")
            ).hexdigest()[:16]
            quality_status = "ok" if value is not None else "data_insufficient"
            serialized_features[key] = {
                "value": _decimal_text(value),
                "unit": _feature_unit(key),
                "quality_status": quality_status,
                "parameters": params,
            }
            observations.append(
                VolatilityFeatureObservation(
                    observation_id=f"vf-{hashlib.sha256(f'{snapshot_id}:{key}:{parameter_set_id}'.encode()).hexdigest()[:40]}",
                    snapshot_id=snapshot_id,
                    instrument_id=instrument_id,
                    timeframe=normalized,
                    feature_key=key,
                    parameter_set_id=parameter_set_id,
                    value_num=value,
                    unit=_feature_unit(key),
                    event_time=event_time,
                    available_at=available_at,
                    calculated_at=now,
                    formula_version=FORMULA_VERSION,
                    source=str(latest.source),
                    quality_status=quality_status,
                    missing_reason=None if value is not None else "insufficient_history",
                    parameters_json=params,
                )
            )

        valid_count = sum(1 for value, _ in feature_values.values() if value is not None)
        snapshot = VolatilityResearchSnapshot(
            snapshot_id=snapshot_id,
            instrument_id=instrument_id,
            timeframe=normalized,
            event_time=event_time,
            available_at=available_at,
            calculated_at=now,
            formula_version=FORMULA_VERSION,
            integration_status="shadow",
            price_volatility_json={
                "status": "ready" if valid_count else "data_insufficient",
                "features": serialized_features,
                "legacy_semantics": {
                    "vol_compression": "bb_width_to_mean_ratio_bucket_not_percentile",
                    "strategy_effect": "unchanged_shadow_only",
                },
            },
            options_expectations_json=_status_block("dvol_or_constant_maturity_iv_not_aligned"),
            tail_pricing_json=_status_block("delta_surface_history_not_available"),
            leverage_crowding_json=_status_block("point_in_time_oi_history_not_aligned"),
            liquidation_pressure_json=_status_block("verified_liquidation_history_not_available"),
            basis_funding_structure_json=_status_block("matched_basis_funding_history_not_aligned"),
            quality_json={
                "status": "research_only",
                "candle_count": len(candles),
                "valid_feature_count": valid_count,
                "total_feature_count": len(feature_values),
                "no_canonical_effect": True,
            },
            timestamp_contract_json={
                "event_time": event_time.isoformat(),
                "available_at": available_at.isoformat(),
                "decision_time": now.isoformat(),
                "valid": event_time <= available_at <= now,
                "bar_open": bar_open.isoformat(),
                "bar_close_estimate": event_time.isoformat(),
            },
        )
        await self.repository.append_volatility_research_snapshot(snapshot, observations)
        return snapshot

    async def latest_snapshot(
        self, instrument_id: str, timeframe: str
    ) -> VolatilityResearchSnapshot | None:
        return await self.repository.latest_volatility_research_snapshot(
            instrument_id, normalize_timeframe(timeframe)
        )
