from __future__ import annotations

from fastapi import Request
from fastapi.responses import JSONResponse
from starlette.middleware.base import BaseHTTPMiddleware

from app.core.config import settings


class LocalOnlyMiddleware(BaseHTTPMiddleware):
    async def dispatch(self, request: Request, call_next):
        if not settings.local_only_enforced:
            return await call_next(request)

        host = request.client.host if request.client is not None else ""
        if host in set(settings.local_allowed_hosts):
            return await call_next(request)

        return JSONResponse(
            status_code=403,
            content={"detail": "local-only mode enabled; remote access is blocked"},
        )
