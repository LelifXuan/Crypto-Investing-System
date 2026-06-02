from __future__ import annotations

import logging
from datetime import datetime, timezone
from typing import Any

from app.repositories.market_repository import MarketRepository
from app.services.market_data_bundle import MarketDataBundleService

logger = logging.getLogger(__name__)

PRIMARY_TIMEFRAMES = ("1w", "1d", "4h", "1h")
TIMEFRAME_LABELS = {"1w": "1W", "1d": "1D", "4h": "4H", "1h": "1H"}


class ChipStructureService:
    """Stable chip-structure facade for alerts and strategy aggregation.

    The heavy historical implementation was corrupted by mojibake in multiple string blocks.
    This version keeps the public payload stable, stays GET-safe by reading cached market data,
    and applies conservative futures gating until richer microstructure evidence is available.
    """

    def __init__(self, repository: MarketRepository) -> None:
        self.repository = repository
        self.market_data = MarketDataBundleService(repository)

    async def analyze(self, instrument_id: str, timeframe: str) -> dict[str, Any]:
        normalized_timeframe = self._normalize_timeframe(timeframe)
        candles = await self._load_candles(instrument_id, normalized_timeframe)
        if len(candles) < 20:
            return self._missing_payload(instrument_id, normalized_timeframe, candles)

        first_close = self._field(candles[0], "close", 0.0)
        latest_close = self._field(candles[-1], "close", first_close)
        change_pct = (latest_close - first_close) / max(abs(first_close), 1.0) * 100
        direction_score = max(min(change_pct * 4, 100), -100)
        primary_regime = self._primary_regime(direction_score)
        state_label = "状态置信较低"
        evidence_quality = "proxy_only"
        evidence_quality_label = "证据不足（仅 K 线涨跌 proxy）"
        risk_score = 45.0 if abs(direction_score) >= 20 else 55.0
        direction_label = (
            "bullish" if direction_score > 15 else "bearish" if direction_score < -15 else "neutral"
        )
        recommended_action = "wait_confirmation" if abs(direction_score) >= 15 else "observe_only"
        generated_at = datetime.now(timezone.utc)
        futures_reason = "缺少 CVD、OI、盘口深度和滑点等微观结构确认，合约默认不建议开仓。"

        return {
            "instrument_id": instrument_id,
            "timeframe": normalized_timeframe,
            "state": "low_confidence",
            "state_label": state_label,
            "state_reason": "当前结果主要基于 K 线与基础价格结构，微观结构证据不足已计入置信度。",
            "primary_regime": primary_regime,
            "primary_regime_label": self._regime_label(primary_regime),
            "secondary_regime": "confirmation_wait",
            "evidence_quality": evidence_quality,
            "evidence_quality_label": evidence_quality_label,
            "direction_score_scale": "signed",
            "weekly_context": "高周期需要结合结构页快照确认。",
            "daily_bias": "日线方向以缓存 K 线变化作为 proxy。",
            "h4_structure": "4H 结构等待成交量与摆动确认。",
            "h1_confirmation": "1H 仅作为短线触发参考。",
            "direction_score": round(direction_score, 2),
            "direction_label": direction_label,
            "confidence_score": 35.0,
            "confidence_label": "low",
            "execution_score": 40.0,
            "execution_label": "pending",
            "state_confidence_label": state_label,
            "execution_quality_label": "盘口执行待确认",
            "entry_trigger_label": "交易触发待定",
            "risk_score": risk_score,
            "risk_label": "elevated",
            "confidence_cap": 55.0,
            "conflict_level": 1,
            "position_multiplier": 0.0,
            "capital_allocation_pct_min": 0.0,
            "capital_allocation_pct_max": 5.0,
            "capital_allocation_label": "0% - 5%",
            "position_sizing_reason": "仍需确认，最多只适合小额观察。",
            "spot_allocation_pct_min": 0.0,
            "spot_allocation_pct_max": 5.0,
            "futures_allocation_pct_min": 0.0,
            "futures_allocation_pct_max": 0.0,
            "probe_position_pct_max": 0.0,
            "spot_allocation_label": "0% - 5%",
            "futures_allocation_label": "0%",
            "probe_position_label": "0%",
            "allocation_reason": futures_reason,
            "direction_permission": "observe_only",
            "capital_ceiling_pct": 5.0,
            "execution_readiness": "pending",
            "recommended_action": recommended_action,
            "recommended_action_v2": "observe",
            "entry_confirmation_required": [
                "等待结构突破或回踩确认。",
                "等待成交量、CVD 或 OI 至少一项同步确认。",
            ],
            "invalidation_conditions": [
                "价格重新回到关键区间内部。",
                "短周期方向与高周期结构重新冲突。",
            ],
            "risk_notes": [
                "当前微观结构输入不足，单一结论可信度较低。",
                futures_reason,
            ],
            "data_quality": {
                "status": "partial",
                "score": 0.55,
                "issues": ["microstructure_missing"],
                "can_analyze": True,
                "can_alert": False,
            },
            "missing_inputs": [
                "OI 尚未同步",
                "CVD / Delta 尚未同步",
                "depth 尚未同步",
                "slippage / spread 尚未同步",
            ],
            "evidence": [
                {
                    "key": "price_change",
                    "label": "区间涨跌",
                    "value": f"{round(change_pct, 2)}%",
                    "impact": "neutral",
                    "summary": f"当前周期起止涨跌约 {round(change_pct, 2)}%",
                },
                {
                    "key": "latest_close",
                    "label": "最新收盘",
                    "value": self._fmt(latest_close),
                    "impact": "low",
                    "summary": f"最新收盘价 {self._fmt(latest_close)}",
                },
            ],
            "risk_gates": ["MICROSTRUCTURE_MISSING"],
            "allow_futures_long": False,
            "futures_gate_checks": [
                {"label": "微观结构证据", "passed": False, "reason": "CVD/OI/盘口数据不足"},
                {"label": "交易触发", "passed": False, "reason": "尚未形成明确触发"},
            ],
            "failed_gate_reasons": [futures_reason],
            "why_no_futures_long": futures_reason,
            "components": {
                "price_change_pct": round(change_pct, 2),
                "latest_close": round(latest_close, 2),
            },
            "explain": [
                "筹码结构证据不足，当前置信度受限。",
                "方向只作为市场状态参考，不直接构成合约开仓许可。",
            ],
            "timeframes": [
                {
                    "timeframe": TIMEFRAME_LABELS.get(normalized_timeframe, normalized_timeframe),
                    "regime": direction_label,
                    "bias": direction_label,
                    "range_position": "unknown",
                    "summary": "缓存 K 线可用，微观结构待补齐。",
                    "confidence_score": 0.55,
                    "status": "low_confidence",
                    "evidence": [f"分析样本数 {len(candles)} 根。"],
                }
            ],
            "generated_at": generated_at,
        }

    async def _load_candles(self, instrument_id: str, timeframe: str) -> list[Any]:
        try:
            bundle = await self.market_data.get_bundle(
                instrument_id=instrument_id,
                timeframe=timeframe,
                limit=240,
                allow_stale=True,
                refresh=False,
            )
        except Exception:
            logger.warning("market data bundle failed, candles empty", exc_info=True)
            return []
        if isinstance(bundle, dict):
            candles = bundle.get("candles", [])
            return list(candles) if isinstance(candles, list) else []
        candles = getattr(bundle, "candles", None)
        return list(candles) if isinstance(candles, list) else []

    def _missing_payload(
        self,
        instrument_id: str,
        timeframe: str,
        candles: list[Any],
    ) -> dict[str, Any]:
        reason = "本地可用 K 线不足，当前置信度为 0，仅作为占位观察。"
        return {
            "instrument_id": instrument_id,
            "timeframe": timeframe,
            "state": "missing",
            "state_label": "信息缺失",
            "state_reason": reason,
            "primary_regime": "no_signal",
            "primary_regime_label": "无信号",
            "secondary_regime": "data_missing",
            "evidence_quality": "proxy_only",
            "evidence_quality_label": "证据不足（缺少 K 线）",
            "direction_score_scale": "signed",
            "weekly_context": reason,
            "daily_bias": reason,
            "h4_structure": reason,
            "h1_confirmation": reason,
            "direction_score": 0.0,
            "direction_label": "neutral",
            "confidence_score": 0.0,
            "confidence_label": "invalid",
            "execution_score": 0.0,
            "execution_label": "blocked",
            "state_confidence_label": "信息缺失",
            "execution_quality_label": "盘口信息不可用",
            "entry_trigger_label": "无交易触发",
            "risk_score": 100.0,
            "risk_label": "extreme",
            "confidence_cap": 0.0,
            "conflict_level": 3,
            "position_multiplier": 0.0,
            "capital_allocation_pct_min": 0.0,
            "capital_allocation_pct_max": 0.0,
            "capital_allocation_label": "0%",
            "position_sizing_reason": reason,
            "spot_allocation_pct_min": 0.0,
            "spot_allocation_pct_max": 0.0,
            "futures_allocation_pct_min": 0.0,
            "futures_allocation_pct_max": 0.0,
            "probe_position_pct_max": 0.0,
            "spot_allocation_label": "0%",
            "futures_allocation_label": "0%",
            "probe_position_label": "0%",
            "allocation_reason": "无可用数据时默认不参与。",
            "direction_permission": "blocked",
            "capital_ceiling_pct": 0.0,
            "execution_readiness": "blocked",
            "recommended_action": "risk_off",
            "recommended_action_v2": "no_trade",
            "entry_confirmation_required": ["等待预计算补齐 K 线与结构快照。"],
            "invalidation_conditions": ["数据仍不可用时继续保持空仓观察。"],
            "risk_notes": [reason],
            "data_quality": {
                "status": "missing",
                "score": 0.0,
                "issues": ["candles_missing"],
                "can_analyze": False,
                "can_alert": False,
            },
            "missing_inputs": ["K 线样本不足", "微观结构未同步"],
            "evidence": [],
            "risk_gates": ["NO_USABLE_CANDLES"],
            "allow_futures_long": False,
            "futures_gate_checks": [],
            "failed_gate_reasons": [reason],
            "why_no_futures_long": reason,
            "components": {},
            "explain": [reason],
            "timeframes": [
                {
                    "timeframe": TIMEFRAME_LABELS.get(timeframe, timeframe),
                    "regime": "neutral",
                    "bias": "neutral",
                    "range_position": "missing",
                    "summary": reason,
                    "confidence_score": 0.0,
                    "status": "missing",
                    "evidence": [f"当前已加载 {len(candles)} 根 K 线。"],
                }
            ],
            "generated_at": datetime.now(timezone.utc),
        }

    @staticmethod
    def _field(item: Any, key: str, default: float = 0.0) -> float:
        if isinstance(item, dict):
            value = item.get(key, default)
        else:
            value = getattr(item, key, default)
        try:
            return float(value)
        except (TypeError, ValueError):
            return default

    @staticmethod
    def _primary_regime(direction_score: float) -> str:
        if direction_score >= 20:
            return "accumulation_proxy"
        if direction_score <= -20:
            return "distribution_proxy"
        return "balanced_auction"

    REGIME_LABELS = {
        "accumulation_proxy": "积累倾向",
        "distribution_proxy": "派发倾向",
        "balanced_auction": "均衡状态",
        "accumulation_confirmed": "积累确认",
        "distribution_confirmed": "派发确认",
        "distribution_candidate": "派发候选",
        "bullish_continuation_range": "偏多延续",
        "bearish_continuation_range": "偏空延续",
        "false_breakout": "假突破",
        "false_breakdown": "假跌破",
        "liquidity_drought": "流动性枯竭",
        "leverage_compression": "杠杆压缩",
        "no_signal": "无信号",
        "missing": "数据缺失",
    }

    @staticmethod
    def _regime_label(regime: str) -> str:
        return ChipStructureService.REGIME_LABELS.get(regime, regime)

    @staticmethod
    def _normalize_timeframe(timeframe: str) -> str:
        value = str(timeframe or "1h").lower()
        return "30d" if value in {"1m", "30d"} else value

    @staticmethod
    def _fmt(value: float | None, digits: int = 2) -> str:
        if value is None:
            return "-"
        return f"{float(value):,.{digits}f}"
