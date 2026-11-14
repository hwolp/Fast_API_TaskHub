from fastapi import HTTPException
from sqlalchemy import select
from sqlalchemy.exc import IntegrityError
from sqlalchemy.ext.asyncio import AsyncSession

from app.models import User, Workspace, WorkspaceMember
from app.models.enums import UserRole, WorkspaceRole
from app.repositories.base import BaseRepository


class WorkspaceRepository(BaseRepository[Workspace]):
    def __init__(self, session: AsyncSession) -> None:
        super().__init__(Workspace, session)

    async def create_with_owner(self, *, name: str, owner_id: int) -> Workspace:
        workspace = Workspace(name=name, owner_id=owner_id)
        self.session.add(workspace)
        await self.session.flush()
        self.session.add(
            WorkspaceMember(
                workspace_id=workspace.id,
                user_id=owner_id,
                role=WorkspaceRole.OWNER,
            )
        )
        await self.session.flush()
        await self.session.refresh(workspace)
        return workspace

    async def list_visible(
        self, user: User, *, page: int = 1, limit: int = 20
    ) -> tuple[list[Workspace], int]:
        stmt = select(Workspace)
        if user.role != UserRole.ADMIN:
            stmt = stmt.where(Workspace.id.in_(self.visible_workspace_ids(user.id)))
        return await self._paginate(stmt, page=page, limit=limit)

    async def user_exists(self, user_id: int) -> bool:
        return (await self.session.get(User, user_id)) is not None

    async def list_members(self, workspace_id: int) -> list[WorkspaceMember]:
        result = await self.session.scalars(
            select(WorkspaceMember)
            .where(WorkspaceMember.workspace_id == workspace_id)
            .order_by(WorkspaceMember.user_id)
        )
        return list(result.all())

    async def get_member(
        self, workspace_id: int, user_id: int
    ) -> WorkspaceMember | None:
        return await self.session.get(WorkspaceMember, (workspace_id, user_id))

    async def add_member(
        self, workspace_id: int, user_id: int, role: WorkspaceRole
    ) -> WorkspaceMember:
        member = WorkspaceMember(workspace_id=workspace_id, user_id=user_id, role=role)
        self.session.add(member)
        try:
            await self.session.flush()
        except IntegrityError:
            await self.session.rollback()
            raise HTTPException(409, "member_already_exists") from None
        await self.session.refresh(member)
        return member

    async def update_member(
        self, member: WorkspaceMember, role: WorkspaceRole
    ) -> WorkspaceMember:
        member.role = role
        await self.session.flush()
        await self.session.refresh(member)
        return member

    async def unassign_workspace_member_tasks(
        self, workspace_id: int, user_id: int
    ) -> None:
        from sqlalchemy import update

        from app.models.project import Project
        from app.models.task import Task

        project_ids = (
            select(Project.id).where(Project.workspace_id == workspace_id).scalar_subquery()
        )
        stmt = (
            update(Task)
            .where(
                Task.project_id.in_(project_ids),
                Task.assignee_id == user_id,
            )
            .values(assignee_id=None)
        )
        await self.session.execute(stmt)
        await self.session.flush()

    async def remove_member(self, member: WorkspaceMember) -> None:
        await self.session.delete(member)
        await self.session.flush()
