"""Stable build identity for strategy construction jobs."""

from __future__ import annotations

import hashlib
import json
from dataclasses import dataclass
from typing import Any, Mapping


def _canonical_json(value: Mapping[str, Any]) -> str:
    return json.dumps(value, sort_keys=True, separators=(",", ":"), default=str)


def _stable_hash(value: Mapping[str, Any], *, prefix: str = "") -> str:
    digest = hashlib.sha256(_canonical_json(value).encode("utf-8")).hexdigest()
    return f"{prefix}{digest}"


@dataclass(frozen=True, slots=True)
class BuildKey:
    instrument: str
    source_watermark: str
    mode: str
    model_version: str
    code_version: str
    config_hash: str

    def as_dict(self) -> dict[str, str]:
        return {
            "instrument": self.instrument,
            "source_watermark": self.source_watermark,
            "mode": self.mode,
            "model_version": self.model_version,
            "code_version": self.code_version,
            "config_hash": self.config_hash,
        }

    @property
    def digest(self) -> str:
        return _stable_hash(self.as_dict(), prefix="build:")


def build_strategy_key(
    *,
    instrument: str,
    source_watermark: str,
    mode: str = "observe_only",
    model_version: str = "",
    code_version: str = "",
    config_hash: str = "",
) -> BuildKey:
    return BuildKey(
        instrument=instrument,
        source_watermark=source_watermark,
        mode=mode,
        model_version=model_version,
        code_version=code_version,
        config_hash=config_hash,
    )
