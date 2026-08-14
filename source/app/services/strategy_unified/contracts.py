# ruff: noqa: E501
from __future__ import annotations

from dataclasses import asdict, dataclass, field
from datetime import UTC, datetime
from hashlib import sha256
from typing import Any, Mapping, Sequence


@dataclass(frozen=True)
class TimeframeSpec:
    logical: str
    cache: str
    role: str
    role_label: str
    horizon: str
    weight_group: str


TIMEFRAME_SPECS: tuple[TimeframeSpec, ...] = (
    TimeframeSpec("1M", "30d", "strategic_background", "月线战略背景", "1Y-3Y", "strategic"),
    TimeframeSpec("1w", "1w", "strategic_structure", "周线战略结构", "3M-18M", "strategic"),
    TimeframeSpec("1d", "1d", "tactical_trend", "日线战术趋势", "1W-8W", "tactical"),
    TimeframeSpec("4h", "4h", "trade_structure", "4H 交易结构", "2D-3W", "tactical_execution"),
    TimeframeSpec("1h", "1h", "entry_trigger", "1H 入场触发", "1D-5D", "execution"),
    TimeframeSpec("15m", "15m", "execution_filter", "15M 执行过滤", "intraday", "execution"),
)

STRATEGIC_WEIGHTS = {"1M": 0.45, "1w": 0.55}
TACTICAL_WEIGHTS = {"1d": 0.62, "4h": 0.38}
EXECUTION_WEIGHTS = {"1h": 0.7, "15m": 0.3}
LONG_THRESHOLD = 58.0
SHORT_THRESHOLD = 58.0
MIN_DIRECTION_GAP = 8.0
DATA_BLOCK_MISSING_CORE_COUNT = 3

UNIFIED_LABELS = {
    "STRATEGIC_LONG_TACTICAL_LONG": "顺周期多头",
    "STRATEGIC_LONG_TACTICAL_SHORT": "短空长多",
    "STRATEGIC_SHORT_TACTICAL_SHORT": "顺周期空头",
    "STRATEGIC_SHORT_TACTICAL_LONG": "空头趋势中的战术反弹",
    "STRATEGIC_ACCUMULATION_TACTICAL_DISTRIBUTION": "战略吸筹区内的战术派发",
    "RANGE_NO_EDGE": "多周期中性震荡",
    "EVENT_LOCKED": "事件锁定",
    "DATA_DEGRADED": "数据质量不足",
    "RISK_OFF": "风险关闭",
}


@dataclass(slots=True)
class EvidenceItem:
    conclusion_key: str
    conclusion: str
    source_modules: list[str] = field(default_factory=list)
    source_timeframes: list[str] = field(default_factory=list)
    calculation_rule: str = ""
    input_features: list[str] = field(default_factory=list)
    confidence: float = 0.0
    freshness: str = "unknown"
    human_explanation: str = ""

    def as_dict(self) -> dict[str, Any]:
        return asdict(self)


@dataclass(slots=True)
class MarketDimension:
    key: str
    label: str
    state: str
    bias: str
    horizon_impact: list[str]
    score: float
    confidence: float
    evidence: list[str] = field(default_factory=list)
    source_modules: list[str] = field(default_factory=list)
    freshness: str = "unknown"
    details: dict[str, Any] = field(default_factory=dict)

    def as_dict(self) -> dict[str, Any]:
        return asdict(self)


@dataclass(slots=True)
class TimeframeNode:
    timeframe: str
    cache_timeframe: str
    role: str
    role_label: str
    horizon: str
    direction: str
    bias: str
    structure_state: str
    state: str
    long_score: float
    short_score: float
    neutral_score: float
    confidence: float
    current_price: float | None
    key_support: float | None
    key_resistance: float | None
    invalidation: float | None
    timeframe_state: str = "DATA_UNAVAILABLE"
    range_state: str = "NONE"
    range_label: str = ""
    range_score: float = 0.0
    range_basis: list[str] = field(default_factory=list)
    range_conflicts: list[str] = field(default_factory=list)
    verdict_code: str = "RANGE_NO_EDGE"
    verdict_label: str = "多周期中性震荡"
    evidence: list[str] = field(default_factory=list)
    source_modules: list[str] = field(default_factory=list)
    freshness: str = "unknown"
    data_quality: dict[str, Any] = field(default_factory=dict)
    raw_status: dict[str, Any] = field(default_factory=dict)

    def as_dict(self) -> dict[str, Any]:
        return asdict(self)


