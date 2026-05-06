from __future__ import annotations

import asyncio
import hashlib
import logging
import os
import time
from collections.abc import Iterable
from dataclasses import asdict, dataclass, field
from datetime import UTC, datetime

from app.core.config import settings
from app.repositories.market_repository import MarketRepository
from app.schemas.market import (
    MacroEventCalendarRead,
    MarketEventRead,
    PrecomputeHintRequest,
    PrecomputeHintResponse,
    PrecomputeStatusRead,
    PrecomputeTaskRead,
)
from app.services.alerts_bundle import AlertsBundleService
from app.services.analysis_bundle import AnalysisBundleService, limit_for_view_window
from app.services.cache_registry import (
    CACHE_SOURCE_VERSION,
    alerts_bundle_cache_key,
    analysis_cache_key,
    expires_at_for_page,
    macro_calendar_cache_key,
    market_events_cache_key,
    monitoring_dashboard_cache_key,
    structure_bundle_cache_key,
)
from app.services.monitoring_dashboard import MonitoringDashboardService
from app.services.structure import StructureSnapshotService

logger = logging.getLogger(__name__)

PRIORITY_WEIGHTS = {
    "base_P0": 1000,
    "base_P1": 800,
    "base_P2": 600,
    "base_P3": 350,
    "base_P4": 120,
    "user_action_boost": 300,
    "current_page_boost": 120,
    "same_instrument_boost": 80,
    "adjacent_timeframe_boost": 40,
    "stale_boost": 60,
    "recency_boost": 20,
    "network_penalty": 80,
    "heavy_compute_penalty": 100,
    "retry_penalty_per_attempt": 60,
}

PAGE_PRIORITY_MATRIX = {
    "analysis": {
        "current": [("analysis", "P1")],
        "secondary": [("secondary_indicators", "P2")],
        "related": [("structure", "P3"), ("alerts", "P3"), ("adjacent_timeframe_analysis", "P3")],
    },
    "structure": {
        "current": [("structure", "P1")],
        "secondary": [("structure_diagnostics", "P2")],
        "related": [("alerts", "P3"), ("analysis", "P3")],
    },
    "alerts": {
        "current": [("alerts", "P1")],
        "secondary": [("microstructure", "P2"), ("divergence", "P2")],
        "related": [("structure", "P3"), ("analysis", "P3"), ("monitoring", "P3")],
    },
    "monitoring": {
        "current": [("monitoring", "P1")],
        "secondary": [("macro", "P2")],
        "related": [("analysis", "P3"), ("alerts", "P3")],
    },
    "macro": {"current": [("macro", "P2")], "secondary": [], "related": []},
    "events": {"current": [("events", "P2")], "secondary": [], "related": []},
    "knowledge": {"current": [], "secondary": [], "related": []},
}

LANE_BY_TASK = {
    "analysis": "interactive_compute",
    "secondary_indicators": "interactive_compute",
    "structure": "background_precompute",
    "structure_diagnostics": "background_precompute",
    "alerts": "background_precompute",
    "divergence": "background_precompute",
    "microstructure": "network_limited",
    "monitoring": "background_precompute",
    "macro": "maintenance",
    "events": "maintenance",
    "adjacent_timeframe_analysis": "background_precompute",
}

TASK_COST_CLASS = {
    "analysis": "medium",
    "secondary_indicators": "light",
    "structure": "heavy",
    "structure_diagnostics": "heavy",
    "alerts": "medium",
    "divergence": "medium",
    "microstructure": "network",
    "monitoring": "medium",
    "macro": "network",
    "events": "network",
    "adjacent_timeframe_analysis": "medium",
}


