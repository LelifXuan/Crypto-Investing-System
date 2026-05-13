from __future__ import annotations

import hashlib
import json
import time
from datetime import UTC, datetime
from decimal import Decimal
from uuid import uuid4

from app.db.models.market import StrategySignal
from app.repositories.market_repository import MarketRepository
from app.schemas.market import PrecomputeHintRequest
from app.services.cache_registry import (
    CACHE_SOURCE_VERSION,
    bundle_status_message,
    cache_status,
    expires_at_for_strategy,
    strategy_bundle_cache_key,
)
from app.services.strategy_signal.confidence_dimensions import build_confidence_report
from app.services.strategy_signal.config_loader import load_strategy_signal_config
from app.services.strategy_signal.iteration_engine import IterationEngine
from app.services.strategy_signal.review_engine import ReviewEngine
from app.services.strategy_signal.scoring_engine import DirectionScoringEngine
from app.services.strategy_signal.snapshot_builder import StrategySnapshotBuilder
from app.services.strategy_signal.strategy_generator import StrategyGenerator


def _json_hash(payload: dict) -> str:
    raw = json.dumps(payload, sort_keys=True, ensure_ascii=False, default=str)
    return hashlib.sha256(raw.encode("utf-8")).hexdigest()


def _jsonable(payload: dict) -> dict:
    return json.loads(json.dumps(payload, ensure_ascii=False, default=str))


def _decimal(value) -> Decimal | None:
    try:
        if value is None:
            return None
        return Decimal(str(value))
    except Exception:
        return None


def _utc_now() -> datetime:
    return datetime.now(UTC)


class StrategySignalUnavailable(RuntimeError):
    """Raised when there is no generated strategy signal to persist."""


