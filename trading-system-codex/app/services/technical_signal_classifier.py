from __future__ import annotations


def classify_signals(candles: list, core_series: dict, secondary_series: dict) -> list[dict]:
    if not candles:
        return []
    signals: list[dict] = []
    close = candles[-1].close if hasattr(candles[-1], "close") else float(candles[-1]["close"]) if isinstance(candles[-1], dict) else 0
    close = float(close) if close else 0

    ema_structure = _classify_ema_structure(candles, core_series, close)
    if ema_structure:
        signals.append(ema_structure)

    adx_signal = _classify_adx_direction(core_series)
    if adx_signal:
        signals.append(adx_signal)

    rsi_signal = _classify_rsi(core_series)
    if rsi_signal:
        signals.append(rsi_signal)

    macd_signal = _classify_macd(core_series)
    if macd_signal:
        signals.append(macd_signal)

    boll_signal = _classify_bollinger(core_series, close)
    if boll_signal:
        signals.append(boll_signal)

    atr_signal = _classify_atr(core_series, close)
    if atr_signal:
        signals.append(atr_signal)

    return signals


def _get_series(series: dict, key: str) -> list:
    if key not in series:
        return []
    data = series[key]
    if isinstance(data, dict):
        return data.get("values", [])
    if isinstance(data, list):
        return data
    return []


def _last(values: list, default: float = 0) -> float:
    return float(values[-1]) if values else float(default)


def _classify_ema_structure(candles: list, core_series: dict, close: float) -> dict | None:
    ema20 = _get_series(core_series, "ema_20")
    ema50 = _get_series(core_series, "ema_50")
    ema200 = _get_series(core_series, "ema_200")
    e20 = _last(ema20, close)
    e50 = _last(ema50, close)
    e200 = _last(ema200, close)

    has_min = e20 > 0 and e50 > 0
    if not has_min:
        return {"indicator_key": "ema_structure", "label": "EMA 结构", "value_num": close, "signal_state": "missing", "signal_label": "待计算", "tone": "neutral", "formula": "EMA20/EMA50/EMA200 排列", "rule": "多头排列: EMA20>EMA50>EMA200; 空头排列: 反向", "comment": "EMA 序列数据不足"}

    bullish_order = e20 > e50 and e50 > e200
    bearish_order = e20 < e50 and e50 < e200
    spread = abs(e20 - e200) / max(close, 1) * 100

    if bullish_order:
        return {"indicator_key": "ema_structure", "label": "EMA 结构", "value_num": close, "signal_state": "bullish", "signal_label": "多头排列" if spread >= 0.8 else "偏多排列", "tone": "bullish", "formula": f"EMA20({e20:.1f}) > EMA50({e50:.1f}) > EMA200({e200:.1f})", "rule": "多头排列", "comment": f"EMA多头排列 {spread:.1f}%"}
    if bearish_order:
        return {"indicator_key": "ema_structure", "label": "EMA 结构", "value_num": close, "signal_state": "bearish", "signal_label": "空头排列" if spread >= 0.8 else "偏空排列", "tone": "bearish", "formula": f"EMA20({e20:.1f}) < EMA50({e50:.1f}) < EMA200({e200:.1f})", "rule": "空头排列", "comment": f"EMA空头排列 {spread:.1f}%"}
    return {"indicator_key": "ema_structure", "label": "EMA 结构", "value_num": close, "signal_state": "neutral", "signal_label": "均线纠缠" if spread <= 0.6 else "均线交错", "tone": "neutral", "formula": f"EMA20({e20:.1f}) EMA50({e50:.1f}) EMA200({e200:.1f})", "rule": "未形成一致排列", "comment": f"EMA纠缠 spread={spread:.1f}%"}


