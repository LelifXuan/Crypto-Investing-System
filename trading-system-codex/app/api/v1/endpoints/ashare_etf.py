from __future__ import annotations

from typing import Literal

from fastapi import APIRouter, Depends, Query

from app.api.dependencies import CurrentUser, require_roles
from app.core.config import settings
from app.schemas.etf import (
    AShareEtfCatalogResponse,
    AShareEtfQuoteResponse,
    AShareEtfSourceHealthResponse,
)
from app.services.ashare_etf_quotes import AShareETFQuoteService, EastmoneyDirectETFClient

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
