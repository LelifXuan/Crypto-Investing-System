from __future__ import annotations

from dataclasses import dataclass

from fastapi import HTTPException, status

from app.core.ids import new_id
from app.core.security import create_access_token, hash_password, verify_password
from app.db.models.auth import User, UserRole
from app.repositories.auth_repository import AuthRepository


@dataclass(slots=True)
class AuthenticatedUser:
    user_id: str
    tenant_id: str
    username: str
    roles: list[str]
    is_active: bool


class AuthService:
    def __init__(self, repository: AuthRepository) -> None:
        self.repository = repository

    async def authenticate(
        self, username: str, password: str
    ) -> tuple[str, int, AuthenticatedUser]:
        user = await self.repository.get_user_by_username(username)
        if user is None or not verify_password(password, user.password_hash) or not user.is_active:
            raise HTTPException(
                status_code=status.HTTP_401_UNAUTHORIZED, detail="invalid credentials"
            )
        roles = await self.repository.list_roles(user.user_id)
        token, expires_in = create_access_token(
            user_id=user.user_id,
            username=user.username,
            tenant_id=user.tenant_id,
            roles=roles,
        )
        return (
            token,
            expires_in,
            AuthenticatedUser(
                user_id=user.user_id,
                tenant_id=user.tenant_id,
                username=user.username,
                roles=roles,
                is_active=user.is_active,
            ),
        )

    async def register_bootstrap_admin(self, tenant_id: str, username: str, password: str) -> User:
        existing = await self.repository.get_user_by_username(username)
        if existing is not None:
            return existing
        user = User(
            user_id=new_id("user"),
            tenant_id=tenant_id,
            username=username,
            email=None,
            password_hash=hash_password(password),
            is_active=True,
        )
        await self.repository.add_user(user)
        await self.repository.add_user_roles(
            [
                UserRole(user_id=user.user_id, role_name="admin"),
                UserRole(user_id=user.user_id, role_name="trader"),
                UserRole(user_id=user.user_id, role_name="analyst"),
                UserRole(user_id=user.user_id, role_name="viewer"),
            ]
        )
        return user