def _classify_adx_direction(core_series: dict) -> dict | None:
    adx_v = _get_series(core_series, "adx_14")
    plus_v = _get_series(core_series, "plus_di")
    minus_v = _get_series(core_series, "minus_di")
    adx = _last(adx_v)
    plus = _last(plus_v)
    minus = _last(minus_v)
    if not adx:
        return None
    if not plus_v or not minus_v:
        return {"indicator_key": "adx_direction", "label": "ADX 趋势强度", "value_num": adx, "signal_state": "neutral", "signal_label": "方向待确认", "tone": "neutral", "formula": f"ADX={adx:.1f}", "rule": "ADX 只判断趋势强度；缺少 +DI/-DI 时不判断方向", "comment": "ADX需结合+DI/-DI确认方向"}
    if abs(plus - minus) < 1e-9:
        return {"indicator_key": "adx_direction", "label": "ADX 趋势强度", "value_num": adx, "signal_state": "neutral", "signal_label": "方向待确认", "tone": "neutral", "formula": f"ADX={adx:.1f} +DI={plus:.1f} -DI={minus:.1f}", "rule": "ADX 只判断趋势强度；+DI/-DI 未拉开时不判断方向", "comment": "ADX方向证据不足"}

    if adx >= 30:
        if plus > minus:
            return {"indicator_key": "adx_direction", "label": "ADX 趋势强度", "value_num": adx, "signal_state": "strong_bullish", "signal_label": "强趋势偏多", "tone": "bullish", "formula": f"ADX={adx:.1f} +DI={plus:.1f} -DI={minus:.1f} +DI>-DI", "rule": "ADX>=30 且 +DI>-DI", "comment": "ADX强趋势偏多"}
        else:
            return {"indicator_key": "adx_direction", "label": "ADX 趋势强度", "value_num": adx, "signal_state": "strong_bearish", "signal_label": "强趋势偏空", "tone": "bearish", "formula": f"ADX={adx:.1f} +DI={plus:.1f} -DI={minus:.1f} -DI>+DI", "rule": "ADX>=30 且 -DI>+DI", "comment": "ADX强趋势偏空"}
    if adx >= 22:
        if plus > minus:
            return {"indicator_key": "adx_direction", "label": "ADX 趋势强度", "value_num": adx, "signal_state": "bullish", "signal_label": "趋势偏多", "tone": "bullish", "formula": f"ADX={adx:.1f} +DI={plus:.1f} -DI={minus:.1f} +DI>-DI", "rule": "ADX>=22 且 +DI>-DI", "comment": "ADX成形偏多"}
        else:
            return {"indicator_key": "adx_direction", "label": "ADX 趋势强度", "value_num": adx, "signal_state": "bearish", "signal_label": "趋势偏空", "tone": "bearish", "formula": f"ADX={adx:.1f} +DI={plus:.1f} -DI={minus:.1f} -DI>+DI", "rule": "ADX>=22 且 -DI>+DI", "comment": "ADX成形偏空"}
    return {"indicator_key": "adx_direction", "label": "ADX 趋势强度", "value_num": adx, "signal_state": "neutral", "signal_label": "趋势较弱", "tone": "neutral", "formula": f"ADX={adx:.1f} +DI={plus:.1f} -DI={minus:.1f}", "rule": "ADX<22", "comment": "ADX趋势偏弱震荡"}


def _classify_rsi(core_series: dict) -> dict | None:
    vals = _get_series(core_series, "rsi_14")
    rsi = _last(vals)
    if not vals:
        return None
    if rsi >= 75:
        return {"indicator_key": "rsi_14", "label": "RSI 14", "value_num": rsi, "signal_state": "risk_hot", "signal_label": "超买风险", "tone": "event", "formula": "RSI = 100 - 100/(1+RS)", "rule": f"RSI={rsi:.1f} >= 75", "comment": "超买风险，追高需谨慎"}
    if rsi >= 60:
        return {"indicator_key": "rsi_14", "label": "RSI 14", "value_num": rsi, "signal_state": "bullish", "signal_label": "偏多", "tone": "bullish", "formula": "RSI = 100 - 100/(1+RS)", "rule": f"RSI={rsi:.1f} >= 60", "comment": "RSI偏多未极端"}
    if rsi <= 30:
        return {"indicator_key": "rsi_14", "label": "RSI 14", "value_num": rsi, "signal_state": "risk_cold", "signal_label": "超卖修复", "tone": "event", "formula": "RSI = 100 - 100/(1+RS)", "rule": f"RSI={rsi:.1f} <= 30", "comment": "超卖修复，存在反弹弹性"}
    if rsi <= 45:
        return {"indicator_key": "rsi_14", "label": "RSI 14", "value_num": rsi, "signal_state": "bearish", "signal_label": "偏空", "tone": "bearish", "formula": "RSI = 100 - 100/(1+RS)", "rule": f"RSI={rsi:.1f} <= 45", "comment": "RSI偏弱"}
    return {"indicator_key": "rsi_14", "label": "RSI 14", "value_num": rsi, "signal_state": "neutral", "signal_label": "中性", "tone": "neutral", "formula": "RSI = 100 - 100/(1+RS)", "rule": f"RSI={rsi:.1f}", "comment": "RSI中性"}


