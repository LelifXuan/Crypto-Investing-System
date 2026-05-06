from __future__ import annotations

import base64
import hashlib
import hmac
import os
from dataclasses import dataclass
from datetime import UTC, datetime, timedelta

import jwt
from jwt import InvalidTokenError

from app.core.config import settings


@dataclass(slots=True)
class TokenPayload:
    sub: str
    username: str
    tenant_id: str
    roles: list[str]
    exp: int


def hash_password(password: str) -> str:
    salt = os.urandom(16)
    derived = hashlib.pbkdf2_hmac("sha256", password.encode("utf-8"), salt, 120_000)
    return f"pbkdf2_sha256${base64.b64encode(salt).decode()}${base64.b64encode(derived).decode()}"


def verify_password(password: str, hashed_password: str) -> bool:
    try:
        algorithm, salt_b64, digest_b64 = hashed_password.split("$", maxsplit=2)
    except ValueError:
        return False
    if algorithm != "pbkdf2_sha256":
        return False
    salt = base64.b64decode(salt_b64.encode())
    expected = base64.b64decode(digest_b64.encode())
    candidate = hashlib.pbkdf2_hmac("sha256", password.encode("utf-8"), salt, 120_000)
    return hmac.compare_digest(candidate, expected)


def create_access_token(
    *, user_id: str, username: str, tenant_id: str, roles: list[str]
) -> tuple[str, int]:
    expires_delta = timedelta(minutes=settings.jwt_access_token_expire_minutes)
    expires_at = datetime.now(UTC) + expires_delta
    payload = {
        "sub": user_id,
        "username": username,
        "tenant_id": tenant_id,
        "roles": roles,
        "exp": expires_at,
    }
    token = jwt.encode(payload, settings.jwt_secret_key, algorithm=settings.jwt_algorithm)
    return token, int(expires_delta.total_seconds())


def decode_access_token(token: str) -> TokenPayload:
    try:
        payload = jwt.decode(token, settings.jwt_secret_key, algorithms=[settings.jwt_algorithm])
    except InvalidTokenError as exc:  # pragma: no cover
        raise ValueError("invalid token") from exc
    return TokenPayload(
        sub=str(payload["sub"]),
        username=str(payload["username"]),
        tenant_id=str(payload["tenant_id"]),
        roles=list(payload.get("roles", [])),
        exp=int(payload["exp"]),
    )
