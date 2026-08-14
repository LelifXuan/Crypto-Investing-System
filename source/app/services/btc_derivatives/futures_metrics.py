from __future__ import annotations

from statistics import median, pstdev
from typing import Any, Sequence

from app.services.btc_derivatives.models import FuturesSnapshot
from app.services.btc_derivatives.options_metrics import safe_float


def pct_change(current: Any, previous: Any) -> float | None:
    current_value = safe_float(current)
    previous_value = safe_float(previous)
    if current_value is None or previous_value is None or previous_value == 0:
        return None
    return (current_value - previous_value) / abs(previous_value)


def aggregate_open_interest(rows: Sequence[FuturesSnapshot]) -> float | None:
    values = [value for row in rows if (value := safe_float(row.open_interest_usd)) is not None]
    return sum(values) if values else None


def aggregate_oi_change_pct(rows: Sequence[FuturesSnapshot]) -> float | None:
    current_values = [
        value for row in rows if (value := safe_float(row.open_interest_usd)) is not None
    ]
    previous_values = [
        value for row in rows if (value := safe_float(row.open_interest_usd_prev)) is not None
    ]
    if not current_values or not previous_values:
        return None
    return pct_change(sum(current_values), sum(previous_values))


def funding_zscore(current: Any, average: Any, stdev: Any = None) -> float | None:
    current_value = safe_float(current)
    average_value = safe_float(average)
    stdev_value = safe_float(stdev)
    if current_value is None or average_value is None:
        return None
    denominator = (
        stdev_value
        if stdev_value is not None and stdev_value > 0
        else max(abs(average_value), 0.0001)
    )
    return (current_value - average_value) / denominator


def price_oi_regime(
    price_change_pct: float | None,
    oi_change_pct: float | None,
) -> dict[str, str]:
    if price_change_pct is None or oi_change_pct is None:
        return {
            "state": "data_insufficient",
            "label": "价格或持仓变化数据不足",
            "interpretation": "无法判断杠杆压力来源",
        }
    if abs(price_change_pct) < 0.002:
        if oi_change_pct > 0.01:
            return {
                "state": "flat_oi_up",
                "label": "横盘增仓",
                "interpretation": "杠杆正在积累，方向尚未确认",
            }
        if oi_change_pct < -0.01:
            return {
                "state": "flat_oi_down",
                "label": "横盘降仓",
                "interpretation": "杠杆降温，短期压力释放",
            }
        return {
            "state": "flat",
            "label": "价格与持仓平稳",
            "interpretation": "衍生品杠杆压力有限",
        }
    if price_change_pct > 0 and oi_change_pct > 0:
        return {
            "state": "price_up_oi_up",
            "label": "上涨增仓",
            "interpretation": "新杠杆进入上行，但多头拥挤风险同步上升",
        }
    if price_change_pct > 0 and oi_change_pct <= 0:
        return {
            "state": "price_up_oi_down",
            "label": "上涨降仓",
            "interpretation": "空头回补主导，追涨需防挤压衰竭",
        }
    if price_change_pct < 0 and oi_change_pct > 0:
        return {
            "state": "price_down_oi_up",
            "label": "下跌增仓",
            "interpretation": "新空头或承压多头增加，下行压力上升",
        }
    return {
        "state": "price_down_oi_down",
        "label": "下跌降仓",
        "interpretation": "去杠杆释放中，晚追空性价比下降",
    }


def futures_metrics(
    rows: Sequence[FuturesSnapshot],
    *,
    price_change_pct: float | None,
) -> dict[str, Any]:
    oi_change = aggregate_oi_change_pct(rows)
    funding_values = [value for row in rows if (value := safe_float(row.funding_rate)) is not None]
    oi_values = {
        row.exchange: value
        for row in rows
        if (value := safe_float(row.open_interest_usd)) is not None
    }
    aggregate_oi = sum(oi_values.values()) if oi_values else None
    return {
        "aggregate_oi_usd": aggregate_oi,
        "aggregate_oi_change_pct": oi_change,
        "average_funding_rate": (
            sum(funding_values) / len(funding_values) if funding_values else None
        ),
        "funding_median": median(funding_values) if funding_values else None,
        "funding_dispersion": (
            pstdev(funding_values) if len(funding_values) >= 2 else 0.0
            if funding_values
            else None
        ),
        "open_interest_distribution": {
            provider: value / aggregate_oi
            for provider, value in oi_values.items()
        }
        if aggregate_oi
        else {},
        "price_oi_regime": price_oi_regime(price_change_pct, oi_change),
    }
