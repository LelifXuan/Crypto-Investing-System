from __future__ import annotations

import json
from pathlib import Path
from typing import Any

REGISTRY_PATH = (
    Path(__file__).resolve().parents[2]
    / "monitoring"
    / "configs"
    / "btc_volatility_research_registry.v1.json"
)


def load_research_registry() -> dict[str, Any]:
    return json.loads(REGISTRY_PATH.read_text(encoding="utf-8"))
