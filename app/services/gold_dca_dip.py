from __future__ import annotations

# ruff: noqa: E501
import math
from dataclasses import dataclass, fields
from datetime import date, datetime, timedelta, timezone
from statistics import mean, pstdev
from typing import Any, Literal, Sequence

DcaStatus = Literal["execute", "already_executed", "stale_quote", "invalid_amount", "insufficient_cash"]
DipStatus = Literal["not_triggered", "candidate", "triggered", "cooldown", "invalid_amount", "insufficient_data", "stale_quote"]
DipState = Literal["normal", "oversold_candidate", "triggered", "cooldown", "reset_ready"]
ExecutionAction = Literal["daily_dca_only", "daily_dca_plus_dip_add", "manual_check", "no_action"]


@dataclass(slots=True)
class Candle:
    ts: datetime
    open: float
    high: float
    low: float
    close: float
    volume: float = 0.0


@dataclass(slots=True)
class GoldSettings:
    daily_dca_amount: float
    dip_add_amount: float
    cooldown_days: int = 7
    quote_max_age_seconds: int = 900
    available_cash: float | None = None
    rsi_candidate: float = 35.0
    rsi_strong: float = 30.0
    cci_candidate: float = -100.0
    cci_strong: float = -150.0
    percent_b_candidate: float = 0.10
    percent_b_strong: float = 0.0
    return_7d_trigger: float = -0.03
    return_14d_trigger: float = -0.05
    drawdown_30d_trigger: float = -0.05
    drawdown_60d_trigger: float = -0.08
    ema20_deviation_trigger: float = -0.02
    ema50_deviation_trigger: float = -0.04
    reset_rsi: float = 45.0
    reset_close_vs_ema20_pct: float = 0.0
    candidate_min_signals: int = 2
    trigger_min_signals: int = 3


@dataclass(slots=True)
class GoldExecutionState:
    executed_today: bool = False
    last_dip_add_date: date | None = None
    last_dip_cycle_id: str | None = None


@dataclass(slots=True)
class QuoteSnapshot:
    price: float
    updated_at: datetime

    def is_stale(self, now: datetime, max_age_seconds: int) -> bool:
        if self.price <= 0:
            return True
        return (now - self.updated_at).total_seconds() > max_age_seconds


@dataclass(slots=True)
class IndicatorSnapshot:
    close: float
    rsi_14: float | None = None
    ema_20: float | None = None
    ema_50: float | None = None
    ema_200: float | None = None
    percent_b: float | None = None
    cci_20: float | None = None
    kdj_j: float | None = None
    atr_14: float | None = None
    natr_14: float | None = None
    obv_slope: float | None = None
    volume_zscore_20: float | None = None
    return_7d: float | None = None
    return_14d: float | None = None
    drawdown_from_30d_high: float | None = None
    drawdown_from_60d_high: float | None = None
    close_vs_ema20_pct: float | None = None
    close_vs_ema50_pct: float | None = None
    close_vs_ema200_pct: float | None = None
    bollinger_reentry_signal: bool | None = None
    rsi_recovery_signal: bool | None = None


@dataclass(slots=True)
class DcaDecision:
    status: DcaStatus
    amount: float
    estimated_xaut_qty: float
    reason: str


@dataclass(slots=True)
class DipSignal:
    key: str
    label: str
    value: float | bool | None
    threshold: float | str
    severity: Literal["candidate", "strong"] = "candidate"


@dataclass(slots=True)
class DipDecision:
    status: DipStatus
    state: DipState
    amount: float
    estimated_xaut_qty: float
    cycle_id: str | None
    cooldown_until: date | None
    triggered_signals: list[str]
    blocking_reasons: list[str]
    reason: str


