from app.core import messages
from app.core.exceptions import NotFoundError
from app.models import Task
from app.repositories.task import TaskRepository
from app.schemas.task import TaskCreate, TaskUpdate


class TaskService:
    def __init__(self, repository: TaskRepository) -> None:
        self.repository = repository
        self.session = repository.session

    async def _get_or_404(self, task_id: int) -> Task:
        task = await self.repository.get(task_id)
        if task is None:
            raise NotFoundError(messages.TASK_NOT_FOUND)
        return task

    async def create_task(self, data: TaskCreate) -> Task:
        task = await self.repository.create(**data.model_dump())
        await self.session.commit()
        return task

    async def list_tasks(
        self, *, page: int = 1, limit: int = 20
    ) -> tuple[list[Task], int]:
        return await self.repository.get_multi(page=page, limit=limit)

    async def get_task(self, task_id: int) -> Task:
        return await self._get_or_404(task_id)

    async def update_task(self, task_id: int, data: TaskUpdate) -> Task:
        task = await self._get_or_404(task_id)
        updated = await self.repository.update(
            task, data.model_dump(exclude_unset=True)
        )
        await self.session.commit()
        return updated

    async def delete_task(self, task_id: int) -> None:
        task = await self._get_or_404(task_id)
        await self.repository.delete(task)
        await self.session.commit()
