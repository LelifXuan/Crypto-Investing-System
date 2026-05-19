from __future__ import annotations

from fastapi import APIRouter, Request
from fastapi.templating import Jinja2Templates

from app.core.paths import app_paths

templates = Jinja2Templates(directory=str(app_paths.templates_dir))
web_router = APIRouter(include_in_schema=False)


def static_asset_version() -> str:
    roots = (app_paths.static_dir, app_paths.templates_dir)
    mtimes = [
        int(path.stat().st_mtime)
        for root in roots
        for path in root.rglob("*")
        if path.is_file() and path.suffix in {".js", ".css", ".html"}
    ]
    return str(max(mtimes) if mtimes else 0)


def render_page(request: Request, title: str, page_id: str):
    return templates.TemplateResponse(
        request=request,
        name="page.html",
        context={"title": title, "page_id": page_id, "asset_version": static_asset_version()},
    )


@web_router.get("/macro-calendar-page")
async def macro_calendar_page(request: Request):
    return render_page(request, "宏观日历", "macro-calendar")


@web_router.get("/market-events-page")
async def market_events_page(request: Request):
    return render_page(request, "市场事件", "market-events")


@web_router.get("/monitoring-page")
async def monitoring_page(request: Request):
    return render_page(request, "监控总览", "monitoring-overview")


@web_router.get("/dashboard")
async def dashboard_page(request: Request):
    return render_page(request, "监控总览", "monitoring-overview")


@web_router.get("/structure-page")
async def structure_page(request: Request):
    return render_page(request, "形态结构", "market-structure")


@web_router.get("/indicators-page")
async def indicators_page(request: Request):
    return render_page(request, "技术指标", "market-analysis")


@web_router.get("/alerts-page")
async def alerts_page(request: Request):
    return render_page(request, "告警中心", "alert-center")


@web_router.get("/knowledge-page")
async def knowledge_page(request: Request):
    return render_page(request, "知识百科", "knowledge-base")


@web_router.get("/ashare-etf-page")
async def ashare_etf_page(request: Request):
    return render_page(request, "A股ETF", "ashare-etf")


@web_router.get("/etf-page")
async def etf_page(request: Request):
    return render_page(request, "A股ETF", "ashare-etf")


@web_router.get("/strategy-page")
async def strategy_page(request: Request):
    return render_page(request, "AI策略", "ai-strategy")
