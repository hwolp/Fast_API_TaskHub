from fastapi import APIRouter, Depends
from typing import Annotated, Any
from app.services.task import TaskService, get_task_service
from app.schemas.task import TaskResponse, TaskCreate, TaskUpdate

router = APIRouter()

TaskServiceDep = Annotated[TaskService, Depends(get_task_service)]


@router.post("/", response_model=TaskResponse, status_code=201)
def create_task(data: TaskCreate, service: TaskServiceDep) -> dict[str, Any]:
    return service.create_task(data)


@router.get("/", response_model=list[TaskResponse])
def list_tasks(service: TaskServiceDep) -> list[dict[str, Any]]:
    return service.list_tasks()


@router.get("/{task_id}", response_model=TaskResponse)
def get_task(task_id: int, service: TaskServiceDep) -> dict[str, Any]:
    return service.get_task(task_id)


@router.patch("/{task_id}", response_model=TaskResponse)
def update_task(
    task_id: int, data: TaskUpdate, service: TaskServiceDep
) -> dict[str, Any]:
    return service.update_task(task_id, data)


@router.delete("/{task_id}", status_code=204)
def delete_task(task_id: int, service: TaskServiceDep) -> None:
    service.delete_task(task_id)

