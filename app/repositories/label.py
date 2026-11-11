from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.models import Label, Project, Task, TaskLabel, User
from app.models.enums import UserRole
from app.repositories.base import BaseRepository


class LabelRepository(BaseRepository[Label]):
    def __init__(self, session: AsyncSession) -> None:
        super().__init__(Label, session)

    async def workspace_id_of_project(self, project_id: int) -> int | None:
        return await self.session.scalar(
            select(Project.workspace_id).where(Project.id == project_id)
        )

    async def get_with_workspace(self, label_id: int) -> tuple[Label, int] | None:
        row = (
            await self.session.execute(
                select(Label, Project.workspace_id)
                .join(Project, Label.project_id == Project.id)
                .where(Label.id == label_id)
            )
        ).first()
        return (row[0], row[1]) if row else None

    async def get_task_with_workspace(self, task_id: int) -> tuple[Task, int] | None:
        row = (
            await self.session.execute(
                select(Task, Project.workspace_id)
                .join(Project, Task.project_id == Project.id)
                .where(Task.id == task_id)
            )
        ).first()
        return (row[0], row[1]) if row else None

    async def list_visible(
        self,
        user: User,
        *,
        project_id: int | None = None,
        page: int = 1,
        limit: int = 20,
    ) -> tuple[list[Label], int]:
        stmt = select(Label)
        if user.role != UserRole.ADMIN:
            visible_projects = select(Project.id).where(
                Project.workspace_id.in_(self.visible_workspace_ids(user.id))
            )
            stmt = stmt.where(Label.project_id.in_(visible_projects))
        if project_id is not None:
            stmt = stmt.where(Label.project_id == project_id)
        return await self._paginate(stmt, page=page, limit=limit)

    async def attach_to_task(self, task_id: int, label_id: int) -> None:
        existing = await self.session.get(TaskLabel, (task_id, label_id))
        if existing is None:
            self.session.add(TaskLabel(task_id=task_id, label_id=label_id))
            await self.session.commit()

    async def detach_from_task(self, task_id: int, label_id: int) -> bool:
        existing = await self.session.get(TaskLabel, (task_id, label_id))
        if existing is None:
            return False
        await self.session.delete(existing)
        await self.session.commit()
        return True

