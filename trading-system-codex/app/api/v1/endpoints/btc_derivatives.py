from __future__ import annotations

from typing import Literal

from fastapi import APIRouter, Query, Response

from app.schemas.btc_derivatives import (
    BtcDerivativesDashboardResponse,
    HedgePlanRequest,
    HedgePlanResponse,
)
from app.schemas.btc_derivatives_sources import SourceProbeResponse
from app.schemas.refresh import RefreshReceipt
from app.services.btc_derivatives.hedge_engine import build_hedge_plan
from app.services.btc_derivatives.live_service import btc_derivatives_live_service

router = APIRouter(prefix="/btc-derivatives", tags=["btc-derivatives"])


@router.get("/dashboard", response_model=BtcDerivativesDashboardResponse)
async def get_dashboard(
    expiry: str | None = Query(default=None),
    expiry_mode: Literal["fixed", "constant_maturity"] = Query(
        default="constant_maturity"
    ),
    maturity_bucket: Literal["30D", "60D", "90D"] = Query(default="60D"),
    window: Literal["7D", "30D", "90D", "180D", "365D"] | None = Query(
        default=None
    ),
    strike_range_pct: Literal["10", "20", "30", "50", "all"] = Query(
        default="30"
    ),
) -> BtcDerivativesDashboardResponse:
    return await btc_derivatives_live_service.dashboard(
        expiry=expiry,
        expiry_mode=expiry_mode,
        maturity_bucket=maturity_bucket,
        window=window,
        strike_range_pct=strike_range_pct,
    )


@router.post(
    "/dashboard/refresh",
    response_model=BtcDerivativesDashboardResponse | RefreshReceipt,
)
async def refresh_dashboard(
    response: Response,
    expiry: str | None = Query(default=None),
    expiry_mode: Literal["fixed", "constant_maturity"] = Query(
        default="constant_maturity"
    ),
    maturity_bucket: Literal["30D", "60D", "90D"] = Query(default="60D"),
    window: Literal["7D", "30D", "90D", "180D", "365D"] | None = Query(
        default=None
    ),
    strike_range_pct: Literal["10", "20", "30", "50", "all"] = Query(
        default="30"
    ),
    wait: bool = Query(default=False),
) -> BtcDerivativesDashboardResponse | RefreshReceipt:
    if wait:
        return await btc_derivatives_live_service.dashboard(
            expiry=expiry,
            expiry_mode=expiry_mode,
            maturity_bucket=maturity_bucket,
            window=window,
            strike_range_pct=strike_range_pct,
            force=True,
        )
    response.status_code = 202
    return btc_derivatives_live_service.enqueue_refresh(
        expiry=expiry,
        expiry_mode=expiry_mode,
        maturity_bucket=maturity_bucket,
        window=window,
        strike_range_pct=strike_range_pct,
    )


@router.get("/sources/status")
async def get_source_status() -> dict[str, object]:
    return {"providers": btc_derivatives_live_service.source_status()}


@router.post("/sources/probe", response_model=SourceProbeResponse)
async def probe_sources() -> SourceProbeResponse:
    return await btc_derivatives_live_service.probe()


@router.get("/live/snapshot", response_model=BtcDerivativesDashboardResponse)
async def get_live_snapshot(
    expiry: str | None = Query(default=None),
    expiry_mode: Literal["fixed", "constant_maturity"] = Query(
        default="constant_maturity"
    ),
    maturity_bucket: Literal["30D", "60D", "90D"] = Query(default="60D"),
    window: Literal["7D", "30D", "90D", "180D", "365D"] | None = Query(
        default=None
    ),
    strike_range_pct: Literal["10", "20", "30", "50", "all"] = Query(
        default="30"
    ),
) -> BtcDerivativesDashboardResponse:
    return await btc_derivatives_live_service.dashboard(
        expiry=expiry,
        expiry_mode=expiry_mode,
        maturity_bucket=maturity_bucket,
        window=window,
        strike_range_pct=strike_range_pct,
    )


@router.post(
    "/live/refresh",
    response_model=BtcDerivativesDashboardResponse | RefreshReceipt,
)
async def refresh_live_snapshot(
    response: Response,
    expiry: str | None = Query(default=None),
    expiry_mode: Literal["fixed", "constant_maturity"] = Query(
        default="constant_maturity"
    ),
    maturity_bucket: Literal["30D", "60D", "90D"] = Query(default="60D"),
    window: Literal["7D", "30D", "90D", "180D", "365D"] | None = Query(
        default=None
    ),
    strike_range_pct: Literal["10", "20", "30", "50", "all"] = Query(
        default="30"
    ),
    wait: bool = Query(default=False),
) -> BtcDerivativesDashboardResponse | RefreshReceipt:
    if wait:
        return await btc_derivatives_live_service.dashboard(
            expiry=expiry,
            expiry_mode=expiry_mode,
            maturity_bucket=maturity_bucket,
            window=window,
            strike_range_pct=strike_range_pct,
            force=True,
        )
    response.status_code = 202
    return btc_derivatives_live_service.enqueue_refresh(
        expiry=expiry,
        expiry_mode=expiry_mode,
        maturity_bucket=maturity_bucket,
        window=window,
        strike_range_pct=strike_range_pct,
    )


@router.post("/hedge-plan", response_model=HedgePlanResponse)
async def plan_hedge(payload: HedgePlanRequest) -> HedgePlanResponse:
    return build_hedge_plan(payload)
