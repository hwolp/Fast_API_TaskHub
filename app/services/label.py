from fastapi import HTTPException

from app.core.permissions import (
    can_manage_label,
    can_modify_task,
    effective_role,
)
from app.core.security import forbidden
from app.models import Label, Task, User
from app.models.enums import WorkspaceRole
from app.repositories.label import LabelRepository
from app.schemas.label import LabelCreate, LabelUpdate


class LabelService:
    def __init__(self, repository: LabelRepository) -> None:
        self.repository = repository

    async def _role(self, workspace_id: int, user: User) -> WorkspaceRole | None:
        return effective_role(
            user, await self.repository.workspace_role(workspace_id, user.id)
        )

    async def _load(self, label_id: int, user: User) -> tuple[Label, WorkspaceRole]:
        found = await self.repository.get_with_workspace(label_id)
        role = await self._role(found[1], user) if found else None
        if found is None or role is None:
            raise HTTPException(404, "label_not_found")
        return found[0], role

    async def _load_task(self, task_id: int, user: User) -> tuple[Task, WorkspaceRole]:
        found = await self.repository.get_task_with_workspace(task_id)
        role = await self._role(found[1], user) if found else None
        if found is None or role is None:
            raise HTTPException(404, "task_not_found")
        return found[0], role

    async def create_label(self, data: LabelCreate, user: User) -> Label:
        workspace_id = await self.repository.workspace_id_of_project(data.project_id)
        role = await self._role(workspace_id, user) if workspace_id is not None else None
        if role is None:
            raise HTTPException(404, "project_not_found")
        if not can_manage_label(role):
            raise forbidden()
        return await self.repository.create(**data.model_dump())

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
            raise forbidden()
        return await self.repository.update(
            label, data.model_dump(exclude_unset=True)
        )

    async def delete_label(self, label_id: int, user: User) -> None:
        label, role = await self._load(label_id, user)
        if not can_manage_label(role):
            raise forbidden()
        await self.repository.delete(label)

    async def attach_label_to_task(
        self, task_id: int, label_id: int, user: User
    ) -> None:
        task, role = await self._load_task(task_id, user)
        label, _ = await self._load(label_id, user)
        if not can_modify_task(role, task, user):
            raise forbidden()
        if label.project_id != task.project_id:
            raise HTTPException(400, "label_project_mismatch")
        await self.repository.attach_to_task(task_id, label_id)

    async def detach_label_from_task(
        self, task_id: int, label_id: int, user: User
    ) -> None:
        task, role = await self._load_task(task_id, user)
        await self._load(label_id, user)
        if not can_modify_task(role, task, user):
            raise forbidden()
        await self.repository.detach_from_task(task_id, label_id)

