from __future__ import annotations

from typing import Literal

from fastapi import APIRouter, Depends, HTTPException, Query

from app.api.dependencies import CurrentUser, require_roles
from app.core.config import settings
from app.schemas.ashare_etf_rebalance import (
    AShareEtfRebalancePlanRequest,
    AShareEtfRebalancePlanResponse,
)
from app.schemas.etf import (
    AShareEtfCatalogResponse,
    AShareEtfQuoteResponse,
    AShareEtfSourceHealthResponse,
)
from app.services.ashare_etf_quotes import AShareETFQuoteService, EastmoneyDirectETFClient
from app.services.ashare_etf_rebalance import (
    CASHFLOW_SYMBOL,
    ETFPosition,
    PlanMode,
    RebalanceConfig,
    normalize_etf_symbol,
    optimize_etf_rebalance,
    validate_halo_positions,
)

router = APIRouter(prefix="/ashare-etf", tags=["ashare-etf"])
etf_router = APIRouter(prefix="/etf", tags=["etf"])


def _build_service() -> AShareETFQuoteService:
    return AShareETFQuoteService(
        providers=[
            EastmoneyDirectETFClient(
                base_url=settings.ashare_etf_eastmoney_base_url,
                timeout_seconds=settings.ashare_etf_timeout_seconds,
            )
        ],
        ttl_seconds=settings.ashare_etf_quote_ttl_seconds,
        stale_cache_seconds=settings.ashare_etf_stale_cache_seconds,
    )


quote_service = _build_service()


async def _catalog() -> AShareEtfCatalogResponse:
    return AShareEtfCatalogResponse.model_validate(quote_service.catalog())


async def _quotes(group: str, force: bool) -> AShareEtfQuoteResponse:
    return AShareEtfQuoteResponse.model_validate(
        await quote_service.get_quotes(group=group, force=force)
    )


async def _health() -> AShareEtfSourceHealthResponse:
    return AShareEtfSourceHealthResponse.model_validate(quote_service.sources_health())


async def _quote_price_by_symbol() -> dict[str, float]:
    payload = await quote_service.get_quotes(group="all", force=False)
    prices: dict[str, float] = {}
    for group in payload.get("groups", []):
        for item in group.get("items", []):
            code = str(item.get("code") or "")
            try:
                symbol = normalize_etf_symbol(code)
            except ValueError:
                continue
            price = item.get("last_price") or item.get("prev_close")
            if price is not None:
                prices[symbol] = float(price)
    return prices


def _resolve_halo_inputs(
    payload: AShareEtfRebalancePlanRequest,
) -> tuple[list, list, list, float]:
    """Pick the HALO position list and cash input from a request payload.

    Supports both the new ``halo_*`` fields and the legacy ``cash_to_invest``
    + ``positions`` fields.  When 159201.SZ is present in the legacy list it is
    silently dropped and a warning is appended so the front end can surface it.

    Returns ``(halo_position_dicts, source_symbols, warnings, halo_cash)``.
    """
    warnings: list[dict[str, str]] = []
    source_symbols: list[str] = []
    if payload.halo_positions is not None:
        halo_payload_positions = list(payload.halo_positions)
        halo_cash = (
            payload.halo_cash_to_invest
            if payload.halo_cash_to_invest is not None
            else payload.cash_to_invest
        )
    else:
        legacy_positions = list(payload.positions)
        cashflow_present = False
        for item in legacy_positions:
            try:
                symbol = normalize_etf_symbol(item.symbol or item.code)
            except ValueError:
                continue
            if symbol == CASHFLOW_SYMBOL:
                cashflow_present = True
                continue
            source_symbols.append(symbol)
        if cashflow_present:
            warnings.append(
                {
                    "code": "cashflow_excluded_from_halo_rotation",
                    "message": (
                        "现金流ETF仅用于月度定投展示，不参与HALO轮动/再平衡计算。"
                    ),
                }
            )
        halo_payload_positions = [
            item
            for item in legacy_positions
            if normalize_etf_symbol(item.symbol or item.code or "") != CASHFLOW_SYMBOL
        ]
        halo_cash = payload.cash_to_invest
    return halo_payload_positions, source_symbols, warnings, float(halo_cash or 0.0)


