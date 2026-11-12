from app.core import messages
from app.core.exceptions import BadRequestError, ForbiddenError, NotFoundError
from app.core.permissions import (
    can_create_task,
    can_delete_task,
    can_modify_task,
)
from app.models import Task, User
from app.models.enums import WorkspaceRole
from app.repositories.task import TaskRepository
from app.schemas.task import TaskCreate, TaskUpdate
from app.services.base import ScopedService


class TaskService(ScopedService[TaskRepository]):
    async def _load(self, task_id: int, user: User) -> tuple[Task, WorkspaceRole, int]:
        return await self.load_with_workspace(
            task_id, user, self.repository.get_with_workspace, messages.TASK_NOT_FOUND
        )

    async def _ensure_assignee(self, workspace_id: int, assignee_id: int) -> None:
        if await self.repository.workspace_role(workspace_id, assignee_id) is None:
            raise BadRequestError(messages.ASSIGNEE_NOT_IN_WORKSPACE)

    async def create_task(self, data: TaskCreate, user: User) -> Task:
        workspace_id = await self.repository.workspace_id_of_project(data.project_id)
        role = (
            await self.get_user_workspace_role(workspace_id, user)
            if workspace_id is not None
            else None
        )
        if role is None:
            raise NotFoundError(messages.PROJECT_NOT_FOUND)
        if not can_create_task(role):
            raise ForbiddenError(messages.FORBIDDEN)
        if data.assignee_id is not None:
            await self._ensure_assignee(workspace_id, data.assignee_id)
        task = await self.repository.create(**data.model_dump(), created_by=user.id)
        await self.session.commit()
        return task

    async def list_tasks(
        self,
        user: User,
        *,
        project_id: int | None = None,
        page: int,
        limit: int,
    ) -> tuple[list[Task], int]:
        return await self.repository.list_visible(
            user, project_id=project_id, page=page, limit=limit
        )

    async def get_task(self, task_id: int, user: User) -> Task:
        task, _, _ = await self._load(task_id, user)
        return task

    async def update_task(self, task_id: int, data: TaskUpdate, user: User) -> Task:
        task, role, workspace_id = await self._load(task_id, user)
        if not can_modify_task(role, task, user):
            raise ForbiddenError(messages.FORBIDDEN)
        changes = data.model_dump(exclude_unset=True)
        if changes.get("assignee_id") is not None:
            await self._ensure_assignee(workspace_id, changes["assignee_id"])
        updated = await self.repository.update(task, changes)
        await self.session.commit()
        return updated

    async def delete_task(self, task_id: int, user: User) -> None:
        task, role, _ = await self._load(task_id, user)
        if not can_delete_task(role, task, user):
            raise ForbiddenError(messages.FORBIDDEN)
        await self.repository.delete(task)
        await self.session.commit()
