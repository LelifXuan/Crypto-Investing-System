from __future__ import annotations

from fastapi import APIRouter, Depends, HTTPException, status
from sqlalchemy.ext.asyncio import AsyncSession

from app.api.dependencies import CurrentUser, get_current_user, get_db_session
from app.core.config import settings
from app.repositories.auth_repository import AuthRepository
from app.schemas.auth import LoginRequest, TokenResponse, UserRead
from app.services.auth import AuthService

router = APIRouter(prefix="/auth", tags=["auth"])


@router.post("/login", response_model=TokenResponse)
async def login(payload: LoginRequest, session: AsyncSession = Depends(get_db_session)) -> TokenResponse:
    if settings.single_user_mode:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="single_user_mode=true: login is disabled, call /auth/me directly on localhost",
        )
    service = AuthService(AuthRepository(session))
    token, expires_in, user = await service.authenticate(payload.username, payload.password)
    return TokenResponse(
        access_token=token,
        expires_in=expires_in,
        user=UserRead(
            user_id=user.user_id,
            tenant_id=user.tenant_id,
            username=user.username,
            is_active=user.is_active,
            roles=user.roles,
            created_at=None,
        ),
    )


@router.get("/me", response_model=UserRead)
async def me(current_user: CurrentUser = Depends(get_current_user)) -> UserRead:
    return UserRead(
        user_id=current_user.user_id,
        tenant_id=current_user.tenant_id,
        username=current_user.username,
        is_active=current_user.is_active,
        roles=current_user.roles,
        created_at=None,
    )