@dataclass(slots=True)
class HorizonView:
    key: str
    label: str
    horizon: str
    source_timeframes: list[str]
    direction: str
    state: str
    instruction: str
    long_score: float
    short_score: float
    confidence: float
    evidence: list[str] = field(default_factory=list)
    source_modules: list[str] = field(default_factory=list)

    def as_dict(self) -> dict[str, Any]:
        return asdict(self)


@dataclass(slots=True)
class HorizonGovernance:
    higher_timeframe_constraint: dict[str, Any]
    lower_timeframe_driver: dict[str, Any]
    position_cap: str
    allowed_sides: list[str]
    upgrade_path: list[str]
    invalidation_path: list[str]

    def as_dict(self) -> dict[str, Any]:
        return asdict(self)


@dataclass(slots=True)
class RiskAlert:
    category: str
    severity: str
    label: str
    message: str
    action: str
    affected_horizons: list[str] = field(default_factory=list)
    source_module: str = ""
    id: str = ""
    key: str = ""

    def as_dict(self) -> dict[str, Any]:
        payload = asdict(self)
        stable_key = self.key or f"{self.category}:{self.severity}:{self.label}:{self.source_module}"
        payload["key"] = stable_key
        payload["id"] = self.id or stable_key
        return payload


@dataclass(slots=True)
class TradePlan:
    id: str
    type: str
    plan_type: str
    label: str
    title: str
    direction: str
    horizon: str
    source_timeframes: list[str]
    entry_logic: str
    entry_zone: list[float]
    stop_loss: float | None
    take_profit: list[dict[str, Any]]
    take_profit_text: str
    invalidation: str
    position_rule: str
    permission: str
    evidence: list[str] = field(default_factory=list)
    trigger: dict[str, Any] = field(default_factory=dict)
    risk_reward: dict[str, Any] = field(default_factory=dict)
    recommended_leverage: float = 0.0
    max_leverage: float = 0.0
    leverage_status: str = "blocked"
    leverage_reason: str = "当前计划不建议使用杠杆。"
    order_type: str = "NONE"
    order_status: str = "NO_DIRECTION"
    execution_price: float | None = None
    limit_price: float | None = None
    conflict_timeframe: str = ""
    confirmation_timeframe: str = ""
    filter_timeframe: str = ""
    price_condition: str = ""
    confirmation_condition: str = ""
    activation_conditions: list[str] = field(default_factory=list)
    price_protection: dict[str, Any] = field(default_factory=dict)
    valid_until: str = ""
    valid_until_iso: str = ""
    # V1.7.x: Stale-plan awareness copy of the same fields on TradeDecision.
    # Surface the same distance / stale info on the per-plan row so the
    # execution plan table can show "距离触发 +N%" without recomputing.
    plan_distance_pct: float = 0.0
    plan_stale_score: int = 0
    plan_stale_reason: str = ""
    planned_leverage: float = 0.0
    trade_timeframe: str = "4h"
    direction_timeframes: list[str] = field(default_factory=lambda: ["1d", "4h"])
    execution_timeframes: list[str] = field(default_factory=lambda: ["1h", "15m"])
    lifecycle_state: str = "SETUP_DETECTED"
    activated_at: str = ""
    invalidated_at: str = ""
    invalidation_reason: str = ""
    levels_active: bool = True

    def as_dict(self) -> dict[str, Any]:
        return asdict(self)


def now_iso() -> str:
    return datetime.now(UTC).isoformat()


def as_mapping(value: Any) -> dict[str, Any]:
    if isinstance(value, Mapping):
        return dict(value)
    if hasattr(value, "model_dump"):
        try:
            return dict(value.model_dump(mode="json"))
        except Exception:
            return {}
    if hasattr(value, "__dict__"):
        return dict(getattr(value, "__dict__", {}) or {})
    return {}


def get_value(value: Any, key: str, default: Any = None) -> Any:
    if isinstance(value, Mapping):
        return value.get(key, default)
    return getattr(value, key, default)


