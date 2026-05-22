from __future__ import annotations

import json
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

ROOT = Path(__file__).resolve().parents[3]

DEFAULT_FRESHNESS_WINDOWS = {
    "intraday": {"fresh": 0.25, "extended": 1, "seed": 1},
    "daily": {"fresh": 7, "extended": 30, "seed": 45},
    "weekly": {"fresh": 30, "extended": 90, "seed": 120},
    "monthly": {"fresh": 120, "extended": 240, "seed": 365},
    "quarterly": {"fresh": 240, "extended": 420, "seed": 540},
    "fomc": {"fresh": 120, "extended": 240, "seed": 365},
    "irregular": {"fresh": 60, "extended": 120, "seed": 180},
}

SCORABLE_STATUSES = {"ok", "live", "cached"}
CONDITIONALLY_SCORABLE = {"stale_cache", "seed_cache"}
NOT_SCORABLE = {
    "stale_seed",
    "web_cached",
    "source_error",
    "proxy_required_unavailable",
    "auth_missing",
    "rate_limited",
    "parser_error",
    "unavailable_placeholder",
    "disabled",
    "not_implemented",
    "pending",
    "missing",
}


def classify_scoring(
    status: str,
    latest_date: str | None,
    frequency: str,
) -> tuple[bool, str | None]:
    """Return whether a macro record is eligible for scoring."""

    normalized = (status or "missing").strip().lower()
    if normalized in SCORABLE_STATUSES:
        return True, None

    if normalized in CONDITIONALLY_SCORABLE:
        windows = _freshness_windows().get(frequency, DEFAULT_FRESHNESS_WINDOWS["daily"])
        window_days = (
            windows.get("extended", 30)
            if normalized == "stale_cache"
            else windows.get("seed", 45)
        )
        age = _age_days(latest_date)
        if age is not None and age <= window_days:
            return True, None
        if age is None:
            return False, "缺少更新时间，暂不参与宏观评分。"
        return False, f"数据已超过评分窗口：{age} 天 > {window_days} 天。"

    if normalized in NOT_SCORABLE:
        return False, _status_reason(normalized)
    return False, f"未知状态 {normalized}，为避免误导暂不参与评分。"


def fallback_for_indicator(
    indicator_id: str,
    live_obs: Any | None,
    frequency: str = "daily",
) -> dict[str, Any]:
    """Return a complete macro row without treating missing data as zero."""

    live_record = _record_from_live(indicator_id, live_obs)
    if live_record["status"] not in {"missing", "pending"} or live_obs is not None:
        is_scored, reason = classify_scoring(
            live_record["status"],
            live_record.get("latest_date"),
            frequency,
        )
        live_record["is_scored"] = is_scored
        live_record["score_block_reason"] = reason
        return live_record

    seed = load_seed_cache().get(indicator_id)
    if seed:
        return _record_from_cache(indicator_id, seed, "seed_cache", frequency)

    web = load_websearch_cache().get(indicator_id)
    if web:
        return _record_from_cache(indicator_id, web, "web_cached", frequency)

    return {
        "indicator_id": indicator_id,
        "value": None,
        "previous_value": None,
        "unit": "",
        "latest_date": None,
        "source": "placeholder",
        "fallback_level": "unavailable_placeholder",
        "status": "unavailable_placeholder",
        "status_reason": "实时接口、运行时缓存、种子缓存和网页快照均不可用。",
        "is_scored": False,
        "score_block_reason": "占位行只用于保证页面不空，不参与评分。",
        "updated_at": None,
    }


def load_seed_cache() -> dict[str, dict[str, Any]]:
    for path in (
        ROOT / "runtime" / "cache" / "macro" / "macro_observations_seed.json",
        ROOT / "runtime" / "cache" / "macro" / "macro_observations.json",
        ROOT / "app" / "assets" / "seed_cache" / "macro_observations_seed.json",
    ):
        data = _load_items(path)
        if data:
            return data
    return {}


def load_websearch_cache() -> dict[str, dict[str, Any]]:
    for path in (
        ROOT / "runtime" / "cache" / "macro" / "macro_websearch_seed.json",
        ROOT / "runtime" / "cache" / "macro" / "macro_websearch.json",
        ROOT / "app" / "assets" / "seed_cache" / "macro_websearch_seed.json",
    ):
        data = _load_items(path)
        if data:
            return data
    return {}


