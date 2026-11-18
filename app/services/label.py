from sqlalchemy.exc import IntegrityError

from app.core import messages
from app.core.exceptions import (
    BadRequestError,
    ConflictError,
    ForbiddenError,
    NotFoundError,
)
from app.core.permissions import can_manage_label, can_modify_task
from app.models import Label, Task, User
from app.repositories.label import LabelRepository
from app.schemas.label import LabelCreate, LabelUpdate
from app.schemas.pagination import PaginationParams
from app.services.base import ScopedEntity, ScopedService


class LabelService(ScopedService[LabelRepository]):
    async def _load(self, label_id: int, user: User) -> ScopedEntity[Label]:
        return await self.load_with_workspace(
            label_id, user, self.repository.get_with_workspace, messages.LABEL_NOT_FOUND
        )

    async def _load_task(self, task_id: int, user: User) -> ScopedEntity[Task]:
        return await self.load_with_workspace(
            task_id, user, self.repository.get_task_with_workspace, messages.TASK_NOT_FOUND
        )

    async def create_label(self, data: LabelCreate, user: User) -> Label:
        proj_scope = await self.load_project_scope(data.project_id, user)
        if not can_manage_label(proj_scope.role):
            raise ForbiddenError(messages.FORBIDDEN)
        self._ensure_project_active(proj_scope.project_status)
        try:
            label = await self.repository.create(**data.model_dump())
            await self.session.commit()
            return label
        except IntegrityError:
            await self.session.rollback()
            raise ConflictError(messages.LABEL_NAME_EXISTS)

    async def list_labels(
        self,
        user: User,
        *,
        pagination: PaginationParams | None = None,
        project_id: int | None = None,
        page: int = 1,
        limit: int = 20,
    ) -> tuple[list[Label], int]:
        return await self.repository.list_visible(
            user, project_id=project_id, pagination=pagination, page=page, limit=limit
        )

    async def get_label(self, label_id: int, user: User) -> Label:
        scoped = await self._load(label_id, user)
        return scoped.entity

    async def update_label(
        self, label_id: int, data: LabelUpdate, user: User
    ) -> Label:
        scoped = await self._load(label_id, user)
        if not can_manage_label(scoped.role):
            raise ForbiddenError(messages.FORBIDDEN)
        self._ensure_project_active(scoped.project_status)
        try:
            updated = await self.repository.update(
                scoped.entity, data.model_dump(exclude_unset=True)
            )
            await self.session.commit()
            return updated
        except IntegrityError:
            await self.session.rollback()
            raise ConflictError(messages.LABEL_NAME_EXISTS)

    async def delete_label(self, label_id: int, user: User) -> None:
        scoped = await self._load(label_id, user)
        if not can_manage_label(scoped.role):
            raise ForbiddenError(messages.FORBIDDEN)
        self._ensure_project_active(scoped.project_status)
        await self.repository.delete(scoped.entity)
        await self.session.commit()

    async def attach_label_to_task(
        self, task_id: int, label_id: int, user: User
    ) -> None:
        task_scoped = await self._load_task(task_id, user)
        label_scoped = await self._load(label_id, user)
        if not can_modify_task(task_scoped.role, task_scoped.entity, user):
            raise ForbiddenError(messages.FORBIDDEN)
        self._ensure_project_active(task_scoped.project_status)
        if label_scoped.entity.project_id != task_scoped.entity.project_id:
            raise BadRequestError(messages.LABEL_PROJECT_MISMATCH)
        await self.repository.attach_to_task(task_id, label_id)
        await self.session.commit()

    async def detach_label_from_task(
        self, task_id: int, label_id: int, user: User
    ) -> None:
        task_scoped = await self._load_task(task_id, user)
        label_scoped = await self._load(label_id, user)
        if not can_modify_task(task_scoped.role, task_scoped.entity, user):
            raise ForbiddenError(messages.FORBIDDEN)
        self._ensure_project_active(task_scoped.project_status)
        if label_scoped.entity.project_id != task_scoped.entity.project_id:
            raise BadRequestError(messages.LABEL_PROJECT_MISMATCH)
        detached = await self.repository.detach_from_task(task_id, label_id)
        if not detached:
            raise NotFoundError(messages.LABEL_NOT_ATTACHED)
        await self.session.commit()
