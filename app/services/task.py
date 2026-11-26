from dataclasses import dataclass

from pydantic import BaseModel, Field, ValidationError

from app.core import messages
from app.core.cache import (
    TASK_LIST_GLOBAL_VERSION_KEY,
    RedisCache,
    TaskListCacheInvalidator,
    task_list_page_key,
    user_version_key,
    workspace_version_key,
)
from app.core.exceptions import BadRequestError, ForbiddenError
from app.core.notifications import TaskAssignedEvent
from app.core.permissions import (
    WRITE_ROLES,
    can_create_task,
    can_delete_task,
    can_modify_task,
)
from app.models import Task, User
from app.models.enums import UserRole
from app.repositories.task import AssigneeInfo, TaskRepository
from app.schemas.pagination import PaginatedResponse, PaginationParams
from app.schemas.task import TaskCreate, TaskResponse, TaskUpdate
from app.services.base import ScopedEntity, ScopedService

TaskPage = PaginatedResponse[TaskResponse]


@dataclass(frozen=True, slots=True)
class TaskWriteResult:
    task: Task
    assigned_event: TaskAssignedEvent | None = None


def _build_assigned_event(
    task: Task,
    workspace_id: int,
    assignee: AssigneeInfo | None,
    actor: User,
) -> TaskAssignedEvent | None:
    if assignee is None or assignee.user_id == actor.id:
        return None
    return TaskAssignedEvent(
        task_id=task.id,
        task_title=task.title,
        project_id=task.project_id,
        workspace_id=workspace_id,
        assignee_id=assignee.user_id,
        assignee_email=assignee.email,
        assignee_name=assignee.full_name,
        assigned_by_id=actor.id,
        assigned_by_name=actor.full_name,
        priority=task.priority.value,
        due_date=task.due_date,
    )


class CachedTaskPage(BaseModel):
    user_version: str
    global_version: str | None = None
    workspace_versions: dict[int, str] = Field(default_factory=dict)
    page: TaskPage


