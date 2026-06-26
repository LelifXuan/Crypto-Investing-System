from __future__ import annotations

from math import isfinite
from typing import Any, Mapping, Sequence

REQUIRED_CHART_IDS = {
    "leverage_pressure_timeline",
    "exchange_crowding_snapshot",
    "term_structure",
    "strike_surface",
    "key_levels_history",
    "options_risk_premium_history",
}

CHART_LAYOUT = {
    "leverage_pressure_timeline": {
        "span": 12,
        "density": "hero",
        "section": "summary",
    },
    "key_levels_history": {
        "span": 6,
        "density": "standard",
        "section": "options",
    },
    "term_structure": {
        "span": 4,
        "density": "compact",
        "section": "futures",
    },
    "strike_surface": {
        "span": 12,
        "density": "surface",
        "section": "options",
    },
    "options_risk_premium_history": {
        "span": 6,
        "density": "standard",
        "section": "options",
    },
    "exchange_crowding_snapshot": {
        "span": 8,
        "density": "surface",
        "section": "futures",
    },
}

CHART_SERIES_STYLE: dict[str, dict[str, dict[str, Any]]] = {
    "key_levels_history": {
        "Spot": {
            "borderWidth": 2.8,
            "borderDash": [],
            "pointRadius": 0,
            "tension": 0.16,
            "order": 1,
        },
        "Call Wall": {
            "borderWidth": 2.2,
            "borderDash": [8, 4],
            "pointRadius": 0,
            "tension": 0.08,
            "order": 2,
        },
        "Put Wall": {
            "borderWidth": 2.2,
            "borderDash": [3, 7],
            "pointRadius": 0,
            "tension": 0.08,
            "order": 3,
        },
        "Max Pain": {
            "borderWidth": 1.5,
            "borderDash": [2, 5],
            "pointRadius": 0,
            "tension": 0.05,
            "order": 4,
            "opacity": 0.55,
        },
    },
    "options_risk_premium_history": {
        "25D Skew": {
            "borderWidth": 2.1,
            "borderDash": [],
            "pointRadius": 0,
            "tension": 0.15,
            "order": 1,
        },
        "Put/Call OI": {
            "borderWidth": 1.8,
            "borderDash": [7, 4],
            "pointRadius": 0,
            "tension": 0.12,
            "order": 2,
        },
        "Put/Call Volume": {
            "borderWidth": 1.7,
            "borderDash": [3, 5],
            "pointRadius": 0,
            "tension": 0.12,
            "order": 3,
            "opacity": 0.74,
        },
        "Call保护成本": {
            "borderWidth": 1.8,
            "borderDash": [1, 4],
            "pointRadius": 0,
            "tension": 0.1,
            "order": 4,
            "opacity": 0.68,
        },
        "Put保护成本": {
            "borderWidth": 1.8,
            "borderDash": [1, 4],
            "pointRadius": 0,
            "tension": 0.1,
            "order": 5,
            "opacity": 0.68,
        },
        "借记价差成本": {
            "borderWidth": 1.6,
            "borderDash": [10, 5],
            "pointRadius": 0,
            "tension": 0.1,
            "order": 6,
            "opacity": 0.6,
        },
    },
    "strike_surface": {
        "Call OI": {"order": 10, "opacity": 0.82},
        "Put OI": {"order": 11, "opacity": 0.82},
        "Call IV": {"borderWidth": 2.1, "pointRadius": 2, "tension": 0.12, "order": 1},
        "Put IV": {
            "borderWidth": 2.1,
            "borderDash": [5, 4],
            "pointRadius": 2,
            "tension": 0.12,
            "order": 2,
        },
    },
}


def _finite(value: Any) -> float | None:
    try:
        number = float(value)
    except (TypeError, ValueError):
        return None
    return number if isfinite(number) else None


def _values(points: Sequence[Mapping[str, Any]], key: str) -> list[float | None]:
    return [_finite(point.get(key)) for point in points]


def _axis(
    profile: str,
    position: str = "left",
    unit: str | None = None,
    *,
    display_ticks: bool = True,
    grid: bool = True,
    include_annotations: bool = True,
    baseline: float | None = None,
    padding_ratio: float | None = None,
) -> dict[str, Any]:
    return {
        "profile": profile,
        "position": position,
        "unit": unit,
        "display_ticks": display_ticks,
        "grid": grid,
        "include_annotations": include_annotations,
        "baseline": baseline,
        "padding_ratio": padding_ratio,
    }


