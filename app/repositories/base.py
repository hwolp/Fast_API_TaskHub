from typing import Any, Generic, TypeVar

from sqlalchemy import Select, func, inspect, or_, select
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.database import Base
from app.models.enums import WorkspaceRole
from app.models.workspace import Workspace, WorkspaceMember

ModelT = TypeVar("ModelT", bound=Base)


class BaseRepository(Generic[ModelT]):
    def __init__(self, model: type[ModelT], session: AsyncSession) -> None:
        self.model = model
        self.session = session

    async def get(self, obj_id: int) -> ModelT | None:
        return await self.session.get(self.model, obj_id)

    async def _paginate(
        self, stmt: Select[tuple[ModelT]], *, page: int = 1, limit: int = 20
    ) -> tuple[list[ModelT], int]:
        total = await self.session.scalar(select(func.count()).select_from(stmt.subquery()))
        ordered = (
            stmt.order_by(*inspect(self.model).primary_key)
            .offset((page - 1) * limit)
            .limit(limit)
        )
        result = await self.session.scalars(ordered)
        return list(result.all()), total or 0

    async def get_multi(
        self, *, page: int = 1, limit: int = 20
    ) -> tuple[list[ModelT], int]:
        return await self._paginate(select(self.model), page=page, limit=limit)

    async def create(self, **data: Any) -> ModelT:
        obj = self.model(**data)
        self.session.add(obj)
        await self.session.flush()
        await self.session.refresh(obj)
        return obj

    async def update(self, obj: ModelT, data: dict[str, Any]) -> ModelT:
        for field, value in data.items():
            setattr(obj, field, value)
        await self.session.flush()
        await self.session.refresh(obj)
        return obj

    async def delete(self, obj: ModelT) -> None:
        await self.session.delete(obj)
        await self.session.flush()

    async def workspace_role(self, workspace_id: int, user_id: int) -> WorkspaceRole | None:
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

    def visible_workspace_ids(self, user_id: int) -> Select[tuple[int]]:
        member_of = select(WorkspaceMember.workspace_id).where(
            WorkspaceMember.user_id == user_id
        )
        return select(Workspace.id).where(
            or_(Workspace.owner_id == user_id, Workspace.id.in_(member_of))
        )

    async def workspace_id_of_project(self, project_id: int) -> int | None:
        from app.models.project import Project
        return await self.session.scalar(
            select(Project.workspace_id).where(Project.id == project_id)
        )

    async def get_task_with_workspace(self, task_id: int) -> tuple[Any, int] | None:
        from app.models.project import Project
        from app.models.task import Task
        row = (
            await self.session.execute(
                select(Task, Project.workspace_id)
                .join(Project, Task.project_id == Project.id)
                .where(Task.id == task_id)
            )
        ).first()
        return (row[0], row[1]) if row else None
