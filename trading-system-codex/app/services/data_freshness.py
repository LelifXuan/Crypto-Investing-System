from __future__ import annotations

from dataclasses import dataclass
from datetime import datetime, timedelta, timezone
from typing import Any

TIMEFRAME_ALIASES = {
    "1M": "30d",
    "1m": "30d",
    "1mo": "30d",
    "30D": "30d",
}

TIMEFRAME_SECONDS = {
    "1h": 60 * 60,
    "4h": 4 * 60 * 60,
    "1d": 24 * 60 * 60,
    "1w": 7 * 24 * 60 * 60,
}


@dataclass(frozen=True)
class FreshnessState:
    freshness_state: str
    expected_closed_bar_ts: datetime | None
    latest_cached_bar_ts: datetime | None
    next_refresh_after: datetime | None
    refresh_reason: str

    def as_dict(self) -> dict[str, Any]:
        return {
            "freshness_state": self.freshness_state,
            "expected_closed_bar_ts": (
                self.expected_closed_bar_ts.isoformat()
                if self.expected_closed_bar_ts
                else None
            ),
            "latest_cached_bar_ts": (
                self.latest_cached_bar_ts.isoformat()
                if self.latest_cached_bar_ts
                else None
            ),
            "next_refresh_after": (
                self.next_refresh_after.isoformat()
                if self.next_refresh_after
                else None
            ),
            "refresh_reason": self.refresh_reason,
        }


def normalize_timeframe(timeframe: str | None) -> str:
    value = (timeframe or "1d").strip()
    return TIMEFRAME_ALIASES.get(value, value.lower())


def parse_ts(value: Any) -> datetime | None:
    if isinstance(value, datetime):
        parsed = value
    elif isinstance(value, str) and value.strip():
        try:
            parsed = datetime.fromisoformat(value.strip().replace("Z", "+00:00"))
        except ValueError:
            return None
    else:
        return None
    if parsed.tzinfo is None:
        parsed = parsed.replace(tzinfo=timezone.utc)
    return parsed.astimezone(timezone.utc)


def _floor_fixed_interval(now: datetime, seconds: int) -> datetime:
    epoch_seconds = int(now.timestamp())
    floored = epoch_seconds - (epoch_seconds % seconds)
    return datetime.fromtimestamp(floored, timezone.utc)


def _floor_month(now: datetime) -> datetime:
    return datetime(now.year, now.month, 1, tzinfo=timezone.utc)


def expected_closed_bar_ts(
    timeframe: str,
    *,
    now: datetime | None = None,
    grace_seconds: int = 90,
) -> datetime | None:
    current = (now or datetime.now(timezone.utc)).astimezone(timezone.utc)
    tf = normalize_timeframe(timeframe)
    if tf == "30d":
        boundary = _floor_month(current)
        previous = (
            datetime(boundary.year - 1, 12, 1, tzinfo=timezone.utc)
            if boundary.month == 1
            else datetime(boundary.year, boundary.month - 1, 1, tzinfo=timezone.utc)
        )
        return previous if current < boundary + timedelta(seconds=grace_seconds) else boundary
    seconds = TIMEFRAME_SECONDS.get(tf)
    if seconds is None:
        return None
    boundary = _floor_fixed_interval(current, seconds)
    if current < boundary + timedelta(seconds=grace_seconds):
        return boundary - timedelta(seconds=seconds)
    return boundary


def bar_close_freshness(
    timeframe: str,
    latest_cached_bar_ts: Any,
    *,
    now: datetime | None = None,
    grace_seconds: int = 90,
) -> FreshnessState:
    expected = expected_closed_bar_ts(
        timeframe,
        now=now,
        grace_seconds=grace_seconds,
    )
    latest = parse_ts(latest_cached_bar_ts)
    if expected is None:
        return FreshnessState(
            freshness_state="unknown",
            expected_closed_bar_ts=None,
            latest_cached_bar_ts=latest,
            next_refresh_after=None,
            refresh_reason="unsupported_timeframe",
        )
    next_refresh = expected + timedelta(
        seconds=TIMEFRAME_SECONDS.get(normalize_timeframe(timeframe), 0) or 30 * 24 * 60 * 60
    )
    if latest is None:
        return FreshnessState(
            freshness_state="missing",
            expected_closed_bar_ts=expected,
            latest_cached_bar_ts=None,
            next_refresh_after=next_refresh,
            refresh_reason="missing_cached_bar",
        )
    if latest >= expected:
        return FreshnessState(
            freshness_state="fresh",
            expected_closed_bar_ts=expected,
            latest_cached_bar_ts=latest,
            next_refresh_after=next_refresh,
            refresh_reason="latest_closed_bar_cached",
        )
    return FreshnessState(
        freshness_state="due",
        expected_closed_bar_ts=expected,
        latest_cached_bar_ts=latest,
        next_refresh_after=next_refresh,
        refresh_reason="new_closed_bar_available",
    )