def _dataset(
    label: str,
    data: Sequence[Any],
    y_axis_id: str,
    axis_profile: str,
    chart_type: str,
    value_format: str,
    unit: str | None = None,
    style: Mapping[str, Any] | None = None,
) -> dict[str, Any]:
    return {
        "label": label,
        "data": list(data),
        "y_axis_id": y_axis_id,
        "axis_profile": axis_profile,
        "chart_type": chart_type,
        "value_format": value_format,
        "unit": unit,
        "style": dict(style or {}),
    }


def _chart(
    chart_id: str,
    title: str,
    labels: Sequence[Any],
    axes: dict[str, dict[str, Any]],
    datasets: Sequence[dict[str, Any]],
    *,
    chart_type: str = "line",
    annotations: Sequence[dict[str, Any]] = (),
    metadata: Mapping[str, Any] | None = None,
    empty_reason: str = "暂无足够数据",
) -> dict[str, Any]:
    labels_list = [str(label) for label in labels]
    has_values = any(
        any(value is not None for value in dataset.get("data", []))
        for dataset in datasets
    )
    return {
        "id": chart_id,
        "type": chart_type,
        "title": title,
        "labels": labels_list,
        "axes": axes,
        "datasets": list(datasets),
        "annotations": list(annotations),
        "metadata": dict(metadata or {}),
        "status": "ok" if labels_list and has_values else "data_insufficient",
        "empty_reason": None if labels_list and has_values else empty_reason,
    }


def _futures_layout(futures_rows: Sequence[Mapping[str, Any]]) -> dict[str, dict[str, Any]]:
    labels = [
        f"{row.get('exchange', '')} {row.get('instrument', '')}".strip()
        for row in futures_rows
    ]
    average_label_length = (
        sum(len(label) for label in labels) / len(labels)
        if labels
        else 0
    )
    if len(labels) >= 4 or average_label_length >= 24:
        return {
            "exchange_crowding_snapshot": {
                "span": 12,
                "density": "surface",
                "section": "futures",
            },
            "term_structure": {
                "span": 12,
                "density": "compact",
                "section": "futures",
            },
        }
    return {
        "exchange_crowding_snapshot": {
            "span": 8,
            "density": "surface",
            "section": "futures",
        },
        "term_structure": {
            "span": 4,
            "density": "compact",
            "section": "futures",
        },
    }


def build_chart_layout_payload(
    futures_rows: Sequence[Mapping[str, Any]] = (),
) -> dict[str, Any]:
    cards = {
        chart_id: dict(layout)
        for chart_id, layout in CHART_LAYOUT.items()
    }
    cards.update(_futures_layout(futures_rows))
    return {
        "sections": [
            {
                "id": "summary",
                "title": "总览",
                "charts": ["leverage_pressure_timeline"],
            },
            {
                "id": "futures",
                "title": "期货 / 永续",
                "charts": ["exchange_crowding_snapshot", "term_structure"],
            },
            {
                "id": "options",
                "title": "期权结构",
                "charts": [
                    "key_levels_history",
                    "options_risk_premium_history",
                    "strike_surface",
                ],
            },
        ],
        "cards": cards,
    }


