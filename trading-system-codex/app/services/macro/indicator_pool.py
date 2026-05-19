from __future__ import annotations

from dataclasses import dataclass, field
from datetime import datetime, timezone, date
from decimal import Decimal
from typing import Any, Optional

FRESHNESS_DAYS = {
    "intraday": 0.1, "daily": 3, "weekly": 14,
    "monthly": 45, "quarterly": 120, "fomc": 60, "irregular": 30,
}


@dataclass
class MacroIndicator:
    id: str
    module_id: str
    module_name_zh: str
    module_weight: float
    name_zh: str
    unit: str
    frequency: str
    priority: str
    source: str
    source_chain: list[dict] = field(default_factory=list)
    derived: Optional[dict] = None
    default_is_scored: bool = True
    value: Optional[float] = None
    previous_value: Optional[float] = None
    latest_date: Optional[str] = None
    updated_at: Optional[str] = None
    status: str = "missing"
    status_reason: str = "未获取到有效数据"
    is_scored: bool = False
    score_block_reason: Optional[str] = "缺失有效数据，未参与评分。"
    cache_hit: bool = False
    source_url_safe: Optional[str] = None
    insight: Optional[str] = None
    observation_ts: Optional[datetime] = None
    value_decimal: Optional[Decimal] = None

    @property
    def value_text(self) -> str | None:
        if self.value is None:
            return None
        return f"{self.value:.2f}{self.unit}"

    @classmethod
    def from_config(cls, config: dict) -> "MacroIndicator":
        source_chain = config.get("source_chain", [])
        primary_source = source_chain[0]["source"] if source_chain else "unknown"
        return cls(
            id=config["id"],
            module_id=config.get("module_id", ""),
            module_name_zh=config.get("module_name_zh", ""),
            module_weight=config.get("module_weight", 0),
            name_zh=config.get("name_zh", config["id"]),
            unit=config.get("unit", ""),
            frequency=config.get("frequency", "daily"),
            priority=config.get("priority", "should"),
            source=primary_source,
            source_chain=source_chain,
            derived=config.get("derived"),
            default_is_scored=config.get("default_is_scored", True),
        )


@dataclass
class MacroModuleSnapshot:
    id: str
    name_zh: str
    weight: float
    module_role: str
    indicators: list[MacroIndicator] = field(default_factory=list)
    module_score: Optional[float] = None
    module_contribution: float = 0.0
    effective_count: int = 0
    missing_count: int = 0
    stale_count: int = 0
    cached_count: int = 0
    disabled_count: int = 0
    total_count: int = 0
    is_scored: bool = False
    not_scored_reason: Optional[str] = None
    last_updated_at: Optional[str] = None
    summary: str = ""
    confidence: str = "insufficient"
    indicators_detail: list[dict] = field(default_factory=list)


@dataclass
class MacroSnapshot:
    score_base: float = 50.0
    modules: list[MacroModuleSnapshot] = field(default_factory=list)
    total_score: float = 50.0
    score_scale: str = "0-100，50 为中性"
    score_band: str = "中性"
    score_explanation: str = ""
    confidence: str = "insufficient"
    data_completeness: dict = field(default_factory=lambda: {"effective_count": 0, "total_count": 0, "ratio": 0.0})
    operation_bias: str = "观望"
    regime_label_cn: str = "数据不足"
    regime_summary: str = ""
    event_window_summary: Optional[str] = None
    event_items: list[dict] = field(default_factory=list)
    warnings: list[str] = field(default_factory=list)
    next_event: Optional[dict] = None
    generated_at: str = field(default_factory=lambda: datetime.now(timezone.utc).isoformat())


def classify_indicator_status(value, latest_date, frequency, now=None) -> tuple[str, str]:
    if value is None:
        return "missing", "未获取到有效数据"
    if not latest_date:
        return "missing", "缺少数据日期"
    now = now or datetime.now(timezone.utc)
    try:
        obs_date = date.fromisoformat(str(latest_date)[:10])
    except ValueError:
        return "missing", "无法解析数据日期"
    max_age = FRESHNESS_DAYS.get(frequency, 30)
    age_days = (now.date() - obs_date).days
    if age_days > max_age:
        return "stale", f"数据已超过允许新鲜度窗口：{age_days} 天 > {max_age} 天"
    return "ok", "数据正常"


def classify_confidence(effective_count: int, total_count: int) -> str:
    if total_count <= 0:
        return "insufficient"
    ratio = effective_count / total_count
    if ratio >= 0.75:
        return "high"
    if ratio >= 0.50:
        return "medium"
    if ratio >= 0.25:
        return "low"
    return "insufficient"


def build_score_explanation(score_base: float, contributions: list[tuple[str, float]]) -> str:
    parts = [f"宏观总分 = {score_base:g} 中性基准"]
    for name, contribution in contributions:
        sign = "+" if contribution >= 0 else "-"
        parts.append(f"{sign} {abs(contribution):.1f} {name}贡献")
    return " ".join(parts)
