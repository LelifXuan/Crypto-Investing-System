from __future__ import annotations

from datetime import datetime, timezone
from typing import Any

from app.schemas.btc_derivatives import BtcDerivativesDashboardResponse
from app.schemas.btc_derivatives_sources import LiveSnapshotEnvelope
from app.services.btc_derivatives.chart_builder import build_consolidated_dashboard_charts
from app.services.btc_derivatives.constant_maturity import (
    select_constant_maturity_expiry,
)
from app.services.btc_derivatives.futures_metrics import (
    futures_metrics,
    pct_change,
)
from app.services.btc_derivatives.market_state_engine import (
    build_key_level_cards,
    build_market_state,
    decision_cards,
)
from app.services.btc_derivatives.models import FuturesSnapshot, OptionQuote
from app.services.btc_derivatives.options_metrics import (
    atm_iv_term_structure,
    chain_rows_for_expiry,
    iv_smile,
    liquidity_class,
    max_pain,
    mid_price,
    option_walls,
    put_call_ratios,
    skew_25d,
    spread_pct,
)
from app.services.btc_derivatives.time_window_policy import (
    TIME_WINDOW_POLICY,
    filter_history_window,
    resolve_window,
)
from app.services.btc_derivatives.wall_tracker import (
    movement_summary,
)


def now_iso() -> str:
    return datetime.now(timezone.utc).replace(microsecond=0).isoformat().replace("+00:00", "Z")

def _serialize_side(quote: OptionQuote | None) -> dict[str, Any] | None:
    if quote is None:
        return None
    return {
        "bid": quote.bid,
        "ask": quote.ask,
        "mark": quote.mark,
        "mid": mid_price(quote.bid, quote.ask, quote.mark),
        "spread_pct": spread_pct(quote.bid, quote.ask),
        "iv": quote.iv,
        "delta": quote.delta,
        "open_interest": quote.open_interest,
        "volume_24h": quote.volume_24h,
        "liquidity": liquidity_class(quote),
    }


