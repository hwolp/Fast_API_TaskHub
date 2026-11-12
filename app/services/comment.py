from app.core import messages
from app.core.exceptions import ForbiddenError, NotFoundError
from app.core.permissions import (
    can_create_comment,
    can_delete_comment,
    can_modify_comment,
)
from app.models import Comment, User
from app.models.enums import WorkspaceRole
from app.repositories.comment import CommentRepository
from app.schemas.comment import CommentCreate, CommentUpdate
from app.services.base import ScopedService


class CommentService(ScopedService[CommentRepository]):
    async def _load(
        self, comment_id: int, user: User
    ) -> tuple[Comment, WorkspaceRole]:
        return await self.load_with_workspace(
            comment_id, user, self.repository.get_with_workspace, messages.COMMENT_NOT_FOUND
        )

    async def create_comment(self, data: CommentCreate, user: User) -> Comment:
        found = await self.repository.get_task_with_workspace(data.task_id)
        role = (
            await self.get_user_workspace_role(found[1], user) if found else None
        )
        if found is None or role is None:
            raise NotFoundError(messages.TASK_NOT_FOUND)
        if not can_create_comment(role):
            raise ForbiddenError(messages.FORBIDDEN)
        comment = await self.repository.create(**data.model_dump(), author_id=user.id)
        await self.session.commit()
        return comment

    async def list_comments(
        self,
        user: User,
        *,
        task_id: int | None = None,
        page: int,
        limit: int,
    ) -> tuple[list[Comment], int]:
        return await self.repository.list_visible(
            user, task_id=task_id, page=page, limit=limit
        )

    async def get_comment(self, comment_id: int, user: User) -> Comment:
        comment, _ = await self._load(comment_id, user)
        return comment

    async def update_comment(
        self, comment_id: int, data: CommentUpdate, user: User
    ) -> Comment:
        comment, role = await self._load(comment_id, user)
        if not can_modify_comment(role, comment, user):
            raise ForbiddenError(messages.FORBIDDEN)
        updated = await self.repository.update(
            comment, data.model_dump(exclude_unset=True)
        )
        await self.session.commit()
        return updated

    async def delete_comment(self, comment_id: int, user: User) -> None:
        comment, role = await self._load(comment_id, user)
        if not can_delete_comment(role, comment, user):
            raise ForbiddenError(messages.FORBIDDEN)
        await self.repository.delete(comment)
        await self.session.commit()
