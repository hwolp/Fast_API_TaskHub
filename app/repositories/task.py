from dataclasses import dataclass

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy.orm import selectinload

from app.models import Project, Task, User, Workspace, WorkspaceMember
from app.models.enums import ProjectStatus, UserRole, WorkspaceRole
from app.repositories.base import BaseRepository
from app.schemas.pagination import PaginationParams


@dataclass(frozen=True, slots=True)
class AssigneeInfo:
    user_id: int
    email: str
    full_name: str
    is_active: bool
    role: WorkspaceRole | None


class TaskRepository(BaseRepository[Task]):
    def __init__(self, session: AsyncSession) -> None:
        super().__init__(Task, session)

    async def get_cache_scope_workspace_ids(
        self, user: User, project_id: int | None
    ) -> tuple[list[int], bool]:
        if user.role == UserRole.ADMIN and project_id is None:
            return [], True
        if project_id is not None:
            proj_ws_id = await self.session.scalar(
                select(Project.workspace_id).where(Project.id == project_id)
            )
            if proj_ws_id is None:
                return [], False
            if user.role == UserRole.ADMIN:
                return [proj_ws_id], True
            role = await self.workspace_role(proj_ws_id, user.id)
            return ([proj_ws_id], True) if role is not None else ([], True)
        ws_ids = list(
            (await self.session.scalars(self.visible_workspace_ids(user.id))).all()
        )
        return sorted(ws_ids), True

    async def get_with_workspace(
        self, task_id: int
    ) -> tuple[Task, int, ProjectStatus] | None:
        return await self.get_task_with_workspace(task_id)

    async def get_assignee_info(
        self, workspace_id: int, user_id: int
    ) -> AssigneeInfo | None:
        stmt = (
            select(
                User.id,
                User.email,
                User.full_name,
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
        found_id, email, full_name, is_active, owner_id, member_role = row
        role = WorkspaceRole.OWNER if owner_id == user_id else member_role
        return AssigneeInfo(
            user_id=found_id,
            email=email,
            full_name=full_name,
            is_active=bool(is_active),
            role=role,
        )

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