@dataclass(slots=True)
class ExecutionPlan:
    symbol: str
    as_of: datetime
    quote: dict[str, Any]
    daily_dca: DcaDecision
    dip_add: DipDecision
    execution: dict[str, Any]
    indicators: IndicatorSnapshot | None
    diagnostics: dict[str, Any]

    def to_dict(self) -> dict[str, Any]:
        return {
            "symbol": self.symbol,
            "as_of": self.as_of.isoformat(),
            "quote": self.quote,
            "daily_dca": _dataclass_to_dict(self.daily_dca),
            "dip_add": _dataclass_to_dict(self.dip_add),
            "execution": self.execution,
            "indicators": _dataclass_to_dict(self.indicators) if self.indicators else None,
            "diagnostics": self.diagnostics,
        }


def _dataclass_to_dict(obj: Any) -> dict[str, Any]:
    result: dict[str, Any] = {}
    for field_info in fields(obj):
        value = getattr(obj, field_info.name)
        if isinstance(value, (datetime, date)):
            result[field_info.name] = value.isoformat()
        else:
            result[field_info.name] = value
    return result


def _float(value: Any) -> float | None:
    try:
        number = float(value)
    except (TypeError, ValueError):
        return None
    return number if math.isfinite(number) else None


def _field(candle: Any, key: str) -> Any:
    return candle.get(key) if isinstance(candle, dict) else getattr(candle, key, None)


def _pct_change(current: float, previous: float | None) -> float | None:
    if previous is None or previous == 0:
        return None
    return (current / previous) - 1.0


def _ema(values: Sequence[float], window: int) -> float | None:
    if not values:
        return None
    multiplier = 2.0 / (window + 1.0)
    current = values[0]
    for value in values[1:]:
        current = ((value - current) * multiplier) + current
    return current


def _rsi(values: Sequence[float], window: int = 14) -> float | None:
    if len(values) < window + 1:
        return None
    gains: list[float] = []
    losses: list[float] = []
    for idx in range(1, len(values)):
        delta = values[idx] - values[idx - 1]
        gains.append(max(delta, 0.0))
        losses.append(abs(min(delta, 0.0)))
    avg_gain = mean(gains[:window])
    avg_loss = mean(losses[:window])
    for idx in range(window, len(gains)):
        avg_gain = ((avg_gain * (window - 1)) + gains[idx]) / window
        avg_loss = ((avg_loss * (window - 1)) + losses[idx]) / window
    if avg_loss == 0:
        return 100.0
    rs = avg_gain / avg_loss
    return 100.0 - (100.0 / (1.0 + rs))


def _bollinger_percent_b(values: Sequence[float], window: int = 20) -> float | None:
    if len(values) < window:
        return None
    chunk = values[-window:]
    middle = mean(chunk)
    sigma = pstdev(chunk)
    upper = middle + 2.0 * sigma
    lower = middle - 2.0 * sigma
    if upper == lower:
        return None
    return (values[-1] - lower) / (upper - lower)


def _cci(candles: Sequence[Candle], window: int = 20) -> float | None:
    if len(candles) < window:
        return None
    typical = [(item.high + item.low + item.close) / 3.0 for item in candles[-window:]]
    typical_mean = mean(typical)
    mean_deviation = mean(abs(item - typical_mean) for item in typical)
    if mean_deviation == 0:
        return None
    return (typical[-1] - typical_mean) / (0.015 * mean_deviation)


def _atr(candles: Sequence[Candle], window: int = 14) -> float | None:
    if len(candles) < window:
        return None
    ranges: list[float] = [candles[0].high - candles[0].low]
    for idx in range(1, len(candles)):
        previous = candles[idx - 1].close
        current = candles[idx]
        ranges.append(max(current.high - current.low, abs(current.high - previous), abs(current.low - previous)))
    current_atr = mean(ranges[:window])
    for value in ranges[window:]:
        current_atr = ((current_atr * (window - 1)) + value) / window
    return current_atr


def _volume_zscore(candles: Sequence[Candle], window: int = 20) -> float | None:
    if len(candles) < window:
        return None
    volumes = [item.volume for item in candles[-window:]]
    sigma = pstdev(volumes)
    if sigma == 0:
        return None
    return (volumes[-1] - mean(volumes)) / sigma


