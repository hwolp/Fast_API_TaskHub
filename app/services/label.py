from app.core import messages
from app.core.exceptions import (
    BadRequestError,
    ForbiddenError,
    NotFoundError,
)
from app.core.permissions import can_manage_label, can_modify_task
from app.models import Label, Task, User
from app.models.enums import WorkspaceRole
from app.repositories.label import LabelRepository
from app.schemas.label import LabelCreate, LabelUpdate
from app.services.base import ScopedService


class LabelService(ScopedService[LabelRepository]):
    async def _load(self, label_id: int, user: User) -> tuple[Label, WorkspaceRole]:
        return await self.load_with_workspace(
            label_id, user, self.repository.get_with_workspace, messages.LABEL_NOT_FOUND
        )

    async def _load_task(self, task_id: int, user: User) -> tuple[Task, WorkspaceRole]:
        return await self.load_with_workspace(
            task_id, user, self.repository.get_task_with_workspace, messages.TASK_NOT_FOUND
        )

    async def create_label(self, data: LabelCreate, user: User) -> Label:
        workspace_id = await self.repository.workspace_id_of_project(data.project_id)
        role = (
            await self.get_user_workspace_role(workspace_id, user)
            if workspace_id is not None
            else None
        )
        if role is None:
            raise NotFoundError(messages.PROJECT_NOT_FOUND)
        if not can_manage_label(role):
            raise ForbiddenError(messages.FORBIDDEN)
        label = await self.repository.create(**data.model_dump())
        await self.session.commit()
        return label

    async def list_labels(
        self,
        user: User,
        *,
        project_id: int | None = None,
        page: int,
        limit: int,
    ) -> tuple[list[Label], int]:
        return await self.repository.list_visible(
            user, project_id=project_id, page=page, limit=limit
        )

    async def get_label(self, label_id: int, user: User) -> Label:
        label, _ = await self._load(label_id, user)
        return label

    async def update_label(
        self, label_id: int, data: LabelUpdate, user: User
    ) -> Label:
        label, role = await self._load(label_id, user)
        if not can_manage_label(role):
            raise ForbiddenError(messages.FORBIDDEN)
        updated = await self.repository.update(
            label, data.model_dump(exclude_unset=True)
        )
        await self.session.commit()
        return updated

    async def delete_label(self, label_id: int, user: User) -> None:
        label, role = await self._load(label_id, user)
        if not can_manage_label(role):
            raise ForbiddenError(messages.FORBIDDEN)
        await self.repository.delete(label)
        await self.session.commit()

    async def attach_label_to_task(
        self, task_id: int, label_id: int, user: User
    ) -> None:
        task, role = await self._load_task(task_id, user)
        label, _ = await self._load(label_id, user)
        if not can_modify_task(role, task, user):
            raise ForbiddenError(messages.FORBIDDEN)
        if label.project_id != task.project_id:
            raise BadRequestError(messages.LABEL_PROJECT_MISMATCH)
        await self.repository.attach_to_task(task_id, label_id)
        await self.session.commit()

    async def detach_label_from_task(
        self, task_id: int, label_id: int, user: User
    ) -> None:
        task, role = await self._load_task(task_id, user)
        await self._load(label_id, user)
        if not can_modify_task(role, task, user):
            raise ForbiddenError(messages.FORBIDDEN)
        await self.repository.detach_from_task(task_id, label_id)
        await self.session.commit()
