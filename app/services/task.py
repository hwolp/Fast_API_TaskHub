from fastapi import HTTPException

from app.core.permissions import (
    can_create_task,
    can_delete_task,
    can_modify_task,
    effective_role,
)
from app.core.security import forbidden
from app.models import Task, User
from app.models.enums import WorkspaceRole
from app.repositories.task import TaskRepository
from app.schemas.task import TaskCreate, TaskUpdate


class TaskService:
    def __init__(self, repository: TaskRepository) -> None:
        self.repository = repository

    async def _role(self, workspace_id: int, user: User) -> WorkspaceRole | None:
        return effective_role(
            user, await self.repository.workspace_role(workspace_id, user.id)
        )

    async def _load(self, task_id: int, user: User) -> tuple[Task, WorkspaceRole, int]:
        found = await self.repository.get_with_workspace(task_id)
        role = await self._role(found[1], user) if found else None
        if found is None or role is None:
            raise HTTPException(404, "task_not_found")
        return found[0], role, found[1]

    async def _ensure_assignee(self, workspace_id: int, assignee_id: int) -> None:
        if await self.repository.workspace_role(workspace_id, assignee_id) is None:
            raise HTTPException(400, "assignee_not_in_workspace")

    async def create_task(self, data: TaskCreate, user: User) -> Task:
        workspace_id = await self.repository.workspace_id_of_project(data.project_id)
        role = await self._role(workspace_id, user) if workspace_id is not None else None
        if role is None:
            raise HTTPException(404, "project_not_found")
        if not can_create_task(role):
            raise forbidden()
        if data.assignee_id is not None:
            await self._ensure_assignee(workspace_id, data.assignee_id)
        return await self.repository.create(**data.model_dump(), created_by=user.id)

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
            raise forbidden()
        changes = data.model_dump(exclude_unset=True)
        if changes.get("assignee_id") is not None:
            await self._ensure_assignee(workspace_id, changes["assignee_id"])
        return await self.repository.update(task, changes)

    async def delete_task(self, task_id: int, user: User) -> None:
        task, role, _ = await self._load(task_id, user)
        if not can_delete_task(role, task, user):
            raise forbidden()
        await self.repository.delete(task)
