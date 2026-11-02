from datetime import datetime
from typing import Any


class TaskRepository:
    def __init__(self) -> None:
        self._tasks: dict[int, dict[str, Any]] = {}
        self._id_counter = 1

    def create(self, data: dict[str, Any]) -> dict[str, Any]:
        task_id = self._id_counter
        self._id_counter += 1
        now = datetime.now()
        task = {
            "id": task_id,
            **data,
            "created_at": data.get("created_at") or now,
        }
        self._tasks[task_id] = task
        return task

    def get_all(self) -> list[dict[str, Any]]:
        return list(self._tasks.values())

    def get_by_id(self, task_id: int) -> dict[str, Any] | None:
        return self._tasks.get(task_id)

    def update(self, task_id: int, data: dict[str, Any]) -> dict[str, Any] | None:
        task = self._tasks.get(task_id)
        if not task:
            return None
        task.update(data)
        self._tasks[task_id] = task
        return task

    def delete(self, task_id: int) -> bool:
        if task_id in self._tasks:
            del self._tasks[task_id]
            return True
        return False


_task_repository = TaskRepository()


def get_task_repository() -> TaskRepository:
    return _task_repository