@dataclass(slots=True)
class PrecomputeTask:
    task_type: str
    page_type: str
    cache_key: str
    dedupe_key: str
    lane: str
    priority_level: str
    score: int
    instrument_id: str | None = None
    timeframe: str | None = None
    view_window: str | None = None
    current_page: str | None = None
    reason: str | None = None
    visible: bool = True
    attempt_count: int = 0
    created_at: float = field(default_factory=time.monotonic)
    params_hash: str = ""

    def as_status_dict(self) -> dict:
        payload = asdict(self)
        payload["created_at"] = round(self.created_at, 3)
        return payload


class PrecomputeTaskPlanner:
    def build_tasks(self, payload: PrecomputeHintRequest) -> list[PrecomputeTask]:
        page = normalize_page(payload.current_page)
        if page not in PAGE_PRIORITY_MATRIX:
            return []
        instrument_id = payload.instrument_id or "btc-usdt-perp"
        timeframe = normalize_timeframe(payload.timeframe)
        view_window = payload.view_window or "default"
        selected_candidates = set(payload.candidates or [])
        page_plan = PAGE_PRIORITY_MATRIX[page]
        tasks: list[PrecomputeTask] = []
        for bucket in ("current", "secondary", "related"):
            for task_type, priority_level in page_plan[bucket]:
                if (
                    selected_candidates
                    and task_type not in selected_candidates
                    and bucket != "current"
                ):
                    continue
                tasks.extend(
                    self._expand_task_type(
                        task_type=task_type,
                        priority_level=priority_level,
                        page=page,
                        instrument_id=instrument_id,
                        timeframe=timeframe,
                        view_window=view_window,
                        reason=payload.reason,
                        visible=payload.visible,
                    )
                )
        return self.sort_tasks(tasks)

    def sort_tasks(self, tasks: Iterable[PrecomputeTask]) -> list[PrecomputeTask]:
        return sorted(tasks, key=lambda item: (-item.score, item.created_at))

    def _expand_task_type(
        self,
        *,
        task_type: str,
        priority_level: str,
        page: str,
        instrument_id: str,
        timeframe: str,
        view_window: str,
        reason: str | None,
        visible: bool,
    ) -> list[PrecomputeTask]:
        items: list[PrecomputeTask] = []
        if task_type == "analysis":
            limit = limit_for_view_window(timeframe, view_window)
            items.append(
                self._build_task(
                    task_type=task_type,
                    page_type="analysis",
                    cache_key=analysis_cache_key(instrument_id, timeframe, limit),
                    instrument_id=instrument_id,
                    timeframe=timeframe,
                    view_window=view_window,
                    priority_level=priority_level,
                    page=page,
                    reason=reason,
                    visible=visible,
                )
            )
        elif task_type == "adjacent_timeframe_analysis":
            for neighbor in adjacent_timeframes(timeframe):
                limit = limit_for_view_window(neighbor, view_window)
                items.append(
                    self._build_task(
                        task_type=task_type,
                        page_type="analysis",
                        cache_key=analysis_cache_key(instrument_id, neighbor, limit),
                        instrument_id=instrument_id,
                        timeframe=neighbor,
                        view_window=view_window,
                        priority_level=priority_level,
                        page=page,
                        reason=reason,
                        visible=False,
                    )
                )
        elif task_type in {"structure", "structure_diagnostics"}:
            items.append(
                self._build_task(
                    task_type=task_type,
                    page_type="structure",
                    cache_key=structure_bundle_cache_key(instrument_id, timeframe, True, 220),
                    instrument_id=instrument_id,
                    timeframe=timeframe,
                    priority_level=priority_level,
                    page=page,
                    reason=reason,
                    visible=visible,
                )
            )
        elif task_type == "alerts":
            items.append(
                self._build_task(
                    task_type=task_type,
                    page_type="alerts",
                    cache_key=alerts_bundle_cache_key(instrument_id, timeframe),
                    instrument_id=instrument_id,
                    timeframe=timeframe,
                    priority_level=priority_level,
                    page=page,
                    reason=reason,
                    visible=visible,
                )
            )
        elif task_type == "monitoring":
            items.append(
                self._build_task(
                    task_type=task_type,
                    page_type="monitoring",
                    cache_key=monitoring_dashboard_cache_key(instrument_id, timeframe),
                    instrument_id=instrument_id,
                    timeframe=timeframe,
                    priority_level=priority_level,
                    page=page,
                    reason=reason,
                    visible=visible,
                )
            )
        elif task_type == "macro":
            items.append(
                self._build_task(
                    task_type=task_type,
                    page_type="macro",
                    cache_key=macro_calendar_cache_key(200, None, None),
                    priority_level=priority_level,
                    page=page,
                    reason=reason,
                    visible=visible,
                )
            )
        elif task_type == "events":
            items.append(
                self._build_task(
                    task_type=task_type,
                    page_type="events",
                    cache_key=market_events_cache_key(60, False),
                    priority_level=priority_level,
                    page=page,
                    reason=reason,
                    visible=visible,
                )
            )
        elif task_type in {"secondary_indicators", "microstructure", "divergence"}:
            # tracked in queue/status but executed as part of page bundle generation
            items.append(
                self._build_task(
                    task_type=task_type,
                    page_type=page if page in {"analysis", "alerts"} else "analysis",
                    cache_key=f"{task_type}:{instrument_id}:{timeframe}:{CACHE_SOURCE_VERSION}",
                    instrument_id=instrument_id,
                    timeframe=timeframe,
                    priority_level=priority_level,
                    page=page,
                    reason=reason,
                    visible=visible,
                )
            )
        return items

    def _build_task(
        self,
        *,
        task_type: str,
        page_type: str,
        cache_key: str,
        priority_level: str,
        page: str,
        reason: str | None,
        visible: bool,
        instrument_id: str | None = None,
        timeframe: str | None = None,
        view_window: str | None = None,
    ) -> PrecomputeTask:
        dedupe_task_type = {
            "secondary_indicators": "analysis",
            "structure_diagnostics": "structure",
            "divergence": "alerts",
            "microstructure": "alerts",
        }.get(task_type, task_type)
        signature = (
            f"{dedupe_task_type}|{instrument_id or '-'}|{timeframe or '-'}|"
            f"{view_window or '-'}|{cache_key}"
        )
        params_hash = hashlib.sha1(signature.encode("utf-8")).hexdigest()[:12]
        dedupe_key = f"{dedupe_task_type}:{instrument_id or '-'}:{timeframe or '-'}:{params_hash}"
        lane = LANE_BY_TASK.get(task_type, "background_precompute")
        score = self._score(
            priority_level=priority_level,
            task_type=task_type,
            page=page,
            instrument_id=instrument_id,
            timeframe=timeframe,
            visible=visible,
            reason=reason,
        )
        return PrecomputeTask(
            task_type=task_type,
            page_type=page_type,
            cache_key=cache_key,
            dedupe_key=dedupe_key,
            lane=lane,
            priority_level=priority_level,
            score=score,
            instrument_id=instrument_id,
            timeframe=timeframe,
            view_window=view_window,
            current_page=page,
            reason=reason,
            visible=visible,
            params_hash=params_hash,
        )

    def _score(
        self,
        *,
        priority_level: str,
        task_type: str,
        page: str,
        instrument_id: str | None,
        timeframe: str | None,
        visible: bool,
        reason: str | None,
    ) -> int:
        score = PRIORITY_WEIGHTS[f"base_{priority_level}"]
        if visible:
            score += PRIORITY_WEIGHTS["current_page_boost"]
        if reason and any(token in reason.lower() for token in ("refresh", "manual", "click")):
            score += PRIORITY_WEIGHTS["user_action_boost"]
        if instrument_id:
            score += PRIORITY_WEIGHTS["same_instrument_boost"]
        if timeframe in {"4h", "1d", "1w"} and task_type == "adjacent_timeframe_analysis":
            score += PRIORITY_WEIGHTS["adjacent_timeframe_boost"]
        if TASK_COST_CLASS.get(task_type) == "heavy":
            score -= PRIORITY_WEIGHTS["heavy_compute_penalty"]
        if TASK_COST_CLASS.get(task_type) == "network":
            score -= PRIORITY_WEIGHTS["network_penalty"]
        return score


