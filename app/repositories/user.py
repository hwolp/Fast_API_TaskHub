from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.models import Project, Task, User
from app.repositories.base import BaseRepository


class UserRepository(BaseRepository[User]):
    def __init__(self, session: AsyncSession) -> None:
        super().__init__(User, session)

    async def list_assigned_task_workspace_ids(self, user_id: int) -> list[int]:
        stmt = (
            select(Project.workspace_id)
            .join(Task, Task.project_id == Project.id)
            .where(Task.assignee_id == user_id)
            .distinct()
        )
        result = await self.session.scalars(stmt)
        return list(result.all())
