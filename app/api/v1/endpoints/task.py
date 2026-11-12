from typing import Annotated

from fastapi import APIRouter, Depends, Query

from app.dependencies import CurrentUser, get_task_service
from app.schemas.pagination import PaginatedResponse
from app.schemas.task import TaskCreate, TaskResponse, TaskUpdate
from app.services.task import TaskService

router = APIRouter()
TaskServiceDep = Annotated[TaskService, Depends(get_task_service)]


@router.post("/", response_model=TaskResponse, status_code=201)
async def create_task(data: TaskCreate, user: CurrentUser, service: TaskServiceDep):
    return await service.create_task(data, user)


@router.get("/", response_model=PaginatedResponse[TaskResponse])
async def list_tasks(
    user: CurrentUser,
    service: TaskServiceDep,
    page: Annotated[int, Query(ge=1)] = 1,
    limit: Annotated[int, Query(ge=1, le=100)] = 20,
):
    items, total = await service.list_tasks(user, page=page, limit=limit)
    return PaginatedResponse(items=items, total=total)


@router.get("/{task_id}", response_model=TaskResponse)
async def get_task(task_id: int, user: CurrentUser, service: TaskServiceDep):
    return await service.get_task(task_id, user)


@router.patch("/{task_id}", response_model=TaskResponse)
async def update_task(
    task_id: int, data: TaskUpdate, user: CurrentUser, service: TaskServiceDep
):
    return await service.update_task(task_id, data, user)


@router.delete("/{task_id}", status_code=204)
async def delete_task(task_id: int, user: CurrentUser, service: TaskServiceDep):
    await service.delete_task(task_id, user)