async def _rebalance_plan(
    payload: AShareEtfRebalancePlanRequest,
) -> AShareEtfRebalancePlanResponse:
    try:
        halo_payload_positions, _source_symbols, warnings, halo_cash = _resolve_halo_inputs(payload)

        need_quote_fill = any(
            item.current_price is None for item in halo_payload_positions
        )
        quote_prices = await _quote_price_by_symbol() if need_quote_fill else {}

        positions: list[ETFPosition] = []
        for item in halo_payload_positions:
            symbol = normalize_etf_symbol(item.symbol or item.code)
            current_price = item.current_price or quote_prices.get(symbol)
            if current_price is None or current_price <= 0:
                raise ValueError(f"{symbol}:current_price_required")
            positions.append(
                ETFPosition(
                    symbol=symbol,
                    shares=item.shares,
                    cost_price=item.cost_price,
                    current_price=float(current_price),
                )
            )

        validate_halo_positions(positions)

        config = RebalanceConfig(
            mode=PlanMode(payload.mode),
            cash_to_invest=halo_cash,
            lot_size=payload.lot_size,
            tolerance_pct=payload.tolerance_pct,
            hard_tolerance_pct=payload.hard_tolerance_pct,
            min_trade_amount=payload.min_trade_amount,
            fee_rate=payload.fee_rate,
            min_fee=payload.min_fee,
            trade_count_penalty=payload.trade_count_penalty,
            cash_deviation_penalty=payload.cash_deviation_penalty,
            avoid_loss_sell_inside_hard_band=payload.avoid_loss_sell_inside_hard_band,
        )
        plan = optimize_etf_rebalance(
            positions,
            config,
            target_weights=payload.halo_target_weights,
        )
        if warnings:
            plan["warnings"] = warnings
        return AShareEtfRebalancePlanResponse.model_validate(plan)
    except ValueError as exc:
        raise HTTPException(status_code=400, detail=str(exc)) from exc



@router.get("/catalog", response_model=AShareEtfCatalogResponse)
async def get_ashare_etf_catalog(
    _: CurrentUser = Depends(require_roles("admin", "trader", "analyst", "viewer")),
) -> AShareEtfCatalogResponse:
    return await _catalog()


@router.get("/quotes", response_model=AShareEtfQuoteResponse)
async def get_ashare_etf_quotes(
    group: Literal["all", "cashflow", "halo"] = Query(default="all"),
    force: bool = Query(default=False),
    _: CurrentUser = Depends(require_roles("admin", "trader", "analyst", "viewer")),
) -> AShareEtfQuoteResponse:
    return await _quotes(group, force)


@router.post("/quotes/refresh", response_model=AShareEtfQuoteResponse)
async def refresh_ashare_etf_quotes(
    group: Literal["all", "cashflow", "halo"] = Query(default="all"),
    _: CurrentUser = Depends(require_roles("admin", "trader", "analyst")),
) -> AShareEtfQuoteResponse:
    return await _quotes(group, True)


@router.get("/sources/health", response_model=AShareEtfSourceHealthResponse)
async def get_ashare_etf_sources_health(
    _: CurrentUser = Depends(require_roles("admin", "trader", "analyst", "viewer")),
) -> AShareEtfSourceHealthResponse:
    return await _health()


@router.post("/rebalance/plan", response_model=AShareEtfRebalancePlanResponse)
async def plan_ashare_etf_rebalance(
    payload: AShareEtfRebalancePlanRequest,
    _: CurrentUser = Depends(require_roles("admin", "trader", "analyst", "viewer")),
) -> AShareEtfRebalancePlanResponse:
    return await _rebalance_plan(payload)


@etf_router.get("/catalog", response_model=AShareEtfCatalogResponse)
async def get_etf_catalog(
    _: CurrentUser = Depends(require_roles("admin", "trader", "analyst", "viewer")),
) -> AShareEtfCatalogResponse:
    return await _catalog()


@etf_router.get("/quotes", response_model=AShareEtfQuoteResponse)
async def get_etf_quotes(
    group: Literal["all", "cashflow", "halo"] = Query(default="all"),
    force: bool = Query(default=False),
    _: CurrentUser = Depends(require_roles("admin", "trader", "analyst", "viewer")),
) -> AShareEtfQuoteResponse:
    return await _quotes(group, force)


@etf_router.post("/quotes/refresh", response_model=AShareEtfQuoteResponse)
async def refresh_etf_quotes(
    group: Literal["all", "cashflow", "halo"] = Query(default="all"),
    _: CurrentUser = Depends(require_roles("admin", "trader", "analyst")),
) -> AShareEtfQuoteResponse:
    return await _quotes(group, True)


@etf_router.get("/sources/health", response_model=AShareEtfSourceHealthResponse)
async def get_etf_sources_health(
    _: CurrentUser = Depends(require_roles("admin", "trader", "analyst", "viewer")),
) -> AShareEtfSourceHealthResponse:
    return await _health()


@etf_router.post("/rebalance/plan", response_model=AShareEtfRebalancePlanResponse)
async def plan_etf_rebalance(
    payload: AShareEtfRebalancePlanRequest,
    _: CurrentUser = Depends(require_roles("admin", "trader", "analyst", "viewer")),
) -> AShareEtfRebalancePlanResponse:
    return await _rebalance_plan(payload)
