from __future__ import annotations

from datetime import date, datetime, timezone
from math import isfinite
from typing import Any

from app.schemas.btc_derivatives import BtcDerivativesDashboardResponse
from app.schemas.btc_derivatives_sources import LiveSnapshotEnvelope
from app.services.btc_derivatives.chart_builder import build_consolidated_dashboard_charts
from app.services.btc_derivatives.constant_maturity import (
    BUCKET_DTE,
    select_constant_maturity_expiry,
)
from app.services.btc_derivatives.expiry_policy import (
    classify_expiry,
    nearest_standard_expiry,
    standard_expiries,
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
    standardized_protection_costs,
)
from app.services.btc_derivatives.options_wall_signal import evaluate_key_levels_axis
from app.services.btc_derivatives.time_window_policy import (
    TIME_WINDOW_POLICY,
    filter_history_window,
    resolve_window,
)
from app.services.btc_derivatives.wall_tracker import (
    movement_summary,
)
from app.services.indicator_judgement import build_indicator_judgement


def now_iso() -> str:
    return datetime.now(timezone.utc).replace(microsecond=0).isoformat().replace("+00:00", "Z")


def _finite(value: Any) -> float | None:
    try:
        number = float(value)
    except (TypeError, ValueError):
        return None
    return number if isfinite(number) else None


def _last_history_number(history: list[dict[str, Any]], key: str) -> float | None:
    for item in reversed(history):
        value = _finite(item.get(key))
        if value is not None:
            return value
    return None


def _last_history_item(history: list[dict[str, Any]]) -> dict[str, Any]:
    for item in reversed(history):
        if isinstance(item, dict):
            return item
    return {}


def _parse_history_timestamp(value: Any) -> datetime | None:
    if isinstance(value, datetime):
        parsed = value
    elif isinstance(value, str) and value.strip():
        text = value.strip()
        try:
            parsed = datetime.fromisoformat(text.replace("Z", "+00:00"))
        except ValueError:
            try:
                parsed = datetime.fromisoformat(f"{text}T00:00:00+00:00")
            except ValueError:
                return None
    else:
        return None
    if parsed.tzinfo is None:
        parsed = parsed.replace(tzinfo=timezone.utc)
    return parsed.astimezone(timezone.utc)


def _history_item_day(item: dict[str, Any]) -> date | None:
    parsed = _parse_history_timestamp(item.get("timestamp"))
    return parsed.date() if parsed else None


def _previous_history_item(
    history: list[dict[str, Any]],
    *,
    current_timestamp: datetime | None,
) -> dict[str, Any]:
    """Return the latest valid history point before the current UTC day.

    The daily key-level history may already contain today's refreshed point.
    Comparing the current snapshot against that same-day point hides real
    day-over-day migration (for example 72k -> 75k Call Wall becomes 75k ->
    75k).  This helper deliberately skips all points from the current UTC day.
    """

    if not history:
        return {}
    if current_timestamp is None:
        return _last_history_item(history)
    current_day = current_timestamp.astimezone(timezone.utc).date()
    for item in reversed(history):
        if not isinstance(item, dict):
            continue
        item_day = _history_item_day(item)
        if item_day is None or item_day < current_day:
            return item
    return {}


def _parse_expiry_date(value: Any) -> date | None:
    if isinstance(value, date) and not isinstance(value, datetime):
        return value
    if isinstance(value, datetime):
        return value.date()
    if isinstance(value, str) and value.strip():
        try:
            return datetime.strptime(value.strip(), "%Y-%m-%d").date()
        except ValueError:
            return None
    return None


def _basis_pct(mark_price: float | None, spot_price: float | None) -> float | None:
    if mark_price is None or spot_price is None or spot_price <= 0:
        return None
    return (mark_price - spot_price) / spot_price


def _annualized_basis_pct(
    basis_pct: float | None,
    expiry: str | None,
    *,
    as_of: date,
) -> float | None:
    expiry_date = _parse_expiry_date(expiry)
    if basis_pct is None or expiry_date is None:
        return None
    dte = (expiry_date - as_of).days
    if dte <= 0:
        return None
    return basis_pct * 365 / dte