def normalize_candle(item: Any) -> Candle | None:
    ts = _field(item, "ts") or _field(item, "ts_open") or _field(item, "timestamp")
    close = _float(_field(item, "close"))
    if ts is None or close is None:
        return None
    if isinstance(ts, str):
        ts = datetime.fromisoformat(ts.replace("Z", "+00:00"))
    return Candle(
        ts=ts,
        open=_float(_field(item, "open")) or close,
        high=_float(_field(item, "high")) or close,
        low=_float(_field(item, "low")) or close,
        close=close,
        volume=_float(_field(item, "volume")) or 0.0,
    )


def build_indicator_snapshot(candles: Sequence[Candle], precomputed: dict[str, Any] | None = None) -> IndicatorSnapshot | None:
    if len(candles) < 21:
        return None
    precomputed = precomputed or {}
    closes = [item.close for item in candles]
    latest = closes[-1]
    ema_20 = _float(precomputed.get("ema_20")) or _ema(closes, 20)
    ema_50 = _float(precomputed.get("ema_50")) or _ema(closes, 50)
    ema_200 = _float(precomputed.get("ema_200")) or _ema(closes, 200)
    atr_14 = _float(precomputed.get("atr_14")) or _atr(candles, 14)
    natr_14 = _float(precomputed.get("natr_14")) or ((atr_14 / latest) if atr_14 and latest else None)
    high_30 = max(closes[-30:]) if len(closes) >= 30 else max(closes)
    high_60 = max(closes[-60:]) if len(closes) >= 60 else max(closes)
    return IndicatorSnapshot(
        close=latest,
        rsi_14=_float(precomputed.get("rsi_14")) or _rsi(closes),
        ema_20=ema_20,
        ema_50=ema_50,
        ema_200=ema_200,
        percent_b=_float(precomputed.get("percent_b")) if precomputed.get("percent_b") is not None else _bollinger_percent_b(closes),
        cci_20=_float(precomputed.get("cci_20")) or _cci(candles),
        kdj_j=_float(precomputed.get("kdj_j")),
        atr_14=atr_14,
        natr_14=natr_14,
        obv_slope=_float(precomputed.get("obv_slope")),
        volume_zscore_20=_volume_zscore(candles),
        return_7d=_pct_change(latest, closes[-8] if len(closes) >= 8 else None),
        return_14d=_pct_change(latest, closes[-15] if len(closes) >= 15 else None),
        drawdown_from_30d_high=_pct_change(latest, high_30),
        drawdown_from_60d_high=_pct_change(latest, high_60),
        close_vs_ema20_pct=_pct_change(latest, ema_20),
        close_vs_ema50_pct=_pct_change(latest, ema_50),
        close_vs_ema200_pct=_pct_change(latest, ema_200),
        bollinger_reentry_signal=bool(precomputed.get("bollinger_reentry_signal", False)),
        rsi_recovery_signal=bool(precomputed.get("rsi_recovery_signal", False)),
    )


def indicator_from_mapping(payload: dict[str, Any] | None) -> IndicatorSnapshot | None:
    if not payload:
        return None
    close = _float(payload.get("close"))
    if close is None:
        return None
    allowed = {field.name for field in fields(IndicatorSnapshot)}
    values = {key: payload.get(key) for key in allowed if key in payload}
    values["close"] = close
    return IndicatorSnapshot(**values)


def _format_card_value(value: float | bool | None, unit: str, digits: int) -> str:
    if value is None:
        return "-"
    if isinstance(value, bool):
        return "是" if value else "否"
    if unit == "%":
        return f"{value * 100:.{digits}f}%"
    return f"{value:.{digits}f}"


