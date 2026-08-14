from __future__ import annotations

import time
from datetime import datetime, timezone

from app.db.models.market import MarkPrice
from app.repositories.market_repository import MarketRepository
from app.schemas.market import AnalysisBundleRead, CandleRead, MarkPriceRead
from app.services.cache_registry import CACHE_SOURCE_VERSION, source_freshness
from app.services.contract_snapshot import ContractSnapshotService
from app.services.data_freshness import bar_close_freshness
from app.services.final_decision import FinalDecisionService
from app.services.indicator_matrix import IndicatorMatrixService
from app.services.indicator_monitoring import IndicatorMonitoringService
from app.services.market import MarketService
from app.services.market_data_bundle import MarketDataBundleService
from app.services.page_snapshot_cache import (
    analysis_cache_key,
    bundle_status_message,
    cache_status,
    expires_at_for_page,
)
from app.services.range_regime import RangeClassification, classify_range
from app.services.strategy_signal.config_loader import detect_asset_class, detect_mode

UTC = timezone.utc


def _extract_latest_adx(adx_series) -> float | None:
    """Pull the latest non-null ADX value from a series of numbers."""
    if not isinstance(adx_series, list) or not adx_series:
        return None
    for value in reversed(adx_series):
        try:
            numeric = float(value)
        except (TypeError, ValueError):
            continue
        return numeric
    return None


def _compute_payload_mode(payload: dict) -> tuple[str, str, RangeClassification]:
    """Derive ``mode`` / ``asset_class`` from a freshly built payload.

    Used by both :meth:`get_bundle` (read path) and :meth:`refresh_bundle`
    (write path) so the frontend can render the regime badge consistently
    regardless of which code path produced the page-snapshot cache.
    """
    instrument_id = str(payload.get("instrument_id") or "")
    timeframe = str(payload.get("timeframe") or "")
    final_decision = payload.get("final_decision") or {}
    components = final_decision.get("components") if isinstance(final_decision, dict) else {}
    structure_overall = (
        components.get("structure_overall")
        if isinstance(components, dict)
        else None
    )
    if not isinstance(structure_overall, dict):
        structure_overall = {}
    secondary = payload.get("secondary_indicator_series") or {}
    adx_value = _extract_latest_adx(secondary.get("adx_14"))
    regime = (
        structure_overall.get("regime")
        or final_decision.get("chip_regime")
        or ""
    )
    asset_class = detect_asset_class(instrument_id)
    mode = detect_mode(
        regime=regime if isinstance(regime, str) else "",
        adx=adx_value if adx_value is not None else 20,
        asset_class=asset_class,
        timeframe=timeframe,
    )
    if structure_overall.get("range_state") in {
        "UPWARD_RANGE", "DOWNWARD_RANGE", "NEUTRAL_RANGE"
    }:
        range_classification = RangeClassification(
            range_state=str(structure_overall.get("range_state")),
            range_label=str(structure_overall.get("range_label") or ""),
            range_score=float(structure_overall.get("range_score") or 0.0),
            range_basis=list(structure_overall.get("range_basis") or []),
            range_conflicts=list(structure_overall.get("range_conflicts") or []),
        )
    else:
        range_classification = classify_range(
            regime=mode,
            structure_score=final_decision.get("direction_score"),
        )
    return mode, asset_class, range_classification


WINDOW_PROFILES = {
    "1h": {
        "short": {"visibleBars": 96, "calcBars": 360},
        "default": {"visibleBars": 240, "calcBars": 720},
        "long": {"visibleBars": 480, "calcBars": 1200},
    },
    "4h": {
        "short": {"visibleBars": 90, "calcBars": 300},
        "default": {"visibleBars": 180, "calcBars": 480},
        "long": {"visibleBars": 360, "calcBars": 900},
    },
    "1d": {
        "short": {"visibleBars": 90, "calcBars": 240},
        "default": {"visibleBars": 180, "calcBars": 420},
        "long": {"visibleBars": 360, "calcBars": 900},
    },
    "1w": {
        "short": {"visibleBars": 52, "calcBars": 156},
        "default": {"visibleBars": 104, "calcBars": 260},
        "long": {"visibleBars": 208, "calcBars": 520},
    },
    "30d": {
        "short": {"visibleBars": 36, "calcBars": 120},
        "default": {"visibleBars": 60, "calcBars": 180},
        "long": {"visibleBars": 120, "calcBars": 360},
    },
}


