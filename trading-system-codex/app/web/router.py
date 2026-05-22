from __future__ import annotations

import os
import time
from dataclasses import dataclass

from fastapi import APIRouter, Request
from fastapi.templating import Jinja2Templates

from app.core.paths import app_paths

templates = Jinja2Templates(directory=str(app_paths.templates_dir))
web_router = APIRouter(include_in_schema=False)

ASSET_VERSION_TTL_SECONDS = 2.0


@dataclass
class AssetVersionCache:
    value: str = "0"
    checked_at: float = 0.0


_asset_version_cache = AssetVersionCache()


PAGE_TITLES = {
    "macro-calendar": "宏观日历",
    "market-events": "市场事件",
    "monitoring-overview": "监控总览",
    "market-structure": "形态结构",
    "market-analysis": "技术指标",
    "alert-center": "告警中心",
    "knowledge-base": "知识百科",
    "ashare-etf": "A股ETF",
    "ai-strategy": "AI策略",
}


def static_asset_version() -> str:
    env_version = os.getenv("APP_ASSET_VERSION")
    if env_version:
        return env_version

    now = time.monotonic()
    if now - _asset_version_cache.checked_at < ASSET_VERSION_TTL_SECONDS:
        return _asset_version_cache.value

    roots = (app_paths.static_dir, app_paths.templates_dir)
    mtimes = [
        int(path.stat().st_mtime)
        for root in roots
        for path in root.rglob("*")
        if path.is_file() and path.suffix in {".js", ".css", ".html"}
    ]
    _asset_version_cache.value = str(max(mtimes) if mtimes else 0)
    _asset_version_cache.checked_at = now
    return _asset_version_cache.value


def render_page(request: Request, title: str, page_id: str):
    return templates.TemplateResponse(
        request=request,
        name="page.html",
        context={"title": title, "page_id": page_id, "asset_version": static_asset_version()},
    )


@web_router.get("/macro-calendar-page")
async def macro_calendar_page(request: Request):
    return render_page(request, PAGE_TITLES["macro-calendar"], "macro-calendar")


@web_router.get("/market-events-page")
async def market_events_page(request: Request):
    return render_page(request, PAGE_TITLES["market-events"], "market-events")


@web_router.get("/monitoring-page")
async def monitoring_page(request: Request):
    return render_page(request, PAGE_TITLES["monitoring-overview"], "monitoring-overview")


@web_router.get("/dashboard")
async def dashboard_page(request: Request):
    return render_page(request, PAGE_TITLES["monitoring-overview"], "monitoring-overview")


@web_router.get("/structure-page")
async def structure_page(request: Request):
    return render_page(request, PAGE_TITLES["market-structure"], "market-structure")


@web_router.get("/indicators-page")
async def indicators_page(request: Request):
    return render_page(request, PAGE_TITLES["market-analysis"], "market-analysis")


@web_router.get("/alerts-page")
async def alerts_page(request: Request):
    return render_page(request, PAGE_TITLES["alert-center"], "alert-center")


@web_router.get("/knowledge-page")
async def knowledge_page(request: Request):
    return render_page(request, PAGE_TITLES["knowledge-base"], "knowledge-base")


@web_router.get("/ashare-etf-page")
async def ashare_etf_page(request: Request):
    return render_page(request, PAGE_TITLES["ashare-etf"], "ashare-etf")


@web_router.get("/etf-page")
async def etf_page(request: Request):
    return render_page(request, PAGE_TITLES["ashare-etf"], "ashare-etf")


@web_router.get("/strategy-page")
async def strategy_page(request: Request):
    return render_page(request, PAGE_TITLES["ai-strategy"], "ai-strategy")