def _bias_for_indicator(key: str, value: float | None, *, lower: float | None = None, upper: float | None = None) -> str:
    """多空语义（5 档：strong_bullish / bullish / neutral / bearish / strong_bearish）。

    判定规则：
    - value 为 None → missing
    - 指标不在 bullish_low/bearish_low 集合内 → neutral（默认中性）
    - bullish_low 集合（越低越看多黄金）：
      rsi_14 / cci_20 / percent_b
    - bearish_low 集合（越低越看空黄金）：
      close_vs_ema20_pct / close_vs_ema50_pct / return_7d / return_14d /
      drawdown_from_30d_high / drawdown_from_60d_high
    - 无阈值（lower=None and upper=None）→ neutral
    - 强档阈值：lower*0.7 / upper*1.3
    """
    if value is None:
        return "missing"
    bullish_low = {"rsi_14", "cci_20", "percent_b"}
    bearish_low = {
        "close_vs_ema20_pct", "close_vs_ema50_pct",
        "return_7d", "return_14d",
        "drawdown_from_30d_high", "drawdown_from_60d_high",
    }
    if lower is None and upper is None:
        return "neutral"
    # 强档阈值：向 strong 方向再延伸 30%（lower>=0 时 *0.7；lower<0 时 *1.3）
    strong_lower = lower * (0.7 if (lower is None or lower >= 0) else 1.3)
    strong_upper = upper * 1.3 if upper is not None else None
    if key in bullish_low:
        if lower is not None and value <= strong_lower:
            return "strong_bullish"
        if lower is not None and value <= lower:
            return "bullish"
        if upper is not None and value >= strong_upper:
            return "strong_bearish"
        if upper is not None and value >= upper:
            return "bearish"
        return "neutral"
    if key in bearish_low:
        if lower is not None and value <= strong_lower:
            return "strong_bearish"
        if lower is not None and value <= lower:
            return "bearish"
        if upper is not None and value >= strong_upper:
            return "strong_bullish"
        if upper is not None and value >= upper:
            return "bullish"
        return "neutral"
    return "neutral"


def _status_for_value(value: float | bool | None, *, lower: float | None = None, upper: float | None = None) -> str:
    if value is None:
        return "数据不足"
    if lower is not None and isinstance(value, float) and value <= lower:
        return "偏低"
    if upper is not None and isinstance(value, float) and value >= upper:
        return "偏高"
    return "可用"


def _indicator_card(
    indicators: IndicatorSnapshot | None,
    *,
    key: str,
    label: str,
    unit: str = "",
    digits: int = 2,
    note: str,
    lower: float | None = None,
    upper: float | None = None,
) -> dict[str, Any]:
    value = getattr(indicators, key, None) if indicators else None
    return {
        "key": key,
        "label": label,
        "value": value,
        "display_value": _format_card_value(value, unit, digits),
        "unit": unit,
        "status": _status_for_value(value, lower=lower, upper=upper),
        "bias": _bias_for_indicator(key, value, lower=lower, upper=upper),
        "note": note,
    }


def build_core_indicator_cards(indicators: IndicatorSnapshot | None) -> list[dict[str, Any]]:
    return [
        _indicator_card(indicators, key="rsi_14", label="RSI14", digits=1, note="衡量日线超跌和修复状态", lower=30, upper=70),
        _indicator_card(indicators, key="ema_20", label="EMA20", digits=2, note="短期趋势均线"),
        _indicator_card(indicators, key="ema_50", label="EMA50", digits=2, note="中期趋势均线"),
        _indicator_card(indicators, key="ema_200", label="EMA200", digits=2, note="长期趋势均线"),
        _indicator_card(indicators, key="percent_b", label="BOLL 位置", digits=2, note="判断价格相对布林通道的位置", lower=0, upper=1),
        _indicator_card(indicators, key="cci_20", label="CCI20", digits=1, note="识别日线错杀或过热状态", lower=-150, upper=150),
        _indicator_card(indicators, key="atr_14", label="ATR14", digits=2, note="衡量日线绝对波动"),
        _indicator_card(indicators, key="natr_14", label="NATR14", unit="%", digits=2, note="衡量标准化波动水平"),
    ]


