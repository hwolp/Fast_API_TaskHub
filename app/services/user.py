from fastapi import HTTPException

from app.core.permissions import (
    can_manage_users,
    can_modify_user,
    can_view_user,
)
from app.core.security import forbidden
from app.models import User
from app.repositories.user import UserRepository
from app.schemas.user import UserUpdate


class UserService:
    def __init__(self, repository: UserRepository) -> None:
        self.repository = repository

    async def _get_or_404(self, user_id: int) -> User:
        target = await self.repository.get(user_id)
        if target is None:
            raise HTTPException(404, "user_not_found")
        return target

    async def list_users(
        self, actor: User, *, page: int, limit: int
    ) -> tuple[list[User], int]:
        if not can_manage_users(actor):
            raise forbidden()
        return await self.repository.get_multi(page=page, limit=limit)

    async def get_user(self, user_id: int, actor: User) -> User:
        if not can_view_user(actor, user_id):
            raise forbidden()
        return await self._get_or_404(user_id)

    async def update_user(
        self, user_id: int, data: UserUpdate, actor: User
    ) -> User:
        if not can_modify_user(actor, user_id):
            raise forbidden()
        changes = data.model_dump(exclude_unset=True)
        if ("role" in changes or "is_active" in changes) and not can_manage_users(actor):
            raise forbidden()
        target = await self._get_or_404(user_id)
        return await self.repository.update(target, changes)

    async def delete_user(self, user_id: int, actor: User) -> None:
        if not can_manage_users(actor):
            raise forbidden()
        target = await self._get_or_404(user_id)
        await self.repository.delete(target)

