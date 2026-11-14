from typing import Annotated

from fastapi import APIRouter, Depends, Query

from app.dependencies import CurrentUser, get_project_service
from app.schemas.pagination import PaginatedResponse
from app.schemas.project import ProjectCreate, ProjectResponse, ProjectUpdate
from app.services.project import ProjectService

router = APIRouter()
ProjectServiceDep = Annotated[ProjectService, Depends(get_project_service)]


@router.post("/", response_model=ProjectResponse, status_code=201)
async def create_project(
    data: ProjectCreate, user: CurrentUser, service: ProjectServiceDep
):
    return await service.create_project(data, user)


@router.get("/", response_model=PaginatedResponse[ProjectResponse])
async def list_projects(
    user: CurrentUser,
    service: ProjectServiceDep,
    workspace_id: Annotated[int | None, Query()] = None,
    page: Annotated[int, Query(ge=1)] = 1,
    limit: Annotated[int, Query(ge=1, le=100)] = 20,
):
    items, total = await service.list_projects(
        user, workspace_id=workspace_id, page=page, limit=limit
    )
    return PaginatedResponse(items=items, total=total)


@router.get("/{project_id}", response_model=ProjectResponse)
async def get_project(
    project_id: int, user: CurrentUser, service: ProjectServiceDep
):
    return await service.get_project(project_id, user)


@router.patch("/{project_id}", response_model=ProjectResponse)
async def update_project(
    project_id: int,
    data: ProjectUpdate,
    user: CurrentUser,
    service: ProjectServiceDep,
):
    return await service.update_project(project_id, data, user)


@router.delete("/{project_id}", status_code=204)
async def delete_project(
    project_id: int, user: CurrentUser, service: ProjectServiceDep
):
    await service.delete_project(project_id, user)