def _wall_concentration(rows: list[Any], option_type: str, wall_oi: Any) -> float | None:
    total = sum(
        _finite(getattr(getattr(row, option_type, None), "open_interest", None)) or 0
        for row in rows
    )
    value = _finite(wall_oi)
    return value / total if value is not None and total > 0 else None


def _maturity_band(dte: int | None) -> str:
    if dte is None:
        return "unknown"
    if dte <= 45:
        return "near_term"
    if dte <= 120:
        return "medium_term"
    return "far_term"


def _options_direction(ladder: list[dict[str, Any]]) -> dict[str, Any]:
    usable = [item for item in ladder if item.get("skew_25d", {}).get("status") == "ok"]
    if not usable:
        return {
            "state": "DATA_INSUFFICIENT",
            "label": "期权方向数据不足",
            "confidence": "low",
            "primary_reason": "25D Skew 尚不可可靠计算，不能回退为方向平衡。",
            "term_consensus": "DATA_INSUFFICIENT",
            "term_conflicts": [],
        }
    by_band: dict[str, list[float]] = {}
    for item in usable:
        value = _finite(item.get("skew_25d", {}).get("put_call_skew"))
        if value is not None:
            by_band.setdefault(str(item["maturity_band"]), []).append(value)
    band_states: dict[str, str] = {}
    for band, values in by_band.items():
        average = sum(values) / len(values)
        band_states[band] = (
            "DOWNSIDE_PROTECTION" if average >= 0.03
            else "UPSIDE_DEMAND" if average <= -0.03
            else "BALANCED"
        )
    directional = {value for value in band_states.values() if value != "BALANCED"}
    conflicts = []
    if len(directional) > 1:
        state = "TERM_DIVERGENCE"
        label = "近远期限方向分化"
        conflicts.append("不同期限的 25D Skew 指向相反，暂不形成统一方向。")
    elif directional:
        state = next(iter(directional))
        label = "下行保护需求偏高" if state == "DOWNSIDE_PROTECTION" else "上行需求偏高"
    else:
        state = "BALANCED"
        label = "期权方向相对平衡"
    return {
        "state": state,
        "label": label,
        "confidence": "high" if len(usable) >= 3 and not conflicts else "medium",
        "primary_reason": "按标准月度/季度到期日的 25D Risk Reversal 形成期限共识。",
        "term_consensus": state,
        "term_states": band_states,
        "term_conflicts": conflicts,
    }


def _interpolate_metric(
    ladder: list[dict[str, Any]], target_dte: int, key: str
) -> tuple[float | None, list[dict[str, Any]], str]:
    points = sorted(
        (int(item["dte"]), item)
        for item in ladder
        if item.get("dte") is not None
        and _finite(item.get("protection_cost", {}).get(key)) is not None
    )
    if not points:
        return None, [], "data_insufficient"
    lower = max((item for item in points if item[0] <= target_dte), default=None)
    upper = min((item for item in points if item[0] >= target_dte), default=None)
    sources: list[dict[str, Any]] = []
    for item in (lower, upper):
        if item is None:
            continue
        source = {"expiry": item[1]["expiry"], "dte": item[0]}
        if source not in sources:
            sources.append(source)
    if lower and upper and lower[0] != upper[0]:
        low_value = float(lower[1]["protection_cost"][key])
        high_value = float(upper[1]["protection_cost"][key])
        weight = (target_dte - lower[0]) / (upper[0] - lower[0])
        return low_value + weight * (high_value - low_value), sources, "interpolated"
    source = min(points, key=lambda item: abs(item[0] - target_dte))
    return float(source[1]["protection_cost"][key]), sources or [
        {"expiry": source[1]["expiry"], "dte": source[0]}
    ], "single_source"