def nested(value: Any, *keys: str, default: Any = None) -> Any:
    current = value
    for key in keys:
        current = get_value(current, key, default=None)
        if current is None:
            return default
    return current


def to_float(value: Any, default: float = 0.0) -> float:
    if value is None or value == "":
        return default
    try:
        return float(value)
    except (TypeError, ValueError):
        return default


def first_float(*values: Any) -> float | None:
    for value in values:
        if value is None or value == "":
            continue
        try:
            return float(value)
        except (TypeError, ValueError):
            continue
    return None


def list_floats(value: Any) -> list[float]:
    if value is None:
        return []
    if isinstance(value, (list, tuple, set)):
        return [parsed for item in value if (parsed := first_float(item)) is not None]
    parsed = first_float(value)
    return [] if parsed is None else [parsed]


def clamp(value: Any, low: float = 0.0, high: float = 100.0) -> float:
    return max(low, min(high, to_float(value, default=low)))


def uniq(values: Sequence[Any]) -> list[str]:
    seen: set[str] = set()
    out: list[str] = []
    for item in values:
        text = str(item or "").strip()
        if not text or text in seen:
            continue
        seen.add(text)
        out.append(text)
    return out


def direction_from_scores(long_score: float, short_score: float) -> str:
    if long_score >= LONG_THRESHOLD and long_score - short_score >= MIN_DIRECTION_GAP:
        return "LONG"
    if short_score >= SHORT_THRESHOLD and short_score - long_score >= MIN_DIRECTION_GAP:
        return "SHORT"
    return "NEUTRAL"


def weighted(nodes: Sequence[TimeframeNode], weights: Mapping[str, float], attr: str) -> float:
    numerator = 0.0
    denominator = 0.0
    for node in nodes:
        weight = weights.get(node.timeframe, 0.0)
        numerator += to_float(getattr(node, attr), 0.0) * weight
        denominator += weight
    return round(numerator / denominator, 2) if denominator > 0 else 0.0


def price_zone(*values: Any) -> list[float]:
    parsed = [value for value in (first_float(v) for v in values) if value is not None]
    if not parsed:
        return []
    if len(parsed) == 1:
        return [round(parsed[0], 2)]
    return [round(min(parsed), 2), round(max(parsed), 2)]


def freshness_from_context(context: Any, bundle: Mapping[str, Any] | None = None) -> str:
    bundle = bundle or {}
    for candidate in (
        bundle.get("freshness_state"),
        bundle.get("cache_state"),
        nested(context, "cache_meta", "cache_state"),
        nested(context, "cache_meta", "freshness_state"),
    ):
        if candidate:
            return str(candidate)
    return "unknown"


def node_by_tf(nodes: Sequence[TimeframeNode], timeframe: str) -> TimeframeNode | None:
    for node in nodes:
        if node.timeframe == timeframe:
            return node
    return None


def dict_payload(value: Any) -> Any:
    if hasattr(value, "as_dict"):
        return value.as_dict()
    if isinstance(value, dict):
        return {k: dict_payload(v) for k, v in value.items()}
    if isinstance(value, list):
        return [dict_payload(v) for v in value]
    if isinstance(value, tuple):
        return [dict_payload(v) for v in value]
    return value


def payload_hash(payload: Mapping[str, Any]) -> str:
    source = repr(sorted((str(k), str(v)) for k, v in payload.items()))
    return sha256(source.encode("utf-8")).hexdigest()[:16]


# Map ``MultiTimeframeStructureEngine`` raw states (from data_loader fallback) to
# the 8 canonical verdict codes. ``NO_EDGE`` and ``CONTEXT_NEUTRAL`` collapse to
# ``RANGE_NO_EDGE``; ``CONTEXT_LONG``/``CONTEXT_SHORT`` map to the strategic pair
# when the timeframe is in STRATEGIC_WEIGHTS, otherwise to a tactical-aligned code.
VERDICT_FROM_STATE: dict[str, str] = {
    "NO_EDGE": "RANGE_NO_EDGE",
    "CONTEXT_NEUTRAL": "RANGE_NO_EDGE",
    "CONTEXT_MISSING": "DATA_DEGRADED",
    "CONTEXT_LONG": "STRATEGIC_LONG_TACTICAL_LONG",
    "CONTEXT_SHORT": "STRATEGIC_SHORT_TACTICAL_SHORT",
    "READY_LONG": "STRATEGIC_LONG_TACTICAL_LONG",
    "READY_SHORT": "STRATEGIC_SHORT_TACTICAL_SHORT",
    "READY_NEUTRAL": "RANGE_NO_EDGE",
    "EVENT_LOCKED": "EVENT_LOCKED",
    "RISK_OFF": "RISK_OFF",
    "DATA_DEGRADED": "DATA_DEGRADED",
}