class TaskService(ScopedService[TaskRepository]):
    def __init__(
        self,
        repository: TaskRepository,
        *,
        cache: RedisCache | None = None,
        task_cache_invalidator: TaskListCacheInvalidator | None = None,
    ) -> None:
        super().__init__(repository)
        self.cache = cache
        self.task_cache_invalidator = (
            task_cache_invalidator or TaskListCacheInvalidator(cache)
        )

    async def _load(self, task_id: int, user: User) -> ScopedEntity[Task]:
        return await self.load_with_workspace(
            task_id, user, self.repository.get_with_workspace, messages.TASK_NOT_FOUND
        )

    async def _ensure_assignee(
        self, workspace_id: int, assignee_id: int
    ) -> AssigneeInfo:
        info = await self.repository.get_assignee_info(workspace_id, assignee_id)
        if info is None or info.role is None:
            raise BadRequestError(messages.ASSIGNEE_NOT_IN_WORKSPACE)
        if not info.is_active:
            raise BadRequestError(messages.ASSIGNEE_INACTIVE)
        if info.role not in WRITE_ROLES:
            raise BadRequestError(messages.ASSIGNEE_INVALID_ROLE)
        return info

    async def create_task(self, data: TaskCreate, user: User) -> TaskWriteResult:
        proj_scope = await self.load_project_scope(data.project_id, user)
        if not can_create_task(proj_scope.role):
            raise ForbiddenError(messages.FORBIDDEN)
        self._ensure_project_active(proj_scope.project_status)
        assignee_info: AssigneeInfo | None = None
        if data.assignee_id is not None:
            assignee_info = await self._ensure_assignee(
                proj_scope.workspace_id, data.assignee_id
            )
        task = await self.repository.create(**data.model_dump(), created_by=user.id)
        await self.session.commit()
        await self.task_cache_invalidator.invalidate(
            workspace_ids=[proj_scope.workspace_id]
        )
        return TaskWriteResult(
            task=task,
            assigned_event=_build_assigned_event(
                task, proj_scope.workspace_id, assignee_info, user
            ),
        )

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

    async def _try_get_cached_page(
        self,
        cache: RedisCache,
        *,
        page_key: str,
        primary_ver_key: str,
        is_admin_unfiltered: bool,
    ) -> TaskPage | None:
        initial = await cache.get_many([page_key, primary_ver_key])
        if initial is None:
            return None
        raw_page, current_primary_ver = initial
        if raw_page is None or current_primary_ver is None:
            return None
        try:
            entry = CachedTaskPage.model_validate_json(raw_page)
        except ValidationError:
            return None
        if is_admin_unfiltered:
            return entry.page if entry.global_version == current_primary_ver else None
        if entry.user_version != current_primary_ver:
            return None
        if not entry.workspace_versions:
            return entry.page
        ws_ids = list(entry.workspace_versions.keys())
        current_ws_vers = await cache.get_many(
            [workspace_version_key(ws_id) for ws_id in ws_ids]
        )
        if current_ws_vers is None:
            return None
        if all(
            current_ws_vers[idx] == entry.workspace_versions[ws_id]
            for idx, ws_id in enumerate(ws_ids)
        ):
            return entry.page
        return None

    async def list_task_page(
        self, user: User, *, pagination: PaginationParams, project_id: int | None
    ) -> TaskPage:
        cache = self.cache
        if cache is None:
            return await self._load_task_page(user, pagination, project_id)

        page_key = task_list_page_key(
            user_id=user.id,
            role=user.role.value,
            project_id=project_id,
            page=pagination.page,
            limit=pagination.limit,
        )
        user_ver_key = user_version_key(user.id)
        is_admin_unfiltered = user.role == UserRole.ADMIN and project_id is None
        primary_ver_key = (
            TASK_LIST_GLOBAL_VERSION_KEY if is_admin_unfiltered else user_ver_key
        )

        cached_page = await self._try_get_cached_page(
            cache,
            page_key=page_key,
            primary_ver_key=primary_ver_key,
            is_admin_unfiltered=is_admin_unfiltered,
        )
        if cached_page is not None:
            return cached_page

        ws_ids, cacheable = await self.repository.get_cache_scope_workspace_ids(
            user, project_id
        )
        if not cacheable:
            return await self._load_task_page(user, pagination, project_id)

        ver_keys = (
            [TASK_LIST_GLOBAL_VERSION_KEY]
            if is_admin_unfiltered
            else [user_ver_key, *(workspace_version_key(ws_id) for ws_id in ws_ids)]
        )
        # Snapshot versions before reading DB so concurrent writes cannot be overwritten.
        versions = await cache.ensure_versions(ver_keys)
        page = await self._load_task_page(user, pagination, project_id)
        if versions is not None:
            if is_admin_unfiltered:
                entry = CachedTaskPage(
                    user_version="",
                    global_version=versions[TASK_LIST_GLOBAL_VERSION_KEY],
                    workspace_versions={},
                    page=page,
                )
            else:
                entry = CachedTaskPage(
                    user_version=versions[user_ver_key],
                    global_version=None,
                    workspace_versions={
                        ws_id: versions[workspace_version_key(ws_id)]
                        for ws_id in ws_ids
                    },
                    page=page,
                )
            await cache.set(page_key, entry.model_dump_json())
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

    async def update_task(
        self, task_id: int, data: TaskUpdate, user: User
    ) -> TaskWriteResult:
        scoped = await self._load(task_id, user)
        if not can_modify_task(scoped.role, scoped.entity, user):
            raise ForbiddenError(messages.FORBIDDEN)
        self._ensure_project_active(scoped.project_status)
        previous_assignee_id = scoped.entity.assignee_id
        changes = data.model_dump(exclude_unset=True)
        assignee_info: AssigneeInfo | None = None
        if changes.get("assignee_id") is not None:
            assignee_info = await self._ensure_assignee(
                scoped.workspace_id, changes["assignee_id"]
            )
        updated = await self.repository.update(scoped.entity, changes)
        await self.session.commit()
        await self.task_cache_invalidator.invalidate(
            workspace_ids=[scoped.workspace_id]
        )
        notify_target = (
            assignee_info
            if assignee_info is not None and updated.assignee_id != previous_assignee_id
            else None
        )
        return TaskWriteResult(
            task=updated,
            assigned_event=_build_assigned_event(
                updated, scoped.workspace_id, notify_target, user
            ),
        )

    async def delete_task(self, task_id: int, user: User) -> None:
        scoped = await self._load(task_id, user)
        if not can_delete_task(scoped.role, scoped.entity, user):
            raise ForbiddenError(messages.FORBIDDEN)
        self._ensure_project_active(scoped.project_status)
        workspace_id = scoped.workspace_id
        await self.repository.delete(scoped.entity)
        await self.session.commit()
        await self.task_cache_invalidator.invalidate(workspace_ids=[workspace_id])
