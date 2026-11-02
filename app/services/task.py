from typing import Annotated, Any
from fastapi import Depends, HTTPException, status
from app.repositories.task import TaskRepository, get_task_repository
from app.schemas.task import TaskCreate, TaskUpdate


class TaskService:
    def __init__(self, repository: TaskRepository) -> None:
        self.repository = repository

    def create_task(self, data: TaskCreate) -> dict[str, Any]:
        task_dict = data.model_dump()
        return self.repository.create(task_dict)

    def list_tasks(self) -> list[dict[str, Any]]:
        return self.repository.get_all()

    def get_task(self, task_id: int) -> dict[str, Any]:
        task = self.repository.get_by_id(task_id)
        if not task:
            raise HTTPException(
                status_code=status.HTTP_404_NOT_FOUND,
                detail=f"Task with ID {task_id} not found",
            )
        return task

    def update_task(self, task_id: int, data: TaskUpdate) -> dict[str, Any]:
        update_data = data.model_dump(exclude_unset=True)
        updated = self.repository.update(task_id, update_data)
        if not updated:
            raise HTTPException(
                status_code=status.HTTP_404_NOT_FOUND,
                detail=f"Task with ID {task_id} not found",
            )
        return updated

    def delete_task(self, task_id: int) -> None:
        deleted = self.repository.delete(task_id)
        if not deleted:
            raise HTTPException(
                status_code=status.HTTP_404_NOT_FOUND,
                detail=f"Task with ID {task_id} not found",
            )


def get_task_service(
    repository: Annotated[TaskRepository, Depends(get_task_repository)]
) -> TaskService:
    return TaskService(repository=repository)

