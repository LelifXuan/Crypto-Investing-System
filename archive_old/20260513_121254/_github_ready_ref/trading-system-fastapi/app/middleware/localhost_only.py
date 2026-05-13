from __future__ import annotations

import ipaddress

from fastapi import Request
from starlette.responses import JSONResponse

from app.core.config import settings


class LocalhostOnlyMiddleware:
    def __init__(self, app) -> None:
        self.app = app

    async def __call__(self, scope, receive, send) -> None:
        if scope.get("type") != "http" or not settings.local_only_enforced:
            await self.app(scope, receive, send)
            return
        request = Request(scope, receive=receive)
        client_host = (request.client.host if request.client else "") or ""
        if _is_allowed_host(client_host):
            await self.app(scope, receive, send)
            return
        response = JSONResponse(
            status_code=403,
            content={"detail": f"local_only_enforced=true, remote host '{client_host}' is not allowed"},
        )
        await response(scope, receive, send)


def _is_allowed_host(host: str) -> bool:
    if host in settings.local_allowed_hosts:
        return True
    try:
        ip = ipaddress.ip_address(host)
    except ValueError:
        return False
    return ip.is_loopback
