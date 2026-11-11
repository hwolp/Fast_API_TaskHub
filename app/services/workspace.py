from fastapi import HTTPException

from app.core.permissions import (
    can_manage_members,
    can_manage_workspace,
    effective_role,
)
from app.core.security import forbidden
from app.models import User, Workspace, WorkspaceMember
from app.models.enums import WorkspaceRole
from app.repositories.workspace import WorkspaceRepository
from app.schemas.workspace import (
    WorkspaceCreate,
    WorkspaceMemberAdd,
    WorkspaceMemberUpdate,
    WorkspaceUpdate,
)


class WorkspaceService:
    def __init__(self, repository: WorkspaceRepository) -> None:
        self.repository = repository

    async def _role(self, workspace_id: int, user: User) -> WorkspaceRole | None:
        return effective_role(
            user, await self.repository.workspace_role(workspace_id, user.id)
        )

    async def _load(
        self, workspace_id: int, user: User
    ) -> tuple[Workspace, WorkspaceRole]:
        workspace = await self.repository.get(workspace_id)
        role = await self._role(workspace_id, user) if workspace else None
        if workspace is None or role is None:
            raise HTTPException(404, "workspace_not_found")
        return workspace, role

    async def create_workspace(self, data: WorkspaceCreate, user: User) -> Workspace:
        return await self.repository.create_with_owner(
            name=data.name, owner_id=user.id
        )

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
            raise forbidden()
        return await self.repository.update(
            workspace, data.model_dump(exclude_unset=True)
        )

    async def delete_workspace(self, workspace_id: int, user: User) -> None:
        workspace, role = await self._load(workspace_id, user)
        if not can_manage_workspace(role):
            raise forbidden()
        await self.repository.delete(workspace)

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
            raise forbidden()
        if not await self.repository.user_exists(data.user_id):
            raise HTTPException(404, "user_not_found")
        if (
            data.user_id == workspace.owner_id
            or await self.repository.get_member(workspace_id, data.user_id) is not None
        ):
            raise HTTPException(409, "member_already_exists")
        return await self.repository.add_member(workspace_id, data.user_id, data.role)

    async def update_member_role(
        self,
        workspace_id: int,
        member_user_id: int,
        data: WorkspaceMemberUpdate,
        user: User,
    ) -> WorkspaceMember:
        workspace, role = await self._load(workspace_id, user)
        if not can_manage_members(role):
            raise forbidden()
        if member_user_id == workspace.owner_id:
            raise HTTPException(400, "cannot_modify_workspace_owner")
        member = await self.repository.get_member(workspace_id, member_user_id)
        if member is None:
            raise HTTPException(404, "member_not_found")
        return await self.repository.update_member(member, data.role)

    async def remove_member(
        self, workspace_id: int, member_user_id: int, user: User
    ) -> None:
        workspace, role = await self._load(workspace_id, user)
        if not can_manage_members(role) and user.id != member_user_id:
            raise forbidden()
        if member_user_id == workspace.owner_id:
            raise HTTPException(400, "cannot_modify_workspace_owner")
        member = await self.repository.get_member(workspace_id, member_user_id)
        if member is None:
            raise HTTPException(404, "member_not_found")
        await self.repository.remove_member(member)

