from __future__ import annotations

import csv
import hashlib
import time as time_module
from calendar import monthrange
from dataclasses import dataclass
from datetime import UTC, date, datetime, time, timedelta
from decimal import Decimal
from io import StringIO

import httpx

from app.core.config import settings
from app.core.decimal_utils import DECIMAL_ZERO, D
from app.core.ids import new_id
from app.db.models.market import (
    IndicatorAlertEvent,
    IndicatorAlertRule,
    IndicatorDefinition,
    IndicatorMonitoringPolicy,
    IndicatorObservation,
    IndicatorRun,
    MacroEventCalendar,
    MacroSourceHealth,
)
from app.monitoring.loader import load_alert_rules, load_indicator_catalog, load_refresh_policies
from app.quant.indicators import (
    adx_wilder_series,
    atr_ema_series,
    atr_wilder_series,
    bbands_series,
    ema_series,
    macd_series,
    obv_series,
    rsi_wilder_series,
    sma_series,
)
from app.repositories.market_repository import MarketRepository
from app.services.contract_snapshot import ContractSnapshotService
from app.services.macro.provider_registry import MacroProviderRegistry
from app.services.market import MarketService
from app.services.microstructure import (
    TradeSample,
    aggregate_cvd_delta,
    summarize_depth_slippage,
    summarize_open_interest,
)

MICROSTRUCTURE_KEYS = {
    "cvd_delta",
    "open_interest_notional",
    "depth_liquidity",
    "slippage_bps",
}


@dataclass(slots=True)
class SyncResult:
    run_id: str
    indicator_key: str
    rows_written: int
    observations: list[IndicatorObservation]