def build_consolidated_dashboard_charts(
    *,
    price_history: Sequence[Mapping[str, Any]],
    futures_rows: Sequence[Mapping[str, Any]],
    basis_points: Sequence[Mapping[str, Any]],
    atm_iv_points: Sequence[Mapping[str, Any]],
    strike_rows: Sequence[Mapping[str, Any]],
    history: Sequence[Mapping[str, Any]],
    spot_price: float | None,
    call_wall: float | None,
    put_wall: float | None,
    max_pain: float | None,
) -> dict[str, Any]:
    term_labels = sorted(
        {
            str(point.get("expiry"))
            for point in [*basis_points, *atm_iv_points]
            if point.get("expiry")
        }
    )
    iv_by_expiry = {str(point.get("expiry")): point for point in atm_iv_points}
    basis_by_expiry = {str(point.get("expiry")): point for point in basis_points}
    term_rows = [
        {
            "expiry": expiry,
            "atm_iv": iv_by_expiry.get(expiry, {}).get("atm_iv"),
            "basis_pct": basis_by_expiry.get(expiry, {}).get("basis_pct"),
            "annualized_basis_pct": basis_by_expiry.get(expiry, {}).get(
                "annualized_basis_pct"
            ),
        }
        for expiry in term_labels
    ]
    annotations = [
        {"type": "verticalLine", "x": value, "label": label}
        for label, value in (
            ("Spot", spot_price),
            ("Call Wall", call_wall),
            ("Put Wall", put_wall),
            ("Max Pain", max_pain),
        )
        if _finite(value) is not None
    ]
    charts = {
        "leverage_pressure_timeline": _chart(
            "leverage_pressure_timeline",
            "价格、持仓与资金费率压力",
            [point.get("timestamp", "") for point in price_history],
            {
                "y_price": _axis("price", "left", "USD", padding_ratio=0.08),
                "y_oi": _axis(
                    "volume",
                    "right",
                    "USD",
                    display_ticks=False,
                    grid=False,
                ),
                "y_funding": _axis(
                    "centeredZero",
                    "right",
                    "zscore",
                    grid=False,
                ),
            },
            [
                _dataset(
                    "BTC 价格",
                    _values(price_history, "spot_price"),
                    "y_price",
                    "price",
                    "line",
                    "price",
                ),
                _dataset(
                    "聚合 OI",
                    _values(price_history, "aggregate_oi_usd"),
                    "y_oi",
                    "volume",
                    "line",
                    "compact_usd",
                ),
                _dataset(
                    "Funding Z",
                    _values(price_history, "funding_zscore"),
                    "y_funding",
                    "centeredZero",
                    "line",
                    "zscore",
                ),
            ],
            chart_type="mixed",
        ),
        "exchange_crowding_snapshot": _chart(
            "exchange_crowding_snapshot",
            "交易所杠杆拥挤快照",
            [
                f"{row.get('exchange', '')} {row.get('instrument', '')}".strip()
                for row in futures_rows
            ],
            {
                "y_oi": _axis("volume", "left", "USD"),
                "y_rate": _axis("centeredZero", "right", "rate", grid=False),
            },
            [
                _dataset(
                    "OI",
                    _values(futures_rows, "open_interest_usd"),
                    "y_oi",
                    "volume",
                    "bar",
                    "compact_usd",
                ),
                _dataset(
                    "OI 24h变化",
                    _values(futures_rows, "oi_change_pct"),
                    "y_rate",
                    "centeredZero",
                    "line",
                    "percent",
                ),
                _dataset(
                    "Funding",
                    _values(futures_rows, "funding_rate"),
                    "y_rate",
                    "centeredZero",
                    "line",
                    "percent",
                ),
                _dataset(
                    "Basis",
                    _values(futures_rows, "basis_pct"),
                    "y_rate",
                    "centeredZero",
                    "line",
                    "percent",
                ),
            ],
            chart_type="mixed",
        ),
        "term_structure": _chart(
            "term_structure",
            "IV 与基差期限结构",
            term_labels,
            {
                "y_iv": _axis("percent", "left", "iv", padding_ratio=0.08),
                "y_basis": _axis("percent", "right", "basis", grid=False, padding_ratio=0.08),
            },
            [
                _dataset(
                    "ATM IV",
                    _values(term_rows, "atm_iv"),
                    "y_iv",
                    "percent",
                    "line",
                    "percent",
                ),
                _dataset(
                    "年化 Basis",
                    _values(term_rows, "annualized_basis_pct"),
                    "y_basis",
                    "percent",
                    "line",
                    "percent",
                ),
                _dataset(
                    "Basis",
                    _values(term_rows, "basis_pct"),
                    "y_basis",
                    "percent",
                    "line",
                    "percent",
                ),
            ],
        ),
        "strike_surface": _chart(
            "strike_surface",
            "行权价表面：OI 与 IV",
            [point.get("strike", "") for point in strike_rows],
            {
                "y_oi": _axis("volume", "left", "contracts"),
                "y_iv": _axis("percent", "right", "iv", grid=False, padding_ratio=0.08),
            },
            [
                _dataset(
                    "Call OI",
                    _values(strike_rows, "call_oi"),
                    "y_oi",
                    "volume",
                    "bar",
                    "integer",
                    style=CHART_SERIES_STYLE["strike_surface"]["Call OI"],
                ),
                _dataset(
                    "Put OI",
                    _values(strike_rows, "put_oi"),
                    "y_oi",
                    "volume",
                    "bar",
                    "integer",
                    style=CHART_SERIES_STYLE["strike_surface"]["Put OI"],
                ),
                _dataset(
                    "Call IV",
                    _values(strike_rows, "call_iv"),
                    "y_iv",
                    "percent",
                    "line",
                    "percent",
                    style=CHART_SERIES_STYLE["strike_surface"]["Call IV"],
                ),
                _dataset(
                    "Put IV",
                    _values(strike_rows, "put_iv"),
                    "y_iv",
                    "percent",
                    "line",
                    "percent",
                    style=CHART_SERIES_STYLE["strike_surface"]["Put IV"],
                ),
            ],
            chart_type="mixed",
            annotations=annotations,
        ),
        "key_levels_history": _chart(
            "key_levels_history",
            "关键行权价迁移",
            [point.get("timestamp", "") for point in history],
            {"y_price": _axis("price", "left", "USD", padding_ratio=0.08)},
            [
                _dataset(
                    "Spot",
                    _values(history, "spot_price"),
                    "y_price",
                    "price",
                    "line",
                    "price",
                    style=CHART_SERIES_STYLE["key_levels_history"]["Spot"],
                ),
                _dataset(
                    "Call Wall",
                    _values(history, "call_wall_strike"),
                    "y_price",
                    "price",
                    "line",
                    "price",
                    style=CHART_SERIES_STYLE["key_levels_history"]["Call Wall"],
                ),
                _dataset(
                    "Put Wall",
                    _values(history, "put_wall_strike"),
                    "y_price",
                    "price",
                    "line",
                    "price",
                    style=CHART_SERIES_STYLE["key_levels_history"]["Put Wall"],
                ),
                _dataset(
                    "Max Pain",
                    _values(history, "max_pain_strike"),
                    "y_price",
                    "price",
                    "line",
                    "price",
                    style=CHART_SERIES_STYLE["key_levels_history"]["Max Pain"],
                ),
            ],
            metadata={"points": list(history)},
            empty_reason="暂无关键行权价历史；最大痛点和期权墙仅为持仓结构参考。",
        ),
        "options_risk_premium_history": _chart(
            "options_risk_premium_history",
            "期权情绪与保护成本",
            [point.get("timestamp", "") for point in history],
            {
                "y_skew": _axis("skew", "left", "skew", baseline=0),
                "y_ratio": _axis("ratio", "right", "ratio", grid=False, baseline=1),
                "y_cost": _axis(
                    "percent",
                    "right",
                    "cost",
                    display_ticks=False,
                    grid=False,
                    padding_ratio=0.08,
                ),
            },
            [
                _dataset(
                    "25D Skew",
                    _values(history, "skew_25d"),
                    "y_skew",
                    "centeredZero",
                    "line",
                    "raw",
                    style=CHART_SERIES_STYLE["options_risk_premium_history"]["25D Skew"],
                ),
                _dataset(
                    "Put/Call OI",
                    _values(history, "put_call_oi_ratio"),
                    "y_ratio",
                    "ratio",
                    "line",
                    "ratio",
                    style=CHART_SERIES_STYLE["options_risk_premium_history"][
                        "Put/Call OI"
                    ],
                ),
                _dataset(
                    "Put/Call Volume",
                    _values(history, "put_call_volume_ratio"),
                    "y_ratio",
                    "ratio",
                    "line",
                    "ratio",
                    style=CHART_SERIES_STYLE["options_risk_premium_history"][
                        "Put/Call Volume"
                    ],
                ),
                _dataset(
                    "Call保护成本",
                    _values(history, "call_protection_cost_pct"),
                    "y_cost",
                    "percent",
                    "line",
                    "percent",
                    style=CHART_SERIES_STYLE["options_risk_premium_history"][
                        "Call保护成本"
                    ],
                ),
                _dataset(
                    "Put保护成本",
                    _values(history, "put_protection_cost_pct"),
                    "y_cost",
                    "percent",
                    "line",
                    "percent",
                    style=CHART_SERIES_STYLE["options_risk_premium_history"][
                        "Put保护成本"
                    ],
                ),
                _dataset(
                    "借记价差成本",
                    _values(history, "debit_spread_cost_pct"),
                    "y_cost",
                    "percent",
                    "line",
                    "percent",
                    style=CHART_SERIES_STYLE["options_risk_premium_history"][
                        "借记价差成本"
                    ],
                ),
            ],
            chart_type="mixed",
            annotations=[
                {
                    "type": "horizontalLine",
                    "y": 1.0,
                    "axis_id": "y_ratio",
                    "label": "Put/Call = 1",
                },
                {
                    "type": "horizontalLine",
                    "y": 0.0,
                    "axis_id": "y_skew",
                    "label": "Skew = 0",
                },
            ],
        ),
    }
    return {
        "charts": charts,
        "chart_layout": build_chart_layout_payload(futures_rows),
    }


def build_dashboard_charts(**kwargs: Any) -> dict[str, dict[str, Any]]:
    """Compatibility wrapper for callers while the six-chart contract is adopted."""
    result = build_consolidated_dashboard_charts(
        price_history=kwargs.get("price_history", []),
        futures_rows=kwargs.get("futures_rows", []),
        basis_points=kwargs.get("basis_points", []),
        atm_iv_points=kwargs.get("atm_iv_points", []),
        strike_rows=[
            {
                **row,
                "call_iv": smile.get("call_iv"),
                "put_iv": smile.get("put_iv"),
            }
            for row, smile in zip(
                kwargs.get("strike_rows", []),
                kwargs.get("iv_smile_points", []),
                strict=False,
            )
        ],
        history=kwargs.get("wall_history", []),
        spot_price=None,
        call_wall=None,
        put_wall=None,
        max_pain=None,
    )
    return result["charts"]
