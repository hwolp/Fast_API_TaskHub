from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy.orm import selectinload

from app.models import Project, Task, User, Workspace, WorkspaceMember
from app.models.enums import ProjectStatus, UserRole, WorkspaceRole
from app.repositories.base import BaseRepository
from app.schemas.pagination import PaginationParams


class TaskRepository(BaseRepository[Task]):
    def __init__(self, session: AsyncSession) -> None:
        super().__init__(Task, session)

    async def get_with_workspace(
        self, task_id: int
    ) -> tuple[Task, int, ProjectStatus] | None:
        return await self.get_task_with_workspace(task_id)

    async def get_assignee_info(
        self, workspace_id: int, user_id: int
    ) -> tuple[bool, WorkspaceRole | None] | None:
        stmt = (
            select(
                User.is_active,
                Workspace.owner_id,
                WorkspaceMember.role,
            )
            .select_from(User)
            .join(Workspace, Workspace.id == workspace_id)
            .outerjoin(
                WorkspaceMember,
                (WorkspaceMember.workspace_id == Workspace.id)
                & (WorkspaceMember.user_id == User.id),
            )
            .where(User.id == user_id)
        )
        row = (await self.session.execute(stmt)).first()
        if row is None:
            return None
        is_active, owner_id, member_role = row
        role = WorkspaceRole.OWNER if owner_id == user_id else member_role
        return bool(is_active), role

    async def list_visible(
        self,
        user: User,
        *,
        pagination: PaginationParams | None = None,
        project_id: int | None = None,
        page: int = 1,
        limit: int = 20,
    ) -> tuple[list[Task], int]:
        stmt = select(Task).options(selectinload(Task.labels))
        if user.role != UserRole.ADMIN:
            visible_projects = select(Project.id).where(
                Project.workspace_id.in_(self.visible_workspace_ids(user.id))
            )
            stmt = stmt.where(Task.project_id.in_(visible_projects))
        if project_id is not None:
            stmt = stmt.where(Task.project_id == project_id)
        return await self._paginate(
            stmt, pagination=pagination, page=page, limit=limit
        )
