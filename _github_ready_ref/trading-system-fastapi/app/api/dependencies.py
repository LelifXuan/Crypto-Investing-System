from __future__ import annotations

from collections.abc import AsyncGenerator, Callable
from dataclasses import dataclass

from fastapi import Depends, HTTPException, status
from fastapi.security import HTTPAuthorizationCredentials, HTTPBearer
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.config import settings
from app.core.db import db_manager
from app.core.security import decode_access_token
from app.repositories.auth_repository import AuthRepository


security = HTTPBearer(auto_error=False)


@dataclass(slots=True)
class CurrentUser:
    user_id: str
    tenant_id: str
    username: str
    roles: list[str]
    is_active: bool


async def get_db_session() -> AsyncGenerator[AsyncSession, None]:
    async with db_manager.session() as session:
        yield session


async def get_current_user(
    credentials: HTTPAuthorizationCredentials | None = Depends(security),
    session: AsyncSession = Depends(get_db_session),
) -> CurrentUser:
    if settings.single_user_mode:
        return CurrentUser(
            user_id=settings.local_user_id,
            tenant_id=settings.local_tenant_id,
            username=settings.local_username,
            roles=list(settings.local_user_roles),
            is_active=True,
        )

    if credentials is None:
        raise HTTPException(status_code=status.HTTP_401_UNAUTHORIZED, detail="missing bearer token")
    try:
        token = decode_access_token(credentials.credentials)
    except ValueError as exc:
        raise HTTPException(status_code=status.HTTP_401_UNAUTHORIZED, detail="invalid bearer token") from exc

    repo = AuthRepository(session)
    user = await repo.get_user_by_id(token.sub)
    if user is None or not user.is_active:
        raise HTTPException(status_code=status.HTTP_401_UNAUTHORIZED, detail="user inactive or not found")
    roles = await repo.list_roles(user.user_id)
    return CurrentUser(
        user_id=user.user_id,
        tenant_id=user.tenant_id,
        username=user.username,
        roles=roles,
        is_active=user.is_active,
    )


def require_roles(*allowed_roles: str) -> Callable[[CurrentUser], CurrentUser]:
    async def dependency(current_user: CurrentUser = Depends(get_current_user)) -> CurrentUser:
        if settings.single_user_mode:
            return current_user
        if not set(current_user.roles).intersection(allowed_roles):
            raise HTTPException(status_code=status.HTTP_403_FORBIDDEN, detail="insufficient role")
        return current_user

    return dependency
