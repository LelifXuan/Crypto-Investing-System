from __future__ import annotations

from dataclasses import dataclass
from datetime import UTC, datetime, timedelta
from decimal import Decimal
from typing import Any

import httpx

from app.db.models.market import IndicatorDefinition, IndicatorObservation
from app.repositories.market_repository import MarketRepository
from app.services.onchain.providers.defillama import DefiLlamaProvider

# DefiLlama snapshot TTL for the AI strategy layer (24h, aligned with ONCHAIN_TTL).
DEFI_LLAMA_STRATEGY_TTL = timedelta(hours=24)

# Canonical indicator keys exposed to the strategy layer.
CORE_KEYS: tuple[str, ...] = (
    "defi_total_tvl",
    "stablecoin_total_mcap",
    "dex_volume_24h",
    "protocol_fees_24h",
)

# Human-readable Chinese labels for the 4 keys (used by evidence rendering).
KEY_LABELS_ZH: dict[str, str] = {
    "defi_total_tvl": "DeFi 锁仓总量",
    "stablecoin_total_mcap": "稳定币总市值",
    "dex_volume_24h": "DEX 24h 交易量",
    "protocol_fees_24h": "协议 24h 手续费",
}


@dataclass(frozen=True)
class DefiLlamaObservationDraft:
    indicator_key: str
    value_num: Decimal | None
    value_json: dict[str, Any]
    source_provider: str
    source_ref: str
    source_granularity: str
    quality_score: Decimal
    observation_ts: datetime
    signal_state: str


@dataclass(frozen=True)
class DefiLlamaCollectOutcome:
    drafts: list[DefiLlamaObservationDraft]
    meta: dict[str, Any]


class DefiLlamaPolicyAdapter:
    """Convert DefiLlama public snapshots into ``IndicatorObservation`` rows.

    The adapter never writes to the cache layer directly; it returns drafts and
    the calling service decides whether to persist.
    """

    def __init__(
        self,
        *,
        provider: DefiLlamaProvider | None = None,
        ttl: timedelta = DEFI_LLAMA_STRATEGY_TTL,
    ) -> None:
        self.provider = provider or DefiLlamaProvider()
        self.ttl = ttl

    async def collect(
        self,
        *,
        now: datetime | None = None,
        client: httpx.AsyncClient | None = None,
    ) -> DefiLlamaCollectOutcome:
        now = now or datetime.now(UTC)
        snapshot = await self.provider.fetch_snapshot(client=client)
        drafts = [self._draft(key, snapshot, now) for key in CORE_KEYS]
        status = self._derive_status(snapshot, drafts)
        meta = {
            "status": status,
            "source_provider": snapshot.source_provider,
            "missing_keys": list(snapshot.missing_fields),
            "missing_inputs": list(snapshot.missing_fields),
            "warnings": [] if status == "live" else list(snapshot.missing_fields),
            "fetched_at": now.isoformat(),
        }
        return DefiLlamaCollectOutcome(drafts=drafts, meta=meta)

    @staticmethod
    def _draft(key: str, snapshot: Any, now: datetime) -> DefiLlamaObservationDraft:
        value = snapshot.indicators.get(key)
        missing = key in snapshot.missing_fields
        if missing or value is None:
            return DefiLlamaObservationDraft(
                indicator_key=key,
                value_num=None,
                value_json={
                    "source": "defillama",
                    "status": "degraded",
                    "missing": True,
                    "reason": "upstream_missing",
                    "missing_fields": list(snapshot.missing_fields),
                },
                source_provider="defillama",
                source_ref=f"defillama:{key}",
                source_granularity="daily",
                quality_score=Decimal("0"),
                observation_ts=now,
                signal_state="missing",
            )
        return DefiLlamaObservationDraft(
            indicator_key=key,
            value_num=Decimal(str(value)),
            value_json={
                "source": "defillama",
                "status": "live",
                "value": float(value),
            },
            source_provider="defillama",
            source_ref=f"defillama:{key}",
            source_granularity="daily",
            quality_score=Decimal("85"),
            observation_ts=now,
            signal_state="fresh",
        )

    @staticmethod
    def _derive_status(snapshot: Any, drafts: list[DefiLlamaObservationDraft]) -> str:
        if snapshot.status == "live":
            return "live"
        if not drafts:
            return "blocked"
        return "degraded"


async def ensure_defillama_definitions(repository: MarketRepository) -> int:
    """Idempotently register the 4 DefiLlama indicator definitions.

    The ``IndicatorObservation.indicator_key`` column has a foreign key to
    ``indicator_definitions.indicator_key``; this helper guarantees the rows
    exist before any observation is written.
    """
    written = 0
    for key in CORE_KEYS:
        definition = IndicatorDefinition(
            indicator_key=key,
            display_name=KEY_LABELS_ZH[key],
            category="onchain",
            family="defi_fundamentals",
            source_provider="defillama",
            source_kind="external_public",
            calc_engine="defillama_provider",
            calc_params_json={"endpoint": "defillama", "core_key": key},
            supported_assets_json=[],
            supported_timeframes_json=["1d"],
            output_fields_json=["value"],
            signal_states_json=["fresh", "missing"],
            default_thresholds_json={},
            use_cases_json=["strategy_onchain_fundamentals"],
            is_enabled=True,
        )
        await repository.upsert_indicator_definition(definition)
        written += 1
    return written


