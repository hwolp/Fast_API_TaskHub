from typing import Annotated

from fastapi import APIRouter, Query

from app.api.v1.params import IdPath
from app.api.v1.responses import (
    BAD_REQUEST_RESPONSE,
    FORBIDDEN_RESPONSE,
    NOT_FOUND_RESPONSE,
)
from app.dependencies import (
    CurrentUser,
    LabelServiceDep,
    TaskServiceDep,
)
from app.schemas.pagination import PaginatedResponse, PaginationDep
from app.schemas.task import TaskCreate, TaskResponse, TaskUpdate

router = APIRouter()


@router.post(
    "/",
    response_model=TaskResponse,
    status_code=201,
    summary="Create a new task in a project",
    responses={**BAD_REQUEST_RESPONSE, **FORBIDDEN_RESPONSE, **NOT_FOUND_RESPONSE},
)
async def create_task(
    data: TaskCreate, user: CurrentUser, service: TaskServiceDep
) -> TaskResponse:
    task = await service.create_task(data, user)
    return TaskResponse.model_validate(task)


@router.get(
    "/",
    response_model=PaginatedResponse[TaskResponse],
    summary="List visible tasks with pagination",
)
async def list_tasks(
    user: CurrentUser,
    service: TaskServiceDep,
    pagination: PaginationDep,
    project_id: Annotated[
        int | None, Query(ge=1, description="Lọc theo ID dự án")
    ] = None,
) -> PaginatedResponse[TaskResponse]:
    return await service.list_task_page(
        user, pagination=pagination, project_id=project_id
    )


@router.get(
    "/{task_id}",
    response_model=TaskResponse,
    summary="Get task details by ID",
    responses=NOT_FOUND_RESPONSE,
)
async def get_task(
    task_id: IdPath, user: CurrentUser, service: TaskServiceDep
) -> TaskResponse:
    task = await service.get_task(task_id, user)
    return TaskResponse.model_validate(task)


@router.patch(
    "/{task_id}",
    response_model=TaskResponse,
    summary="Update task fields or assignee",
    responses={**BAD_REQUEST_RESPONSE, **FORBIDDEN_RESPONSE, **NOT_FOUND_RESPONSE},
)
async def update_task(
    task_id: IdPath, data: TaskUpdate, user: CurrentUser, service: TaskServiceDep
) -> TaskResponse:
    updated = await service.update_task(task_id, data, user)
    return TaskResponse.model_validate(updated)


@router.delete(
    "/{task_id}",
    status_code=204,
    summary="Delete a task by ID",
    responses={**BAD_REQUEST_RESPONSE, **FORBIDDEN_RESPONSE, **NOT_FOUND_RESPONSE},
)
async def delete_task(
    task_id: IdPath, user: CurrentUser, service: TaskServiceDep
) -> None:
    await service.delete_task(task_id, user)


@router.post(
    "/{task_id}/labels/{label_id}",
    status_code=204,
    summary="Attach a label to a task",
    description="Idempotent: attaches a label to the task. Repeated calls are safely ignored.",
    responses={
        **BAD_REQUEST_RESPONSE,
        **FORBIDDEN_RESPONSE,
        **NOT_FOUND_RESPONSE,
    },
)
async def attach_label_to_task(
    task_id: IdPath,
    label_id: IdPath,
    user: CurrentUser,
    service: LabelServiceDep,
) -> None:
    await service.attach_label_to_task(task_id, label_id, user)


@router.delete(
    "/{task_id}/labels/{label_id}",
    status_code=204,
    summary="Detach a label from a task",
    responses={
        **BAD_REQUEST_RESPONSE,
        **FORBIDDEN_RESPONSE,
        **NOT_FOUND_RESPONSE,
    },
)
async def detach_label_from_task(
    task_id: IdPath,
    label_id: IdPath,
    user: CurrentUser,
    service: LabelServiceDep,
) -> None:
    await service.detach_label_from_task(task_id, label_id, user)
