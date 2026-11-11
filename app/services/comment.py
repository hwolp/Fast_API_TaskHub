from fastapi import HTTPException

from app.core.permissions import (
    can_create_comment,
    can_delete_comment,
    can_modify_comment,
    effective_role,
)
from app.core.security import forbidden
from app.models import Comment, User
from app.models.enums import WorkspaceRole
from app.repositories.comment import CommentRepository
from app.schemas.comment import CommentCreate, CommentUpdate


class CommentService:
    def __init__(self, repository: CommentRepository) -> None:
        self.repository = repository

    async def _role(self, workspace_id: int, user: User) -> WorkspaceRole | None:
        return effective_role(
            user, await self.repository.workspace_role(workspace_id, user.id)
        )

    async def _load(
        self, comment_id: int, user: User
    ) -> tuple[Comment, WorkspaceRole]:
        found = await self.repository.get_with_workspace(comment_id)
        role = await self._role(found[1], user) if found else None
        if found is None or role is None:
            raise HTTPException(404, "comment_not_found")
        return found[0], role

    async def create_comment(self, data: CommentCreate, user: User) -> Comment:
        found = await self.repository.get_task_with_workspace(data.task_id)
        role = await self._role(found[1], user) if found else None
        if found is None or role is None:
            raise HTTPException(404, "task_not_found")
        if not can_create_comment(role):
            raise forbidden()
        return await self.repository.create(**data.model_dump(), author_id=user.id)

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
            raise forbidden()
        return await self.repository.update(
            comment, data.model_dump(exclude_unset=True)
        )

    async def delete_comment(self, comment_id: int, user: User) -> None:
        comment, role = await self._load(comment_id, user)
        if not can_delete_comment(role, comment, user):
            raise forbidden()
        await self.repository.delete(comment)