def _classify_macd(core_series: dict) -> dict | None:
    macd_vals = _get_series(core_series, "macd_hist")
    macd_vals = [v for v in macd_vals if v is not None]
    if not macd_vals or len(macd_vals) < 2:
        return None
    hist = float(macd_vals[-1])
    prev = float(macd_vals[-2])
    slope = hist - prev
    if hist > 0 and slope > 0:
        return {"indicator_key": "macd_hist", "label": "MACD 柱状值", "value_num": hist, "signal_state": "bullish", "signal_label": "多头增强", "tone": "bullish", "formula": "MACD = EMA12-EMA26; Hist = MACD-Signal", "rule": f"Hist={hist:.2f} > 0 且扩张", "comment": "MACD多头增强"}
    if hist > 0:
        return {"indicator_key": "macd_hist", "label": "MACD 柱状值", "value_num": hist, "signal_state": "neutral_bullish", "signal_label": "中性偏多", "tone": "bullish", "formula": "MACD = EMA12-EMA26", "rule": f"Hist={hist:.2f} > 0 收敛", "comment": "MACD偏多收敛"}
    if hist < 0 and slope < 0:
        return {"indicator_key": "macd_hist", "label": "MACD 柱状值", "value_num": hist, "signal_state": "bearish", "signal_label": "空头增强", "tone": "bearish", "formula": "MACD = EMA12-EMA26", "rule": f"Hist={hist:.2f} < 0 且扩张", "comment": "MACD空头增强"}
    if hist < 0:
        return {"indicator_key": "macd_hist", "label": "MACD 柱状值", "value_num": hist, "signal_state": "neutral_bearish", "signal_label": "中性偏空", "tone": "bearish", "formula": "MACD = EMA12-EMA26", "rule": f"Hist={hist:.2f} < 0 收敛", "comment": "MACD偏空收敛"}
    return {"indicator_key": "macd_hist", "label": "MACD 柱状值", "value_num": hist, "signal_state": "neutral", "signal_label": "中性", "tone": "neutral", "formula": "MACD = EMA12-EMA26", "rule": f"Hist={hist:.2f}", "comment": "MACD零轴附近"}


def _classify_bollinger(core_series: dict, close: float) -> dict | None:
    upper_v = _get_series(core_series, "bbands_upper")
    lower_v = _get_series(core_series, "bbands_lower")
    middle_v = _get_series(core_series, "bbands_middle")
    if not upper_v or not lower_v:
        return None
    upper = _last(upper_v)
    lower = _last(lower_v)
    middle = _last(middle_v, close)
    width_pct = (upper - lower) / max(middle, 1) * 100
    percent_b = (close - lower) / max(upper - lower, 0.01)
    if percent_b > 1.0 and width_pct >= 8:
        return {"indicator_key": "bbands", "label": "BOLL带", "value_num": close, "signal_state": "volatility_breakout_up", "signal_label": "上轨突破", "tone": "event", "formula": f"width_pct={width_pct:.1f}% percent_b={percent_b:.2f}", "rule": "price > upper 且 width_pct 扩张", "comment": f"BOLL上轨突破 {width_pct:.1f}%，按波动扩张处理"}
    if percent_b < 0 and width_pct >= 8:
        return {"indicator_key": "bbands", "label": "BOLL带", "value_num": close, "signal_state": "volatility_breakout_down", "signal_label": "下轨跌破", "tone": "event", "formula": f"width_pct={width_pct:.1f}% percent_b={percent_b:.2f}", "rule": "price < lower 且 width_pct 扩张", "comment": f"BOLL下轨跌破 {width_pct:.1f}%，按波动扩张处理"}
    if width_pct <= 5:
        return {"indicator_key": "bbands", "label": "BOLL带", "value_num": close, "signal_state": "neutral", "signal_label": "压缩", "tone": "neutral", "formula": f"width_pct={width_pct:.1f}%", "rule": "width_pct <= 5%", "comment": "BOLL压缩待释放"}
    return {"indicator_key": "bbands", "label": "BOLL带", "value_num": close, "signal_state": "neutral", "signal_label": "常态", "tone": "neutral", "formula": f"width_pct={width_pct:.1f}%", "rule": "价格在带内", "comment": "BOLL波动正常"}


def _classify_atr(core_series: dict, close: float) -> dict | None:
    vals = _get_series(core_series, "atr_14")
    atr = _last(vals)
    if not vals:
        return None
    natr = (atr / close * 100) if close > 0 else 0
    if natr >= 3.5:
        return {"indicator_key": "atr_14", "label": "ATR 波动率", "value_num": atr, "signal_state": "event", "signal_label": "波动偏高", "tone": "event", "formula": f"NATR={natr:.1f}% (ATR/close*100)", "rule": f"NATR={natr:.1f}% >= 3.5%", "comment": "ATR波动偏高"}
    if natr >= 2.0:
        return {"indicator_key": "atr_14", "label": "ATR 波动率", "value_num": atr, "signal_state": "neutral", "signal_label": "正常偏高", "tone": "neutral", "formula": f"NATR={natr:.1f}%", "rule": "2% <= NATR < 3.5%", "comment": "ATR正常偏高"}
    return {"indicator_key": "atr_14", "label": "ATR 波动率", "value_num": atr, "signal_state": "neutral", "signal_label": "波动正常", "tone": "neutral", "formula": f"NATR={natr:.1f}%", "rule": "NATR < 2%", "comment": "ATR波动正常"}