class AnalysisBundleService:
    def __init__(self, repository: MarketRepository) -> None:
        self.repository = repository

    async def get_bundle(
        self, instrument_id: str, timeframe: str, view_window: str = "default"
    ) -> AnalysisBundleRead:
        limit = limit_for_view_window(timeframe, view_window)
        cache_key = analysis_cache_key(instrument_id, timeframe, limit)
        cache = await self.repository.get_page_snapshot_cache(cache_key)
        status = cache_status(cache)
        payload = cache.payload_json if cache is not None else {}
        freshness = source_freshness(
            cache.source_updated_at if cache is not None else None,
            timeframe,
        )
        candles = payload.get("candles", [])
        latest_bar_ts = None
        if candles:
            latest = candles[-1]
            latest_bar_ts = (
                latest.get("ts_open")
                if isinstance(latest, dict)
                else getattr(latest, "ts_open", None)
            )
        bar_state = bar_close_freshness(timeframe, latest_bar_ts)
        freshness_state = (
            bar_state.freshness_state
            if bar_state.freshness_state in {"fresh", "due", "missing"}
            else freshness.state
        )
        mode_payload = dict(payload)
        mode_payload.setdefault("instrument_id", instrument_id)
        mode_payload.setdefault("timeframe", timeframe)
        mode, asset_class, range_classification = _compute_payload_mode(mode_payload)
        return AnalysisBundleRead.model_validate(
            {
                "instrument_id": instrument_id,
                "timeframe": timeframe,
                "view_window": view_window,
                "candles": payload.get("candles", []),
                "mark": payload.get("mark"),
                "contract_snapshot": payload.get("contract_snapshot", {}),
                "core_indicator_series": payload.get("core_indicator_series", {}),
                "secondary_indicator_series": payload.get("secondary_indicator_series", {}),
                "final_decision": payload.get("final_decision", {}),
                "mode": mode,
                "asset_class": asset_class,
                **range_classification.as_dict(),
                "status": "ready" if status == "fresh" else status,
                "cache_state": status,
                "freshness_state": freshness_state,
                "source_age_seconds": freshness.age_seconds,
                "snapshot_at": cache.snapshot_at if cache else None,
                "data_ts": cache.data_ts if cache else None,
                "source_updated_at": cache.source_updated_at if cache else None,
                "expires_at": cache.expires_at if cache else None,
                "source_version": cache.source_version if cache else CACHE_SOURCE_VERSION,
                "cost_ms": cache.cost_ms if cache else None,
                "refreshed": False,
                "status_message": (
                    "检测到新收盘 K 线，后台正在重建分析快照。"
                    if freshness_state == "due"
                    else bundle_status_message(status)
                ),
            }
        )

    async def refresh_bundle(
        self,
        instrument_id: str,
        timeframe: str,
        view_window: str = "default",
        *,
        sync_inputs: bool = True,
    ) -> AnalysisBundleRead:
        started = time.perf_counter()
        now = datetime.now(timezone.utc)
        market_service = MarketService(self.repository)
        monitoring_service = IndicatorMonitoringService(self.repository)
        normalized_timeframe = "30d" if timeframe == "1M" else timeframe
        limit = limit_for_view_window(normalized_timeframe, view_window)
        if sync_inputs:
            await MarketDataBundleService(self.repository).get_bundle(
                instrument_id=instrument_id,
                timeframe=normalized_timeframe,
                limit=limit,
                allow_stale=False,
                refresh=True,
            )
            try:
                await monitoring_service.sync_technical(
                    instrument_id=instrument_id,
                    timeframe=normalized_timeframe,
                )
            except Exception:
                # Keep bundle generation resilient if indicator sync is temporarily unavailable.
                pass
        # These helpers share the same SQLAlchemy session and may write computed
        # caches. Keep them sequential to avoid concurrent flushes on one session.
        contract_snapshot = await ContractSnapshotService(self.repository).get_snapshot(
            instrument_id, include_stats=True
        )
        mark = await market_service.get_best_mark(instrument_id=instrument_id, prefer_live=True)
        indicator_matrix = await IndicatorMatrixService(self.repository).get_matrix(
            instrument_id=instrument_id, timeframe=normalized_timeframe, limit=limit
        )
        final_decision = await FinalDecisionService(self.repository).build(
            instrument_id, normalized_timeframe
        )
        market_bundle = await MarketDataBundleService(self.repository).get_bundle(
            instrument_id=instrument_id,
            timeframe=normalized_timeframe,
            limit=limit,
            allow_stale=False,
            refresh=False,
        )
        candles = [CandleRead.model_validate(item) for item in market_bundle.get("candles", [])]
        source_updated_at = candles[-1].ts_open if candles else (mark.ts_event if mark else now)
        core_indicator_series = {
            key: value
            for key, value in indicator_matrix["series"].items()
            if key
            in {
                "ema_20",
                "ema_50",
                "ema_200",
                "ema_30",
                "ema_60",
                "ema_120",
                "ema_12",
                "rsi_14",
                "macd_line",
                "macd_signal",
                "macd_hist",
                "atr_14",
                "natr_14",
            }
        }
        secondary_indicator_series = {
            key: value
            for key, value in indicator_matrix["series"].items()
            if key not in core_indicator_series
        }
        payload = {
            "candles": [item.model_dump(mode="json") for item in candles],
            "mark": self._mark_payload(mark),
            "contract_snapshot": contract_snapshot,
            "core_indicator_series": core_indicator_series,
            "secondary_indicator_series": secondary_indicator_series,
            "final_decision": final_decision,
        }
        mode, asset_class, range_classification = _compute_payload_mode(
            {**payload, "instrument_id": instrument_id, "timeframe": normalized_timeframe}
        )
        payload["mode"] = mode
        payload["asset_class"] = asset_class
        payload.update(range_classification.as_dict())
        cost_ms = int((time.perf_counter() - started) * 1000)
        cache = await self.repository.upsert_page_snapshot_cache(
            cache_key=analysis_cache_key(instrument_id, normalized_timeframe, limit),
            page_type="analysis",
            instrument_id=instrument_id,
            timeframe=normalized_timeframe,
            payload_json=payload,
            status="ready",
            cache_state="fresh",
            snapshot_at=now,
            data_ts=source_updated_at,
            expires_at=expires_at_for_page("analysis", now),
            source_updated_at=source_updated_at,
            source_version=CACHE_SOURCE_VERSION,
            cost_ms=cost_ms,
            meta_json={"view_window": view_window, "limit": limit, "profile": view_window},
        )
        return AnalysisBundleRead.model_validate(
            {
                "instrument_id": instrument_id,
                "timeframe": normalized_timeframe,
                "view_window": view_window,
                "candles": payload["candles"],
                "mark": payload["mark"],
                "contract_snapshot": payload["contract_snapshot"],
                "core_indicator_series": core_indicator_series,
                "secondary_indicator_series": secondary_indicator_series,
                "final_decision": final_decision,
                "mode": mode,
                "asset_class": asset_class,
                **range_classification.as_dict(),
                "status": "ready",
                "cache_state": "fresh",
                "freshness_state": source_freshness(
                    source_updated_at,
                    normalized_timeframe,
                    now=now,
                ).state,
                "source_age_seconds": 0,
                "refresh_completed_at": now,
                "snapshot_at": cache.snapshot_at,
                "data_ts": cache.data_ts,
                "source_updated_at": cache.source_updated_at,
                "expires_at": cache.expires_at,
                "source_version": cache.source_version,
                "cost_ms": cache.cost_ms,
                "refreshed": True,
                "status_message": bundle_status_message("fresh"),
            }
        )

    @staticmethod
    def _mark_payload(mark: MarkPrice | None) -> dict | None:
        if mark is None:
            return None
        if getattr(mark, "mark_id", None) in (None, 0):
            payload = {
                "mark_id": 0,
                "instrument_id": mark.instrument_id,
                "mark_price": mark.mark_price,
                "source": mark.source,
                "ts_event": mark.ts_event,
            }
            return MarkPriceRead.model_validate(payload).model_dump(mode="json")
        return MarkPriceRead.model_validate(mark).model_dump(mode="json")


def limit_for_view_window(timeframe: str, view_window: str = "default") -> int:
    profile = WINDOW_PROFILES.get(timeframe, WINDOW_PROFILES["1d"]).get(
        view_window,
        WINDOW_PROFILES.get(timeframe, WINDOW_PROFILES["1d"])["default"],
    )
    return min(int(profile["calcBars"]), 1000)