class BtcDerivativesService:
    def build_dashboard(
        self,
        *,
        expiry: str | None = None,
        expiry_mode: str = "constant_maturity",
        maturity_bucket: str = "60D",
        window: str | None = None,
        strike_range_pct: str = "30",
        live_snapshot: LiveSnapshotEnvelope,
    ) -> BtcDerivativesDashboardResponse:
        as_of = (
            live_snapshot.data_timestamp.date()
            if live_snapshot.data_timestamp
            else datetime.now(timezone.utc).date()
        )
        quotes = [
                OptionQuote(
                    expiry=item.expiry,
                    strike=item.strike,
                    option_type=item.option_type,
                    bid=item.bid,
                    ask=item.ask,
                    mark=item.mark_price,
                    iv=item.iv,
                    delta=item.delta,
                    gamma=item.gamma,
                    theta=item.theta,
                    vega=item.vega,
                    open_interest=item.open_interest,
                    volume_24h=item.volume_24h,
                    timestamp=(item.provider_timestamp or item.collected_at).isoformat(),
                    provider=item.provider,
                )
                for item in live_snapshot.options
            ]
        futures = [
                FuturesSnapshot(
                    exchange=item.provider,
                    instrument=item.instrument,
                    timestamp=(item.provider_timestamp or item.collected_at).isoformat(),
                    mark_price=item.mark_price,
                    index_price=item.index_price,
                    funding_rate=item.funding_rate,
                    open_interest_usd=item.open_interest_usd,
                    volume_24h_usd=item.volume_24h_usd,
                    expiry=item.expiry,
                    basis_pct=item.basis_pct,
                    annualized_basis_pct=item.annualized_basis_pct,
                )
                for item in live_snapshot.perps
            ]
        spot_values = [
                item.underlying_price
                for item in live_snapshot.options
                if item.underlying_price is not None
            ] or [
                item.index_price or item.mark_price
                for item in live_snapshot.perps
                if item.index_price is not None or item.mark_price is not None
            ]
        spot_price = (
                sorted(spot_values)[len(spot_values) // 2]
                if spot_values
                else 0.0
        )
        expiries = sorted({quote.expiry for quote in quotes})
        if not expiries or spot_price <= 0:
            raise ValueError("live snapshot lacks a usable BTC option chain")
        maturity_selection = select_constant_maturity_expiry(
            expiries,
            as_of=as_of,
            maturity_bucket=maturity_bucket,
        )
        fallback_expiry = maturity_selection.get("expiry") or expiries[-1]
        selected_expiry = expiry if expiry in expiries else fallback_expiry
        chain = chain_rows_for_expiry(quotes, selected_expiry)
        walls = option_walls(chain)
        pain = max_pain(chain)
        skew = skew_25d([quote for quote in quotes if quote.expiry == selected_expiry])
        ratios = put_call_ratios(chain)
        live_price_history = live_snapshot.price_history
        priced = [
            float(item["spot_price"])
            for item in live_price_history
            if item.get("spot_price") not in (None, 0)
        ]
        price_change_pct = (
            (priced[-1] - priced[0]) / abs(priced[0])
            if len(priced) >= 2
            else None
        )
        metric_summary = futures_metrics(
            futures,
            price_change_pct=price_change_pct,
        )
        history = list(live_snapshot.key_level_history)

        futures_rows = [
            {
                "exchange": row.exchange,
                "instrument": row.instrument,
                "timestamp": row.timestamp,
                "mark_price": row.mark_price,
                "funding_rate": row.funding_rate,
                "open_interest_usd": row.open_interest_usd,
                "oi_change_pct": pct_change(
                    row.open_interest_usd,
                    row.open_interest_usd_prev,
                ),
                "volume_24h_usd": row.volume_24h_usd,
                "expiry": row.expiry,
                "basis_pct": row.basis_pct,
                "annualized_basis_pct": row.annualized_basis_pct,
            }
            for row in futures
        ]
        basis_points = [
            {
                "expiry": row.expiry,
                "basis_pct": row.basis_pct,
                "annualized_basis_pct": row.annualized_basis_pct,
            }
            for row in futures
            if row.expiry
        ]
        atm_points = atm_iv_term_structure(quotes, spot_price)
        smile_points = iv_smile(chain)
        strike_limit = None if strike_range_pct == "all" else float(strike_range_pct) / 100
        strike_rows = [
            {
                "strike": row.strike,
                "call_oi": row.call.open_interest if row.call else None,
                "put_oi": row.put.open_interest if row.put else None,
                "call_iv": smile.get("call_iv"),
                "put_iv": smile.get("put_iv"),
            }
            for row, smile in zip(chain, smile_points, strict=False)
            if strike_limit is None
            or abs(row.strike - spot_price) / spot_price <= strike_limit
        ]
        price_history = filter_history_window(
            live_snapshot.price_history,
            resolve_window("leverage_pressure", window),
            as_of=as_of,
        )
        level_history = filter_history_window(
            history,
            resolve_window("wall_max_pain", window),
            as_of=as_of,
        )
        consolidated = build_consolidated_dashboard_charts(
            price_history=price_history,
            futures_rows=futures_rows,
            basis_points=basis_points,
            atm_iv_points=atm_points,
            strike_rows=strike_rows,
            history=level_history,
            spot_price=spot_price,
            call_wall=walls.get("call_wall_strike"),
            put_wall=walls.get("put_wall_strike"),
            max_pain=pain.get("strike"),
        )
        charts = consolidated["charts"]
        movement_history = filter_history_window(
            history,
            "30D",
            as_of=as_of,
        )
        wall_movement = {
            "call_wall": movement_summary(movement_history, "call_wall_strike"),
            "put_wall": movement_summary(movement_history, "put_wall_strike"),
        }
        max_pain_movement = movement_summary(
            movement_history,
            "max_pain_strike",
        )
        funding_median = metric_summary.get("funding_median")
        funding_state = (
            "positive_hot"
            if funding_median is not None and funding_median >= 0.0003
            else "negative_hot"
            if funding_median is not None and funding_median <= -0.0003
            else "neutral"
        )
        basis_values = [
            row.annualized_basis_pct
            for row in futures
            if row.annualized_basis_pct is not None
        ]
        basis_state = (
            "basis_rising"
            if basis_values and sum(basis_values) / len(basis_values) > 0.08
            else "neutral"
        )
        latest_hedge_cost = next(
            (
                item.get("put_protection_cost_pct")
                for item in reversed(history)
                if item.get("put_protection_cost_pct") is not None
            ),
            None,
        )
        hedge_cost_state = (
            "expensive"
            if latest_hedge_cost is not None and latest_hedge_cost >= 0.03
            else "cheap"
            if latest_hedge_cost is not None and latest_hedge_cost <= 0.015
            else "neutral"
        )
        analysis = build_market_state(
            price_oi_state=metric_summary["price_oi_regime"]["state"],
            funding_state=funding_state,
            iv_state="iv_neutral",
            skew_state=(
                "call_skew_high"
                if (skew.get("put_call_skew") or 0) <= -0.05
                else "put_skew_high"
                if (skew.get("put_call_skew") or 0) >= 0.05
                else "skew_neutral"
            ),
            wall_movement=wall_movement,
            max_pain_movement=max_pain_movement,
            data_quality_status=live_snapshot.snapshot_state,
            basis_state=basis_state,
            hedge_cost_state=hedge_cost_state,
            technical_bias=None,
        )
        chart_windows = {
            "leverage_pressure_timeline": {
                "window_type": "time_series",
                "requested_window": window,
                "actual_window": resolve_window("leverage_pressure", window),
                "maximum_window": TIME_WINDOW_POLICY["leverage_pressure"].maximum,
                "data_points": len(price_history),
            },
            "key_levels_history": {
                "window_type": "time_series",
                "requested_window": window,
                "actual_window": resolve_window("wall_max_pain", window),
                "maximum_window": TIME_WINDOW_POLICY["wall_max_pain"].maximum,
                "data_points": len(level_history),
            },
            "options_risk_premium_history": {
                "window_type": "time_series",
                "requested_window": window,
                "actual_window": resolve_window("hedge_cost", window),
                "maximum_window": TIME_WINDOW_POLICY["hedge_cost"].maximum,
                "data_points": len(level_history),
                "available_modes": ["sentiment", "hedge_cost"],
                "default_mode": "sentiment",
            },
        }
        for chart_id in (
            "term_structure",
            "strike_surface",
            "exchange_crowding_snapshot",
        ):
            chart_windows[chart_id] = {
                "window_type": "current_cross_section",
                "requested_window": window,
                "actual_window": "current",
                "maximum_window": "current",
                "data_points": len(charts[chart_id]["labels"]),
            }
        for chart_id, metadata in chart_windows.items():
            option_chart = chart_id in {
                "strike_surface",
                "key_levels_history",
                "options_risk_premium_history",
            }
            providers = sorted(
                {
                    item.provider
                    for item in (
                        live_snapshot.options
                        if option_chart
                        else live_snapshot.perps
                    )
                }
            )
            charts[chart_id]["metadata"] = {
                **charts[chart_id].get("metadata", {}),
                **metadata,
                "providers": providers,
                "primary_provider": (
                    live_snapshot.primary_option_provider
                    if option_chart
                    else (providers[0] if providers else None)
                ),
                "updated_at": (
                    live_snapshot.data_timestamp.isoformat()
                    if live_snapshot.data_timestamp
                    else None
                ),
                "quality": live_snapshot.snapshot_state,
                "missing_reason": charts[chart_id].get("empty_reason"),
            }
        key_level_cards = build_key_level_cards(
            spot_price=spot_price,
            call_wall=walls.get("call_wall_strike"),
            put_wall=walls.get("put_wall_strike"),
            max_pain=pain.get("strike"),
            maturity_bucket=maturity_bucket,
            source_expiry=maturity_selection.get("expiry"),
            source_dte=maturity_selection.get("dte"),
            wall_movement=wall_movement,
            max_pain_movement=max_pain_movement,
        )
        return BtcDerivativesDashboardResponse.model_validate(
            {
                "generated_at": now_iso(),
                "underlying": "BTC",
                "snapshot_state": live_snapshot.snapshot_state,
                "data_timestamp": (
                    live_snapshot.data_timestamp.isoformat()
                    if live_snapshot.data_timestamp
                    else None
                ),
                "source_status": [
                    item.model_dump(mode="json")
                    for item in live_snapshot.source_status
                ],
                "cards": decision_cards(analysis),
                "futures": {
                    "rows": futures_rows,
                    "metrics": metric_summary,
                    "charts": {
                        key: charts[key]
                        for key in (
                            "leverage_pressure_timeline",
                            "exchange_crowding_snapshot",
                            "term_structure",
                        )
                    },
                },
                "options": {
                    "selected_expiry": selected_expiry,
                    "expiries": expiries,
                    "chain": [
                        {
                            "expiry": row.expiry,
                            "strike": row.strike,
                            "call": _serialize_side(row.call),
                            "put": _serialize_side(row.put),
                        }
                        for row in chain
                    ],
                    "metrics": {
                        "atm_iv_term": atm_points,
                        "skew_25d": skew,
                        "put_call_ratios": ratios,
                        "wall_movement": wall_movement,
                        "max_pain_movement": max_pain_movement,
                    },
                    "walls": walls,
                    "max_pain": pain,
                    "key_level_cards": key_level_cards,
                    "charts": {
                        key: charts[key]
                        for key in (
                            "strike_surface",
                            "key_levels_history",
                            "options_risk_premium_history",
                        )
                    },
                },
                "chart_layout": consolidated["chart_layout"],
                "selection": {
                    "expiry_mode": expiry_mode,
                    "maturity_bucket": maturity_bucket,
                    "selected_expiry": selected_expiry,
                    "window": window,
                    "strike_range_pct": strike_range_pct,
                },
                "maturity_selection": maturity_selection,
                "joint_analysis": analysis,
                "hedge_context": {
                    "spot_price": spot_price,
                    "iv_state": "iv_neutral",
                    "liquidity_state": "usable",
                    "preferred_expiry_bucket": "60D",
                    "note": "仅生成有限风险保护方案，不执行下单。",
                },
                "data_quality": {
                    "status": live_snapshot.snapshot_state,
                    "mode": live_snapshot.snapshot_state,
                    "providers": [
                        item.model_dump(mode="json")
                        for item in live_snapshot.source_status
                    ],
                    "missing_fields": live_snapshot.missing_reasons,
                    "stale_snapshots": [],
                    "history_available": len(history) >= 2,
                    "warnings": list(live_snapshot.missing_reasons),
                },
            }
        )
