from __future__ import annotations

from datetime import datetime, timezone
from typing import Any

from app.schemas.btc_derivatives import BtcDerivativesDashboardResponse
from app.schemas.btc_derivatives_sources import (
    LiveSnapshotEnvelope,
    SourceProbeResponse,
)
from app.schemas.refresh import RefreshReceipt
from app.services.btc_derivatives.chart_builder import (
    build_consolidated_dashboard_charts,
)
from app.services.btc_derivatives.service import BtcDerivativesService
from app.services.btc_derivatives.sources.collector import LiveCollector
from app.services.refresh_jobs import refresh_job_service


def _iso_now() -> str:
    return datetime.now(timezone.utc).replace(microsecond=0).isoformat()


def _protection_costs(
    envelope: LiveSnapshotEnvelope,
    expiry: str | None,
    spot_price: float | None,
) -> dict[str, float | str | None]:
    if not expiry or not spot_price:
        return {
            "call_protection_cost_pct": None,
            "put_protection_cost_pct": None,
            "debit_spread_cost_pct": None,
            "selection_method": None,
        }
    chain = [
        item
        for item in envelope.options
        if item.expiry == expiry and item.mid is not None and item.mid > 0
    ]

    def choose(option_type: str, target_delta: float, otm_pct: float):
        side = [item for item in chain if item.option_type == option_type]
        with_delta = [item for item in side if item.delta is not None]
        if with_delta:
            return min(
                with_delta,
                key=lambda item: abs(abs(item.delta or 0) - target_delta),
            ), "delta"
        target_strike = spot_price * (
            1 + otm_pct if option_type == "call" else 1 - otm_pct
        )
        return (
            min(side, key=lambda item: abs(item.strike - target_strike))
            if side
            else None
        ), "otm_estimate"

    long_call, call_method = choose("call", 0.25, 0.05)
    long_put, put_method = choose("put", 0.25, 0.05)
    short_call, spread_method = choose("call", 0.10, 0.15)
    debit = (
        max((long_call.mid or 0) - (short_call.mid or 0), 0)
        if long_call and short_call and short_call.strike > long_call.strike
        else None
    )
    return {
        "call_protection_cost_pct": (
            (long_call.mid or 0) / spot_price if long_call else None
        ),
        "put_protection_cost_pct": (
            (long_put.mid or 0) / spot_price if long_put else None
        ),
        "debit_spread_cost_pct": debit / spot_price if debit is not None else None,
        "selection_method": (
            "delta"
            if {call_method, put_method, spread_method} == {"delta"}
            else "otm_estimate"
        ),
    }


