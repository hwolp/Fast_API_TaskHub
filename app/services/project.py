from fastapi import HTTPException

from app.core.permissions import (
    can_delete_project,
    can_write_project,
    effective_role,
)
from app.core.security import forbidden
from app.models import Project, User
from app.models.enums import WorkspaceRole
from app.repositories.project import ProjectRepository
from app.schemas.project import ProjectCreate, ProjectUpdate


class ProjectService:
    def __init__(self, repository: ProjectRepository) -> None:
        self.repository = repository

    async def _role(self, workspace_id: int, user: User) -> WorkspaceRole | None:
        return effective_role(
            user, await self.repository.workspace_role(workspace_id, user.id)
        )

    async def _load(
        self, project_id: int, user: User
    ) -> tuple[Project, WorkspaceRole]:
        project = await self.repository.get(project_id)
        role = await self._role(project.workspace_id, user) if project else None
        if project is None or role is None:
            raise HTTPException(404, "project_not_found")
        return project, role

    async def create_project(self, data: ProjectCreate, user: User) -> Project:
        role = await self._role(data.workspace_id, user)
        if role is None:
            raise HTTPException(404, "workspace_not_found")
        if not can_write_project(role):
            raise forbidden()
        return await self.repository.create(**data.model_dump())

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
            raise forbidden()
        return await self.repository.update(
            project, data.model_dump(exclude_unset=True)
        )

    async def delete_project(self, project_id: int, user: User) -> None:
        project, role = await self._load(project_id, user)
        if not can_delete_project(role):
            raise forbidden()
        await self.repository.delete(project)

