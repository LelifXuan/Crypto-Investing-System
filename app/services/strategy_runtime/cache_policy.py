"""Cache policy for strategy responses: freshness classification and stale projection."""

from __future__ import annotations

import copy
from dataclasses import dataclass
from datetime import datetime, timedelta, timezone
from enum import Enum
from typing import Any, Mapping


class CacheState(str, Enum):
    """Classification of a cached strategy response relative to its TTL."""

    FRESH = "fresh"
    SOFT_STALE = "soft_stale"
    HARD_STALE = "hard_stale"
    MISS = "miss"
    BUILD_FAILED = "build_failed"


@dataclass(frozen=True, slots=True)
class CanonicalCacheEntry:
    """A cached strategy response with freshness metadata."""

    payload: Mapping[str, Any]
    created_at: datetime
    soft_expires_at: datetime
    hard_expires_at: datetime
    last_success_at: datetime
    build_key: str

    def classify(self, now: datetime | None = None) -> CacheState:
        """Classify this entry's freshness at the given time."""
        now = now or datetime.now(timezone.utc)
        if now < self.soft_expires_at:
            return CacheState.FRESH
        if now < self.hard_expires_at:
            return CacheState.SOFT_STALE
        return CacheState.HARD_STALE


@dataclass(frozen=True, slots=True)
class CachePolicy:
    """TTL configuration for strategy cache entries."""

    soft_ttl_seconds: int
    hard_ttl_seconds: int

    def validate(self) -> None:
        if self.soft_ttl_seconds <= 0:
            raise ValueError("soft_ttl_seconds must be positive")
        if self.hard_ttl_seconds <= self.soft_ttl_seconds:
            raise ValueError("hard_ttl_seconds must exceed soft_ttl_seconds")

    def compute_expiry(self, now: datetime | None = None) -> tuple[datetime, datetime]:
        """Return (soft_expires_at, hard_expires_at) from now."""
        now = now or datetime.now(timezone.utc)
        return (
            now + timedelta(seconds=self.soft_ttl_seconds),
            now + timedelta(seconds=self.hard_ttl_seconds),
        )


def force_observe_projection(
    payload: Mapping[str, Any],
    *,
    blocker: str,
    readiness: str,
) -> dict[str, Any]:
    """Create a response-only downgrade without mutating persisted cache.

    When a cached entry is stale, we must not return it with executable
    permission. This function creates a deep copy with permission forced to
    'observe' and the appropriate blocker/readiness annotations.
    """
    result = copy.deepcopy(dict(payload))
    envelope = result.setdefault("decision_envelope", {})
    decision = envelope.setdefault("decision", {})
    blockers = list(decision.get("blockers") or [])
    if blocker not in blockers:
        blockers.append(blocker)

    decision["permission"] = "observe"
    decision["state"] = "WAIT_TRIGGER"
    decision["order_type"] = "NONE"
    decision["readiness"] = readiness
    decision["blockers"] = blockers
    result.setdefault("runtime", {})["permission_forced_observe"] = True
    return result


def warming_payload(*, job_id: str | None, blocker: str) -> dict[str, Any]:
    """Safe payload for cache miss: no decision, only warming indicator.

    Includes legacy fields (status, prewarm_status, refresh_state) for
    backward compatibility with the existing frontend and test suite.
    """
    return {
        "instrument_id": None,  # Will be set by caller
        "status": "degraded",
        "prewarm_status": "enqueued" if job_id else "disabled",
        "refresh_state": "missing",
        "refresh_limitations": ["Unified strategy snapshot is missing; background prewarm has been queued."],
        "decision": {
            "permission": "observe",
            "state": "WAIT_TRIGGER",
            "order_type": "NONE",
            "readiness": "WARMING",
            "blockers": [blocker],
        },
        "cache": {
            "state": CacheState.MISS.value,
            "refresh_job_id": job_id,
        },
        "runtime": {"permission_forced_observe": True},
        "decision_envelope": {
            "schema_version": "2.0.0",
            "decision": {
                "permission": "observe",
                "state": "WAIT_TRIGGER",
                "order_type": "NONE",
                "readiness": "WARMING",
                "blockers": [blocker],
            },
        },
    }
