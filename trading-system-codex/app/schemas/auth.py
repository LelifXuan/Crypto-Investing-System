from __future__ import annotations

from datetime import datetime

from pydantic import BaseModel

from app.schemas.common import ORMModel


class LoginRequest(BaseModel):
    username: str
    password: str


class UserRead(ORMModel):
    user_id: str
    tenant_id: str
    username: str
    is_active: bool
    roles: list[str]
    created_at: datetime | None = None


class TokenResponse(BaseModel):
    access_token: str
    token_type: str = "bearer"
    expires_in: int
    user: UserRead