class StrategySignalService:
    def __init__(self, repository: MarketRepository) -> None:
        self.repository = repository

    async def get_bundle(
        self,
        instrument_id: str,
        timeframe: str,
        *,
        enqueue_refresh: bool = True,
    ) -> dict:
        cache_key = strategy_bundle_cache_key(instrument_id, timeframe)
        cache = await self.repository.get_page_snapshot_cache(cache_key)
        status = cache_status(cache)
        if cache is not None and isinstance(cache.payload_json, dict) and cache.payload_json:
            payload = dict(cache.payload_json)
            payload.update(
                {
                    "status": "ready" if status == "fresh" else status,
                    "cache_state": status,
                    "refresh_enqueued": status in {"stale", "missing", "updating"},
                    "snapshot_at": cache.snapshot_at,
                    "data_ts": cache.data_ts,
                    "expires_at": cache.expires_at,
                    "source_version": cache.source_version or CACHE_SOURCE_VERSION,
                    "status_message": bundle_status_message(status),
                }
            )
            if status in {"stale", "missing", "error"} and enqueue_refresh:
                await self.enqueue_refresh(instrument_id, timeframe, reason=f"strategy_cache_{status}")
                payload["refresh_enqueued"] = True
            return payload

        if enqueue_refresh:
            await self.enqueue_refresh(instrument_id, timeframe, reason="strategy_cache_missing")
        return self._missing_payload(instrument_id, timeframe, refresh_enqueued=enqueue_refresh)

    async def refresh_bundle(
        self,
        instrument_id: str,
        timeframe: str,
        *,
        reason: str = "scheduled",
    ) -> dict:
        started = time.perf_counter()
        try:
            payload = await self.build_bundle_uncached(instrument_id, timeframe)
            now = _utc_now()
            payload.update(
                {
                    "status": payload.get("status") or "ready",
                    "cache_state": "fresh",
                    "refreshed": True,
                    "refresh_enqueued": False,
                    "snapshot_at": now,
                    "data_ts": payload.get("generated_at") or now,
                    "expires_at": expires_at_for_strategy(timeframe, now),
                    "source_version": CACHE_SOURCE_VERSION,
                    "status_message": payload.get("status_message") or bundle_status_message("fresh"),
                }
            )
            await self.repository.upsert_page_snapshot_cache(
                cache_key=strategy_bundle_cache_key(instrument_id, timeframe),
                page_type="strategy",
                instrument_id=instrument_id,
                timeframe=timeframe,
                payload_json=_jsonable(payload),
                status="ready",
                cache_state="fresh",
                snapshot_at=now,
                data_ts=payload["data_ts"],
                expires_at=payload["expires_at"],
                source_updated_at=payload["data_ts"],
                source_version=CACHE_SOURCE_VERSION,
                cost_ms=int((time.perf_counter() - started) * 1000),
                meta_json={"reason": reason},
            )
            return payload
        except Exception as exc:
            now = _utc_now()
            await self.repository.upsert_page_snapshot_cache(
                cache_key=strategy_bundle_cache_key(instrument_id, timeframe),
                page_type="strategy",
                instrument_id=instrument_id,
                timeframe=timeframe,
                payload_json={},
                status="error",
                cache_state="error",
                snapshot_at=now,
                expires_at=expires_at_for_strategy(timeframe, now),
                source_version=CACHE_SOURCE_VERSION,
                cost_ms=int((time.perf_counter() - started) * 1000),
                last_error=str(exc),
                meta_json={"reason": reason},
            )
            raise

    async def build_bundle_uncached(self, instrument_id: str, timeframe: str) -> dict:
        config = load_strategy_signal_config()
        snapshot = await StrategySnapshotBuilder(self.repository).build(
            instrument_id,
            timeframe,
            dependency_policy="cache_only",
        )
        snapshot["config"] = config
        scores = DirectionScoringEngine(config).compute(snapshot)
        confidence_report = build_confidence_report(snapshot, scores)
        decision = StrategyGenerator(config).build_decision(snapshot, scores)
        decision["confidence_report"] = confidence_report
        decision["confidence_buckets"] = confidence_report["confidence_buckets"]
        review = await ReviewEngine(self.repository).build_review(
            snapshot["instrument_id"],
            snapshot["timeframe"],
            limit=80,
        )
        proposals = await IterationEngine(self.repository).list_proposals(
            snapshot["instrument_id"],
            snapshot["timeframe"],
        )
        confidence_value = float(decision.get("confidence_score") or scores.confidence or 0.0)
        status = "ready" if confidence_value >= 70 else "low_confidence"
        status_message = (
            f"策略信号已生成，当前综合置信度 {confidence_value:.0f}/100。"
            "低置信维度已体现在仓位、入场许可和风险门禁中。"
        )
        auto_save_states = {
            "LONG_TRIGGERED",
            "SHORT_TRIGGERED",
            "WAIT_LONG_CONFIRMATION",
            "WAIT_SHORT_CONFIRMATION",
        }
        if decision.get("strategy_state", "") in auto_save_states:
            await self._auto_save(instrument_id, timeframe, snapshot, decision, config)
        return {
            "instrument_id": snapshot["instrument_id"],
            "timeframe": snapshot["timeframe"],
            "generated_at": _utc_now(),
            "current_price": snapshot.get("current_price"),
            "status": status,
            "cache_state": "fresh",
            "status_message": status_message,
            "snapshot": snapshot,
            "decision": decision,
            "review_summary": review,
            "iteration_proposals": proposals,
            "dependency_state": snapshot.get("dependency_state", {}),
        }

    # Backward-compatible name for callers that still explicitly need a rebuild.
    async def build_bundle(self, instrument_id: str, timeframe: str) -> dict:
        return await self.build_bundle_uncached(instrument_id, timeframe)

    async def enqueue_refresh(self, instrument_id: str, timeframe: str, *, reason: str) -> dict:
        from app.services.precompute import precompute_service

        response = await precompute_service.enqueue_hint(
            PrecomputeHintRequest(
                current_page="strategy",
                instrument_id=instrument_id,
                timeframe=timeframe,
                reason=reason,
                visible=True,
                candidates=["strategy"],
                priority=1,
            )
        )
        return response.model_dump(mode="json")

    async def _auto_save(
        self,
        instrument_id: str,
        timeframe: str,
        snapshot: dict,
        decision: dict,
        config: dict,
    ) -> None:
        from datetime import date as date_type

        from sqlalchemy import func, select

        today = date_type.today()
        stmt = (
            select(func.count())
            .select_from(StrategySignal)
            .where(
                StrategySignal.instrument_id == instrument_id,
                StrategySignal.timeframe == timeframe,
                func.date(StrategySignal.signal_ts) == today,
            )
        )
        result = await self.repository.session.execute(stmt)
        count = result.scalar() or 0
        if count == 0:
            await self._persist_signal(
                signal_key=f"strategy-auto-{uuid4()}",
                instrument_id=instrument_id,
                timeframe=timeframe,
                snapshot=snapshot,
                decision=decision,
                config=config,
                source="ai_strategy_auto",
            )

    async def save_signal(self, instrument_id: str, timeframe: str) -> dict:
        bundle = await self.get_bundle(instrument_id, timeframe, enqueue_refresh=False)
        if bundle.get("cache_state") in {"missing", "updating", "error"} or not bundle.get("decision"):
            raise StrategySignalUnavailable("暂无可保存的策略信号，请等待后台刷新完成后再保存。")
        snapshot = bundle["snapshot"]
        decision = bundle["decision"]
        config = snapshot.get("config", {})
        input_hash = _json_hash({"snapshot": snapshot, "decision": decision})
        signal_key = f"strategy-{uuid4()}"
        await self._persist_signal(
            signal_key=signal_key,
            instrument_id=bundle["instrument_id"],
            timeframe=bundle["timeframe"],
            snapshot=snapshot,
            decision=decision,
            config=config,
            source="ai_strategy_v16",
            input_hash=input_hash,
            bundle=bundle,
        )
        return {
            "signal_key": signal_key,
            "decision_id": signal_key,
            "input_hash": input_hash,
            "model_version": str(config.get("model_versions", {}).get("strategy_model", "strategy-signal-v1.6")),
            "config_version": str(config.get("version", "market-strategy-signal-v1.6")),
            "payload": bundle,
        }

    async def _persist_signal(
        self,
        *,
        signal_key: str,
        instrument_id: str,
        timeframe: str,
        snapshot: dict,
        decision: dict,
        config: dict,
        source: str,
        input_hash: str | None = None,
        bundle: dict | None = None,
    ) -> None:
        primary = decision.get("primary_strategy") or {}
        model_version = str(config.get("model_versions", {}).get("strategy_model", "strategy-signal-v1.6"))
        config_version = str(config.get("version", "market-strategy-signal-v1.6"))
        metadata = {
            "model_version": model_version,
            "config_version": config_version,
        }
        if input_hash:
            metadata["input_hash"] = input_hash
        if bundle:
            metadata["payload"] = _jsonable(bundle)
        signal = StrategySignal(
            signal_key=signal_key,
            recommendation_id=None,
            template_key=primary.get("pattern_type"),
            signal_type="market_strategy_signal",
            instrument_id=instrument_id,
            timeframe=timeframe,
            signal_ts=_utc_now(),
            direction=decision.get("strategy_bias", "neutral"),
            signal_state=decision.get("strategy_state", "NO_EDGE"),
            confidence_score=_decimal(decision.get("confidence_score")),
            entry_price=_decimal(primary.get("entry_price")),
            stop_loss_price=_decimal(primary.get("stop_price")),
            take_profit_price=_decimal(primary.get("take_profit_1")),
            risk_reward_ratio=_decimal(primary.get("risk_reward_ratio")),
            position_size_pct=_decimal(primary.get("capital_pct")),
            signal_source=source,
            trigger_indicators_json=decision.get("entry_checklist", []),
            context_snapshot_json=_jsonable(snapshot),
            market_condition_json=_jsonable(
                {
                    "state": decision.get("strategy_state"),
                    "bias": decision.get("strategy_bias"),
                    "scores": {
                        "long": decision.get("long_score"),
                        "short": decision.get("short_score"),
                        "neutral": decision.get("neutral_score"),
                    },
                }
            ),
            metadata_json=metadata,
        )
        self.repository.session.add(signal)
        await self.repository.session.flush()

    def _missing_payload(
        self,
        instrument_id: str,
        timeframe: str,
        *,
        refresh_enqueued: bool,
    ) -> dict:
        now = _utc_now()
        return {
            "instrument_id": instrument_id,
            "timeframe": timeframe,
            "generated_at": now,
            "current_price": None,
            "status": "updating" if refresh_enqueued else "missing",
            "cache_state": "missing",
            "status_message": "暂无策略快照，后台正在准备当前标的与周期的数据。",
            "snapshot": {
                "instrument_id": instrument_id,
                "timeframe": timeframe,
                "data_quality": {"score": 0, "statuses": {}, "candles_count": 0},
                "dependency_state": {},
            },
            "decision": self._empty_decision(),
            "review_summary": {},
            "iteration_proposals": [],
            "dependency_state": {},
            "refresh_enqueued": refresh_enqueued,
            "snapshot_at": None,
            "data_ts": None,
            "expires_at": expires_at_for_strategy(timeframe, now),
            "source_version": CACHE_SOURCE_VERSION,
        }

    @staticmethod
    def _empty_decision() -> dict:
        plan = {
            "pattern_type": None,
            "pattern_label": "暂无策略",
            "direction": "neutral",
            "capital_pct": 0,
            "max_leverage": 0,
            "entry_conditions": [],
            "invalidation_rules": [],
        }
        return {
            "strategy_state": "NO_EDGE",
            "strategy_state_label": "多空不明",
            "strategy_permission": "observe_only",
            "strategy_permission_label": "仅观察",
            "strategy_bias": "neutral",
            "strategy_bias_label": "中性",
            "long_score": 0,
            "short_score": 0,
            "neutral_score": 100,
            "dominant_direction": "neutral",
            "direction_confidence": 0,
            "confidence_score": 0,
            "execution_score": 0,
            "risk_score": 100,
            "data_quality_score": 0,
            "conflict_score": 0,
            "components": {},
            "risk_reward": {},
            "long_plan": plan,
            "short_plan": plan,
            "primary_strategy": plan,
            "alternative_strategy": plan,
            "backup_strategy": plan,
            "entry_checklist": [],
            "gates": [],
            "no_trade_reasons": ["暂无策略快照，等待后台预计算完成。"],
            "conflict_reasons": [],
            "evidence_matrix": [],
            "review_tags": [],
            "explain": ["当前没有可用策略快照，系统已把当前标的和周期加入后台预计算队列。"],
            "generated_at": _utc_now().isoformat(),
        }