def build_derived_indicator_cards(indicators: IndicatorSnapshot | None) -> list[dict[str, Any]]:
    return [
        _indicator_card(indicators, key="return_7d", label="7 日变化", unit="%", digits=1, note="短窗口回撤强度", lower=-0.03),
        _indicator_card(indicators, key="return_14d", label="14 日变化", unit="%", digits=1, note="两周价格压力", lower=-0.05),
        _indicator_card(indicators, key="drawdown_from_30d_high", label="30 日高点回撤", unit="%", digits=1, note="距离月内高点的回撤", lower=-0.05),
        _indicator_card(indicators, key="drawdown_from_60d_high", label="60 日高点回撤", unit="%", digits=1, note="距离双月高点的回撤", lower=-0.08),
        _indicator_card(indicators, key="close_vs_ema20_pct", label="相对 EMA20", unit="%", digits=1, note="价格相对短期均线偏离", lower=-0.02),
        _indicator_card(indicators, key="close_vs_ema50_pct", label="相对 EMA50", unit="%", digits=1, note="价格相对中期均线偏离", lower=-0.04),
    ]


class GoldDailyDcaEngine:
    def evaluate(self, *, settings: GoldSettings, state: GoldExecutionState, quote: QuoteSnapshot, now: datetime) -> DcaDecision:
        if settings.daily_dca_amount <= 0:
            return DcaDecision("invalid_amount", 0.0, 0.0, "每日基础定投金额未设置，今日不生成基础定投。")
        if quote.is_stale(now, settings.quote_max_age_seconds):
            return DcaDecision("stale_quote", 0.0, 0.0, "XAUT 报价需要刷新，确认最新价格后再执行今日计划。")
        if state.executed_today:
            return DcaDecision("already_executed", 0.0, 0.0, "今日基础定投已记录，避免重复提示。")
        if settings.available_cash is not None and settings.available_cash < settings.daily_dca_amount:
            return DcaDecision("insufficient_cash", 0.0, 0.0, "可用现金不足，基础定投暂缓。")
        amount = round(settings.daily_dca_amount, 8)
        return DcaDecision("execute", amount, round(amount / quote.price, 8), "按长期纪律执行今日基础定投。")


class GoldDipAddEngine:
    def evaluate(
        self,
        *,
        settings: GoldSettings,
        state: GoldExecutionState,
        quote: QuoteSnapshot,
        indicators: IndicatorSnapshot | None,
        now: datetime,
    ) -> DipDecision:
        if settings.dip_add_amount <= 0:
            return DipDecision("invalid_amount", "normal", 0.0, 0.0, None, None, [], [], "黄金坑固定加仓金额未设置。")
        if quote.is_stale(now, settings.quote_max_age_seconds):
            return DipDecision("stale_quote", "normal", 0.0, 0.0, None, None, [], [], "XAUT 报价需要刷新，暂不判断黄金坑。")
        if indicators is None:
            return DipDecision("insufficient_data", "normal", 0.0, 0.0, None, None, [], [], "日线指标不足，黄金坑固定加仓暂不触发；基础定投不受影响。")

        cooldown_until = self._cooldown_until(state, settings)
        if cooldown_until and now.date() < cooldown_until:
            return DipDecision(
                "cooldown",
                "cooldown",
                0.0,
                0.0,
                state.last_dip_cycle_id,
                cooldown_until,
                [],
                [f"冷却期内不重复触发，最早 {cooldown_until.isoformat()} 后重新评估。"],
                "上一轮黄金坑固定加仓后仍在冷却期。",
            )

        signals = collect_oversold_signals(indicators, settings)
        strong_rsi = any(item.key == "rsi_strong" for item in signals)
        price_signal = any(item.key not in {"rsi_strong", "rsi_candidate", "cci_strong", "cci_candidate"} for item in signals)
        triggered = len(signals) >= settings.trigger_min_signals or (strong_rsi and price_signal)
        candidate = len(signals) >= settings.candidate_min_signals
        cycle_id = make_cycle_id(now, indicators)
        if triggered and state.last_dip_cycle_id == cycle_id:
            return DipDecision("cooldown", "cooldown", 0.0, 0.0, cycle_id, cooldown_until, [], ["同一轮超跌事件已经提示过固定加仓。"], "同一轮事件不重复触发。")
        if triggered:
            amount = round(settings.dip_add_amount, 8)
            return DipDecision(
                "triggered",
                "triggered",
                amount,
                round(amount / quote.price, 8),
                cycle_id,
                now.date() + timedelta(days=settings.cooldown_days),
                [format_signal(item) for item in signals],
                [],
                "日线出现多项超跌或错杀信号，触发一次固定黄金坑加仓。",
            )
        if candidate:
            return DipDecision(
                "candidate",
                "oversold_candidate",
                0.0,
                0.0,
                cycle_id,
                None,
                [format_signal(item) for item in signals],
                [],
                "日线已有部分超跌信号，但尚未达到固定加仓条件。",
            )
        state_name: DipState = "reset_ready" if self._is_reset_ready(indicators, settings) else "normal"
        return DipDecision("not_triggered", state_name, 0.0, 0.0, None, None, [], [], "当前未出现日线级别黄金坑。")

    @staticmethod
    def _cooldown_until(state: GoldExecutionState, settings: GoldSettings) -> date | None:
        if not state.last_dip_add_date:
            return None
        return state.last_dip_add_date + timedelta(days=settings.cooldown_days)

    @staticmethod
    def _is_reset_ready(indicators: IndicatorSnapshot, settings: GoldSettings) -> bool:
        rsi_reset = indicators.rsi_14 is not None and indicators.rsi_14 >= settings.reset_rsi
        ema_reset = indicators.close_vs_ema20_pct is not None and indicators.close_vs_ema20_pct >= settings.reset_close_vs_ema20_pct
        return bool(rsi_reset or ema_reset)


