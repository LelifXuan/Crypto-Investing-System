from __future__ import annotations

import json
from dataclasses import asdict, dataclass
from typing import Any, Mapping

from app.core.paths import app_paths

REGISTRY_PATH = (
    app_paths.resource_root
    / "app"
    / "monitoring"
    / "configs"
    / "indicator_judgement_registry.v1.json"
)


@dataclass(frozen=True, slots=True)
class IndicatorJudgement:
    indicator_key: str
    timeframe: str
    value: Any
    axis: str
    state: str
    direction: str
    action_effect: str
    signal_role: str
    confidence: float
    freshness: str
    data_status: str
    reason: str
    invalidation: str
    next_check: str
    source_ref: str

    def as_dict(self) -> dict[str, Any]:
        return asdict(self)


def load_indicator_judgement_registry() -> dict[str, dict[str, Any]]:
    try:
        payload = json.loads(REGISTRY_PATH.read_text(encoding="utf-8"))
    except (OSError, json.JSONDecodeError):
        return {}
    return {
        str(item["indicator_key"]): dict(item)
        for item in payload.get("indicators", [])
        if isinstance(item, Mapping) and item.get("indicator_key")
    }


def registered_indicator_keys() -> set[str]:
    return set(load_indicator_judgement_registry())


def build_indicator_judgement(
    observation: Mapping[str, Any],
    *,
    timeframe: str = "unknown",
    freshness: str = "unknown",
    source_ref: str = "technical_signal_classifier",
) -> dict[str, Any]:
    """Attach semantic meaning without removing legacy signal fields.

    The registry decides whether an observation is directional. Presentation
    fields such as ``tone`` are deliberately ignored when resolving direction.
    """

    key = str(observation.get("indicator_key") or "unknown")
    spec = load_indicator_judgement_registry().get(key)
    if spec is None:
        return IndicatorJudgement(
            indicator_key=key,
            timeframe=timeframe,
            value=observation.get("value_num"),
            axis="data_quality",
            state="UNREGISTERED",
            direction="NONE",
            action_effect="OBSERVE",
            signal_role="data_quality",
            confidence=0.0,
            freshness=freshness,
            data_status="unregistered",
            reason="指标尚未登记语义，不允许参与综合方向计算。",
            invalidation="完成指标语义登记后重新计算。",
            next_check="registry_update",
            source_ref=source_ref,
        ).as_dict()

    legacy_state = str(observation.get("signal_state") or "unknown").lower()
    state_map = spec.get("state_map") or {}
    state = str(state_map.get(legacy_state) or legacy_state or "UNKNOWN").upper()
    data_status = "missing" if legacy_state in {"missing", "no_data", "unknown"} else "ready"
    direction = "NONE"
    if spec.get("directional") and data_status == "ready":
        direction = str((spec.get("direction_map") or {}).get(legacy_state) or "NONE").upper()
    action_map = spec.get("action_map") or {}
    action_effect = str(
        action_map.get(legacy_state) or spec.get("default_action_effect") or "OBSERVE"
    ).upper()
    confidence = float(
        observation.get("confidence")
        or (0 if data_status != "ready" else spec.get("default_confidence", 60))
    )
    return IndicatorJudgement(
        indicator_key=key,
        timeframe=timeframe,
        value=observation.get("value_num"),
        axis=str(spec.get("axis") or "data_quality"),
        state=state,
        direction=direction,
        action_effect=action_effect,
        signal_role=str(spec.get("signal_role") or "observe"),
        confidence=max(0.0, min(100.0, confidence)),
        freshness=freshness,
        data_status=data_status,
        reason=str(
            observation.get("comment") or observation.get("signal_label") or "等待更多证据。"
        ),
        invalidation=str(
            observation.get("invalidation")
            or spec.get("invalidation")
            or "指标状态发生变化时重新评估。"
        ),
        next_check=str(observation.get("next_check") or spec.get("next_check") or "next_close"),
        source_ref=source_ref,
    ).as_dict()


def attach_indicator_judgement(
    observation: Mapping[str, Any],
    *,
    timeframe: str = "unknown",
    freshness: str = "unknown",
    source_ref: str = "technical_signal_classifier",
) -> dict[str, Any]:
    payload = dict(observation)
    payload["indicator_judgement"] = build_indicator_judgement(
        payload,
        timeframe=timeframe,
        freshness=freshness,
        source_ref=source_ref,
    )
    return payload
