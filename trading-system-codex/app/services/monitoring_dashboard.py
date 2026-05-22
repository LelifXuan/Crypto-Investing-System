from __future__ import annotations

import logging
import time
from datetime import datetime, timedelta, timezone
from decimal import Decimal
from typing import Any

from app.repositories.market_repository import MarketRepository
from app.schemas.market import (
    AlertEventRead,
    IndicatorObservationRead,
    MacroOverviewResponse,
    MonitoringDashboardRead,
)
from app.services.analysis_bundle import AnalysisBundleService
from app.services.cache_registry import CACHE_SOURCE_VERSION
from app.services.indicator_monitoring import IndicatorMonitoringService
from app.services.page_snapshot_cache import (
    bundle_status_message,
    cache_status,
    expires_at_for_page,
    monitoring_dashboard_cache_key,
)

UTC = timezone.utc
logger = logging.getLogger(__name__)


MONITORING_STALE_MAX_AGE = timedelta(days=1)


class MonitoringDashboardService:
    def __init__(self, repository: MarketRepository) -> None:
        self.repository = repository

    async def get_bundle(
        self,
        instrument_id: str,
        timeframe: str,
        *,
        allow_refresh: bool = False,
    ) -> MonitoringDashboardRead:
        cache = await self.repository.get_page_snapshot_cache(
            monitoring_dashboard_cache_key(instrument_id, timeframe)
        )
        status = cache_status(cache)
        payload = cache.payload_json if cache is not None else {}
        if allow_refresh and (
            cache is None
            or status in {"missing", "stale", "error", "updating"}
            or self._is_effectively_empty(payload)
        ):
            logger.info(
                "monitoring dashboard refresh is needed for %s/%s; returning cached shell with is_stale=true",
                instrument_id,
                timeframe,
            )
            macro_overview = payload.get("macro_overview")
        else:
            macro_overview = payload.get("macro_overview")
        if isinstance(macro_overview, dict) and macro_overview.get("status") == "unavailable":
            macro_overview = None
        return MonitoringDashboardRead.model_validate(
            {
                "instrument_id": instrument_id,
                "timeframe": timeframe,
                "macro_overview": macro_overview,
                "technical_observations": payload.get("technical_observations", []),
                "technical_source": payload.get("technical_source"),
                "technical_indicator_count": payload.get(
                    "technical_indicator_count",
                    len(payload.get("technical_observations", [])),
                ),
                "onchain_observations": [],
                "alert_events": self._filter_monitoring_alert_events(
                    payload.get("alert_events", [])
                ),
                "cross_asset": payload.get("cross_asset", []),
                "source_status": self._normalize_source_status(payload.get("source_status", {})),
                "status": "ready" if status == "fresh" else status,
                "cache_state": status,
                "snapshot_at": cache.snapshot_at if cache else None,
                "data_ts": cache.data_ts if cache else None,
                "source_updated_at": cache.source_updated_at if cache else None,
                "expires_at": cache.expires_at if cache else None,
                "source_version": cache.source_version if cache else CACHE_SOURCE_VERSION,
                "cost_ms": cache.cost_ms if cache else None,
                "refreshed": False,
                "status_message": bundle_status_message(status),
            }
        )

    async def refresh_bundle(self, instrument_id: str, timeframe: str) -> MonitoringDashboardRead:
        started = time.perf_counter()
        now = datetime.now(timezone.utc)
        monitoring_service = IndicatorMonitoringService(self.repository)
        if await self._category_is_stale("macro"):
            try:
                await monitoring_service.sync_macro()
            except Exception:
                logger.warning("sync failed for %s", exc_info=True)

        macro_overview = await self._macro_overview_payload()
        if isinstance(macro_overview, dict) and macro_overview.get("regime_key") == "unknown":
            macro_overview = None
        cross_asset = await self._cross_asset_snapshot()
        source_status = await self._data_source_status()
        technical_from_analysis = await self._technical_observations_from_analysis_bundle(
            instrument_id,
            timeframe,
            now,
        )
        technical_raw = await self.repository.list_indicator_observations(
            category="technical",
            instrument_id=instrument_id,
            timeframe=timeframe,
            limit=50,
        )
        alert_events_raw = await self.repository.list_alert_events(limit=20)
        alert_events = self._filter_monitoring_alert_events(
            [
                AlertEventRead.model_validate(item).model_dump(mode="json")
                for item in alert_events_raw
            ]
        )
        legacy_technical = [
            self._annotate_observation(
                IndicatorObservationRead.model_validate(item).model_dump(mode="json"),
                item,
                now,
            )
            for item in technical_raw
        ]
        technical_observations = self._merge_technical_observations(
            technical_from_analysis,
            legacy_technical,
        )
        all_ts = [
            *(self._parse_ts(item.get("observation_ts")) for item in technical_observations),
        ]
        all_ts = [item for item in all_ts if item is not None]
        source_updated_at = max(all_ts, default=now)
        payload = {
            "macro_overview": macro_overview,
            "technical_observations": technical_observations,
            "technical_source": (
                "analysis_bundle" if technical_from_analysis else "indicator_observations"
            ),
            "technical_indicator_count": len(technical_observations),
            "onchain_observations": [],
            "alert_events": alert_events,
            "cross_asset": cross_asset,
            "source_status": source_status,
        }
        cache = await self.repository.upsert_page_snapshot_cache(
            cache_key=monitoring_dashboard_cache_key(instrument_id, timeframe),
            page_type="monitoring",
            instrument_id=instrument_id,
            timeframe=timeframe,
            payload_json=payload,
            status="ready",
            cache_state="fresh",
            snapshot_at=now,
            data_ts=source_updated_at,
            expires_at=expires_at_for_page("monitoring", now),
            source_updated_at=source_updated_at,
            source_version=CACHE_SOURCE_VERSION,
            cost_ms=int((time.perf_counter() - started) * 1000),
            meta_json={"alert_limit": 20, "technical_limit": 50},
        )
        return MonitoringDashboardRead.model_validate(
            {
                "instrument_id": instrument_id,
                "timeframe": timeframe,
                **payload,
                "status": "ready",
                "cache_state": "fresh",
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

    @classmethod
    def _is_effectively_empty(cls, payload: dict[str, Any] | None) -> bool:
        if not payload:
            return True
        macro_overview = payload.get("macro_overview")
        has_macro = bool(macro_overview) and not (
            isinstance(macro_overview, dict) and macro_overview.get("status") == "unavailable"
        )
        return not any(
            [
                payload.get("technical_observations"),
                cls._filter_monitoring_alert_events(payload.get("alert_events", [])),
                payload.get("cross_asset"),
                has_macro,
            ]
        )

    async def _technical_observations_from_analysis_bundle(
        self,
        instrument_id: str,
        timeframe: str,
        now: datetime,
    ) -> list[dict[str, Any]]:
        service = AnalysisBundleService(self.repository)
        bundle = await service.get_bundle(instrument_id, timeframe, "default")
        if bundle.cache_state in {"missing", "stale", "error"}:
            try:
                bundle = await service.refresh_bundle(instrument_id, timeframe, "default")
            except Exception:
                logger.warning("analysis bundle refresh failed for monitoring", exc_info=True)
        series = {
            **(bundle.core_indicator_series or {}),
            **(bundle.secondary_indicator_series or {}),
        }
        candles = bundle.candles or []
        latest_candle = candles[-1] if candles else None
        observation_ts = latest_candle.ts_open if latest_candle else now
        if observation_ts.tzinfo is None:
            observation_ts = observation_ts.replace(tzinfo=UTC)
        close = self._to_float(getattr(latest_candle, "close", None))
        items: list[dict[str, Any]] = []
        for key in [
            "ema_20",
            "ema_50",
            "ema_200",
            "rsi_14",
            "macd_hist",
            "atr_14",
            "natr_14",
            "bbands_width",
            "percent_b",
            "adx_14",
            "plus_di",
            "minus_di",
            "obv",
            "kdj_j",
            "cci_20",
            "volume",
        ]:
            value = self._latest_series_value(series.get(key))
            if value is None:
                continue
            items.append(
                {
                    "observation_id": f"analysis-bundle:{instrument_id}:{timeframe}:{key}",
                    "indicator_key": key,
                    "category": "technical",
                    "instrument_id": instrument_id,
                    "asset_code": None,
                    "country_code": None,
                    "timeframe": timeframe,
                    "observation_ts": observation_ts.isoformat(),
                    "value_num": value,
                    "value_text": None,
                    "value_json": {"source": "analysis_bundle"},
                    "baseline_num": None,
                    "delta_num": None,
                    "zscore_num": None,
                    "percentile_num": None,
                    "signal_state": self._analysis_signal_state(key, value, close),
                    "signal_score": None,
                    "source_provider": "analysis_bundle",
                    "source_ref": "analysis_bundle.default",
                    "source_granularity": timeframe,
                    "is_preliminary": False,
                    "quality_score": Decimal("95"),
                    "freshness_label": "current",
                    "freshness_seconds": max(0, int((now - observation_ts).total_seconds())),
                }
            )
        return items

    @staticmethod
    def _merge_technical_observations(
        preferred: list[dict[str, Any]],
        fallback: list[dict[str, Any]],
    ) -> list[dict[str, Any]]:
        merged: dict[tuple[str, str | None], dict[str, Any]] = {}
        for item in fallback:
            merged[(str(item.get("indicator_key")), item.get("timeframe"))] = item
        for item in preferred:
            merged[(str(item.get("indicator_key")), item.get("timeframe"))] = item
        return list(merged.values())

    @classmethod
    def _filter_monitoring_alert_events(cls, items: Any) -> list[dict[str, Any]]:
        if not isinstance(items, list):
            return []
        return [item for item in items if isinstance(item, dict) and not cls._is_hidden_alert(item)]

    @staticmethod
    def _is_hidden_alert(item: dict[str, Any]) -> bool:
        parts = [
            item.get("rule_key"),
            item.get("indicator_key"),
            item.get("asset_code"),
            item.get("source_provider"),
            item.get("source_ref"),
        ]
        payload = item.get("event_payload_json") or item.get("payload_json") or {}
        if isinstance(payload, dict):
            parts.extend(str(value) for value in payload.values())
        haystack = " ".join(str(part or "").lower() for part in parts)
        return any(
            token in haystack
            for token in ("glassnode", "demo_fallback", "onchain", "链上")
        )

    @staticmethod
    def _latest_series_value(values: Any) -> float | None:
        if not isinstance(values, list):
            return None
        for value in reversed(values):
            parsed = MonitoringDashboardService._to_float(value)
            if parsed is not None:
                return parsed
        return None

    @staticmethod
    def _to_float(value: Any) -> float | None:
        if value in (None, "", "-", "--"):
            return None
        try:
            return float(value)
        except (TypeError, ValueError):
            return None

    @staticmethod
    def _parse_ts(value: Any) -> datetime | None:
        if isinstance(value, datetime):
            return value if value.tzinfo else value.replace(tzinfo=UTC)
        if not value:
            return None
        try:
            parsed = datetime.fromisoformat(str(value).replace("Z", "+00:00"))
            return parsed if parsed.tzinfo else parsed.replace(tzinfo=UTC)
        except ValueError:
            return None

    @staticmethod
    def _analysis_signal_state(key: str, value: float, close: float | None) -> str:
        if key.startswith("ema_"):
            if close is None:
                return "normal"
            return "bullish" if close >= value else "bearish"
        if key == "rsi_14":
            if value >= 70:
                return "overbought"
            if value <= 30:
                return "oversold"
            if value > 55:
                return "strong"
            if value < 45:
                return "weak"
            return "neutral"
        if key == "macd_hist":
            if value > 0:
                return "positive_hist"
            if value < 0:
                return "negative_hist"
            return "neutral"
        if key == "natr_14":
            if value >= 3:
                return "expanded"
            if value <= 1:
                return "compressed"
            return "normal"
        if key == "percent_b":
            if value >= 1:
                return "breakout_up"
            if value <= 0:
                return "breakout_down"
            return "normal"
        if key == "adx_14":
            if value >= 25:
                return "strong_trend"
            if value < 18:
                return "weak_trend"
            return "developing_trend"
        if key == "kdj_j":
            if value >= 90:
                return "overbought"
            if value <= 10:
                return "oversold"
            return "neutral"
        if key == "cci_20":
            if value >= 100:
                return "strong"
            if value <= -100:
                return "weak"
            return "neutral"
        return "normal"

    async def _category_is_stale(
        self,
        category: str,
        *,
        instrument_id: str | None = None,
        timeframe: str | None = None,
    ) -> bool:
        items = await self.repository.list_indicator_observations(
            category=category,
            instrument_id=instrument_id,
            timeframe=timeframe,
            limit=1,
        )
        if not items:
            return True
        ts = (
            items[0].observation_ts
            if items[0].observation_ts.tzinfo
            else items[0].observation_ts.replace(tzinfo=UTC)
        )
        return ts < datetime.now(timezone.utc) - MONITORING_STALE_MAX_AGE

    async def _macro_overview_payload(self) -> dict:
        try:
            from app.services.macro_overview import MacroOverviewService

            macro_overview = await MacroOverviewService(self.repository).build_overview()
            return MacroOverviewResponse.model_validate(macro_overview).model_dump(mode="json")
        except Exception as exc:
            logger.warning("macro overview build failed: %s", exc)
            return {
                # This fallback must not be scored as a real macro signal.
                "regime_key": "unknown",
                "regime_label_cn": "宏观暂不可用",
                "regime_summary": f"宏观数据构建异常：{exc}",
                "policy_score": 0,
                "inflation_score": 0,
                "growth_score": 0,
                "liquidity_score": 0,
                "total_score": 0,
                "score_scale": "0-100；高分偏风险偏好，低分偏风险收缩",
                "score_band": "不可用",
                "layer_contributions": {},
                "operation_bias": "观察",
                "event_window_status": "inactive",
                "event_window_summary": "无法获取事件窗口信息",
                "next_event_title": None,
                "next_event_at": None,
                "event_items": [],
                "layers": [],
            }

    async def _cross_asset_snapshot(self) -> list[dict]:
        tokens = {
            "xau-usdt-perp": "黄金",
            "xaut-usdt-perp": "Tether Gold",
            "spyx-usdt-perp": "标普500",
            "qqqx-usdt-perp": "纳斯达克100",
            "slvon-usdt-perp": "白银",
        }
        results = []
        for instrument_id, label in tokens.items():
            try:
                candles = await self.repository.list_candles(
                    instrument_id=instrument_id,
                    timeframe="1d",
                    limit=2,
                )
                if candles:
                    latest = candles[-1]
                    prev = candles[-2] if len(candles) > 1 else None
                    change_pct = (
                        (float(latest.close) - float(prev.close)) / float(prev.close) * 100
                        if prev and prev.close
                        else None
                    )
                    results.append(
                        {
                            "instrument_id": instrument_id,
                            "label": label,
                            "price": float(latest.close),
                            "change_pct": round(change_pct, 2) if change_pct is not None else None,
                            "ts": latest.ts_open.isoformat(),
                        }
                    )
            except Exception:
                pass
        return results

    async def _data_source_status(self) -> dict[str, dict[str, Any]]:
        status: dict[str, dict[str, Any]] = {}
        try:
            candles = await self.repository.list_candles(
                instrument_id="btc-usdt-perp",
                timeframe="1h",
                limit=1,
            )
            if candles:
                latest_ts = getattr(candles[-1], "ts_open", None)
                updated_at = latest_ts.isoformat() if isinstance(latest_ts, datetime) else None
                status["gateio"] = self._source_status_entry(
                    "online",
                    "Gate.io",
                    "K 线缓存可用；技术、结构和告警会复用本地快照。",
                    updated_at=updated_at,
                )
            else:
                status["gateio"] = self._source_status_entry(
                    "no_data",
                    "Gate.io",
                    "本地暂无 K 线缓存；等待手动刷新或后台预计算补齐。",
                )
        except Exception as exc:
            status["gateio"] = self._source_status_entry(
                "offline",
                "Gate.io",
                "读取 Gate.io 缓存或连接状态失败。",
                last_error=str(exc),
            )

        try:
            dff = await self.repository.latest_observation("us_dff")
            effr = await self.repository.latest_observation("effr")
            rate_obs = dff or effr
            if rate_obs and rate_obs.value_num is not None:
                updated_at = (
                    rate_obs.observation_ts.isoformat()
                    if rate_obs.observation_ts
                    else None
                )
                status["fred"] = self._source_status_entry(
                    "online",
                    "FRED",
                    "宏观利率观测可用。",
                    updated_at=updated_at,
                )
            else:
                status["fred"] = self._source_status_entry(
                    "no_data",
                    "FRED",
                    "暂未读取到 FRED 最新观测；宏观页会使用缓存或降级展示。",
                )
        except Exception as exc:
            status["fred"] = self._source_status_entry(
                "offline",
                "FRED",
                "读取 FRED 观测失败。",
                last_error=str(exc),
            )

        try:
            events = await self.repository.list_recent_market_events(limit=1)
            if events:
                event_ts = getattr(events[0], "ts_event", None)
                updated_at = event_ts.isoformat() if isinstance(event_ts, datetime) else None
                status["market_events"] = self._source_status_entry(
                    "online",
                    "市场事件",
                    "事件信息流缓存可用。",
                    updated_at=updated_at,
                )
            else:
                status["market_events"] = self._source_status_entry(
                    "no_data",
                    "市场事件",
                    "暂未读取到事件缓存；等待同步任务补齐。",
                )
        except Exception as exc:
            status["market_events"] = self._source_status_entry(
                "offline",
                "市场事件",
                "读取事件缓存失败。",
                last_error=str(exc),
            )

        status["ashare_etf"] = await self._ashare_etf_source_status()
        return status

    async def _ashare_etf_source_status(self) -> dict[str, Any]:
        try:
            from app.services.ashare_etf_quotes import AShareETFQuoteService

            summary = AShareETFQuoteService.persistent_cache_summary()
        except Exception as exc:
            return self._source_status_entry(
                "offline",
                "A股ETF",
                "读取 A股ETF 本地快照失败。",
                last_error=str(exc),
            )
        if summary.get("has_cache"):
            return self._source_status_entry(
                "stale_cache",
                "A股ETF",
                "A股ETF 行情独立于加密货币工作流；当前可读取最近行情快照。",
                updated_at=summary.get("generated_at"),
            )
        return self._source_status_entry(
            "no_data",
            "A股ETF",
            "A股ETF 行情源暂未形成可用快照；ETF 页面会保留标的列表并等待下次刷新。",
        )

    @staticmethod
    def _source_status_entry(
        status: str,
        label: str,
        message: str,
        *,
        last_error: str | None = None,
        updated_at: str | None = None,
    ) -> dict[str, Any]:
        return {
            "status": status,
            "label": label,
            "message": message,
            "last_error": last_error,
            "updated_at": updated_at,
        }

    @classmethod
    def _normalize_source_status(cls, raw: Any) -> dict[str, dict[str, Any]]:
        labels = {
            "gateio": "Gate.io",
            "fred": "FRED",
            "market_events": "市场事件",
            "ashare_etf": "A股ETF",
        }
        messages = {
            "online": "信源在线，缓存可用。",
            "ok": "信源在线，缓存可用。",
            "fresh": "信源在线，缓存可用。",
            "no_data": "信源未返回可用数据，等待后台补齐。",
            "missing": "信源未返回可用数据，等待后台补齐。",
            "not_configured": "信源未配置；系统会使用缓存或降级展示。",
            "auth_missing": "API Key 未配置；这不是系统故障。",
            "offline": "信源读取失败。",
            "error": "信源读取失败。",
            "source_error": "信源读取失败。",
            "stale_cache": "正在使用最近缓存。",
            "stale": "正在使用最近缓存。",
            "cached": "正在使用最近缓存。",
            "updating": "等待监控快照返回信源状态。",
            "pending": "等待监控快照返回信源状态。",
        }
        fallback_message = "状态暂不可用。"
        normalized: dict[str, dict[str, Any]] = {}
        source = raw if isinstance(raw, dict) else {}
        for key, value in source.items():
            if key not in labels:
                continue
            if isinstance(value, dict):
                source_status = str(value.get("status") or "unknown")
                raw_message = value.get("message")
                raw_label = value.get("label")
                normalized[key] = {
                    "status": source_status,
                    "label": cls._clean_cached_text(raw_label) or labels[key],
                    "message": cls._clean_cached_text(raw_message)
                    or messages.get(source_status, fallback_message),
                    "last_error": value.get("last_error"),
                    "updated_at": value.get("updated_at"),
                }
            else:
                source_status = str(value or "unknown")
                normalized[key] = cls._source_status_entry(
                    source_status,
                    labels[key],
                    messages.get(source_status, fallback_message),
                )
        for key, label in labels.items():
            if key not in normalized:
                normalized[key] = cls._source_status_entry(
                    "updating",
                    label,
                    messages["updating"],
                )
        return normalized

    @staticmethod
    def _clean_cached_text(value: Any) -> str | None:
        if not value:
            return None
        text = str(value)
        mojibake_tokens = tuple(chr(codepoint) for codepoint in (0xFFFD, 0x934B, 0x7039, 0x93C6))
        if any(token in text for token in mojibake_tokens):
            return None
        return text

    @staticmethod
    def _annotate_observation(d: dict, item, now: datetime) -> dict:
        obs_ts = item.observation_ts
        if obs_ts.tzinfo is None:
            obs_ts = obs_ts.replace(tzinfo=UTC)
        age_seconds = (now - obs_ts).total_seconds()
        freshness_seconds = 7200
        d["status"] = "fresh" if age_seconds < freshness_seconds else "stale"
        is_demo = (item.value_json or {}).get("is_demo", False)
        is_preliminary = getattr(item, "is_preliminary", False) or False
        d["recommendation_usable"] = not is_demo and not is_preliminary and d["status"] == "fresh"
        return d