def normalize_page(page: str) -> str:
    normalized = str(page or "").strip().lower()
    mapping = {
        "market-analysis": "analysis",
        "analysis": "analysis",
        "market-structure": "structure",
        "structure": "structure",
        "alert-center": "alerts",
        "alerts": "alerts",
        "monitoring-overview": "monitoring",
        "monitoring": "monitoring",
        "macro-calendar": "macro",
        "macro": "macro",
        "market-events": "events",
        "events": "events",
        "knowledge-base": "knowledge",
        "knowledge": "knowledge",
    }
    return mapping.get(normalized, normalized)


def normalize_timeframe(timeframe: str | None) -> str:
    if timeframe == "1M":
        return "30d"
    return timeframe or "1d"


def adjacent_timeframes(timeframe: str) -> list[str]:
    ordered = ["1h", "4h", "1d", "1w", "30d"]
    if timeframe not in ordered:
        return []
    idx = ordered.index(timeframe)
    neighbors = []
    if idx - 1 >= 0:
        neighbors.append(ordered[idx - 1])
    if idx + 1 < len(ordered):
        neighbors.append(ordered[idx + 1])
    return neighbors


class PrecomputeService:
    def __init__(self) -> None:
        self._queue: list[PrecomputeTask] = []
        self._queued: dict[str, PrecomputeTask] = {}
        self._running_by_lane: dict[str, PrecomputeTask] = {}
        self._last_seen_at: dict[str, float] = {}
        self._recent_failures: list[dict] = []
        self._lock = asyncio.Lock()
        self._wakeup = asyncio.Event()
        self._planner = PrecomputeTaskPlanner()

    async def enqueue_hint(self, payload: PrecomputeHintRequest) -> PrecomputeHintResponse:
        if not settings.precompute_enabled:
            return PrecomputeHintResponse(status="disabled", queue_depth=len(self._queue))
        tasks = self._planner.build_tasks(payload)
        if not tasks:
            return PrecomputeHintResponse(status="skipped", queue_depth=len(self._queue))
        accepted = 0
        deduped = 0
        queued_keys: list[str] = []
        async with self._lock:
            for task in tasks:
                state = self._enqueue_task_locked(task)
                if state == "accepted":
                    accepted += 1
                    queued_keys.append(task.cache_key)
                else:
                    deduped += 1
            queue_depth = len(self._queue)
        if accepted:
            self._wakeup.set()
            return PrecomputeHintResponse(
                status="accepted",
                accepted=accepted,
                queued=accepted,
                deduped=deduped,
                queue_depth=queue_depth,
                queued_keys=queued_keys,
            )
        return PrecomputeHintResponse(
            status="deduped",
            accepted=0,
            queued=0,
            deduped=deduped,
            queue_depth=queue_depth,
            queued_keys=queued_keys,
        )

    async def status(self) -> PrecomputeStatusRead:
        async with self._lock:
            running_task = next(iter(self._running_by_lane.values()), None)
            lane_counters: dict[str, int] = {}
            for task in self._queue:
                lane_counters[task.lane] = lane_counters.get(task.lane, 0) + 1
            return PrecomputeStatusRead(
                queue_depth=len(self._queue),
                running_task=running_task.as_status_dict() if running_task else None,
                lane_counters=lane_counters,
                recent_failures=list(self._recent_failures[-10:]),
            )

    async def task_status(self, task_key: str) -> PrecomputeTaskRead:
        async with self._lock:
            for task in self._queue:
                if task.dedupe_key == task_key or task.cache_key == task_key:
                    return PrecomputeTaskRead(
                        task_key=task_key,
                        status="queued",
                        lane=task.lane,
                        priority_level=task.priority_level,
                        score=task.score,
                        cache_key=task.cache_key,
                        task_type=task.task_type,
                        instrument_id=task.instrument_id,
                        timeframe=task.timeframe,
                        reason=task.reason,
                        visible=task.visible,
                        current_page=task.current_page,
                    )
            for task in self._running_by_lane.values():
                if task.dedupe_key == task_key or task.cache_key == task_key:
                    return PrecomputeTaskRead(
                        task_key=task_key,
                        status="running",
                        lane=task.lane,
                        priority_level=task.priority_level,
                        score=task.score,
                        cache_key=task.cache_key,
                        task_type=task.task_type,
                        instrument_id=task.instrument_id,
                        timeframe=task.timeframe,
                        reason=task.reason,
                        visible=task.visible,
                        current_page=task.current_page,
                    )
            failure = next(
                (
                    item
                    for item in reversed(self._recent_failures)
                    if item.get("cache_key") == task_key or item.get("task_key") == task_key
                ),
                None,
            )
            if failure:
                return PrecomputeTaskRead(
                    task_key=task_key,
                    status="error",
                    lane=failure.get("lane"),
                    cache_key=failure.get("cache_key"),
                    task_type=failure.get("task_type"),
                    last_error=failure.get("error"),
                )
        return PrecomputeTaskRead(task_key=task_key, status="missing")

    async def process_next(self, repository: MarketRepository) -> bool:
        if not settings.precompute_enabled or not self._cpu_is_idle():
            return False
        async with self._lock:
            if not self._queue:
                return False
            task = self._queue.pop(0)
            self._queued.pop(task.dedupe_key, None)
            self._running_by_lane[task.lane] = task
        try:
            await self._execute_task(repository, task)
            return True
        except Exception as exc:  # pragma: no cover
            logger.exception("precompute task failed for %s: %s", task.cache_key, exc)
            self._recent_failures.append(
                {
                    "task_key": task.dedupe_key,
                    "cache_key": task.cache_key,
                    "task_type": task.task_type,
                    "lane": task.lane,
                    "error": str(exc),
                    "ts": datetime.now(UTC).isoformat(),
                }
            )
            await repository.upsert_page_snapshot_cache(
                cache_key=task.cache_key,
                page_type=task.page_type,
                instrument_id=task.instrument_id,
                timeframe=task.timeframe,
                payload_json={},
                status="error",
                cache_state="error",
                snapshot_at=datetime.now(UTC),
                expires_at=expires_at_for_page(task.page_type, datetime.now(UTC)),
                source_updated_at=None,
                source_version=CACHE_SOURCE_VERSION,
                last_error=str(exc),
                meta_json={
                    "reason": task.reason or "",
                    "view_window": task.view_window,
                    "lane": task.lane,
                },
            )
            return False
        finally:
            async with self._lock:
                self._running_by_lane.pop(task.lane, None)
                if self._queue:
                    self._wakeup.set()

    async def wait_for_work(self, timeout_seconds: float) -> bool:
        async with self._lock:
            if self._queue:
                return True
            self._wakeup.clear()
        try:
            await asyncio.wait_for(self._wakeup.wait(), timeout=timeout_seconds)
            return True
        except TimeoutError:
            return False

    def _enqueue_task_locked(self, task: PrecomputeTask) -> str:
        now = time.monotonic()
        running = self._running_by_lane.get(task.lane)
        if running and running.dedupe_key == task.dedupe_key:
            return "deduped"
        existing = self._queued.get(task.dedupe_key)
        if existing is not None:
            existing.score = max(existing.score, task.score)
            if task.reason:
                existing.reason = task.reason
            if task.visible:
                existing.visible = True
            self._queue.sort(key=lambda item: (-item.score, item.created_at))
            return "deduped"
        if len(self._queue) >= settings.precompute_max_queue_size:
            return "skipped"
        last_seen = self._last_seen_at.get(task.dedupe_key, 0.0)
        if now - last_seen < settings.precompute_min_seconds_between_same_key:
            return "deduped"
        self._last_seen_at[task.dedupe_key] = now
        self._queue.append(task)
        self._queued[task.dedupe_key] = task
        self._queue.sort(key=lambda item: (-item.score, item.created_at))
        return "accepted"

    async def _execute_task(self, repository: MarketRepository, task: PrecomputeTask) -> None:
        if task.page_type == "analysis" and task.instrument_id and task.timeframe:
            await AnalysisBundleService(repository).refresh_bundle(
                task.instrument_id, task.timeframe, task.view_window or "default"
            )
            return
        if task.page_type == "alerts" and task.instrument_id and task.timeframe:
            await AlertsBundleService(repository).refresh_bundle(task.instrument_id, task.timeframe)
            return
        if task.page_type == "monitoring" and task.instrument_id and task.timeframe:
            await MonitoringDashboardService(repository).refresh_bundle(
                task.instrument_id,
                task.timeframe,
            )
            return
        if task.page_type == "structure" and task.instrument_id and task.timeframe:
            service = StructureSnapshotService(repository)
            await service.refresh_snapshot(
                task.instrument_id,
                task.timeframe,
                include_geometry=True,
                include_diagnostics=True,
            )
            await service.persist_bundle_cache(
                task.instrument_id,
                task.timeframe,
                include_geometry=True,
                candles_limit=220,
            )
            return
        if task.page_type == "macro":
            items = await repository.list_macro_events(limit=200)
            payload = [
                MacroEventCalendarRead.model_validate(item).model_dump(mode="json")
                for item in items
            ]
            now = datetime.now(UTC)
            await repository.upsert_page_snapshot_cache(
                cache_key=task.cache_key,
                page_type="macro",
                payload_json={"items": payload},
                status="ready",
                cache_state="fresh",
                snapshot_at=now,
                data_ts=max((item.scheduled_at for item in items), default=now),
                expires_at=expires_at_for_page("macro", now),
                source_updated_at=max((item.scheduled_at for item in items), default=now),
                source_version=CACHE_SOURCE_VERSION,
                meta_json={"lane": task.lane},
            )
            return
        if task.page_type == "events":
            items = await repository.list_market_events(limit=60)
            mapping = await repository.list_market_event_instrument_ids(
                [item.event_id for item in items]
            )
            payload = [
                MarketEventRead(
                    event_id=item.event_id,
                    category=item.category,
                    title=item.title,
                    summary=item.summary,
                    source=item.source,
                    reliability=item.reliability,
                    ts_event=item.ts_event,
                    payload_json=item.payload_json,
                    instrument_ids=mapping.get(item.event_id, []),
                ).model_dump(mode="json")
                for item in items
            ]
            now = datetime.now(UTC)
            await repository.upsert_page_snapshot_cache(
                cache_key=task.cache_key,
                page_type="events",
                payload_json={"items": payload},
                status="ready",
                cache_state="fresh",
                snapshot_at=now,
                data_ts=max((item.ts_event for item in items), default=now),
                expires_at=expires_at_for_page("events", now),
                source_updated_at=max((item.ts_event for item in items), default=now),
                source_version=CACHE_SOURCE_VERSION,
                meta_json={"lane": task.lane},
            )

    @staticmethod
    def _cpu_is_idle() -> bool:
        if hasattr(os, "getloadavg"):
            try:
                load = os.getloadavg()[0]
                cpu_count = os.cpu_count() or 1
                return (load / cpu_count) <= settings.precompute_cpu_idle_threshold
            except OSError:
                return True
        return True


precompute_service = PrecomputeService()
