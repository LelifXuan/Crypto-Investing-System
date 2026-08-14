from __future__ import annotations

import json
from dataclasses import dataclass
from typing import Any

from app.core.paths import app_paths
from app.schemas.market import MacroOverviewIndicatorRead
from app.services.macro.indicator_key_aliases import canonical_macro_key

DEFAULT_REGISTRY_PATH = (
    app_paths.resource_root
    / "app"
    / "monitoring"
    / "configs"
    / "macro_scoring_registry.v1.json"
)


@dataclass(frozen=True)
class MacroScoreResult:
    indicator_key: str
    canonical_key: str
    score: int | None
    is_scored: bool
    formula_id: str | None
    reason: str | None = None


def _clamp01(value: float) -> float:
    return max(0.0, min(1.0, value))


def _direct(value: float, low: float, high: float) -> int:
    if high == low:
        return 50
    return round(_clamp01((value - low) / (high - low)) * 100)


def _inverse(value: float, low: float, high: float) -> int:
    return 100 - _direct(value, low, high)


def _range_mid(value: float, low: float, high: float) -> int:
    if high == low:
        return 50
    midpoint = (low + high) / 2
    radius = abs(high - low) / 2
    return round((1 - _clamp01(abs(value - midpoint) / radius)) * 100)


def _range_score(value: float, bearish_below: float, bullish_above: float) -> int:
    return _direct(value, bearish_below, bullish_above)


class MacroScoringEngine:
    """Registry-driven macro scoring with unit-specific fallbacks.

    The registry is the primary source. A small override table keeps the
    scoring safe for important indicators that were absent or previously
    grouped with the wrong unit family.
    """

    UNIT_SAFE_OVERRIDES: dict[str, dict[str, Any]] = {
        "usd_cny": {
            "formula_id": "inverse_linear",
            "thresholds": {"low": 6.80, "high": 7.45},
            "unit": "CNY per USD",
        },
        "initial_claims": {
            "formula_id": "inverse_linear",
            "thresholds": {"low": 180_000, "high": 400_000},
            "unit": "count",
        },
        "continuing_claims": {
            "formula_id": "inverse_linear",
            "thresholds": {"low": 1_500_000, "high": 2_300_000},
            "unit": "count",
        },
        "vix": {
            "formula_id": "inverse_linear",
            "thresholds": {"low": 15.0, "high": 28.0},
            "unit": "index",
        },
    }

    EVENT_SCORES = {
        "inactive": 50,
        "clear": 50,
        "pre_event": 25,
        "post_event": 35,
        "live_event": 20,
        "event_wait": 25,
        "block": 20,
    }

    def __init__(self, registry: dict[str, Any]) -> None:
        self.registry = registry
        self._rules = self._build_rules(registry)

    @classmethod
    def load_default(cls) -> "MacroScoringEngine":
        return cls(json.loads(DEFAULT_REGISTRY_PATH.read_text(encoding="utf-8")))

    @staticmethod
    def _build_rules(registry: dict[str, Any]) -> dict[str, dict[str, Any]]:
        rules: dict[str, dict[str, Any]] = {}
        for item in registry.get("indicators") or []:
            key = str(item.get("indicator_key") or "").strip()
            if not key:
                continue
            all_keys = {key, *(item.get("aliases") or [])}
            for raw_key in all_keys:
                rules[canonical_macro_key(str(raw_key))] = dict(item)
        for key, value in MacroScoringEngine.UNIT_SAFE_OVERRIDES.items():
            rules[key] = {**rules.get(key, {}), **value, "indicator_key": key}
        rules.setdefault(
            "fomc_event_window",
            {
                "indicator_key": "fomc_event_window",
                "formula_id": "event_window_penalty",
                "unit": "state",
            },
        )
        return rules

    def score(self, item: MacroOverviewIndicatorRead) -> MacroScoreResult:
        orig_key = item.indicator_key
        canonical_key = canonical_macro_key(orig_key)
        rule = self._rules.get(canonical_key)
        formula = str(rule.get("formula_id") or "") if rule else None
        if rule and rule.get("scoring_policy") == "display_only":
            return MacroScoreResult(
                orig_key, canonical_key, None, False, formula, "display_only"
            )

        if formula == "event_window_penalty":
            state = str(item.value_text or item.signal_state or "").strip().lower()
            return MacroScoreResult(
                indicator_key=orig_key,
                canonical_key=canonical_key,
                score=self.EVENT_SCORES.get(state, 50),
                is_scored=True,
                formula_id=formula,
            )

        if item.value_num is None:
            return MacroScoreResult(orig_key, canonical_key, None, False, formula, "missing_value")
        if item.value_text is not None:
            return MacroScoreResult(orig_key, canonical_key, None, False, formula, "text_value")
        if not rule:
            return MacroScoreResult(
                orig_key, canonical_key, None, False, None, "registry_rule_missing"
            )

        value = float(item.value_num)
        thresholds = rule.get("thresholds") or {}
        if formula in {"momentum_20d", "mom_pct"}:
            history = self._history_values(item)
            if len(history) < 5:
                return MacroScoreResult(
                    orig_key, canonical_key, None, False, formula, "history_insufficient"
                )
            base = sum(history[:5]) / min(5, len(history))
            if base <= 0:
                return MacroScoreResult(
                    orig_key, canonical_key, None, False, formula, "invalid_history"
                )
            pct = (value - base) / base * 100
            if pct > 8:
                score = 80
            elif pct > 3:
                score = 65
            elif pct < -8:
                score = 20
            elif pct < -3:
                score = 35
            else:
                score = 50
            return MacroScoreResult(orig_key, canonical_key, score, True, formula)

        if formula == "inverse_linear":
            score = _inverse(value, float(thresholds["low"]), float(thresholds["high"]))
        elif formula == "direct_linear":
            score = _direct(value, float(thresholds["low"]), float(thresholds["high"]))
        elif formula == "range_mid":
            score = _range_mid(value, float(thresholds["low"]), float(thresholds["high"]))
        elif formula == "range_score":
            score = _range_score(
                value,
                float(thresholds.get("bearish_below", thresholds.get("low", 0))),
                float(thresholds.get("bullish_above", thresholds.get("high", 100))),
            )
        else:
            score = 50

        return MacroScoreResult(orig_key, canonical_key, max(0, min(100, score)), True, formula)

    @staticmethod
    def _history_values(item: MacroOverviewIndicatorRead) -> list[float]:
        payload = getattr(item, "value_json", None)
        if not isinstance(payload, dict):
            return []
        raw_history = payload.get("history") or payload.get("values") or []
        values: list[float] = []
        if isinstance(raw_history, list):
            for raw in raw_history:
                if isinstance(raw, dict):
                    raw = raw.get("value") or raw.get("close")
                try:
                    values.append(float(raw))
                except (TypeError, ValueError):
                    continue
        return values


DEFAULT_MACRO_SCORING_ENGINE = MacroScoringEngine.load_default()
