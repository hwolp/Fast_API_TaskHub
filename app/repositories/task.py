from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.models import Project, Task, User
from app.models.enums import UserRole
from app.repositories.base import BaseRepository


class TaskRepository(BaseRepository[Task]):
    def __init__(self, session: AsyncSession) -> None:
        super().__init__(Task, session)

    async def get_with_workspace(self, task_id: int) -> tuple[Task, int] | None:
        return await self.get_task_with_workspace(task_id)

    async def list_visible(
        self,
        user: User,
        *,
        project_id: int | None = None,
        page: int = 1,
        limit: int = 20,
    ) -> tuple[list[Task], int]:
        stmt = select(Task)
        if user.role != UserRole.ADMIN:
            visible_projects = select(Project.id).where(
                Project.workspace_id.in_(self.visible_workspace_ids(user.id))
            )
            stmt = stmt.where(Task.project_id.in_(visible_projects))
        if project_id is not None:
            stmt = stmt.where(Task.project_id == project_id)
        return await self._paginate(stmt, page=page, limit=limit)