async def persist_drafts(
    repository: MarketRepository,
    drafts: list[DefiLlamaObservationDraft],
) -> int:
    """Persist drafts to ``IndicatorObservation`` and return the row count.

    ``observation_id`` and ``dedupe_key`` follow the same pattern used by
    ``IndicatorMonitoringService.record_observation``.
    """
    import uuid

    written = 0
    for draft in drafts:
        observation_id = f"defillama-{draft.indicator_key}-{uuid.uuid4().hex[:12]}"
        dedupe_key = "|".join(
            [
                draft.indicator_key,
                "",  # instrument_id
                "",  # asset_code
                "",  # country_code
                "",  # timeframe
                draft.observation_ts.isoformat(),
            ]
        )
        observation = IndicatorObservation(
            observation_id=observation_id,
            dedupe_key=dedupe_key,
            indicator_key=draft.indicator_key,
            category="onchain",
            observation_ts=draft.observation_ts,
            effective_start_ts=draft.observation_ts,
            effective_end_ts=None,
            value_num=draft.value_num,
            value_text=None,
            value_json=draft.value_json,
            baseline_num=None,
            delta_num=None,
            zscore_num=None,
            percentile_num=None,
            signal_state=draft.signal_state,
            signal_score=None,
            source_provider=draft.source_provider,
            source_ref=draft.source_ref,
            source_granularity=draft.source_granularity,
            is_preliminary=False,
            quality_score=draft.quality_score,
            run_id=None,
        )
        await repository.add_or_update_observation(observation)
        written += 1
    return written


async def collect_via_router(router: Any) -> DefiLlamaCollectOutcome:
    """Collect one DefiLlama snapshot per ``CORE_KEY`` through ``OnchainProviderRouter``.

    Each call uses the router so existing tests can ``monkeypatch``
    ``OnchainProviderRouter.fetch_metric`` without touching the network. The
    router already covers DefiLlama; other providers are stubbed out.
    """
    from datetime import datetime as _dt
    from datetime import timezone as _tz

    now = _dt.now(_tz.utc)
    drafts: list[DefiLlamaObservationDraft] = []
    missing_keys: list[str] = []
    statuses: list[str] = []
    for key in CORE_KEYS:
        payload = await router.fetch_metric(key)
        status = str(payload.get("status") or "degraded")
        value = payload.get("value")
        per_missing = list(payload.get("missing_fields") or [])
        statuses.append(status)
        if value is None or status in {"degraded", "missing", "blocked"}:
            missing_keys.append(key)
            for missing_key in per_missing:
                if missing_key not in missing_keys:
                    missing_keys.append(missing_key)
            drafts.append(
                DefiLlamaObservationDraft(
                    indicator_key=key,
                    value_num=None,
                    value_json={
                        "source": "defillama",
                        "status": status,
                        "missing": True,
                        "missing_fields": per_missing,
                    },
                    source_provider="defillama",
                    source_ref=f"defillama:{key}",
                    source_granularity="daily",
                    quality_score=Decimal("0"),
                    observation_ts=now,
                    signal_state="missing",
                )
            )
            continue
        drafts.append(
            DefiLlamaObservationDraft(
                indicator_key=key,
                value_num=Decimal(str(value)),
                value_json={
                    "source": "defillama",
                    "status": status,
                    "value": float(value),
                },
                source_provider="defillama",
                source_ref=f"defillama:{key}",
                source_granularity="daily",
                quality_score=Decimal("85"),
                observation_ts=now,
                signal_state="fresh",
            )
        )
    overall = (
        "live" if all(s == "live" for s in statuses) else "degraded" if statuses else "blocked"
    )
    meta = {
        "status": overall,
        "source_provider": "defillama",
        "missing_keys": missing_keys,
        "missing_inputs": missing_keys,
        "warnings": [] if overall == "live" else missing_keys,
        "fetched_at": now.isoformat(),
    }
    return DefiLlamaCollectOutcome(drafts=drafts, meta=meta)


__all__ = [
    "CORE_KEYS",
    "DEFI_LLAMA_STRATEGY_TTL",
    "DefiLlamaCollectOutcome",
    "DefiLlamaObservationDraft",
    "DefiLlamaPolicyAdapter",
    "KEY_LABELS_ZH",
    "collect_via_router",
    "ensure_defillama_definitions",
    "persist_drafts",
]