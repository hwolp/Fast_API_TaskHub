from app.core import messages
from app.core.exceptions import (
    BadRequestError,
    ConflictError,
    ForbiddenError,
    NotFoundError,
)
from app.core.permissions import can_manage_members, can_manage_workspace
from app.models import User, Workspace, WorkspaceMember
from app.models.enums import WorkspaceRole
from app.repositories.workspace import WorkspaceRepository
from app.schemas.workspace import (
    WorkspaceCreate,
    WorkspaceMemberAdd,
    WorkspaceMemberUpdate,
    WorkspaceUpdate,
)
from app.services.base import ScopedService


class WorkspaceService(ScopedService[WorkspaceRepository]):
    async def _load(
        self, workspace_id: int, user: User
    ) -> tuple[Workspace, WorkspaceRole]:
        workspace = await self.repository.get(workspace_id)
        role = (
            await self.get_user_workspace_role(workspace_id, user)
            if workspace
            else None
        )
        if workspace is None or role is None:
            raise NotFoundError(messages.WORKSPACE_NOT_FOUND)
        return workspace, role

    async def create_workspace(self, data: WorkspaceCreate, user: User) -> Workspace:
        workspace = await self.repository.create_with_owner(
            name=data.name, owner_id=user.id
        )
        await self.session.commit()
        return workspace

    async def list_workspaces(
        self, user: User, *, page: int, limit: int
    ) -> tuple[list[Workspace], int]:
        return await self.repository.list_visible(user, page=page, limit=limit)

    async def get_workspace(self, workspace_id: int, user: User) -> Workspace:
        workspace, _ = await self._load(workspace_id, user)
        return workspace

    async def update_workspace(
        self, workspace_id: int, data: WorkspaceUpdate, user: User
    ) -> Workspace:
        workspace, role = await self._load(workspace_id, user)
        if not can_manage_workspace(role):
            raise ForbiddenError(messages.FORBIDDEN)
        updated = await self.repository.update(
            workspace, data.model_dump(exclude_unset=True)
        )
        await self.session.commit()
        return updated

    async def delete_workspace(self, workspace_id: int, user: User) -> None:
        workspace, role = await self._load(workspace_id, user)
        if not can_manage_workspace(role):
            raise ForbiddenError(messages.FORBIDDEN)
        await self.repository.delete(workspace)
        await self.session.commit()

    async def list_members(
        self, workspace_id: int, user: User
    ) -> list[WorkspaceMember]:
        await self._load(workspace_id, user)
        return await self.repository.list_members(workspace_id)

    async def add_member(
        self, workspace_id: int, data: WorkspaceMemberAdd, user: User
    ) -> WorkspaceMember:
        workspace, role = await self._load(workspace_id, user)
        if not can_manage_members(role):
            raise ForbiddenError(messages.FORBIDDEN)
        if data.role == WorkspaceRole.OWNER:
            raise BadRequestError("cannot_assign_owner_role")
        if not await self.repository.user_exists(data.user_id):
            raise NotFoundError(messages.USER_NOT_FOUND)
        if (
            data.user_id == workspace.owner_id
            or await self.repository.get_member(workspace_id, data.user_id) is not None
        ):
            raise ConflictError(messages.MEMBER_ALREADY_EXISTS)
        member = await self.repository.add_member(workspace_id, data.user_id, data.role)
        await self.session.commit()
        return member

    async def update_member_role(
        self,
        workspace_id: int,
        member_user_id: int,
        data: WorkspaceMemberUpdate,
        user: User,
    ) -> WorkspaceMember:
        workspace, role = await self._load(workspace_id, user)
        if not can_manage_members(role):
            raise ForbiddenError(messages.FORBIDDEN)
        if data.role == WorkspaceRole.OWNER:
            raise BadRequestError("cannot_assign_owner_role")
        if member_user_id == workspace.owner_id:
            raise BadRequestError(messages.CANNOT_MODIFY_WORKSPACE_OWNER)
        member = await self.repository.get_member(workspace_id, member_user_id)
        if member is None:
            raise NotFoundError(messages.MEMBER_NOT_FOUND)
        updated = await self.repository.update_member(member, data.role)
        await self.session.commit()
        return updated

    async def remove_member(
        self, workspace_id: int, member_user_id: int, user: User
    ) -> None:
        workspace, role = await self._load(workspace_id, user)
        if not can_manage_members(role) and user.id != member_user_id:
            raise ForbiddenError(messages.FORBIDDEN)
        if member_user_id == workspace.owner_id:
            raise BadRequestError(messages.CANNOT_MODIFY_WORKSPACE_OWNER)
        member = await self.repository.get_member(workspace_id, member_user_id)
        if member is None:
            raise NotFoundError(messages.MEMBER_NOT_FOUND)
        await self.repository.remove_member(member)
        await self.session.commit()