class IndicatorMonitoringService:
    def __init__(self, repository: MarketRepository) -> None:
        self.repository = repository
        self.market_service = MarketService(repository)
        self.contract_snapshot_service = ContractSnapshotService(
            repository,
            market_service=self.market_service,
        )
        self.macro_provider_registry = MacroProviderRegistry()
        self._technical_batch_cache: dict | None = None

    async def seed_defaults(self, default_instrument_id: str = "btc-usdt-perp") -> None:
        for row in load_indicator_catalog():
            await self.repository.upsert_indicator_definition(
                IndicatorDefinition(
                    indicator_key=row["indicator_key"],
                    display_name=row["display_name"],
                    category=row["category"],
                    family=row["family"],
                    source_provider=row["source_provider"],
                    source_kind=row["source_kind"],
                    calc_engine=row["calc_engine"],
                    calc_params_json=row.get("calc_params", {}),
                    supported_assets_json=row.get("supported_assets", []),
                    supported_timeframes_json=row.get("supported_timeframes", []),
                    output_fields_json=row.get("output_fields", []),
                    signal_states_json=row.get("signal_states", []),
                    default_thresholds_json=row.get("default_thresholds", {}),
                    use_cases_json=row.get("use_cases", []),
                    is_enabled=bool(row.get("is_enabled", True)),
                )
            )

        for row in load_refresh_policies():
            instrument_id = row.get("instrument_id")
            if row.get("scope_type") == "instrument" and instrument_id is None:
                instrument_id = default_instrument_id
            await self.repository.upsert_monitoring_policy(
                IndicatorMonitoringPolicy(
                    policy_id=self._stable_id(
                        "pol",
                        row["indicator_key"],
                        row.get("scope_type", "global"),
                        instrument_id or "",
                        row.get("asset_code") or "",
                        row.get("timeframe") or "",
                    ),
                    indicator_key=row["indicator_key"],
                    scope_type=row.get("scope_type", "global"),
                    instrument_id=instrument_id,
                    asset_code=row.get("asset_code"),
                    timeframe=row.get("timeframe"),
                    mode=row["mode"],
                    interval_seconds=row.get("interval_seconds"),
                    cron_expr=row.get("cron_expr"),
                    timezone=row.get("timezone"),
                    event_key=row.get("event_key"),
                    calendar_source=row.get("calendar_source"),
                    release_key=row.get("release_key"),
                    fallback_interval_seconds=row.get("fallback_interval_seconds"),
                    priority=int(row.get("priority", 5)),
                    is_enabled=True,
                    next_run_at=datetime.now(UTC),
                )
            )

        for row in load_alert_rules():
            await self.repository.upsert_alert_rule(
                IndicatorAlertRule(
                    rule_key=row["rule_key"],
                    indicator_key=row["indicator_key"],
                    enabled=bool(row.get("enabled", True)),
                    severity=row["severity"],
                    category=row["category"],
                    scope_type=row["scope_type"],
                    condition_type=row["condition_type"],
                    comparator=row.get("comparator"),
                    threshold_num=D(row["threshold_num"])
                    if row.get("threshold_num") is not None
                    else None,
                    lower_threshold_num=D(row["lower_threshold_num"])
                    if row.get("lower_threshold_num") is not None
                    else None,
                    upper_threshold_num=D(row["upper_threshold_num"])
                    if row.get("upper_threshold_num") is not None
                    else None,
                    state_value=row.get("state_value"),
                    percentile_ref_window_points=row.get("percentile_ref_window_points"),
                    consecutive_points=row.get("consecutive_points"),
                    dedupe_window_seconds=int(row.get("dedupe_window_seconds", 300)),
                    cooldown_seconds=int(row.get("cooldown_seconds", 300)),
                    action_channels_json=row.get("action_channels", ["db", "api", "ui"]),
                    message_template=row["message_template"],
                    extra_config_json=row.get("extra_config", {}),
                )
            )

        await self.ensure_macro_calendar()

    async def run_due_policies(self, as_of: datetime | None = None) -> list[SyncResult]:
        now = as_of or datetime.now(UTC)
        results: list[SyncResult] = []
        policies = await self.repository.list_monitoring_policies(
            enabled_only=True, due_only=True, as_of=now
        )
        for policy in policies:
            try:
                results.append(await self.run_policy(policy, trigger_type="scheduler"))
            finally:
                await self.repository.update_monitoring_policy_schedule(
                    policy.policy_id,
                    last_run_at=now,
                    next_run_at=self._next_run(policy, now),
                )
        return results

    async def run_policy(
        self, policy: IndicatorMonitoringPolicy, trigger_type: str = "manual"
    ) -> SyncResult:
        definition = await self.repository.get_indicator_definition(policy.indicator_key)
        if definition is None:
            raise ValueError(f"unknown indicator: {policy.indicator_key}")
        run = await self.repository.add_indicator_run(
            IndicatorRun(
                run_id=new_id("run"),
                indicator_key=policy.indicator_key,
                scope_type=policy.scope_type,
                scope_ref=policy.instrument_id or policy.asset_code or "global",
                status="running",
                trigger_type=trigger_type,
                trigger_ref=policy.event_key or policy.mode,
                started_at=datetime.now(UTC),
                rows_written=0,
                stats_json={},
            )
        )
        try:
            observations = await self._sync_definition(definition, policy, run.run_id)
            await self._evaluate_alerts(observations)
            await self.repository.finish_indicator_run(
                run.run_id,
                status="succeeded",
                rows_written=len(observations),
                finished_at=datetime.now(UTC),
                stats_json={"indicator_key": policy.indicator_key},
            )
            return SyncResult(
                run_id=run.run_id,
                indicator_key=policy.indicator_key,
                rows_written=len(observations),
                observations=observations,
            )
        except Exception as exc:
            await self.repository.finish_indicator_run(
                run.run_id,
                status="failed",
                rows_written=0,
                error_code="sync_failed",
                error_message=str(exc),
                finished_at=datetime.now(UTC),
                stats_json={},
            )
            raise

    async def sync_macro(self) -> list[SyncResult]:
        results: list[SyncResult] = []
        policies = await self.repository.list_monitoring_policies(
            enabled_only=True, category="macro"
        )
        for policy in policies:
            try:
                results.append(await self.run_policy(policy, trigger_type="manual"))
            except Exception:
                continue
        await self._refresh_macro_source_health()
        return results

    async def sync_onchain(self) -> list[SyncResult]:
        return [
            await self.run_policy(policy, trigger_type="manual")
            for policy in await self.repository.list_monitoring_policies(
                enabled_only=True, category="onchain"
            )
        ]

    async def sync_technical(
        self,
        instrument_id: str,
        timeframe: str | None = None,
        *,
        include_microstructure: bool = True,
    ) -> list[SyncResult]:
        results: list[SyncResult] = []
        policies = [
            policy
            for policy in await self.repository.list_monitoring_policies(
                enabled_only=True, instrument_id=instrument_id, category="technical"
            )
            if (not timeframe or policy.timeframe in {None, timeframe})
            and (include_microstructure or policy.indicator_key not in MICROSTRUCTURE_KEYS)
        ]
        self._technical_batch_cache = {
            "candles": {},
            "futures_ref": {},
            "contract": {},
            "trades": {},
            "contract_stats": {},
            "order_book": {},
            "history": {},
        }
        try:
            for policy in policies:
                results.append(await self.run_policy(policy, trigger_type="manual"))
        finally:
            self._technical_batch_cache = None
        return results

    def _batch_bucket(self, bucket: str) -> dict:
        if self._technical_batch_cache is None:
            return {}
        return self._technical_batch_cache.setdefault(bucket, {})

    async def _cached_gate_futures_ref(self, instrument_id: str):
        bucket = self._batch_bucket("futures_ref")
        if instrument_id in bucket:
            return bucket[instrument_id]
        ref = await self._gate_futures_ref(instrument_id)
        bucket[instrument_id] = ref
        return ref

    async def _cached_contract(self, instrument_id: str):
        ref = await self._cached_gate_futures_ref(instrument_id)
        settle = ref.settle or settings.gateio_default_settle
        key = f"{settle}:{ref.symbol}"
        bucket = self._batch_bucket("contract")
        if key not in bucket:
            snapshot = await self.contract_snapshot_service.get_snapshot(instrument_id, force=True)
            bucket[key] = {
                "mark_price": snapshot.get("mark_price"),
                "index_price": snapshot.get("index_price"),
                "last_price": snapshot.get("last_price"),
                "funding_rate": snapshot.get("funding_rate"),
            }
        return ref, bucket[key]

    async def _cached_candles(self, instrument_id: str, timeframe: str, limit: int = 240):
        key = f"{instrument_id}:{timeframe}:{limit}"
        bucket = self._batch_bucket("candles")
        if key not in bucket:
            bucket[key] = await self.market_service.sync_candles_from_provider(
                instrument_id=instrument_id,
                timeframe=timeframe,
                limit=limit,
                persist=True,
            )
        return bucket[key]

    async def ensure_macro_calendar(self) -> None:
        now = datetime.now(UTC)
        year = now.year
        for month in range(1, 13):
            await self._upsert_macro_calendar_event(
                "bls",
                "us_cpi",
                f"US CPI ({year}-{month:02d})",
                self._mid_month_release(year, month, 15),
            )
            await self._upsert_macro_calendar_event(
                "bls",
                "us_nfp",
                f"US NFP ({year}-{month:02d})",
                self._first_weekday_release(year, month, 4),
            )
            await self._upsert_macro_calendar_event(
                "ism",
                "ism_mfg",
                f"ISM Manufacturing ({year}-{month:02d})",
                self._first_business_day(year, month, 15),
            )
            await self._upsert_macro_calendar_event(
                "ism",
                "ism_srv",
                f"ISM Services ({year}-{month:02d})",
                self._third_business_day(year, month, 15),
            )
        for month in (3, 6, 9, 12):
            await self._upsert_macro_calendar_event(
                "federal_reserve",
                "fomc",
                f"FOMC Decision ({year}-{month:02d})",
                datetime(year, month, 18, 18, 0, tzinfo=UTC),
            )

    async def _upsert_macro_calendar_event(
        self, provider_key: str, event_key: str, title: str, scheduled_at: datetime
    ) -> None:
        actual, consensus, previous = self._macro_stub_values(event_key, scheduled_at)
        status = "released" if scheduled_at <= datetime.now(UTC) else "scheduled"
        surprise = (
            actual - consensus
            if actual is not None and consensus is not None and status == "released"
            else None
        )
        await self.repository.upsert_macro_event(
            MacroEventCalendar(
                event_id=self._stable_id("mec", provider_key, event_key, scheduled_at.isoformat()),
                provider_key=provider_key,
                event_key=event_key,
                country_code="US",
                title=title,
                scheduled_at=scheduled_at,
                actual_value_num=actual if status == "released" else None,
                consensus_value_num=consensus,
                previous_value_num=previous,
                surprise_num=surprise,
                importance="high",
                status=status,
                source_ref=f"{provider_key}:{event_key}",
                payload_json={},
            )
        )

    async def _sync_definition(
        self,
        definition: IndicatorDefinition,
        policy: IndicatorMonitoringPolicy,
        run_id: str,
    ) -> list[IndicatorObservation]:
        if definition.category == "technical":
            return await self._sync_technical_definition(definition, policy, run_id)
        if definition.category == "macro":
            return await self._sync_macro_definition(definition, policy, run_id)
        return await self._sync_onchain_definition(definition, policy, run_id)

    async def _sync_technical_definition(
        self,
        definition: IndicatorDefinition,
        policy: IndicatorMonitoringPolicy,
        run_id: str,
    ) -> list[IndicatorObservation]:
        instrument_id = policy.instrument_id or "btc-usdt-perp"
        timeframe = policy.timeframe or "1h"
        indicator_key = definition.indicator_key

        if indicator_key in {
            "mark_price",
            "index_price",
            "funding_rate",
            "basis_rate",
            "price_to_mark_deviation",
            "price_to_index_deviation",
            "funding_rate_zscore",
            "basis_rate_zscore",
        }:
            ref, contract = await self._cached_contract(instrument_id)
            mark = D(contract.get("mark_price") or contract.get("last_price"))
            index_price = D(contract.get("index_price") or contract.get("last_price") or mark)
            last_price = D(contract.get("last_price") or mark)
            funding_rate = D(contract.get("funding_rate") or "0")
            basis_rate = ((mark - index_price) / index_price) if index_price else DECIMAL_ZERO
            values = {
                "mark_price": mark,
                "index_price": index_price,
                "funding_rate": funding_rate,
                "basis_rate": basis_rate,
                "price_to_mark_deviation": ((last_price - mark) / mark) if mark else DECIMAL_ZERO,
                "price_to_index_deviation": ((last_price - index_price) / index_price)
                if index_price
                else DECIMAL_ZERO,
            }
            if indicator_key in {"funding_rate_zscore", "basis_rate_zscore"}:
                base_key = "funding_rate" if indicator_key.startswith("funding") else "basis_rate"
                history = await self.repository.list_indicator_observations(
                    base_key, instrument_id=instrument_id, limit=60
                )
                series = [D(item.value_num) for item in history if item.value_num is not None] + [
                    values[base_key]
                ]
                value_num = self._zscore(series)
            else:
                value_num = values[indicator_key]
            obs = await self._persist_observation(
                definition=definition,
                run_id=run_id,
                instrument_id=instrument_id,
                timeframe=policy.timeframe or "5s",
                observation_ts=datetime.now(UTC),
                value_num=value_num,
                value_json={
                    "last_price": str(last_price),
                    "mark_price": str(mark),
                    "index_price": str(index_price),
                },
                signal_state=self._technical_state(indicator_key, value_num),
                source_provider="gateio",
                source_ref=f"futures.contract:{ref.symbol}",
                source_granularity=policy.timeframe or "5s",
            )
            return [obs]

        if indicator_key in {
            "cvd_delta",
            "open_interest_notional",
            "depth_liquidity",
            "slippage_bps",
        }:
            return await self._sync_microstructure_definition(
                definition=definition,
                policy=policy,
                run_id=run_id,
                instrument_id=instrument_id,
                timeframe=timeframe,
            )

        candles = await self._cached_candles(instrument_id, timeframe, 240)
        if not candles:
            return []
        closes = [D(item.close) for item in candles]
        highs = [D(item.high) for item in candles]
        lows = [D(item.low) for item in candles]
        volumes = [D(item.volume) for item in candles]
        ts = candles[-1].ts_open
        value_num: Decimal | None = None
        value_json: dict = {}
        if indicator_key == "ema_20":
            result = ema_series(closes, 20)
            value_num = result.value
            value_json = self._indicator_meta(result)
        elif indicator_key == "ema_50":
            result = ema_series(closes, 50)
            value_num = result.value
            value_json = self._indicator_meta(result)
        elif indicator_key == "ema_200":
            result = ema_series(closes, 200)
            value_num = result.value
            value_json = self._indicator_meta(result)
        elif indicator_key == "adx_14":
            result = adx_wilder_series(highs, lows, closes, 14)
            value_num = result["adx"].value
            value_json = {
                **self._indicator_meta(result["adx"]),
                "plus_di": str(result["plus_di"].value),
                "minus_di": str(result["minus_di"].value),
                "dx": str(result["dx"].value),
            }
        elif indicator_key == "macd_12_26_9":
            result = macd_series(closes)
            value_num = result.histogram.value
            value_json = {
                **self._indicator_meta(result.histogram),
                "macd": str(result.macd.value),
                "signal": str(result.signal.value),
                "hist": str(result.histogram.value),
            }
        elif indicator_key == "rsi_14":
            result = rsi_wilder_series(closes, 14)
            value_num = result.value
            value_json = self._indicator_meta(result)
        elif indicator_key == "atr_14":
            result = atr_wilder_series(highs, lows, closes, 14)
            value_num = result.value
            value_json = {**self._indicator_meta(result), "variant": "wilder"}
        elif indicator_key == "natr_14":
            result = atr_wilder_series(highs, lows, closes, 14)
            atr = result.value
            value_num = (atr / closes[-1] * Decimal("100")) if closes[-1] else DECIMAL_ZERO
            value_json = {**self._indicator_meta(result), "variant": "wilder", "atr": str(atr)}
        elif indicator_key == "bbands_20_2":
            result = bbands_series(closes)
            value_num = result.middle.value
            value_json = {
                **self._indicator_meta(result.middle),
                "upper": str(result.upper.value),
                "middle": str(result.middle.value),
                "lower": str(result.lower.value),
                "bandwidth": str(result.bandwidth.value),
                "percent_b": str(result.percent_b.value),
            }
        elif indicator_key == "obv":
            result = obv_series(closes, volumes)
            value_num = result.value
            value_json = self._indicator_meta(result)
        elif indicator_key == "volume_surge_ratio":
            baseline = sma_series(volumes, 20).value
            value_num = (volumes[-1] / baseline) if baseline else DECIMAL_ZERO
        obs = await self._persist_observation(
            definition=definition,
            run_id=run_id,
            instrument_id=instrument_id,
            timeframe=timeframe,
            observation_ts=ts,
            value_num=value_num,
            value_json=value_json,
            signal_state=self._technical_state(indicator_key, value_num, value_json),
            source_provider="gateio",
            source_ref="candles",
            source_granularity=timeframe,
        )
        if indicator_key == "natr_14":
            history = await self.repository.list_indicator_observations(
                "natr_14", instrument_id=instrument_id, timeframe=timeframe, limit=90
            )
            series = [D(item.value_num) for item in history if item.value_num is not None] + (
                [value_num] if value_num is not None else []
            )
            obs.percentile_num = self._percentile_rank(series, value_num or DECIMAL_ZERO)
        return [obs]

    async def _sync_microstructure_definition(
        self,
        *,
        definition: IndicatorDefinition,
        policy: IndicatorMonitoringPolicy,
        run_id: str,
        instrument_id: str,
        timeframe: str,
    ) -> list[IndicatorObservation]:
        ref = await self._cached_gate_futures_ref(instrument_id)
        settle = ref.settle or settings.gateio_default_settle
        contract_bucket = self._batch_bucket("contract")
        contract_key = f"{settle}:{ref.symbol}"
        if contract_key not in contract_bucket:
            contract_bucket[contract_key] = (
                await self.market_service.gate_client.get_futures_contract(
                    settle,
                    ref.symbol,
                )
            )
        contract = contract_bucket[contract_key]
        mark = D(contract.get("mark_price") or contract.get("last_price"))
        multiplier = D(contract.get("quanto_multiplier") or "1")
        ts = datetime.now(UTC)
        key = definition.indicator_key

        if key == "cvd_delta":
            trades_bucket = self._batch_bucket("trades")
            trades_key = f"{settle}:{ref.symbol}:100"
            if trades_key not in trades_bucket:
                trades_bucket[trades_key] = (
                    await self.market_service.gate_client.list_futures_trades(
                        settle=settle,
                        contract=ref.symbol,
                        limit=100,
                    )
                )
            trades = trades_bucket[trades_key]
            previous = await self.repository.latest_observation(
                "cvd_delta",
                instrument_id=instrument_id,
                timeframe=timeframe,
            )
            previous_cvd = (
                D((previous.value_json or {}).get("cvd") or "0")
                if previous
                else DECIMAL_ZERO
            )
            summary = aggregate_cvd_delta(
                [
                    TradeSample(price=item.price, size=item.size, side=item.side)
                    for item in trades
                ],
                previous_cvd=previous_cvd,
            )
            value_json = {
                "buy_volume": str(summary.buy_volume),
                "sell_volume": str(summary.sell_volume),
                "delta": str(summary.delta),
                "cvd": str(summary.cvd),
                "trade_count": summary.trade_count,
                "contract": ref.symbol,
            }
            value_num = summary.delta
            if summary.delta > 0:
                signal_state = "buy_delta"
            elif summary.delta < 0:
                signal_state = "sell_delta"
            else:
                signal_state = "neutral"
            source_ref = f"futures.trades:{ref.symbol}"
        elif key == "open_interest_notional":
            stats_bucket = self._batch_bucket("contract_stats")
            stats_key = f"{settle}:{ref.symbol}:5m:2"
            if stats_key not in stats_bucket:
                stats_bucket[stats_key] = (
                    await self.market_service.gate_client.get_futures_contract_stats(
                        settle=settle,
                        contract=ref.symbol,
                        interval="5m",
                        limit=2,
                    )
                )
            stats = stats_bucket[stats_key]
            latest_oi = stats[-1].open_interest if stats else DECIMAL_ZERO
            previous_oi = stats[-2].open_interest if len(stats) >= 2 else None
            summary = summarize_open_interest(
                latest_oi,
                mark,
                previous_open_interest=previous_oi,
                contract_multiplier=multiplier,
            )
            value_json = {
                "open_interest": str(summary.open_interest),
                "open_interest_notional": str(summary.open_interest_notional),
                "open_interest_change": str(summary.open_interest_change)
                if summary.open_interest_change is not None
                else None,
                "open_interest_change_pct": str(summary.open_interest_change_pct)
                if summary.open_interest_change_pct is not None
                else None,
                "mark_price": str(mark),
                "contract": ref.symbol,
            }
            value_num = summary.open_interest_notional
            signal_state = (
                "rising"
                if (summary.open_interest_change or DECIMAL_ZERO) > 0
                else "falling"
                if (summary.open_interest_change or DECIMAL_ZERO) < 0
                else "neutral"
            )
            source_ref = f"futures.contract_stats:{ref.symbol}"
        else:
            book_bucket = self._batch_bucket("order_book")
            book_key = f"{settle}:{ref.symbol}:50"
            if book_key not in book_bucket:
                book_bucket[book_key] = (
                    await self.market_service.gate_client.get_futures_order_book(
                        settle=settle,
                        contract=ref.symbol,
                        limit=50,
                        with_id=True,
                    )
                )
            book = book_bucket[book_key]
            summary = summarize_depth_slippage(
                book.bids,
                book.asks,
                notional=Decimal("10000"),
            )
            value_json = {
                "spread_bps": str(summary.spread_bps),
                "depth_10bps": str(summary.depth_10bps),
                "depth_50bps": str(summary.depth_50bps),
                "depth_100bps": str(summary.depth_100bps),
                "buy_slippage_bps": str(summary.buy_slippage_bps)
                if summary.buy_slippage_bps is not None
                else None,
                "sell_slippage_bps": str(summary.sell_slippage_bps)
                if summary.sell_slippage_bps is not None
                else None,
                "contract": ref.symbol,
            }
            value_num = (
                summary.depth_50bps
                if key == "depth_liquidity"
                else summary.spread_bps
            )
            signal_state = "thin" if summary.depth_50bps <= Decimal("50000") else "normal"
            if key == "slippage_bps" and (
                (summary.buy_slippage_bps or DECIMAL_ZERO) >= Decimal("20")
                or (summary.sell_slippage_bps or DECIMAL_ZERO) >= Decimal("20")
            ):
                signal_state = "wide"
            source_ref = f"futures.order_book:{ref.symbol}"

        obs = await self._persist_observation(
            definition=definition,
            run_id=run_id,
            instrument_id=instrument_id,
            timeframe=timeframe,
            observation_ts=ts,
            value_num=value_num,
            value_json=value_json,
            signal_state=signal_state,
            source_provider="gateio",
            source_ref=source_ref,
            source_granularity=policy.timeframe or "1m",
        )
        return [obs]

    async def _gate_futures_ref(self, instrument_id: str):
        instrument = await self.repository.get_instrument(instrument_id)
        if instrument is None:
            raise ValueError(f"instrument not found: {instrument_id}")
        ref = MarketService.resolve_gate_reference(instrument)
        if ref.product_type != "futures":
            raise ValueError(f"instrument is not a Gate.io futures contract: {instrument_id}")
        return ref

    async def _sync_macro_definition(
        self,
        definition: IndicatorDefinition,
        policy: IndicatorMonitoringPolicy,
        run_id: str,
    ) -> list[IndicatorObservation]:
        indicator_key = definition.indicator_key
        provider = self.macro_provider_registry.resolve(
            source_provider=definition.source_provider,
            source_kind=definition.source_kind,
        )
        if provider is not None and definition.source_kind == "raw_series":
            symbol = str(definition.calc_params_json.get("external_symbol"))
            fetch_started_at = time_module.perf_counter()
            try:
                result = await provider.fetch_latest(symbol)
                await self._record_macro_source_health(
                    provider_key=provider.provider_key,
                    source_key=symbol,
                    status="live",
                    message=None,
                    latency_ms=int((time_module.perf_counter() - fetch_started_at) * 1000),
                    payload_json={"indicator_key": indicator_key},
                )
            except Exception as exc:
                await self._record_macro_source_health(
                    provider_key=provider.provider_key,
                    source_key=symbol,
                    status="stale",
                    message=str(exc),
                    latency_ms=int((time_module.perf_counter() - fetch_started_at) * 1000),
                    payload_json={"indicator_key": indicator_key},
                )
                raise
            country_code = "global" if indicator_key in {"dollar_index", "gold"} else "US"
            obs = await self._persist_observation(
                definition=definition,
                run_id=run_id,
                country_code=country_code,
                timeframe="1d",
                observation_ts=result.observation_ts,
                value_num=result.value,
                value_json=result.metadata or {},
                signal_state=self._macro_state(indicator_key, result.value),
                source_provider=provider.provider_key,
                source_ref=result.source_ref,
                source_granularity=result.source_granularity,
            )
            return [obs]
        if indicator_key == "us_10y_2y_spread":
            ten = await self.repository.latest_observation("us_10y_yield")
            two = await self.repository.latest_observation("us_2y_yield")
            if ten is None or two is None or ten.value_num is None or two.value_num is None:
                return []
            value = D(ten.value_num) - D(two.value_num)
            obs = await self._persist_observation(
                definition=definition,
                run_id=run_id,
                country_code="US",
                timeframe="1d",
                observation_ts=max(ten.observation_ts, two.observation_ts),
                value_num=value,
                value_json={"ten": str(ten.value_num), "two": str(two.value_num)},
                signal_state=self._macro_state(indicator_key, value),
                source_provider="derived",
                source_ref="us_10y_yield/us_2y_yield",
                source_granularity="1d",
            )
            return [obs]
        await self.ensure_macro_calendar()
        if indicator_key == "fomc_event_window":
            events = await self.repository.list_macro_events(event_key="fomc", limit=8)
            now = datetime.now(UTC)
            current_state = "inactive"
            event_ts = now
            for event in events:
                scheduled_at = (
                    event.scheduled_at
                    if event.scheduled_at.tzinfo
                    else event.scheduled_at.replace(tzinfo=UTC)
                )
                delta = (scheduled_at - now).total_seconds()
                if 0 <= delta <= 24 * 3600:
                    current_state = "pre_event"
                    event_ts = scheduled_at
                    break
                if -6 * 3600 <= delta < 0:
                    current_state = "post_event"
                    event_ts = scheduled_at
                    break
            obs = await self._persist_observation(
                definition=definition,
                run_id=run_id,
                country_code="US",
                timeframe="event",
                observation_ts=event_ts,
                value_text=current_state,
                value_json={"state": current_state},
                signal_state=current_state,
                source_provider="federal_reserve",
                source_ref="fomc_calendar",
                source_granularity="event",
            )
            return [obs]

        release_key = policy.release_key or indicator_key
        latest = await self.repository.latest_macro_event(release_key, released_only=True)
        if latest is None:
            return []
        if provider is not None:
            await self._record_macro_source_health(
                provider_key=provider.provider_key,
                source_key=release_key,
                status="live",
                message=None,
                payload_json={"event_id": latest.event_id},
            )
        obs = await self._persist_observation(
            definition=definition,
            run_id=run_id,
            country_code="US",
            timeframe="event",
            observation_ts=latest.scheduled_at,
            value_num=latest.actual_value_num,
            delta_num=latest.surprise_num,
            value_json={
                "actual": str(latest.actual_value_num)
                if latest.actual_value_num is not None
                else None,
                "consensus": str(latest.consensus_value_num)
                if latest.consensus_value_num is not None
                else None,
                "previous": str(latest.previous_value_num)
                if latest.previous_value_num is not None
                else None,
                "surprise": str(latest.surprise_num) if latest.surprise_num is not None else None,
            },
            signal_state=self._macro_state(indicator_key, latest.actual_value_num),
            source_provider=latest.provider_key,
            source_ref=latest.event_key,
            source_granularity="event",
        )
        return [obs]

    async def _record_macro_source_health(
        self,
        *,
        provider_key: str,
        source_key: str,
        status: str,
        message: str | None,
        latency_ms: int | None = None,
        payload_json: dict | None = None,
    ) -> None:
        now = datetime.now(UTC)
        await self.repository.upsert_macro_source_health(
            MacroSourceHealth(
                provider_key=provider_key,
                source_key=source_key,
                status=status,
                message=message,
                last_success_at=now if status in {"live", "healthy"} else None,
                last_failure_at=now
                if status in {"stale", "error", "pending"} and message
                else None,
                latency_ms=latency_ms,
                payload_json=payload_json or {},
            )
        )

    async def _refresh_macro_source_health(self) -> None:
        for provider in self.macro_provider_registry.providers():
            status, message = await provider.healthcheck()
            await self._record_macro_source_health(
                provider_key=provider.provider_key,
                source_key="provider",
                status=status,
                message=message,
            )

    async def _sync_onchain_definition(
        self,
        definition: IndicatorDefinition,
        policy: IndicatorMonitoringPolicy,
        run_id: str,
    ) -> list[IndicatorObservation]:
        asset_code = policy.asset_code or str(
            definition.calc_params_json.get("asset_scope") or "BTC"
        )
        timeframe = policy.timeframe or "24h"
        now = datetime.now(UTC)
        value = self._demo_onchain_value(definition.indicator_key, asset_code, now)
        history = await self.repository.list_indicator_observations(
            definition.indicator_key, asset_code=asset_code, limit=60
        )
        series = [D(item.value_num) for item in reversed(history) if item.value_num is not None] + [
            value
        ]
        obs = await self._persist_observation(
            definition=definition,
            run_id=run_id,
            asset_code=asset_code,
            timeframe=timeframe,
            observation_ts=now,
            value_num=value,
            zscore_num=self._zscore(series) if len(series) > 1 else DECIMAL_ZERO,
            value_json={
                "mode": "demo_fallback" if not settings.glassnode_api_key else "placeholder"
            },
            signal_state=self._onchain_state(definition.indicator_key, value),
            source_provider="glassnode",
            source_ref="demo-fallback",
            source_granularity=timeframe,
            is_preliminary=not bool(settings.glassnode_api_key),
            quality_score=Decimal(
                settings.monitoring_demo_quality_score
                if not settings.glassnode_api_key
                else settings.monitoring_default_quality_score
            ),
        )
        return [obs]

    async def _persist_observation(
        self,
        *,
        definition: IndicatorDefinition,
        run_id: str,
        observation_ts: datetime,
        value_num: Decimal | None = None,
        value_text: str | None = None,
        value_json: dict | None = None,
        baseline_num: Decimal | None = None,
        delta_num: Decimal | None = None,
        zscore_num: Decimal | None = None,
        percentile_num: Decimal | None = None,
        signal_state: str | None = None,
        signal_score: Decimal | None = None,
        source_provider: str,
        source_ref: str,
        source_granularity: str,
        instrument_id: str | None = None,
        asset_code: str | None = None,
        country_code: str | None = None,
        timeframe: str | None = None,
        is_preliminary: bool = False,
        quality_score: Decimal | None = None,
    ) -> IndicatorObservation:
        observation = IndicatorObservation(
            observation_id=new_id("obs"),
            dedupe_key="|".join(
                [
                    definition.indicator_key,
                    instrument_id or "",
                    asset_code or "",
                    country_code or "",
                    timeframe or "",
                    observation_ts.isoformat(),
                ]
            ),
            indicator_key=definition.indicator_key,
            category=definition.category,
            instrument_id=instrument_id,
            asset_code=asset_code,
            country_code=country_code,
            timeframe=timeframe,
            observation_ts=observation_ts,
            effective_start_ts=observation_ts,
            effective_end_ts=None,
            value_num=value_num,
            value_text=value_text,
            value_json=value_json or {},
            baseline_num=baseline_num,
            delta_num=delta_num,
            zscore_num=zscore_num,
            percentile_num=percentile_num,
            signal_state=signal_state,
            signal_score=signal_score,
            source_provider=source_provider,
            source_ref=source_ref,
            source_granularity=source_granularity,
            is_preliminary=is_preliminary,
            quality_score=quality_score or Decimal(settings.monitoring_default_quality_score),
            run_id=run_id,
        )
        return await self.repository.add_or_update_observation(observation)

    async def _evaluate_alerts(self, observations: list[IndicatorObservation]) -> None:
        for observation in observations:
            payload = observation.value_json or {}
            if payload.get("is_immature") or payload.get("lookback_ready") is False:
                continue
            rules = await self.repository.list_alert_rules(
                enabled_only=True, indicator_key=observation.indicator_key
            )
            for rule in rules:
                if not self._rule_matches(rule, observation):
                    continue
                await self.repository.add_alert_event(
                    IndicatorAlertEvent(
                        alert_event_id=new_id("alr"),
                        rule_key=rule.rule_key,
                        indicator_key=rule.indicator_key,
                        observation_id=observation.observation_id,
                        severity=rule.severity,
                        status="open",
                        instrument_id=observation.instrument_id,
                        asset_code=observation.asset_code,
                        timeframe=observation.timeframe,
                        triggered_at=datetime.now(UTC),
                        resolved_at=None,
                        dedupe_key="|".join(
                            [
                                rule.rule_key,
                                observation.instrument_id or observation.asset_code or "global",
                                observation.timeframe or "",
                                observation.observation_ts.isoformat(),
                            ]
                        ),
                        title=rule.rule_key,
                        message=rule.message_template.format(
                            instrument_id=observation.instrument_id or "",
                            asset_code=observation.asset_code or "",
                        ),
                        event_payload_json={
                            "indicator_key": observation.indicator_key,
                            "value_num": str(observation.value_num)
                            if observation.value_num is not None
                            else None,
                            "signal_state": observation.signal_state,
                        },
                    )
                )

    def _rule_matches(self, rule: IndicatorAlertRule, observation: IndicatorObservation) -> bool:
        field = str(rule.extra_config_json.get("value_field") or "value_num")
        value = getattr(observation, field, None)
        if rule.condition_type == "state_equals":
            return observation.signal_state == rule.state_value
        if (
            rule.condition_type == "abs_threshold"
            and value is not None
            and rule.threshold_num is not None
        ):
            return abs(D(value)) >= D(rule.threshold_num)
        if (
            rule.condition_type == "threshold"
            and value is not None
            and rule.threshold_num is not None
        ):
            return self._compare(D(value), str(rule.comparator or "gte"), D(rule.threshold_num))
        if (
            rule.condition_type == "percentile_band"
            and observation.percentile_num is not None
            and rule.upper_threshold_num is not None
        ):
            return D(observation.percentile_num) >= D(rule.upper_threshold_num)
        if (
            rule.condition_type == "consecutive_threshold"
            and observation.value_num is not None
            and rule.threshold_num is not None
        ):
            return self._compare(
                D(observation.value_num), str(rule.comparator or "lt"), D(rule.threshold_num)
            )
        return False

    async def _fred_latest(self, symbol: str) -> tuple[datetime, Decimal]:
        async with httpx.AsyncClient(timeout=10) as client:
            response = await client.get(settings.fred_public_csv_url, params={"id": symbol})
            response.raise_for_status()
        rows = list(csv.DictReader(StringIO(response.text)))
        if not rows:
            raise ValueError(f"no fred rows for {symbol}")
        date_field = next(
            (
                key
                for key in rows[0].keys()
                if str(key).strip().lower() in {"date", "observation_date"}
            ),
            None,
        )
        if date_field is None:
            raise ValueError(f"no date column for {symbol}")
        value_field = (
            symbol
            if symbol in rows[0]
            else next(
                (
                    key
                    for key in rows[0].keys()
                    if str(key).strip().lower() == str(symbol).strip().lower()
                ),
                None,
            )
        )
        if value_field is None:
            raise ValueError(f"no value column for {symbol}")
        for row in reversed(rows):
            value = row.get(value_field)
            if not value or value == ".":
                continue
            date_value = row.get(date_field)
            if not date_value:
                continue
            return datetime.fromisoformat(f"{date_value}T00:00:00+00:00"), D(value)
        raise ValueError(f"no fred observation for {symbol}")

    @staticmethod
    def _macro_stub_values(
        event_key: str, scheduled_at: datetime
    ) -> tuple[Decimal | None, Decimal | None, Decimal | None]:
        month_seed = Decimal((scheduled_at.month % 5) + 1) / Decimal("10")
        if event_key == "us_cpi":
            return (
                Decimal("2.7") + month_seed,
                Decimal("2.6") + month_seed,
                Decimal("2.5") + month_seed,
            )
        if event_key == "us_nfp":
            return Decimal("185"), Decimal("170"), Decimal("160")
        if event_key == "ism_mfg":
            return Decimal("50.8"), Decimal("50.2"), Decimal("49.9")
        if event_key == "ism_srv":
            return Decimal("52.3"), Decimal("51.7"), Decimal("51.1")
        return None, None, None

    @staticmethod
    def _demo_onchain_value(indicator_key: str, asset_code: str, now: datetime) -> Decimal:
        seed = int(
            hashlib.md5(
                f"{indicator_key}:{asset_code}:{now.date().isoformat()}".encode("utf-8")
            ).hexdigest()[:8],
            16,
        )
        base = Decimal(seed % 1000) / Decimal("100")
        ranges = {
            "btc_mvrv": Decimal("0.8") + (base / Decimal("4")),
            "eth_mvrv": Decimal("0.9") + (base / Decimal("5")),
            "btc_sth_mvrv": Decimal("0.7") + (base / Decimal("6")),
            "btc_lth_mvrv": Decimal("1.1") + (base / Decimal("7")),
            "btc_exchange_net_position_change": Decimal("-5000") + Decimal(seed % 10000),
            "eth_exchange_net_position_change": Decimal("-3000") + Decimal(seed % 6000),
            "btc_active_addresses": Decimal("900000") + Decimal(seed % 150000),
            "eth_active_addresses": Decimal("500000") + Decimal(seed % 100000),
        }
        return ranges.get(indicator_key, base)

    @staticmethod
    def _technical_state(
        indicator_key: str, value: Decimal | None, payload: dict | None = None
    ) -> str:
        payload = payload or {}
        if payload.get("is_immature") or payload.get("lookback_ready") is False:
            return "immature"
        if value is None:
            return "neutral"
        if indicator_key.startswith("ema_"):
            return "bullish"
        if indicator_key == "rsi_14":
            if value <= Decimal("30"):
                return "oversold"
            if value >= Decimal("70"):
                return "overbought"
            return "neutral"
        if indicator_key == "adx_14":
            if value >= Decimal("25"):
                return "strong_trend"
            if value < Decimal("20"):
                return "weak_trend"
            return "developing_trend"
        if indicator_key == "natr_14":
            if value >= Decimal("3"):
                return "expanded"
            if value <= Decimal("1"):
                return "compressed"
            return "normal"
        if indicator_key == "volume_surge_ratio":
            if value >= Decimal("2"):
                return "extreme"
            if value >= Decimal("1.3"):
                return "elevated"
            return "normal"
        if indicator_key == "macd_12_26_9":
            hist = D((payload or {}).get("hist", value))
            return "positive_hist" if hist >= DECIMAL_ZERO else "negative_hist"
        return "normal"

    @staticmethod
    def _macro_state(indicator_key: str, value: Decimal | None) -> str:
        if value is None:
            return "neutral"
        if indicator_key == "us_10y_2y_spread" and value is not None:
            if value <= Decimal("-0.5"):
                return "deep_inversion"
            if value < DECIMAL_ZERO:
                return "inversion"
            return "steepening"
        if indicator_key in {"us_dff", "us_2y_yield", "us_10y_yield", "ust_10y_yield"}:
            if value >= Decimal("4.5"):
                return "rising"
            if value <= Decimal("3.5"):
                return "falling"
            return "neutral"
        if indicator_key in {"us_cpi_yoy", "us_core_cpi_yoy"} and value is not None:
            return "heating" if value >= Decimal("3") else "cooling"
        if indicator_key in {"ism_mfg_pmi", "ism_srv_pmi"} and value is not None:
            return "expansion" if value >= Decimal("50") else "contraction"
        if indicator_key == "hy_oas":
            if value >= Decimal("5"):
                return "wide"
            if value <= Decimal("3.5"):
                return "tight"
            return "neutral"
        if indicator_key in {"financial_conditions", "tga"}:
            if value >= Decimal("1"):
                return "tight"
            if value <= DECIMAL_ZERO:
                return "loose"
            return "neutral"
        if indicator_key == "on_rrp":
            if value >= Decimal("500"):
                return "rising"
            if value <= Decimal("100"):
                return "falling"
            return "neutral"
        if indicator_key == "dollar_index":
            if value >= Decimal("120"):
                return "strengthening"
            if value <= Decimal("110"):
                return "weakening"
            return "neutral"
        if indicator_key == "gold":
            if value >= Decimal("2300"):
                return "strong"
            if value <= Decimal("1800"):
                return "soft"
            return "neutral"
        if indicator_key == "vix":
            if value >= Decimal("22"):
                return "stressed"
            if value <= Decimal("16"):
                return "calm"
            return "neutral"
        return "neutral"

    @staticmethod
    def _onchain_state(indicator_key: str, value: Decimal) -> str:
        if indicator_key.endswith("mvrv"):
            if value < Decimal("1"):
                return "undervalued"
            if value >= Decimal("3.5"):
                return "overheated"
            return "neutral"
        if "exchange_net_position_change" in indicator_key:
            return "outflow_dominant" if value < DECIMAL_ZERO else "inflow_dominant"
        if "active_addresses" in indicator_key:
            return "expanding" if value >= Decimal("1000000") else "normal"
        return "neutral"

    @staticmethod
    def _next_run(policy: IndicatorMonitoringPolicy, now: datetime) -> datetime:
        interval = (
            policy.interval_seconds
            or policy.fallback_interval_seconds
            or settings.monitoring_scheduler_poll_seconds
        )
        return now + timedelta(seconds=interval)

    @staticmethod
    def _compare(left: Decimal, comparator: str, right: Decimal) -> bool:
        if comparator == "gte":
            return left >= right
        if comparator == "gt":
            return left > right
        if comparator == "lt":
            return left < right
        if comparator == "lte":
            return left <= right
        if comparator == "eq":
            return left == right
        return False

    @staticmethod
    def _sma(values: list[Decimal], window: int) -> Decimal:
        return sma_series(values, window).value

    @staticmethod
    def _ema(values: list[Decimal], window: int) -> Decimal:
        return ema_series(values, window).value

    @staticmethod
    def _rsi(values: list[Decimal], window: int) -> Decimal:
        return rsi_wilder_series(values, window).value

    @staticmethod
    def _tr(high: Decimal, low: Decimal, prev_close: Decimal) -> Decimal:
        return max(high - low, abs(high - prev_close), abs(low - prev_close))

    def _atr(
        self, highs: list[Decimal], lows: list[Decimal], closes: list[Decimal], window: int
    ) -> Decimal:
        return atr_wilder_series(highs, lows, closes, window).value

    def _atr_ema(
        self, highs: list[Decimal], lows: list[Decimal], closes: list[Decimal], window: int
    ) -> Decimal:
        return atr_ema_series(highs, lows, closes, window).value

    @staticmethod
    def _obv(closes: list[Decimal], volumes: list[Decimal]) -> Decimal:
        if not closes:
            return DECIMAL_ZERO
        obv = DECIMAL_ZERO
        for idx in range(1, len(closes)):
            if closes[idx] > closes[idx - 1]:
                obv += volumes[idx]
            elif closes[idx] < closes[idx - 1]:
                obv -= volumes[idx]
        return obv

    def _macd(self, closes: list[Decimal]) -> tuple[Decimal, Decimal, Decimal]:
        result = macd_series(closes)
        return result.macd.value, result.signal.value, result.histogram.value

    def _bbands(self, closes: list[Decimal]) -> tuple[Decimal, Decimal, Decimal, Decimal, Decimal]:
        result = bbands_series(closes)
        return (
            result.upper.value,
            result.middle.value,
            result.lower.value,
            result.bandwidth.value,
            result.percent_b.value,
        )

    def _adx(
        self, highs: list[Decimal], lows: list[Decimal], closes: list[Decimal], window: int
    ) -> Decimal:
        return adx_wilder_series(highs, lows, closes, window)["adx"].value

    @staticmethod
    def _indicator_meta(result) -> dict:
        return {
            "warmup": result.warmup,
            "lookback_ready": result.lookback_ready,
            "is_immature": result.is_immature,
        }

    @staticmethod
    def _zscore(values: list[Decimal]) -> Decimal:
        if len(values) < 2:
            return DECIMAL_ZERO
        mean = sum(values, DECIMAL_ZERO) / Decimal(len(values))
        variance = sum(((item - mean) ** 2 for item in values), DECIMAL_ZERO) / Decimal(len(values))
        std = variance.sqrt()
        if std == 0:
            return DECIMAL_ZERO
        return (values[-1] - mean) / std

    @staticmethod
    def _percentile_rank(values: list[Decimal], target: Decimal) -> Decimal:
        if not values:
            return DECIMAL_ZERO
        lower = sum(1 for value in values if value <= target)
        return Decimal(lower) / Decimal(len(values)) * Decimal("100")

    @staticmethod
    def _mid_month_release(year: int, month: int, day: int) -> datetime:
        return datetime.combine(
            date(year, month, min(day, monthrange(year, month)[1])), time(13, 30), tzinfo=UTC
        )

    @staticmethod
    def _first_business_day(year: int, month: int, hour: int) -> datetime:
        current = date(year, month, 1)
        while current.weekday() >= 5:
            current += timedelta(days=1)
        return datetime.combine(current, time(hour, 0), tzinfo=UTC)

    @staticmethod
    def _third_business_day(year: int, month: int, hour: int) -> datetime:
        current = date(year, month, 1)
        count = 0
        while True:
            if current.weekday() < 5:
                count += 1
                if count == 3:
                    return datetime.combine(current, time(hour, 0), tzinfo=UTC)
            current += timedelta(days=1)

    @staticmethod
    def _first_weekday_release(year: int, month: int, weekday: int) -> datetime:
        current = date(year, month, 1)
        while current.weekday() != weekday:
            current += timedelta(days=1)
        return datetime.combine(current, time(13, 30), tzinfo=UTC)

    @staticmethod
    def _stable_id(prefix: str, *parts: str) -> str:
        digest = hashlib.md5("|".join(parts).encode("utf-8")).hexdigest()[:16]
        return f"{prefix}_{digest}"
