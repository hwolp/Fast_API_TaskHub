from pydantic import ValidationError

from app.core import messages
from app.core.cache import RedisCache
from app.core.exceptions import BadRequestError, ForbiddenError
from app.core.permissions import (
    WRITE_ROLES,
    can_create_task,
    can_delete_task,
    can_modify_task,
)
from app.models import Task, User
from app.repositories.task import TaskRepository
from app.schemas.pagination import PaginatedResponse, PaginationParams
from app.schemas.task import TaskCreate, TaskResponse, TaskUpdate
from app.services.base import ScopedEntity, ScopedService


TaskPage = PaginatedResponse[TaskResponse]


class TaskService(ScopedService[TaskRepository]):
    def __init__(
        self, repository: TaskRepository, *, cache: RedisCache | None = None
    ) -> None:
        super().__init__(repository)
        self.cache = cache

    async def _load(self, task_id: int, user: User) -> ScopedEntity[Task]:
        return await self.load_with_workspace(
            task_id, user, self.repository.get_with_workspace, messages.TASK_NOT_FOUND
        )

    async def _ensure_assignee(self, workspace_id: int, assignee_id: int) -> None:
        info = await self.repository.get_assignee_info(workspace_id, assignee_id)
        if info is None or info[1] is None:
            raise BadRequestError(messages.ASSIGNEE_NOT_IN_WORKSPACE)
        is_active, role = info
        if not is_active:
            raise BadRequestError(messages.ASSIGNEE_INACTIVE)
        if role not in WRITE_ROLES:
            raise BadRequestError(messages.ASSIGNEE_INVALID_ROLE)

    async def create_task(self, data: TaskCreate, user: User) -> Task:
        proj_scope = await self.load_project_scope(data.project_id, user)
        if not can_create_task(proj_scope.role):
            raise ForbiddenError(messages.FORBIDDEN)
        self._ensure_project_active(proj_scope.project_status)
        if data.assignee_id is not None:
            await self._ensure_assignee(proj_scope.workspace_id, data.assignee_id)
        task = await self.repository.create(**data.model_dump(), created_by=user.id)
        await self.commit_task_list_changes()
        return task

    async def list_tasks(
        self,
        user: User,
        *,
        pagination: PaginationParams | None = None,
        project_id: int | None = None,
        page: int = 1,
        limit: int = 20,
    ) -> tuple[list[Task], int]:
        return await self.repository.list_visible(
            user, project_id=project_id, pagination=pagination, page=page, limit=limit
        )

    async def list_task_page(
        self, user: User, *, pagination: PaginationParams, project_id: int | None
    ) -> TaskPage:
        cache = self.cache
        if cache is None:
            return await self._load_task_page(user, pagination, project_id)

        version = await self.repository.list_revision()
        key = (
            f"taskhub:tasks:list:v1:{version}:{user.id}:{user.role.value}:"
            f"{project_id}:{pagination.page}:{pagination.limit}"
        )
        cached = await cache.get(key)
        if cached is not None:
            try:
                return TaskPage.model_validate_json(cached)
            except ValidationError:
                pass

        page = await self._load_task_page(user, pagination, project_id)
        await cache.set(key, page.model_dump_json())
        return page

    async def _load_task_page(
        self, user: User, pagination: PaginationParams, project_id: int | None
    ) -> TaskPage:
        items, total = await self.list_tasks(
            user, pagination=pagination, project_id=project_id
        )
        return TaskPage(
            items=[TaskResponse.model_validate(item) for item in items],
            total=total,
        )

    async def get_task(self, task_id: int, user: User) -> Task:
        scoped = await self._load(task_id, user)
        return scoped.entity

    async def update_task(self, task_id: int, data: TaskUpdate, user: User) -> Task:
        scoped = await self._load(task_id, user)
        if not can_modify_task(scoped.role, scoped.entity, user):
            raise ForbiddenError(messages.FORBIDDEN)
        self._ensure_project_active(scoped.project_status)
        changes = data.model_dump(exclude_unset=True)
        if changes.get("assignee_id") is not None:
            await self._ensure_assignee(scoped.workspace_id, changes["assignee_id"])
        updated = await self.repository.update(scoped.entity, changes)
        await self.commit_task_list_changes()
        return updated

    async def delete_task(self, task_id: int, user: User) -> None:
        scoped = await self._load(task_id, user)
        if not can_delete_task(scoped.role, scoped.entity, user):
            raise ForbiddenError(messages.FORBIDDEN)
        self._ensure_project_active(scoped.project_status)
        await self.repository.delete(scoped.entity)
        await self.commit_task_list_changes()
