from typing import Any, Callable, Generic, NamedTuple, TypeVar

from app.core import messages
from app.core.exceptions import BadRequestError, NotFoundError
from app.core.permissions import effective_role
from app.models import User
from app.models.enums import ProjectStatus, WorkspaceRole
from app.repositories.base import BaseRepository
from app.repositories.task import bump_task_list_revision

RepoT = TypeVar("RepoT", bound=BaseRepository)
EntityT = TypeVar("EntityT")


class ScopedEntity(NamedTuple, Generic[EntityT]):
    entity: EntityT
    role: WorkspaceRole
    workspace_id: int
    project_status: ProjectStatus


class ProjectScope(NamedTuple):
    workspace_id: int
    role: WorkspaceRole
    project_status: ProjectStatus


class ScopedService(Generic[RepoT]):
    def __init__(self, repository: RepoT) -> None:
        self.repository = repository
        self.session = repository.session

    async def commit_task_list_changes(self) -> None:
        # Change the cache namespace atomically with the data and permission changes.
        await bump_task_list_revision(self.session)
        await self.session.commit()

    def _ensure_project_active(self, status: ProjectStatus) -> None:
        if status == ProjectStatus.ARCHIVED:
            raise BadRequestError(messages.PROJECT_ARCHIVED)

    async def get_user_workspace_role(
        self, workspace_id: int, user: User
    ) -> WorkspaceRole | None:
        raw_role = await self.repository.workspace_role(workspace_id, user.id)
        return effective_role(user, raw_role)

    async def load_project_scope(
        self, project_id: int, user: User
    ) -> ProjectScope:
        proj_info = await self.repository.workspace_id_of_project(project_id)
        role = (
            await self.get_user_workspace_role(proj_info[0], user)
            if proj_info is not None
            else None
        )
        if proj_info is None or role is None:
            raise NotFoundError(messages.PROJECT_NOT_FOUND)
        return ProjectScope(
            workspace_id=proj_info[0],
            role=role,
            project_status=proj_info[1],
        )

    async def load_with_workspace(
        self,
        entity_id: int,
        user: User,
        loader: Callable[[int], Any],
        not_found_message: str,
    ) -> ScopedEntity:
        found = await loader(entity_id)
        role = (
            await self.get_user_workspace_role(found[1], user) if found else None
        )
        if found is None or role is None:
            raise NotFoundError(not_found_message)
        return ScopedEntity(
            entity=found[0],
            role=role,
            workspace_id=found[1],
            project_status=found[2],
        )
