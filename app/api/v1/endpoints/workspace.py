from typing import Annotated

from fastapi import APIRouter, Depends

from app.dependencies import CurrentUser, get_workspace_service
from app.schemas.pagination import PaginatedResponse, PaginationDep
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


@router.post(
    "/",
    response_model=WorkspaceResponse,
    status_code=201,
    summary="Create a new workspace",
)
async def create_workspace(
    data: WorkspaceCreate, user: CurrentUser, service: WorkspaceServiceDep
):
    return await service.create_workspace(data, user)


@router.get(
    "/",
    response_model=PaginatedResponse[WorkspaceResponse],
    summary="List workspaces with pagination",
)
async def list_workspaces(
    user: CurrentUser,
    service: WorkspaceServiceDep,
    pagination: PaginationDep,
):
    items, total = await service.list_workspaces(
        user, page=pagination.page, limit=pagination.limit
    )
    return PaginatedResponse(items=items, total=total)


@router.get(
    "/{workspace_id}",
    response_model=WorkspaceResponse,
    summary="Get workspace details by ID",
)
async def get_workspace(
    workspace_id: int, user: CurrentUser, service: WorkspaceServiceDep
):
    return await service.get_workspace(workspace_id, user)


@router.patch(
    "/{workspace_id}",
    response_model=WorkspaceResponse,
    summary="Update workspace name",
)
async def update_workspace(
    workspace_id: int,
    data: WorkspaceUpdate,
    user: CurrentUser,
    service: WorkspaceServiceDep,
):
    return await service.update_workspace(workspace_id, data, user)


@router.delete(
    "/{workspace_id}",
    status_code=204,
    summary="Delete a workspace",
)
async def delete_workspace(
    workspace_id: int, user: CurrentUser, service: WorkspaceServiceDep
):
    await service.delete_workspace(workspace_id, user)


@router.get(
    "/{workspace_id}/members",
    response_model=list[WorkspaceMemberResponse],
    summary="List all members in a workspace",
)
async def list_members(
    workspace_id: int, user: CurrentUser, service: WorkspaceServiceDep
):
    return await service.list_members(workspace_id, user)


@router.post(
    "/{workspace_id}/members",
    response_model=WorkspaceMemberResponse,
    status_code=201,
    summary="Add a new member to a workspace",
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
    summary="Update member role in a workspace",
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


@router.delete(
    "/{workspace_id}/members/{member_user_id}",
    status_code=204,
    summary="Remove a member from a workspace or leave workspace",
)
async def remove_member(
    workspace_id: int,
    member_user_id: int,
    user: CurrentUser,
    service: WorkspaceServiceDep,
):
    await service.remove_member(workspace_id, member_user_id, user)