def _add_signal(signals: list[DipSignal], *, key: str, label: str, value: float | None, threshold: float) -> None:
    if value is not None and value <= threshold:
        signals.append(DipSignal(key, label, value, threshold))


def collect_oversold_signals(indicators: IndicatorSnapshot, settings: GoldSettings) -> list[DipSignal]:
    signals: list[DipSignal] = []
    if indicators.rsi_14 is not None:
        if indicators.rsi_14 <= settings.rsi_strong:
            signals.append(DipSignal("rsi_strong", "RSI14 深度超跌", indicators.rsi_14, settings.rsi_strong, "strong"))
        elif indicators.rsi_14 <= settings.rsi_candidate:
            signals.append(DipSignal("rsi_candidate", "RSI14 进入超跌观察区", indicators.rsi_14, settings.rsi_candidate))
    if indicators.percent_b is not None:
        if indicators.percent_b < settings.percent_b_strong:
            signals.append(DipSignal("percent_b_strong", "跌破布林下轨", indicators.percent_b, settings.percent_b_strong, "strong"))
        elif indicators.percent_b <= settings.percent_b_candidate:
            signals.append(DipSignal("percent_b_candidate", "接近布林下轨", indicators.percent_b, settings.percent_b_candidate))
    if indicators.cci_20 is not None:
        if indicators.cci_20 <= settings.cci_strong:
            signals.append(DipSignal("cci_strong", "CCI20 深度超跌", indicators.cci_20, settings.cci_strong, "strong"))
        elif indicators.cci_20 <= settings.cci_candidate:
            signals.append(DipSignal("cci_candidate", "CCI20 超跌", indicators.cci_20, settings.cci_candidate))
    _add_signal(signals, key="return_7d", label="近 7 日快速回撤", value=indicators.return_7d, threshold=settings.return_7d_trigger)
    _add_signal(signals, key="return_14d", label="近 14 日明显回撤", value=indicators.return_14d, threshold=settings.return_14d_trigger)
    _add_signal(signals, key="drawdown_30d", label="较 30 日高点明显回撤", value=indicators.drawdown_from_30d_high, threshold=settings.drawdown_30d_trigger)
    _add_signal(signals, key="drawdown_60d", label="较 60 日高点明显回撤", value=indicators.drawdown_from_60d_high, threshold=settings.drawdown_60d_trigger)
    _add_signal(signals, key="ema20_deviation", label="价格明显低于 EMA20", value=indicators.close_vs_ema20_pct, threshold=settings.ema20_deviation_trigger)
    _add_signal(signals, key="ema50_deviation", label="价格明显低于 EMA50", value=indicators.close_vs_ema50_pct, threshold=settings.ema50_deviation_trigger)
    return signals


