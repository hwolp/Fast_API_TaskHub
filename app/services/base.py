from typing import Any, Generic, TypeVar

from app.core.exceptions import NotFoundError
from app.core.permissions import effective_role
from app.models import User
from app.models.enums import WorkspaceRole
from app.repositories.base import BaseRepository

RepoT = TypeVar("RepoT", bound=BaseRepository)


class ScopedService(Generic[RepoT]):
    def __init__(self, repository: RepoT) -> None:
        self.repository = repository
        self.session = repository.session

    async def get_user_workspace_role(
        self, workspace_id: int, user: User
    ) -> WorkspaceRole | None:
        raw_role = await self.repository.workspace_role(workspace_id, user.id)
        return effective_role(user, raw_role)

    async def load_with_workspace(
        self,
        entity_id: int,
        user: User,
        loader,
        not_found_message: str,
    ) -> tuple[Any, WorkspaceRole, int]:
        found = await loader(entity_id)
        role = (
            await self.get_user_workspace_role(found[1], user) if found else None
        )
        if found is None or role is None:
            raise NotFoundError(not_found_message)
        return found[0], role, found[1]

