from __future__ import annotations

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.db.models.auth import User, UserRole


class AuthRepository:
    def __init__(self, session: AsyncSession) -> None:
        self.session = session

    async def add_user(self, user: User) -> User:
        self.session.add(user)
        await self.session.flush()
        return user

    async def add_user_roles(self, roles: list[UserRole]) -> None:
        self.session.add_all(roles)
        await self.session.flush()

    async def get_user_by_username(self, username: str) -> User | None:
        result = await self.session.execute(select(User).where(User.username == username))
        return result.scalar_one_or_none()

    async def get_user_by_id(self, user_id: str) -> User | None:
        result = await self.session.execute(select(User).where(User.user_id == user_id))
        return result.scalar_one_or_none()

    async def list_roles(self, user_id: str) -> list[str]:
        result = await self.session.execute(
            select(UserRole.role_name).where(UserRole.user_id == user_id).order_by(UserRole.role_name)
        )
        return [row[0] for row in result.all()]