def pick_context(
    contexts: Mapping[str, Any],
    primary: str,
    fallback: Sequence[str] = (),
) -> dict[str, Any]:
    """Return the first usable ``context`` snapshot.

    A context is "usable" when its ``cache_meta.cache_state`` is not in
    ``{missing, error, updating}``. The primary timeframe wins when usable;
    otherwise we walk the fallback list. Empty dict means no context was
    available, which downstream engines translate to ``DATA_MISSING``.

    Contexts may be plain dicts (production) or ``SimpleNamespace`` (tests);
    ``as_mapping`` normalises both into a dict snapshot.
    """
    bad_states = {"missing", "error", "updating"}

    def _is_usable(ctx: Any) -> bool:
        if not ctx:
            return False
        cache_state = str(nested(ctx, "cache_meta", "cache_state") or "").lower()
        return cache_state not in bad_states

    for tf in (primary, *fallback):
        candidate = contexts.get(tf)
        if candidate is None:
            continue
        if not isinstance(candidate, Mapping):
            candidate = as_mapping(candidate)
        if _is_usable(candidate):
            return dict(candidate)
    primary_ctx = contexts.get(primary)
    if primary_ctx is not None and not isinstance(primary_ctx, Mapping):
        primary_ctx = as_mapping(primary_ctx)
    if isinstance(primary_ctx, Mapping):
        return dict(primary_ctx)
    return {}


def verdict_for_node(state: str, direction: str, timeframe: str) -> str:
    """Resolve the verdict code for a timeframe node.

    Uses ``VERDICT_FROM_STATE`` for the 8 canonical codes and patches in
    tactical-aligned codes when the timeframe is a tactical TF and the
    direction is aligned but the state is the raw CONTEXT_* variant.
    """
    code = VERDICT_FROM_STATE.get(str(state or "").upper(), "RANGE_NO_EDGE")
    if code in {"STRATEGIC_LONG_TACTICAL_LONG"} and timeframe in {"4h", "1h", "15m"}:
        return "CONTEXT_ALIGNED_LONG"
    if code in {"STRATEGIC_SHORT_TACTICAL_SHORT"} and timeframe in {"4h", "1h", "15m"}:
        return "CONTEXT_ALIGNED_SHORT"
    if code == "RANGE_NO_EDGE" and direction in {"LONG", "SHORT"}:
        return "CONTEXT_ALIGNED_LONG" if direction == "LONG" else "CONTEXT_ALIGNED_SHORT"
    return code


def evidence_confidence(
    *,
    freshness: str,
    consistency: float,
    coverage: float,
) -> float:
    """Single confidence source for ``EvidenceTraceBuilder``.

    Combines three orthogonal factors:
    - freshness: maps ``fresh / ready / usable_stale / stale / missing / error``
      to a base score in ``[0, 1]``.
    - consistency: agreement ratio ``[0, 1]`` (1 = all sources agree).
    - coverage: ratio of inputs that produced a value ``[0, 1]``.
    Final score is rounded to 2 decimals; clamped to ``[0, 100]``.
    """
    freshness_score = {
        "fresh": 1.0,
        "ready": 0.95,
        "usable_stale": 0.7,
        "live": 0.95,
        "degraded": 0.55,
        "stale": 0.4,
        "missing": 0.0,
        "error": 0.0,
        "updating": 0.3,
    }.get(str(freshness or "").lower(), 0.5)
    consistency = max(0.0, min(1.0, float(consistency or 0.0)))
    coverage = max(0.0, min(1.0, float(coverage or 0.0)))
    combined = freshness_score * (0.55 + 0.25 * consistency + 0.20 * coverage)
    return round(max(0.0, min(100.0, combined * 100.0)), 2)
