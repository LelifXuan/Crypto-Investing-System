from __future__ import annotations

from dataclasses import dataclass, field
from datetime import datetime, timezone
from typing import Any, Dict, Optional

from app.services.macro.secret_loader import redact


@dataclass
class AdapterResult:
    indicator_id: str
    source: str
    source_type: str
    value: Optional[float] = None
    previous_value: Optional[float] = None
    unit: Optional[str] = None
    latest_date: Optional[str] = None
    updated_at: str = field(default_factory=lambda: datetime.now(timezone.utc).isoformat())
    raw_period: Optional[str] = None
    status: str = "missing"
    status_reason: str = "未获取到有效数据"
    is_scored: bool = False
    score_block_reason: Optional[str] = "缺失有效数据，未参与评分。"
    latency_ms: Optional[int] = None
    cache_hit: bool = False
    source_url_safe: Optional[str] = None
    raw: Optional[Dict[str, Any]] = None

    def to_public_dict(self, include_raw: bool = False) -> Dict[str, Any]:
        import dataclasses
        d = dataclasses.asdict(self)
        if not include_raw:
            d.pop("raw", None)
        return redact(d)
