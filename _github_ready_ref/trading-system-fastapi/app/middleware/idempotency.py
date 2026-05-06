from __future__ import annotations

import hashlib
import json

from fastapi.responses import JSONResponse, Response
from starlette.concurrency import iterate_in_threadpool
from starlette.middleware.base import BaseHTTPMiddleware
from starlette.requests import Request

from app.core.config import settings
from app.core.db import db_manager
from app.db.models.eventing import IdempotencyKeyRecord
from app.repositories.idempotency_repository import IdempotencyRepository


class FillIdempotencyMiddleware(BaseHTTPMiddleware):
    async def dispatch(self, request: Request, call_next):
        if request.method != "POST" or not request.url.path.endswith("/positions/fills"):
            return await call_next(request)

        idempotency_key = request.headers.get("Idempotency-Key")
        if settings.require_idempotency_for_fill_writes and not idempotency_key:
            return JSONResponse(status_code=400, content={"detail": "missing Idempotency-Key header"})
        if not idempotency_key:
            return await call_next(request)

        body = await request.body()
        request_hash = hashlib.sha256(body).hexdigest()

        async with db_manager.session() as session:
            repo = IdempotencyRepository(session)
            existing = await repo.find(idempotency_key=idempotency_key, request_path=request.url.path)
            if existing is not None:
                if existing.request_hash != request_hash:
                    return JSONResponse(status_code=409, content={"detail": "idempotency key reused with different payload"})
                if existing.state == "SUCCEEDED" and existing.response_body is not None:
                    media_type = existing.content_type or "application/json"
                    return Response(
                        content=existing.response_body,
                        status_code=existing.response_status or 200,
                        media_type=media_type,
                    )
                if existing.state == "PROCESSING":
                    return JSONResponse(status_code=409, content={"detail": "request already in progress"})
            else:
                await repo.add(
                    IdempotencyKeyRecord(
                        idempotency_key=idempotency_key,
                        request_path=request.url.path,
                        request_hash=request_hash,
                        state="PROCESSING",
                    )
                )

        async def receive() -> dict:
            return {"type": "http.request", "body": body, "more_body": False}

        request = Request(request.scope, receive)
        response = await call_next(request)
        response_body = b""
        async for chunk in response.body_iterator:
            response_body += chunk
        response.body_iterator = iterate_in_threadpool(iter([response_body]))

        async with db_manager.session() as session:
            repo = IdempotencyRepository(session)
            record = await repo.find(idempotency_key=idempotency_key, request_path=request.url.path)
            if record is not None:
                record.state = "SUCCEEDED" if response.status_code < 500 else "FAILED"
                record.response_status = response.status_code
                record.content_type = response.media_type or response.headers.get("content-type")
                try:
                    record.response_body = response_body.decode("utf-8")
                    if record.content_type and "application/json" in record.content_type:
                        json.loads(record.response_body)
                except Exception:
                    record.response_body = response_body.decode("utf-8", errors="ignore")
        return response
