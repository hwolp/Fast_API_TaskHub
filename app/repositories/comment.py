from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.models import Comment, Project, Task, User
from app.models.enums import UserRole
from app.repositories.base import BaseRepository


class CommentRepository(BaseRepository[Comment]):
    def __init__(self, session: AsyncSession) -> None:
        super().__init__(Comment, session)

    async def get_task_with_workspace(self, task_id: int) -> tuple[Task, int] | None:
        row = (
            await self.session.execute(
                select(Task, Project.workspace_id)
                .join(Project, Task.project_id == Project.id)
                .where(Task.id == task_id)
            )
        ).first()
        return (row[0], row[1]) if row else None

    async def get_with_workspace(self, comment_id: int) -> tuple[Comment, int] | None:
        row = (
            await self.session.execute(
                select(Comment, Project.workspace_id)
                .join(Task, Comment.task_id == Task.id)
                .join(Project, Task.project_id == Project.id)
                .where(Comment.id == comment_id)
            )
        ).first()
        return (row[0], row[1]) if row else None

    async def list_visible(
        self,
        user: User,
        *,
        task_id: int | None = None,
        page: int = 1,
        limit: int = 20,
    ) -> tuple[list[Comment], int]:
        stmt = select(Comment)
        if user.role != UserRole.ADMIN:
            visible_projects = select(Project.id).where(
                Project.workspace_id.in_(self.visible_workspace_ids(user.id))
            )
            visible_tasks = select(Task.id).where(Task.project_id.in_(visible_projects))
            stmt = stmt.where(Comment.task_id.in_(visible_tasks))
        if task_id is not None:
            stmt = stmt.where(Comment.task_id == task_id)
        return await self._paginate(stmt, page=page, limit=limit)

