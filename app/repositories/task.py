from sqlalchemy import func, or_, select
from sqlalchemy.ext.asyncio import AsyncSession

from app.models import Project, Task, User, Workspace, WorkspaceMember
from app.models.enums import UserRole, WorkspaceRole
from app.repositories.base import BaseRepository


class TaskRepository(BaseRepository[Task]):
    def __init__(self, session: AsyncSession) -> None:
        super().__init__(Task, session)

    async def workspace_id_of_project(self, project_id: int) -> int | None:
        return await self.session.scalar(
            select(Project.workspace_id).where(Project.id == project_id)
        )

    async def get_with_workspace(self, task_id: int) -> tuple[Task, int] | None:
        row = (await self.session.execute(
            select(Task, Project.workspace_id)
            .join(Project, Task.project_id == Project.id)
            .where(Task.id == task_id)
        )).first()
        return (row[0], row[1]) if row else None

    async def workspace_role(self, workspace_id: int, user_id: int) -> WorkspaceRole | None:
        """OWNER if user owns the workspace, else their membership role, else None."""
        owner_id = await self.session.scalar(
            select(Workspace.owner_id).where(Workspace.id == workspace_id)
        )
        if owner_id is None:
            return None
        if owner_id == user_id:
            return WorkspaceRole.OWNER
        return await self.session.scalar(
            select(WorkspaceMember.role).where(
                WorkspaceMember.workspace_id == workspace_id,
                WorkspaceMember.user_id == user_id,
            )
        )

    async def list_visible(
        self, user: User, *, page: int, limit: int
    ) -> tuple[list[Task], int]:
        """Tasks in workspaces the user owns or belongs to (ADMIN: every task)."""
        stmt = select(Task)
        if user.role != UserRole.ADMIN:
            member_of = select(WorkspaceMember.workspace_id).where(
                WorkspaceMember.user_id == user.id
            )
            owned = select(Workspace.id).where(Workspace.owner_id == user.id)
            visible_projects = select(Project.id).where(or_(
                Project.workspace_id.in_(member_of), Project.workspace_id.in_(owned),
            ))
            stmt = stmt.where(Task.project_id.in_(visible_projects))
        total = await self.session.scalar(select(func.count()).select_from(stmt.subquery()))
        result = await self.session.scalars(
            stmt.order_by(Task.id).offset((page - 1) * limit).limit(limit)
        )
        return list(result.all()), total or 0