def _break_legacy_rolls(
    history: list[dict[str, Any]],
    expiry_mode: str = "constant_maturity",
) -> list[dict[str, Any]]:
    output: list[dict[str, Any]] = []
    previous_expiry: str | None = None
    previous_method: str | None = None
    cost_keys = (
        "call_protection_cost_pct",
        "put_protection_cost_pct",
        "debit_spread_cost_pct",
    )
    # In constant_maturity mode the service interpolates between the two nearest
    # standard expiries, so adjacent cache rows can legitimately land on different
    # source_expiry values without invalidating the cost series. Suppress the
    # expiry_rollover NULL-out in that mode; method_change is a real policy
    # change and breaks the series in either mode.
    suppress_expiry_rollover = expiry_mode == "constant_maturity"
    for item in history:
        current = dict(item)
        expiry = str(item.get("source_expiry") or "") or None
        method = str(item.get("selection_method") or "legacy")
        break_reason = None
        if previous_method is not None and method != previous_method:
            break_reason = "method_change"
        elif (
            not suppress_expiry_rollover
            and previous_expiry is not None
            and expiry != previous_expiry
            and not item.get("constant_maturity_interpolated")
        ):
            break_reason = "expiry_rollover"
        if break_reason:
            for key in cost_keys:
                current[key] = None
            current["series_break_reason"] = break_reason
            # Carry the from/to values so chart_builder can render a readable
            # annotation label ("到期日切换：08-28 → 09-25" /
            # "方法切换：otm_estimate → constant_delta"). previous_* may be None
            # on the very first row in theory, but break_reason is only set when
            # previous_* is not None, so the lookups below are safe.
            if break_reason == "expiry_rollover":
                current["series_break_detail"] = (
                    f"expiry_rollover:{previous_expiry}->{expiry}"
                )
            elif break_reason == "method_change":
                current["series_break_detail"] = (
                    f"method_change:{previous_method}->{method}"
                )
        output.append(current)
        previous_expiry = expiry
        previous_method = method
    return output


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
        all_expiries = sorted({quote.expiry for quote in quotes})
        expiries = standard_expiries(all_expiries, as_of=as_of)
        quotes = [quote for quote in quotes if quote.expiry in expiries]
        if not expiries or spot_price <= 0:
            raise ValueError("live snapshot lacks a usable BTC option chain")
        maturity_selection = select_constant_maturity_expiry(
            expiries,
            as_of=as_of,
            maturity_bucket=maturity_bucket,
        )
        fallback_expiry = maturity_selection.get("expiry") or expiries[-1]
        selection_status = "ok"
        selection_reason = ""
        if expiry_mode == "fixed":
            if expiry in expiries:
                selected_expiry = expiry
            else:
                requested = classify_expiry(expiry, as_of=as_of)
                target_dte = (
                    requested.dte
                    if requested.dte and requested.dte > 0
                    else BUCKET_DTE[maturity_bucket]
                )
                selected_expiry = nearest_standard_expiry(
                    expiries, as_of=as_of, target_dte=target_dte
                ) or fallback_expiry
                selection_status = "normalized"
                selection_reason = "所选到期日不是标准月末到期，已迁移至最近标准到期日。"
        else:
            selected_expiry = fallback_expiry
            if expiry and expiry != selected_expiry:
                selection_status = "constant_maturity_override"
                selection_reason = "恒定期限模式忽略固定到期日，按期限桶选择标准到期日。"
        selected_context = classify_expiry(selected_expiry, as_of=as_of)
        chain = chain_rows_for_expiry(quotes, selected_expiry)
        walls = option_walls(chain)
        pain = max_pain(chain)
        # The fallback pool is every standard expiry *other* than the
        # selected one, in case the primary chain is too sparse to produce
        # 25D call/put on its own. The metric stays per-selected-expiry in
        # semantics; only missing sides are borrowed (skew_25d handles that).
        skew_fallback_quotes = [
            quote for quote in quotes if quote.expiry != selected_expiry
        ]
        skew = skew_25d(
            [quote for quote in quotes if quote.expiry == selected_expiry],
            spot_price,
            as_of=as_of,
            fallback_quotes=skew_fallback_quotes,
        )
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
        maturity_ladder: list[dict[str, Any]] = []
        for ladder_expiry in expiries:
            ladder_context = classify_expiry(ladder_expiry, as_of=as_of)
            ladder_quotes = [quote for quote in quotes if quote.expiry == ladder_expiry]
            ladder_rows = chain_rows_for_expiry(quotes, ladder_expiry)
            ladder_walls = option_walls(ladder_rows)
            ladder_pain = max_pain(ladder_rows)
            ladder_ratios = put_call_ratios(ladder_rows)
            ladder_skew = skew_25d(
                ladder_quotes,
                spot_price,
                as_of=as_of,
            )
            protection_cost = standardized_protection_costs(
                ladder_quotes,
                spot_price=spot_price,
                as_of=as_of,
            )
            same_expiry_history = [
                item for item in history if item.get("source_expiry") == ladder_expiry
            ]
            total_oi = float(ladder_ratios.get("call_oi") or 0) + float(
                ladder_ratios.get("put_oi") or 0
            )
            maturity_ladder.append(
                {
                    "expiry": ladder_expiry,
                    "dte": ladder_context.dte,
                    "cycle": ladder_context.cycle,
                    "maturity_band": _maturity_band(ladder_context.dte),
                    "call_wall": ladder_walls.get("call_wall_strike"),
                    "put_wall": ladder_walls.get("put_wall_strike"),
                    "max_pain": ladder_pain.get("strike"),
                    "call_wall_distance_pct": (
                        (float(ladder_walls["call_wall_strike"]) - spot_price) / spot_price
                        if ladder_walls.get("call_wall_strike") is not None else None
                    ),
                    "put_wall_distance_pct": (
                        (float(ladder_walls["put_wall_strike"]) - spot_price) / spot_price
                        if ladder_walls.get("put_wall_strike") is not None else None
                    ),
                    "call_wall_oi": ladder_walls.get("call_wall_oi"),
                    "put_wall_oi": ladder_walls.get("put_wall_oi"),
                    "call_wall_concentration": _wall_concentration(
                        ladder_rows, "call", ladder_walls.get("call_wall_oi")
                    ),
                    "put_wall_concentration": _wall_concentration(
                        ladder_rows, "put", ladder_walls.get("put_wall_oi")
                    ),
                    "total_oi": total_oi,
                    "atm_iv": next(
                        (
                            item.get("atm_iv")
                            for item in atm_iv_term_structure(ladder_quotes, spot_price)
                            if item.get("expiry") == ladder_expiry
                        ),
                        None,
                    ),
                    "skew_25d": ladder_skew,
                    "put_call_ratios": ladder_ratios,
                    "protection_cost": protection_cost,
                    "wall_movement": {
                        "call_wall": movement_summary(same_expiry_history, "call_wall_strike"),
                        "put_wall": movement_summary(same_expiry_history, "put_wall_strike"),
                    },
                    "data_status": (
                        "ok" if ladder_skew.get("status") == "ok" and total_oi > 0
                        else "partial"
                    ),
                }
            )
        ladder_total_oi = sum(float(item.get("total_oi") or 0) for item in maturity_ladder)
        for item in maturity_ladder:
            item["term_oi_share"] = (
                float(item.get("total_oi") or 0) / ladder_total_oi
                if ladder_total_oi > 0 else None
            )
        options_direction = _options_direction(maturity_ladder)
        iv_values = [
            float(value)
            for item in maturity_ladder
            if (value := _finite(item.get("atm_iv"))) is not None
        ]
        selected_iv = next(
            (
                _finite(item.get("atm_iv"))
                for item in maturity_ladder
                if item["expiry"] == selected_expiry
            ),
            None,
        )
        iv_state = (
            "iv_high" if selected_iv is not None and selected_iv >= 0.65
            else "iv_low" if selected_iv is not None and selected_iv <= 0.40
            else "iv_neutral" if selected_iv is not None
            else "data_insufficient"
        )
        volatility_risk = {
            "state": iv_state,
            "label": {
                "iv_high": "隐含波动率偏高",
                "iv_low": "隐含波动率偏低",
                "iv_neutral": "隐含波动率处于常态区间",
            }.get(iv_state, "波动率数据不足"),
            "selected_atm_iv": selected_iv,
            "term_slope": (
                iv_values[-1] - iv_values[0] if len(iv_values) >= 2 else None
            ),
            "basis": "标准到期日 ATM IV 与期限斜率",
        }
        target_dte = BUCKET_DTE[maturity_bucket]
        interpolated_cost: dict[str, Any] = {}
        interpolation_sources: list[dict[str, Any]] = []
        interpolation_status = "data_insufficient"
        for key in (
            "call_protection_cost_pct",
            "put_protection_cost_pct",
            "debit_spread_cost_pct",
        ):
            value, sources, status = _interpolate_metric(maturity_ladder, target_dte, key)
            interpolated_cost[key] = value
            if len(sources) > len(interpolation_sources):
                interpolation_sources = sources
            if status == "interpolated":
                interpolation_status = status
            elif interpolation_status == "data_insufficient":
                interpolation_status = status
        interpolated_cost.update(
            {
                "target_dte": target_dte,
                "sources": interpolation_sources,
                "interpolation_status": interpolation_status,
                "selection_method": "constant_delta",
            }
        )
        futures_basis = {
            row.instrument: {
                "basis_pct": (
                    row.basis_pct
                    if row.basis_pct is not None
                    else _basis_pct(row.mark_price, row.index_price or spot_price)
                ),
                "annualized_basis_pct": row.annualized_basis_pct,
            }
            for row in futures
        }
        for row in futures:
            basis_pct = futures_basis[row.instrument]["basis_pct"]
            futures_basis[row.instrument]["annualized_basis_pct"] = (
                row.annualized_basis_pct
                if row.annualized_basis_pct is not None
                else _annualized_basis_pct(basis_pct, row.expiry, as_of=as_of)
            )

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
                "basis_pct": futures_basis[row.instrument]["basis_pct"],
                "annualized_basis_pct": futures_basis[row.instrument][
                    "annualized_basis_pct"
                ],
            }
            for row in futures
        ]
        basis_points = [
            {
                "expiry": row.expiry,
                "basis_pct": futures_basis[row.instrument]["basis_pct"],
                "annualized_basis_pct": futures_basis[row.instrument][
                    "annualized_basis_pct"
                ],
            }
            for row in futures
            if row.expiry
            and futures_basis[row.instrument]["basis_pct"] is not None
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
        same_expiry_history = [
            item
            for item in history
            if item.get("source_expiry") == selected_expiry
            or (len(expiries) == 1 and not item.get("source_expiry"))
        ]
        level_history = filter_history_window(
            same_expiry_history,
            resolve_window("wall_max_pain", window),
            as_of=as_of,
        )
        bucket_history = [
            item
            for item in history
            if item.get("maturity_bucket") in {None, maturity_bucket}
        ]
        risk_history = _break_legacy_rolls(
            filter_history_window(
                bucket_history,
                resolve_window("hedge_cost", window),
                as_of=as_of,
            ),
            expiry_mode=expiry_mode,
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
            risk_history=risk_history,
        )
        charts = consolidated["charts"]
        movement_history = filter_history_window(
            same_expiry_history,
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
        current_timestamp = (
            live_snapshot.data_timestamp
            if live_snapshot.data_timestamp
            else datetime.now(timezone.utc)
        )
        previous_key_level = _previous_history_item(
            movement_history,
            current_timestamp=current_timestamp,
        )
        comparison_timestamp = previous_key_level.get("timestamp")
        comparison_is_same_day = False
        previous_day = _history_item_day(previous_key_level) if previous_key_level else None
        if previous_day is not None:
            comparison_is_same_day = (
                previous_day == current_timestamp.astimezone(timezone.utc).date()
            )
        options_wall_signal = evaluate_key_levels_axis(
            spot_price=spot_price,
            previous_spot_price=_finite(previous_key_level.get("spot_price")),
            call_wall=walls.get("call_wall_strike"),
            previous_call_wall=_finite(previous_key_level.get("call_wall_strike")),
            put_wall=walls.get("put_wall_strike"),
            previous_put_wall=_finite(previous_key_level.get("put_wall_strike")),
            max_pain=pain.get("strike"),
            previous_max_pain=_finite(previous_key_level.get("max_pain_strike")),
            data_quality_status=live_snapshot.snapshot_state,
            provider=live_snapshot.primary_option_provider,
            quality=live_snapshot.snapshot_state,
            stale=live_snapshot.snapshot_state == "stale",
            rollover=bool(previous_key_level.get("rollover")),
            provider_changed=bool(previous_key_level.get("source_provider_change")),
            comparison_basis=(
                "previous_utc_day"
                if previous_key_level
                else "missing_previous_utc_day"
            ),
            comparison_timestamp=comparison_timestamp,
            comparison_is_same_day=comparison_is_same_day,
            selected_expiry=selected_expiry,
            source_dte=selected_context.dte,
            oi_context={
                "call_wall_open_interest": walls.get("call_wall_oi"),
                "put_wall_open_interest": walls.get("put_wall_oi"),
                "put_call_oi_ratio": ratios.get("put_call_oi_ratio"),
            },
            iv_context={
                "put_call_skew": skew.get("put_call_skew"),
                "skew_status": skew.get("status"),
                "delta_source": skew.get("delta_source"),
                "atm_iv_term_points": len(atm_points),
            },
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
        latest_hedge_cost = interpolated_cost.get("put_protection_cost_pct")
        hedge_cost_state = (
            "expensive"
            if latest_hedge_cost is not None and latest_hedge_cost >= 0.03
            else "cheap"
            if latest_hedge_cost is not None and latest_hedge_cost <= 0.015
            else "neutral"
        )
        comparable_costs = [
            float(value)
            for item in risk_history
            if item.get("constant_maturity_interpolated")
            if (value := _finite(item.get("put_protection_cost_pct"))) is not None
        ]
        previous_cost = comparable_costs[-1] if comparable_costs else None
        seven_day_cost = comparable_costs[-7] if len(comparable_costs) >= 7 else None
        cost_percentile = (
            sum(value <= float(latest_hedge_cost) for value in comparable_costs)
            / len(comparable_costs)
            if latest_hedge_cost is not None and comparable_costs else None
        )
        protection_cost_regime = {
            "state": hedge_cost_state,
            "label": {
                "expensive": "保护成本偏高",
                "cheap": "保护成本偏低",
                "neutral": "保护成本处于常态区间",
            }[hedge_cost_state],
            "current_put_cost_pct": latest_hedge_cost,
            "current_call_cost_pct": interpolated_cost.get("call_protection_cost_pct"),
            "call_put_cost_spread": (
                float(interpolated_cost["put_protection_cost_pct"])
                - float(interpolated_cost["call_protection_cost_pct"])
                if interpolated_cost.get("put_protection_cost_pct") is not None
                and interpolated_cost.get("call_protection_cost_pct") is not None
                else None
            ),
            "change_1d": (
                (float(latest_hedge_cost) - previous_cost) / abs(previous_cost)
                if latest_hedge_cost is not None and previous_cost not in {None, 0}
                else None
            ),
            "change_7d": (
                (float(latest_hedge_cost) - seven_day_cost) / abs(seven_day_cost)
                if latest_hedge_cost is not None and seven_day_cost not in {None, 0}
                else None
            ),
            "history_percentile": cost_percentile,
            "interpolation_status": interpolation_status,
            "sources": interpolation_sources,
            "direction_effect": "risk_only",
            "primary_reason": (
                "采用同 Delta、恒定期限成本；绝对水平只影响风险与对冲，不单独决定方向。"
            ),
        }
        analysis = build_market_state(
            price_oi_state=metric_summary["price_oi_regime"]["state"],
            funding_state=funding_state,
            iv_state=iv_state,
            skew_state=(
                "call_skew_high"
                if skew.get("status") == "ok" and float(skew["put_call_skew"]) <= -0.03
                else "put_skew_high"
                if skew.get("status") == "ok" and float(skew["put_call_skew"]) >= 0.03
                else "skew_neutral"
                if skew.get("status") == "ok"
                else "data_insufficient"
            ),
            wall_movement=wall_movement,
            max_pain_movement=max_pain_movement,
            data_quality_status=live_snapshot.snapshot_state,
            basis_state=basis_state,
            hedge_cost_state=hedge_cost_state,
            technical_bias=None,
            options_wall_signal=options_wall_signal,
            options_direction=options_direction,
        )
        analysis["options_direction"] = options_direction
        analysis["volatility_risk"] = volatility_risk
        analysis["protection_cost_regime"] = protection_cost_regime
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
                "data_points": len(risk_history),
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
            source_expiry=selected_expiry,
            source_dte=selected_context.dte,
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
                    "standard_expiries": expiries,
                    "maturity_ladder": maturity_ladder,
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
                        "options_wall_signal": options_wall_signal,
                        "options_direction": options_direction,
                        "volatility_risk": volatility_risk,
                        "protection_cost_regime": protection_cost_regime,
                        "constant_maturity_protection_cost": interpolated_cost,
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
                    "effective_expiry": selected_expiry,
                    "effective_dte": selected_context.dte,
                    "selection_status": selection_status,
                    "selection_reason": selection_reason,
                    "window": window,
                    "strike_range_pct": strike_range_pct,
                },
                "maturity_selection": maturity_selection,
                "joint_analysis": analysis,
                "hedge_context": {
                    "spot_price": spot_price,
                    "iv_state": iv_state,
                    "liquidity_state": "usable",
                    "preferred_expiry_bucket": "60D",
                    "note": "仅生成有限风险保护方案，不执行下单。",
                },
                "indicator_judgements": [
                    build_indicator_judgement(
                        {
                            "indicator_key": "funding_rate",
                            "signal_state": funding_state,
                            "value_num": funding_median,
                            "comment": (
                                "资金费率只反映永续合约拥挤度，"
                                "用于降级或确认，不单独决定方向。"
                            ),
                        },
                        timeframe="current",
                        freshness=live_snapshot.snapshot_state,
                        source_ref="btc_derivatives.futures.funding",
                    ),
                    build_indicator_judgement(
                        {
                            "indicator_key": "call_wall",
                            "signal_state": wall_movement.get("call_wall", "unknown"),
                            "value_num": walls.get("call_wall_strike"),
                            "comment": "Call Wall 仅作为关键价位，不参与方向投票。",
                        },
                        timeframe=maturity_bucket,
                        freshness=live_snapshot.snapshot_state,
                        source_ref="btc_derivatives.options.call_wall",
                    ),
                    build_indicator_judgement(
                        {
                            "indicator_key": "put_wall",
                            "signal_state": wall_movement.get("put_wall", "unknown"),
                            "value_num": walls.get("put_wall_strike"),
                            "comment": "Put Wall 仅作为关键价位，不参与方向投票。",
                        },
                        timeframe=maturity_bucket,
                        freshness=live_snapshot.snapshot_state,
                        source_ref="btc_derivatives.options.put_wall",
                    ),
                    build_indicator_judgement(
                        {
                            "indicator_key": "max_pain",
                            "signal_state": max_pain_movement,
                            "value_num": pain.get("strike"),
                            "comment": "最大痛点只用于观察持仓分布迁移，不作为价格预测。",
                        },
                        timeframe=maturity_bucket,
                        freshness=live_snapshot.snapshot_state,
                        source_ref="btc_derivatives.options.max_pain",
                    ),
                ],
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
                    "greeks_coverage": {
                        "provider_delta_count": sum(quote.delta is not None for quote in quotes),
                        "total_option_count": len(quotes),
                        "provider_delta_ratio": (
                            sum(quote.delta is not None for quote in quotes) / len(quotes)
                            if quotes else 0
                        ),
                        "effective_delta_source": skew.get("delta_source", "unavailable"),
                    },
                    "expiry_coverage": {
                        "raw_expiry_count": len(all_expiries),
                        "standard_expiry_count": len(expiries),
                        "excluded_expiry_count": len(all_expiries) - len(expiries),
                        "policy": "month_end_friday",
                    },
                    "warnings": list(live_snapshot.missing_reasons),
                },
            }
        )
