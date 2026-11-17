from typing import Annotated

from fastapi import APIRouter, Depends, Query

from app.dependencies import CurrentUser, get_label_service, get_task_service
from app.schemas.pagination import PaginatedResponse, PaginationDep
from app.schemas.task import TaskCreate, TaskResponse, TaskUpdate
from app.services.label import LabelService
from app.services.task import TaskService

router = APIRouter()
TaskServiceDep = Annotated[TaskService, Depends(get_task_service)]
LabelServiceDep = Annotated[LabelService, Depends(get_label_service)]

BAD_REQUEST_RESPONSE = {
    400: {"description": "Invalid assignee or archived project"}
}
FORBIDDEN_RESPONSE = {403: {"description": "Forbidden"}}
NOT_FOUND_RESPONSE = {404: {"description": "Task or project not found"}}


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
    return await service.create_task(data, user)


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
    items, total = await service.list_tasks(
        user,
        project_id=project_id,
        page=pagination.page,
        limit=pagination.limit,
    )
    return PaginatedResponse(items=items, total=total)


@router.get(
    "/{task_id}",
    response_model=TaskResponse,
    summary="Get task details by ID",
    responses=NOT_FOUND_RESPONSE,
)
async def get_task(
    task_id: int, user: CurrentUser, service: TaskServiceDep
) -> TaskResponse:
    return await service.get_task(task_id, user)


@router.patch(
    "/{task_id}",
    response_model=TaskResponse,
    summary="Update task fields or assignee",
    responses={**BAD_REQUEST_RESPONSE, **FORBIDDEN_RESPONSE, **NOT_FOUND_RESPONSE},
)
async def update_task(
    task_id: int, data: TaskUpdate, user: CurrentUser, service: TaskServiceDep
) -> TaskResponse:
    return await service.update_task(task_id, data, user)


@router.delete(
    "/{task_id}",
    status_code=204,
    summary="Delete a task by ID",
    responses={**BAD_REQUEST_RESPONSE, **FORBIDDEN_RESPONSE, **NOT_FOUND_RESPONSE},
)
async def delete_task(
    task_id: int, user: CurrentUser, service: TaskServiceDep
) -> None:
    await service.delete_task(task_id, user)


@router.post(
    "/{task_id}/labels/{label_id}",
    status_code=204,
    summary="Attach a label to a task",
    responses={
        400: {"description": "Label project mismatch or archived project"},
        **FORBIDDEN_RESPONSE,
        404: {"description": "Task or label not found"},
    },
)
async def attach_label_to_task(
    task_id: int,
    label_id: int,
    user: CurrentUser,
    service: LabelServiceDep,
) -> None:
    await service.attach_label_to_task(task_id, label_id, user)


@router.delete(
    "/{task_id}/labels/{label_id}",
    status_code=204,
    summary="Detach a label from a task",
    responses={
        400: {"description": "Label project mismatch or archived project"},
        **FORBIDDEN_RESPONSE,
        404: {"description": "Task or label not found"},
    },
)
async def detach_label_from_task(
    task_id: int,
    label_id: int,
    user: CurrentUser,
    service: LabelServiceDep,
) -> None:
    await service.detach_label_from_task(task_id, label_id, user)