def _empty_dashboard(
    envelope: LiveSnapshotEnvelope,
    *,
    expiry_mode: str,
    maturity_bucket: str,
    window: str | None,
    strike_range_pct: str,
) -> BtcDerivativesDashboardResponse:
    futures_rows = [
        {
            "exchange": item.provider,
            "instrument": item.instrument,
            "timestamp": (item.provider_timestamp or item.collected_at).isoformat(),
            "mark_price": item.mark_price,
            "funding_rate": item.funding_rate,
            "open_interest_usd": item.open_interest_usd,
            "volume_24h_usd": item.volume_24h_usd,
            "expiry": item.expiry,
            "basis_pct": item.basis_pct,
            "annualized_basis_pct": item.annualized_basis_pct,
        }
        for item in envelope.perps
    ]
    spot_values = [
        item.index_price or item.mark_price
        for item in envelope.perps
        if item.index_price is not None or item.mark_price is not None
    ]
    spot_price = (
        sorted(spot_values)[len(spot_values) // 2]
        if spot_values
        else None
    )
    consolidated = build_consolidated_dashboard_charts(
        price_history=envelope.price_history,
        futures_rows=futures_rows,
        basis_points=[],
        atm_iv_points=[],
        strike_rows=[],
        history=[],
        spot_price=spot_price,
        call_wall=None,
        put_wall=None,
        max_pain=None,
    )
    charts = consolidated["charts"]
    reason = (
        "真实期权主链当前不可用；期货与永续数据仍按可用公开源展示"
        if envelope.perps
        else "真实公开数据源当前不可用，且没有 15 分钟内的真实缓存"
    )
    futures_chart_ids = {
        "leverage_pressure_timeline",
        "exchange_crowding_snapshot",
        "term_structure",
    }
    for chart_id, chart in charts.items():
        if chart["status"] != "ok":
            chart["empty_reason"] = reason
        providers = sorted(
            {
                item.provider
                for item in (
                    envelope.perps
                    if chart_id in futures_chart_ids
                    else envelope.options
                )
            }
        )
        chart["metadata"] = {
            **chart.get("metadata", {}),
            "providers": providers,
            "primary_provider": providers[0] if providers else None,
            "updated_at": (
                envelope.data_timestamp.isoformat()
                if envelope.data_timestamp
                else None
            ),
            "quality": envelope.snapshot_state,
            "missing_reason": reason if chart["status"] != "ok" else None,
        }
    snapshot_state = envelope.snapshot_state if envelope.perps else "data_insufficient"
    return BtcDerivativesDashboardResponse.model_validate(
        {
            "generated_at": _iso_now(),
            "snapshot_state": snapshot_state,
            "data_timestamp": (
                envelope.data_timestamp.isoformat()
                if envelope.data_timestamp
                else None
            ),
            "source_status": [
                item.model_dump(mode="json") for item in envelope.source_status
            ],
            "cards": [],
            "futures": {
                "rows": futures_rows,
                "metrics": {},
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
                "selected_expiry": None,
                "expiries": [],
                "chain": [],
                "metrics": {},
                "walls": {},
                "max_pain": {},
                "key_level_cards": [],
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
                "selected_expiry": None,
                "window": window,
                "strike_range_pct": strike_range_pct,
            },
            "maturity_selection": {
                "maturity_bucket": maturity_bucket,
                "status": "data_insufficient",
            },
            "joint_analysis": {
                "display_items": [],
                "inference_blocks": [
                    {
                        "category": category,
                        "title": title,
                        "tone": "neutral",
                        "explanation": "真实数据暂不可用，无法形成推定。",
                    }
                    for category, title in (
                        ("futures", "期货与永续"),
                        ("options", "期权"),
                        ("key_levels", "关键价位"),
                        ("hedge_cost", "保护成本"),
                    )
                ],
                "direct_command": "none_data_insufficient",
            },
            "hedge_context": {
                "spot_price": spot_price,
                "iv_state": "data_insufficient",
                "liquidity_state": "data_insufficient",
                "note": "真实数据不足，暂不生成保护方案。",
            },
            "data_quality": {
                "status": "partial" if envelope.perps else "data_insufficient",
                "mode": snapshot_state,
                "providers": [
                    item.model_dump(mode="json")
                    for item in envelope.source_status
                ],
                "missing_fields": envelope.missing_reasons or [reason],
                "warnings": [reason],
                "history_available": False,
            },
        }
    )


class BtcDerivativesLiveService:
    def __init__(
        self,
        *,
        collector: LiveCollector | None = None,
        dashboard_builder: BtcDerivativesService | None = None,
    ) -> None:
        self.collector = collector or LiveCollector()
        self.dashboard_builder = dashboard_builder or BtcDerivativesService()

    def source_status(self) -> list[dict[str, Any]]:
        return [
            item.model_dump(mode="json")
            for item in self.collector.statuses()
        ]

    async def probe(self) -> SourceProbeResponse:
        return await self.collector.probe()

    async def dashboard(
        self,
        *,
        expiry: str | None = None,
        expiry_mode: str = "constant_maturity",
        maturity_bucket: str = "60D",
        window: str | None = None,
        strike_range_pct: str = "30",
        force: bool = False,
    ) -> BtcDerivativesDashboardResponse:
        envelope = await self.collector.snapshot(
            force=force,
            allow_network=force,
        )
        if (
            envelope.snapshot_state == "data_insufficient"
            or not envelope.options
        ):
            return _empty_dashboard(
                envelope,
                expiry_mode=expiry_mode,
                maturity_bucket=maturity_bucket,
                window=window,
                strike_range_pct=strike_range_pct,
            )
        envelope.key_level_history = self.collector.cache.read_history()
        try:
            dashboard = self.dashboard_builder.build_dashboard(
                expiry=expiry,
                expiry_mode=expiry_mode,
                maturity_bucket=maturity_bucket,
                window=window,
                strike_range_pct=strike_range_pct,
                live_snapshot=envelope,
            )
        except (ValueError, KeyError):
            envelope.missing_reasons.append("主期权链缺少可计算的到期日、现价或持仓量")
            return _empty_dashboard(
                envelope,
                expiry_mode=expiry_mode,
                maturity_bucket=maturity_bucket,
                window=window,
                strike_range_pct=strike_range_pct,
            )
        previous = envelope.key_level_history[-1] if envelope.key_level_history else {}
        metrics = dashboard.options.metrics
        protection = _protection_costs(
            envelope,
            dashboard.options.selected_expiry,
            dashboard.hedge_context.get("spot_price"),
        )
        point = {
            "timestamp": (
                envelope.data_timestamp or datetime.now(timezone.utc)
            ).isoformat(),
            "expiry": dashboard.options.selected_expiry,
            "source_expiry": dashboard.options.selected_expiry,
            "source_dte": dashboard.maturity_selection.get("dte"),
            "maturity_bucket": maturity_bucket,
            "spot_price": dashboard.hedge_context.get("spot_price"),
            "call_wall_strike": dashboard.options.walls.get("call_wall_strike"),
            "put_wall_strike": dashboard.options.walls.get("put_wall_strike"),
            "max_pain_strike": dashboard.options.max_pain.get("strike"),
            "skew_25d": metrics.get("skew_25d", {}).get("put_call_skew"),
            "put_call_oi_ratio": metrics.get("put_call_ratios", {}).get(
                "put_call_oi_ratio"
            ),
            "put_call_volume_ratio": metrics.get("put_call_ratios", {}).get(
                "put_call_volume_ratio"
            ),
            **protection,
            "source_provider": envelope.primary_option_provider,
            "source_provider_change": bool(
                previous.get("source_provider")
                and previous.get("source_provider")
                != envelope.primary_option_provider
            ),
            "rollover": bool(
                previous.get("source_expiry")
                and previous.get("source_expiry")
                != dashboard.options.selected_expiry
            ),
        }
        envelope.key_level_history = self.collector.cache.append_daily(point)
        self.collector.archive.append(
            provider="derived",
            underlying="BTC",
            data_type="daily_metrics",
            captured_at=envelope.data_timestamp or datetime.now(timezone.utc),
            records=[point],
        )
        return self.dashboard_builder.build_dashboard(
            expiry=expiry,
            expiry_mode=expiry_mode,
            maturity_bucket=maturity_bucket,
            window=window,
            strike_range_pct=strike_range_pct,
            live_snapshot=envelope,
        )

    def enqueue_refresh(
        self,
        *,
        expiry: str | None = None,
        expiry_mode: str = "constant_maturity",
        maturity_bucket: str = "60D",
        window: str | None = None,
        strike_range_pct: str = "30",
    ) -> RefreshReceipt:
        dedupe_key = ":".join(
            [
                "btc_derivatives",
                expiry or "-",
                expiry_mode,
                maturity_bucket,
                window or "-",
                strike_range_pct,
            ]
        )

        async def operation() -> dict[str, str]:
            await self.dashboard(
                expiry=expiry,
                expiry_mode=expiry_mode,
                maturity_bucket=maturity_bucket,
                window=window,
                strike_range_pct=strike_range_pct,
                force=True,
            )
            return {"cache_key": "btc-derivatives:dashboard"}

        return refresh_job_service.enqueue(
            scope="btc_derivatives",
            dedupe_key=dedupe_key,
            operation=operation,
        )


btc_derivatives_live_service = BtcDerivativesLiveService()
