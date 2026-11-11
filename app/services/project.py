from app.core import messages
from app.core.exceptions import ForbiddenError, NotFoundError
from app.core.permissions import can_delete_project, can_write_project
from app.models import Project, User
from app.models.enums import WorkspaceRole
from app.repositories.project import ProjectRepository
from app.schemas.project import ProjectCreate, ProjectUpdate
from app.services.base import ScopedService


class ProjectService(ScopedService[ProjectRepository]):
    async def _load(
        self, project_id: int, user: User
    ) -> tuple[Project, WorkspaceRole]:
        project = await self.repository.get(project_id)
        role = (
            await self.get_user_workspace_role(project.workspace_id, user)
            if project
            else None
        )
        if project is None or role is None:
            raise NotFoundError(messages.PROJECT_NOT_FOUND)
        return project, role

    async def create_project(self, data: ProjectCreate, user: User) -> Project:
        role = await self.get_user_workspace_role(data.workspace_id, user)
        if role is None:
            raise NotFoundError(messages.WORKSPACE_NOT_FOUND)
        if not can_write_project(role):
            raise ForbiddenError(messages.FORBIDDEN)
        project = await self.repository.create(**data.model_dump())
        await self.session.commit()
        return project

    async def list_projects(
        self,
        user: User,
        *,
        workspace_id: int | None = None,
        page: int,
        limit: int,
    ) -> tuple[list[Project], int]:
        return await self.repository.list_visible(
            user, workspace_id=workspace_id, page=page, limit=limit
        )

    async def get_project(self, project_id: int, user: User) -> Project:
        project, _ = await self._load(project_id, user)
        return project

    async def update_project(
        self, project_id: int, data: ProjectUpdate, user: User
    ) -> Project:
        project, role = await self._load(project_id, user)
        if not can_write_project(role):
            raise ForbiddenError(messages.FORBIDDEN)
        updated = await self.repository.update(
            project, data.model_dump(exclude_unset=True)
        )
        await self.session.commit()
        return updated

    async def delete_project(self, project_id: int, user: User) -> None:
        project, role = await self._load(project_id, user)
        if not can_delete_project(role):
            raise ForbiddenError(messages.FORBIDDEN)
        await self.repository.delete(project)
        await self.session.commit()