def _record_from_live(indicator_id: str, live_obs: Any | None) -> dict[str, Any]:
    if live_obs is None:
        return {
            "indicator_id": indicator_id,
            "value": None,
            "previous_value": None,
            "unit": "",
            "latest_date": None,
            "source": "none",
            "fallback_level": "missing",
            "status": "missing",
            "status_reason": "暂无实时观测值。",
            "is_scored": False,
            "score_block_reason": "缺少观测值。",
            "updated_at": None,
        }

    if isinstance(live_obs, dict):
        latest_date = (
            live_obs.get("latest_date")
            or live_obs.get("observation_date")
            or live_obs.get("observation_ts")
            or live_obs.get("updated_at")
        )
        value = live_obs.get("value", live_obs.get("value_num"))
        source = live_obs.get("source") or live_obs.get("source_provider") or "live"
        status = live_obs.get("status") or "ok"
        unit = live_obs.get("unit", "")
    else:
        observation_ts = getattr(live_obs, "observation_ts", None)
        latest_date = (
            observation_ts.isoformat()
            if hasattr(observation_ts, "isoformat")
            else observation_ts
        )
        value = getattr(live_obs, "value_num", None)
        source = getattr(live_obs, "source_provider", None) or "live"
        status = getattr(live_obs, "status", None) or "ok"
        unit = getattr(live_obs, "unit", "")

    normalized_date = _date_text(latest_date)
    return {
        "indicator_id": indicator_id,
        "value": _safe_float(value),
        "previous_value": None,
        "unit": unit or "",
        "latest_date": normalized_date,
        "source": source,
        "fallback_level": "live_api" if status in {"ok", "live"} else status,
        "status": status,
        "status_reason": (
            "实时或本地观测值可用。"
            if status in {"ok", "live"}
            else _status_reason(status)
        ),
        "is_scored": False,
        "score_block_reason": None,
        "updated_at": normalized_date,
    }


def _record_from_cache(
    indicator_id: str,
    item: dict[str, Any],
    fallback_level: str,
    frequency: str,
) -> dict[str, Any]:
    latest_date = _date_text(
        item.get("latest_date") or item.get("observation_date") or item.get("updated_at")
    )
    status = str(item.get("status") or fallback_level)
    if fallback_level == "web_cached":
        status = "web_cached"
    is_scored, reason = classify_scoring(status, latest_date, frequency)
    return {
        "indicator_id": indicator_id,
        "value": _safe_float(item.get("value")),
        "previous_value": _safe_float(item.get("previous_value")),
        "unit": item.get("unit", ""),
        "latest_date": latest_date,
        "source": item.get("source", fallback_level),
        "fallback_level": fallback_level,
        "status": status,
        "status_reason": item.get("status_reason") or _status_reason(status),
        "is_scored": is_scored,
        "score_block_reason": reason,
        "updated_at": latest_date,
    }


def _freshness_windows() -> dict[str, dict[str, float]]:
    path = ROOT / "app" / "monitoring" / "configs" / "portable_macro_never_empty_policy.v2.json"
    if not path.exists():
        return DEFAULT_FRESHNESS_WINDOWS
    try:
        data = json.loads(path.read_text(encoding="utf-8"))
    except (OSError, json.JSONDecodeError):
        return DEFAULT_FRESHNESS_WINDOWS
    return (
        data.get("macro_never_empty", {}).get("freshness_windows_days")
        or DEFAULT_FRESHNESS_WINDOWS
    )


def _load_items(path: Path) -> dict[str, dict[str, Any]]:
    if not path.exists():
        return {}
    try:
        payload = json.loads(path.read_text(encoding="utf-8"))
    except (OSError, json.JSONDecodeError):
        return {}
    items = payload.get("items", payload if isinstance(payload, list) else [])
    if not isinstance(items, list):
        return {}
    result: dict[str, dict[str, Any]] = {}
    for item in items:
        if not isinstance(item, dict):
            continue
        key = item.get("indicator_id") or item.get("indicator_key") or item.get("id")
        if key:
            result[str(key)] = item
    return result


def _age_days(latest_date: str | None) -> int | None:
    parsed = _parse_date(latest_date)
    if parsed is None:
        return None
    return (datetime.now(timezone.utc).date() - parsed.date()).days


def _parse_date(value: Any | None) -> datetime | None:
    if value is None:
        return None
    if isinstance(value, datetime):
        return (
            value.astimezone(timezone.utc)
            if value.tzinfo
            else value.replace(tzinfo=timezone.utc)
        )
    text = str(value)
    try:
        return datetime.fromisoformat(text.replace("Z", "+00:00"))
    except ValueError:
        try:
            return datetime.strptime(text[:10], "%Y-%m-%d").replace(tzinfo=timezone.utc)
        except ValueError:
            return None


def _date_text(value: Any | None) -> str | None:
    parsed = _parse_date(value)
    if parsed is None:
        return str(value) if value else None
    return parsed.date().isoformat()


def _safe_float(value: Any | None) -> float | None:
    if value is None or value == "":
        return None
    try:
        return float(value)
    except (TypeError, ValueError):
        return None


def _status_reason(status: str) -> str:
    mapping = {
        "stale_cache": "使用运行时缓存，数据可能略滞后。",
        "seed_cache": "使用随包种子缓存，可作为低置信参考。",
        "stale_seed": "种子缓存已超过评分窗口，只展示不评分。",
        "web_cached": "使用网页快照，只展示不评分。",
        "source_error": "数据源请求失败，等待下一次刷新。",
        "proxy_required_unavailable": "当前网络可能需要代理，但未检测到可用代理。",
        "auth_missing": "数据源需要 API Key，当前未配置。",
        "rate_limited": "数据源限流，稍后可重试。",
        "parser_error": "数据源返回格式无法解析。",
        "unavailable_placeholder": "暂无可用数据，占位行不参与评分。",
        "disabled": "该数据源已禁用。",
        "not_implemented": "该数据源尚未接入。",
        "pending": "后台正在准备数据。",
        "missing": "暂无观测值。",
    }
    return mapping.get((status or "missing").lower(), "状态暂不可用。")
