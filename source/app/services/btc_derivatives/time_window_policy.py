from __future__ import annotations

from dataclasses import dataclass
from datetime import date, datetime, timedelta
from typing import Any, Sequence

WINDOW_DAYS = {
    "7D": 7,
    "30D": 30,
    "90D": 90,
    "180D": 180,
    "365D": 365,
}


@dataclass(frozen=True)
class TimeWindowPolicy:
    default: str
    maximum: str
    granularity: str
    is_cross_section: bool = False


TIME_WINDOW_POLICY = {
    "spot_price": TimeWindowPolicy("30D", "365D", "1h/4h/1d"),
    "leverage_pressure": TimeWindowPolicy("90D", "365D", "daily_snapshot"),
    "perp_oi": TimeWindowPolicy("30D", "180D", "1h/4h"),
    "funding": TimeWindowPolicy("30D", "365D", "8h_raw_daily_agg"),
    "futures_basis": TimeWindowPolicy(
        "90D",
        "365D",
        "expiry_cross_section_daily_history",
    ),
    "options_chain": TimeWindowPolicy(
        "current",
        "current",
        "selected_expiry_strike",
        is_cross_section=True,
    ),
    "iv_smile": TimeWindowPolicy(
        "current",
        "180D",
        "selected_expiry_daily_snapshot",
        is_cross_section=True,
    ),
    "atm_iv_term": TimeWindowPolicy(
        "current",
        "365D",
        "expiry_cross_section_daily_history",
        is_cross_section=True,
    ),
    "wall_max_pain": TimeWindowPolicy("180D", "365D", "daily_snapshot"),
    "hedge_cost": TimeWindowPolicy("180D", "365D", "daily_snapshot"),
}


def resolve_window(data_family: str, requested: str | None) -> str:
    policy = TIME_WINDOW_POLICY[data_family]
    if policy.is_cross_section:
        return "current"
    selected = requested or policy.default
    if selected not in WINDOW_DAYS:
        selected = policy.default
    return min(
        (selected, policy.maximum),
        key=lambda value: WINDOW_DAYS[value],
    )


def _as_date(value: Any) -> date | None:
    if isinstance(value, datetime):
        return value.date()
    if isinstance(value, date):
        return value
    text = str(value or "").replace("Z", "+00:00")
    try:
        return datetime.fromisoformat(text).date()
    except ValueError:
        try:
            return datetime.strptime(text[:10], "%Y-%m-%d").date()
        except ValueError:
            return None


def filter_history_window(
    points: Sequence[dict[str, Any]],
    window: str,
    *,
    as_of: date,
) -> list[dict[str, Any]]:
    if window == "current":
        return list(points)
    days = WINDOW_DAYS[window]
    start = as_of - timedelta(days=days - 1)
    return [
        dict(point)
        for point in points
        if (point_date := _as_date(point.get("timestamp"))) is not None
        and start <= point_date <= as_of
    ]
