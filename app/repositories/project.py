from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.models import Project, User
from app.models.enums import UserRole
from app.repositories.base import BaseRepository


class ProjectRepository(BaseRepository[Project]):
    def __init__(self, session: AsyncSession) -> None:
        super().__init__(Project, session)

    async def list_visible(
        self,
        user: User,
        *,
        workspace_id: int | None = None,
        page: int = 1,
        limit: int = 20,
    ) -> tuple[list[Project], int]:
        stmt = select(Project)
        if user.role != UserRole.ADMIN:
            stmt = stmt.where(
                Project.workspace_id.in_(self.visible_workspace_ids(user.id))
            )
        if workspace_id is not None:
            stmt = stmt.where(Project.workspace_id == workspace_id)
        return await self._paginate(stmt, page=page, limit=limit)

