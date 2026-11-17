from typing import Annotated

from fastapi import APIRouter, Depends, Query

from app.dependencies import CurrentUser, get_project_service
from app.schemas.pagination import PaginatedResponse, PaginationDep
from app.schemas.project import ProjectCreate, ProjectResponse, ProjectUpdate
from app.services.project import ProjectService

router = APIRouter()
ProjectServiceDep = Annotated[ProjectService, Depends(get_project_service)]

FORBIDDEN_RESPONSE = {403: {"description": "Forbidden"}}
NOT_FOUND_RESPONSE = {404: {"description": "Project or workspace not found"}}


@router.post(
    "/",
    response_model=ProjectResponse,
    status_code=201,
    summary="Create a new project in a workspace",
    responses={**FORBIDDEN_RESPONSE, **NOT_FOUND_RESPONSE},
)
async def create_project(
    data: ProjectCreate, user: CurrentUser, service: ProjectServiceDep
) -> ProjectResponse:
    return await service.create_project(data, user)


@router.get(
    "/",
    response_model=PaginatedResponse[ProjectResponse],
    summary="List visible projects with pagination",
)
async def list_projects(
    user: CurrentUser,
    service: ProjectServiceDep,
    pagination: PaginationDep,
    workspace_id: Annotated[int | None, Query(ge=1)] = None,
) -> PaginatedResponse[ProjectResponse]:
    items, total = await service.list_projects(
        user,
        workspace_id=workspace_id,
        page=pagination.page,
        limit=pagination.limit,
    )
    return PaginatedResponse(items=items, total=total)


@router.get(
    "/{project_id}",
    response_model=ProjectResponse,
    summary="Get project details by ID",
    responses=NOT_FOUND_RESPONSE,
)
async def get_project(
    project_id: int, user: CurrentUser, service: ProjectServiceDep
) -> ProjectResponse:
    return await service.get_project(project_id, user)


@router.patch(
    "/{project_id}",
    response_model=ProjectResponse,
    summary="Update project details or status",
    responses={**FORBIDDEN_RESPONSE, **NOT_FOUND_RESPONSE},
)
async def update_project(
    project_id: int,
    data: ProjectUpdate,
    user: CurrentUser,
    service: ProjectServiceDep,
) -> ProjectResponse:
    return await service.update_project(project_id, data, user)


@router.delete(
    "/{project_id}",
    status_code=204,
    summary="Delete a project and cascade delete all child tasks, labels, and comments",
    responses={**FORBIDDEN_RESPONSE, **NOT_FOUND_RESPONSE},
)
async def delete_project(
    project_id: int, user: CurrentUser, service: ProjectServiceDep
) -> None:
    await service.delete_project(project_id, user)