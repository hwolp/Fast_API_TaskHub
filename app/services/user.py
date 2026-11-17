from sqlalchemy.exc import IntegrityError

from app.core import messages
from app.core.exceptions import (
    BadRequestError,
    ForbiddenError,
    NotFoundError,
)
from app.core.permissions import (
    can_manage_users,
    can_modify_user,
    can_view_user,
)
from app.models import User
from app.repositories.user import UserRepository
from app.schemas.user import UserUpdate


class UserService:
    def __init__(self, repository: UserRepository) -> None:
        self.repository = repository
        self.session = repository.session

    async def _get_or_404(self, user_id: int) -> User:
        target = await self.repository.get(user_id)
        if target is None:
            raise NotFoundError(messages.USER_NOT_FOUND)
        return target

    async def list_users(
        self, actor: User, *, page: int, limit: int
    ) -> tuple[list[User], int]:
        if not can_manage_users(actor):
            raise ForbiddenError(messages.FORBIDDEN)
        return await self.repository.get_multi(page=page, limit=limit)

    async def get_user(self, user_id: int, actor: User) -> User:
        if not can_view_user(actor, user_id):
            raise ForbiddenError(messages.FORBIDDEN)
        return await self._get_or_404(user_id)

    async def update_user(
        self, user_id: int, data: UserUpdate, actor: User
    ) -> User:
        if not can_modify_user(actor, user_id):
            raise ForbiddenError(messages.FORBIDDEN)
        changes = data.model_dump(exclude_unset=True)
        if "role" in changes or "is_active" in changes:
            if not can_manage_users(actor):
                raise ForbiddenError(messages.FORBIDDEN)
            if actor.id == user_id:
                raise BadRequestError(messages.CANNOT_MODIFY_OWN_ADMIN_STATUS)
        target = await self._get_or_404(user_id)
        updated = await self.repository.update(target, changes)
        await self.session.commit()
        return updated

    async def delete_user(self, user_id: int, actor: User) -> None:
        if not can_manage_users(actor):
            raise ForbiddenError(messages.FORBIDDEN)
        if actor.id == user_id:
            raise BadRequestError(messages.CANNOT_DELETE_OWN_ACCOUNT)
        target = await self._get_or_404(user_id)
        try:
            await self.repository.delete(target)
            await self.session.commit()
        except IntegrityError:
            await self.session.rollback()
            raise BadRequestError(
                messages.CANNOT_DELETE_USER_WITH_DEPENDENCIES
            ) from None
