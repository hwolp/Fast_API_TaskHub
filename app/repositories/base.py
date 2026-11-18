from typing import Any, Generic, TypeVar

from sqlalchemy import Select, func, inspect, or_, select
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy.orm import selectinload

from app.core.database import Base
from app.models.enums import ProjectStatus, WorkspaceRole
from app.models.project import Project
from app.models.task import Task
from app.models.workspace import Workspace, WorkspaceMember
from app.schemas.pagination import PaginationParams

ModelT = TypeVar("ModelT", bound=Base)


class BaseRepository(Generic[ModelT]):
    def __init__(self, model: type[ModelT], session: AsyncSession) -> None:
        self.model = model
        self.session = session

    async def get(self, obj_id: int) -> ModelT | None:
        return await self.session.get(self.model, obj_id)

    async def _paginate(
        self,
        stmt: Select[tuple[ModelT]],
        *,
        pagination: PaginationParams | None = None,
        page: int = 1,
        limit: int = 20,
    ) -> tuple[list[ModelT], int]:
        p = pagination.page if pagination is not None else page
        l = pagination.limit if pagination is not None else limit
        total = await self.session.scalar(
            select(func.count()).select_from(stmt.subquery())
        )
        ordered = (
            stmt.order_by(*inspect(self.model).primary_key)
            .offset((p - 1) * l)
            .limit(l)
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

    async def workspace_role(
        self, workspace_id: int, user_id: int
    ) -> WorkspaceRole | None:
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

    async def workspace_id_of_project(
        self, project_id: int
    ) -> tuple[int, ProjectStatus] | None:
        row = (
            await self.session.execute(
                select(Project.workspace_id, Project.status).where(
                    Project.id == project_id
                )
            )
        ).first()
        return (row[0], row[1]) if row else None

    async def get_task_with_workspace(
        self, task_id: int
    ) -> tuple[Task, int, ProjectStatus] | None:
        row = (
            await self.session.execute(
                select(Task, Project.workspace_id, Project.status)
                .options(selectinload(Task.labels))
                .join(Project, Task.project_id == Project.id)
                .where(Task.id == task_id)
            )
        ).first()
        return (row[0], row[1], row[2]) if row else None