def format_signal(signal: DipSignal) -> str:
    value = signal.value
    if isinstance(value, float):
        value_text = f"{value:.2%}" if abs(value) < 1 else f"{value:.2f}"
    else:
        value_text = str(value)
    threshold = signal.threshold
    threshold_text = f"{threshold:.2%}" if isinstance(threshold, float) and abs(threshold) < 1 else str(threshold)
    return f"{signal.label}: 当前 {value_text}，阈值 {threshold_text}"


def make_cycle_id(now: datetime, indicators: IndicatorSnapshot) -> str:
    rsi_bucket = "na" if indicators.rsi_14 is None else str(int(indicators.rsi_14 // 5 * 5))
    return f"{now.date().isoformat()}-rsi{rsi_bucket}"


class GoldExecutionComposer:
    def compose(
        self,
        *,
        symbol: str,
        quote: QuoteSnapshot,
        now: datetime,
        settings: GoldSettings,
        state: GoldExecutionState,
        indicators: IndicatorSnapshot | None,
    ) -> ExecutionPlan:
        daily = GoldDailyDcaEngine().evaluate(settings=settings, state=state, quote=quote, now=now)
        dip = GoldDipAddEngine().evaluate(settings=settings, state=state, quote=quote, indicators=indicators, now=now)
        base_amount = daily.amount if daily.status == "execute" else 0.0
        dip_amount = dip.amount if dip.status == "triggered" else 0.0
        total_amount = base_amount + dip_amount
        estimated_qty = total_amount / quote.price if quote.price > 0 else 0.0

        if daily.status == "stale_quote" or dip.status == "stale_quote":
            action: ExecutionAction = "manual_check"
            summary = "XAUT 报价需要刷新，今日计划先进入人工复核。"
        elif total_amount <= 0:
            action = "no_action"
            summary = "今日没有新的黄金买入计划。"
        elif dip.status == "triggered":
            action = "daily_dca_plus_dip_add"
            summary = "今日执行基础定投，并因日线超跌额外固定加仓一次。"
        else:
            action = "daily_dca_only"
            summary = "今日仅执行基础定投，黄金坑固定加仓未触发。"

        core_cards = build_core_indicator_cards(indicators)
        derived_cards = build_derived_indicator_cards(indicators)
        return ExecutionPlan(
            symbol=symbol,
            as_of=now,
            quote={"price": quote.price, "updated_at": quote.updated_at.isoformat(), "is_stale": quote.is_stale(now, settings.quote_max_age_seconds)},
            daily_dca=daily,
            dip_add=dip,
            execution={
                "action": action,
                "base_dca_amount": round(base_amount, 8),
                "dip_add_amount": round(dip_amount, 8),
                "total_amount": round(total_amount, 8),
                "estimated_xaut_qty": round(estimated_qty, 8),
                "summary": summary,
            },
            indicators=indicators,
            diagnostics={
                "data_quality": "ok" if indicators else "partial",
                "quote_state": "stale" if quote.is_stale(now, settings.quote_max_age_seconds) else "fresh",
                "strategy_formula": {
                    "base": "x",
                    "dip": "n × x",
                    "total_when_triggered": "x + n × x",
                },
                "core_indicator_cards": core_cards,
                "derived_indicator_cards": derived_cards,
                "reused_indicators": [item["key"] for item in core_cards],
                "computed_derived_indicators": [item["key"] for item in derived_cards],
                "missing_optional_indicators": [] if indicators else ["daily_candles"],
            },
        )


def now_utc() -> datetime:
    return datetime.now(timezone.utc)
