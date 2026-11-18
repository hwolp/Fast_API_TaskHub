from app.core import messages
from app.core.exceptions import ForbiddenError
from app.core.permissions import (
    can_create_comment,
    can_delete_comment,
    can_modify_comment,
)
from app.models import Comment, Task, User
from app.repositories.comment import CommentRepository
from app.schemas.comment import CommentCreate, CommentUpdate
from app.schemas.pagination import PaginationParams
from app.services.base import ScopedEntity, ScopedService


class CommentService(ScopedService[CommentRepository]):
    async def _load(self, comment_id: int, user: User) -> ScopedEntity[Comment]:
        return await self.load_with_workspace(
            comment_id, user, self.repository.get_with_workspace, messages.COMMENT_NOT_FOUND
        )

    async def _load_task(self, task_id: int, user: User) -> ScopedEntity[Task]:
        return await self.load_with_workspace(
            task_id, user, self.repository.get_task_with_workspace, messages.TASK_NOT_FOUND
        )

    async def create_comment(self, data: CommentCreate, user: User) -> Comment:
        task_scoped = await self._load_task(data.task_id, user)
        if not can_create_comment(task_scoped.role):
            raise ForbiddenError(messages.FORBIDDEN)
        self._ensure_project_active(task_scoped.project_status)
        comment = await self.repository.create(**data.model_dump(), author_id=user.id)
        await self.session.commit()
        return comment

    async def list_comments(
        self,
        user: User,
        *,
        pagination: PaginationParams | None = None,
        task_id: int | None = None,
        page: int = 1,
        limit: int = 20,
    ) -> tuple[list[Comment], int]:
        return await self.repository.list_visible(
            user, task_id=task_id, pagination=pagination, page=page, limit=limit
        )

    async def get_comment(self, comment_id: int, user: User) -> Comment:
        scoped = await self._load(comment_id, user)
        return scoped.entity

    async def update_comment(
        self, comment_id: int, data: CommentUpdate, user: User
    ) -> Comment:
        scoped = await self._load(comment_id, user)
        if not can_modify_comment(scoped.role, scoped.entity, user):
            raise ForbiddenError(messages.FORBIDDEN)
        self._ensure_project_active(scoped.project_status)
        updated = await self.repository.update(
            scoped.entity, data.model_dump(exclude_unset=True)
        )
        await self.session.commit()
        return updated

    async def delete_comment(self, comment_id: int, user: User) -> None:
        scoped = await self._load(comment_id, user)
        if not can_delete_comment(scoped.role, scoped.entity, user):
            raise ForbiddenError(messages.FORBIDDEN)
        self._ensure_project_active(scoped.project_status)
        await self.repository.delete(scoped.entity)
        await self.session.commit()
