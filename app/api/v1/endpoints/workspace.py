from typing import Annotated

from fastapi import APIRouter, Depends, Query

from app.dependencies import CurrentUser, get_workspace_service
from app.schemas.pagination import PaginatedResponse
from app.schemas.workspace import (
    WorkspaceCreate,
    WorkspaceMemberAdd,
    WorkspaceMemberResponse,
    WorkspaceMemberUpdate,
    WorkspaceResponse,
    WorkspaceUpdate,
)
from app.services.workspace import WorkspaceService

router = APIRouter()
WorkspaceServiceDep = Annotated[WorkspaceService, Depends(get_workspace_service)]


@router.post("/", response_model=WorkspaceResponse, status_code=201)
async def create_workspace(
    data: WorkspaceCreate, user: CurrentUser, service: WorkspaceServiceDep
):
    return await service.create_workspace(data, user)


@router.get("/", response_model=PaginatedResponse[WorkspaceResponse])
async def list_workspaces(
    user: CurrentUser,
    service: WorkspaceServiceDep,
    page: Annotated[int, Query(ge=1)] = 1,
    limit: Annotated[int, Query(ge=1, le=100)] = 20,
):
    items, total = await service.list_workspaces(user, page=page, limit=limit)
    return PaginatedResponse(items=items, total=total)


@router.get("/{workspace_id}", response_model=WorkspaceResponse)
async def get_workspace(
    workspace_id: int, user: CurrentUser, service: WorkspaceServiceDep
):
    return await service.get_workspace(workspace_id, user)


@router.patch("/{workspace_id}", response_model=WorkspaceResponse)
async def update_workspace(
    workspace_id: int,
    data: WorkspaceUpdate,
    user: CurrentUser,
    service: WorkspaceServiceDep,
):
    return await service.update_workspace(workspace_id, data, user)


@router.delete("/{workspace_id}", status_code=204)
async def delete_workspace(
    workspace_id: int, user: CurrentUser, service: WorkspaceServiceDep
):
    await service.delete_workspace(workspace_id, user)


@router.get(
    "/{workspace_id}/members", response_model=list[WorkspaceMemberResponse]
)
async def list_members(
    workspace_id: int, user: CurrentUser, service: WorkspaceServiceDep
):
    return await service.list_members(workspace_id, user)


@router.post(
    "/{workspace_id}/members",
    response_model=WorkspaceMemberResponse,
    status_code=201,
)
async def add_member(
    workspace_id: int,
    data: WorkspaceMemberAdd,
    user: CurrentUser,
    service: WorkspaceServiceDep,
):
    return await service.add_member(workspace_id, data, user)


@router.patch(
    "/{workspace_id}/members/{member_user_id}",
    response_model=WorkspaceMemberResponse,
)
async def update_member_role(
    workspace_id: int,
    member_user_id: int,
    data: WorkspaceMemberUpdate,
    user: CurrentUser,
    service: WorkspaceServiceDep,
):
    return await service.update_member_role(
        workspace_id, member_user_id, data, user
    )


@router.delete("/{workspace_id}/members/{member_user_id}", status_code=204)
async def remove_member(
    workspace_id: int,
    member_user_id: int,
    user: CurrentUser,
    service: WorkspaceServiceDep,
):
    await service.remove_member(workspace_id, member_user_id, user)

