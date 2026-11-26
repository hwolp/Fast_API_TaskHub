from typing import Annotated

from fastapi import APIRouter, Query

from app.api.v1.params import IdPath
from app.api.v1.responses import FORBIDDEN_RESPONSE, NOT_FOUND_RESPONSE
from app.dependencies import CurrentUser, ProjectServiceDep
from app.schemas.pagination import PaginatedResponse, PaginationDep
from app.schemas.project import ProjectCreate, ProjectResponse, ProjectUpdate

router = APIRouter()


@router.post(
    "/",
    response_model=ProjectResponse,
    status_code=201,
    summary="Create a new project in a workspace",
    description="Creates a project inside the target workspace. Requires EDITOR, OWNER, or global ADMIN.",
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
    description="Returns paginated projects visible to the user, optionally filtered by workspace ID.",
)
async def list_projects(
    user: CurrentUser,
    service: ProjectServiceDep,
    pagination: PaginationDep,
    workspace_id: Annotated[
        int | None, Query(ge=1, description="Filter projects by workspace ID")
    ] = None,
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
    description="Returns project details if the user has workspace access.",
    responses=NOT_FOUND_RESPONSE,
)
async def get_project(
    project_id: IdPath, user: CurrentUser, service: ProjectServiceDep
) -> ProjectResponse:
    return await service.get_project(project_id, user)


@router.patch(
    "/{project_id}",
    response_model=ProjectResponse,
    summary="Update project details or status",
    description="Updates project metadata or toggles ACTIVE/ARCHIVED status. Requires EDITOR, OWNER, or global ADMIN.",
    responses={**FORBIDDEN_RESPONSE, **NOT_FOUND_RESPONSE},
)
async def update_project(
    project_id: IdPath,
    data: ProjectUpdate,
    user: CurrentUser,
    service: ProjectServiceDep,
) -> ProjectResponse:
    return await service.update_project(project_id, data, user)


@router.delete(
    "/{project_id}",
    status_code=204,
    summary="Delete a project and cascade delete all child tasks, labels, and comments",
    description="Permanently deletes a project and all child resources. Requires workspace OWNER or global ADMIN.",
    responses={**FORBIDDEN_RESPONSE, **NOT_FOUND_RESPONSE},
)
async def delete_project(
    project_id: IdPath, user: CurrentUser, service: ProjectServiceDep
) -> None:
    await service.delete_project(project_id, user)
