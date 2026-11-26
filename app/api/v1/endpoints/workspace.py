from fastapi import APIRouter

from app.api.v1.params import IdPath
from app.api.v1.responses import (
    BAD_REQUEST_RESPONSE,
    CONFLICT_RESPONSE,
    FORBIDDEN_RESPONSE,
    NOT_FOUND_RESPONSE,
)
from app.dependencies import CurrentUser, WorkspaceServiceDep
from app.schemas.pagination import PaginatedResponse, PaginationDep
from app.schemas.workspace import (
    WorkspaceCreate,
    WorkspaceMemberAdd,
    WorkspaceMemberResponse,
    WorkspaceMemberUpdate,
    WorkspaceResponse,
    WorkspaceUpdate,
)

router = APIRouter()


@router.post(
    "/",
    response_model=WorkspaceResponse,
    status_code=201,
    summary="Create a new workspace",
    description="Creates a workspace owned by the authenticated user.",
)
async def create_workspace(
    data: WorkspaceCreate, user: CurrentUser, service: WorkspaceServiceDep
):
    return await service.create_workspace(data, user)


@router.get(
    "/",
    response_model=PaginatedResponse[WorkspaceResponse],
    summary="List workspaces with pagination",
    description="Returns paginated workspaces visible to the authenticated user.",
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
    description="Returns workspace details if the user is a member or global admin.",
    responses=NOT_FOUND_RESPONSE,
)
async def get_workspace(
    workspace_id: IdPath, user: CurrentUser, service: WorkspaceServiceDep
):
    return await service.get_workspace(workspace_id, user)


@router.patch(
    "/{workspace_id}",
    response_model=WorkspaceResponse,
    summary="Update workspace name",
    description="Updates workspace metadata. Requires workspace OWNER or global ADMIN.",
    responses={**FORBIDDEN_RESPONSE, **NOT_FOUND_RESPONSE},
)
async def update_workspace(
    workspace_id: IdPath,
    data: WorkspaceUpdate,
    user: CurrentUser,
    service: WorkspaceServiceDep,
):
    return await service.update_workspace(workspace_id, data, user)


@router.delete(
    "/{workspace_id}",
    status_code=204,
    summary="Delete a workspace",
    description="Deletes a workspace and cascades to its projects, tasks, labels, and comments. Requires workspace OWNER or global ADMIN.",
    responses={**FORBIDDEN_RESPONSE, **NOT_FOUND_RESPONSE},
)
async def delete_workspace(
    workspace_id: IdPath, user: CurrentUser, service: WorkspaceServiceDep
):
    await service.delete_workspace(workspace_id, user)


@router.get(
    "/{workspace_id}/members",
    response_model=list[WorkspaceMemberResponse],
    summary="List all members in a workspace",
    description="Lists workspace members and their roles for an accessible workspace.",
    responses=NOT_FOUND_RESPONSE,
)
async def list_members(
    workspace_id: IdPath, user: CurrentUser, service: WorkspaceServiceDep
):
    return await service.list_members(workspace_id, user)


@router.post(
    "/{workspace_id}/members",
    response_model=WorkspaceMemberResponse,
    status_code=201,
    summary="Add a new member to a workspace",
    description="Adds a user as EDITOR or VIEWER. Requires workspace OWNER or global ADMIN.",
    responses={
        **FORBIDDEN_RESPONSE,
        **NOT_FOUND_RESPONSE,
        **CONFLICT_RESPONSE,
    },
)
async def add_member(
    workspace_id: IdPath,
    data: WorkspaceMemberAdd,
    user: CurrentUser,
    service: WorkspaceServiceDep,
):
    return await service.add_member(workspace_id, data, user)


@router.patch(
    "/{workspace_id}/members/{member_user_id}",
    response_model=WorkspaceMemberResponse,
    summary="Update member role in a workspace",
    description="Changes a member role between EDITOR and VIEWER. Downgrading to VIEWER unassigns their workspace tasks.",
    responses={
        **BAD_REQUEST_RESPONSE,
        **FORBIDDEN_RESPONSE,
        **NOT_FOUND_RESPONSE,
    },
)
async def update_member_role(
    workspace_id: IdPath,
    member_user_id: IdPath,
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
    description="Removes a member (by OWNER/ADMIN) or allows a non-owner member to leave, unassigning their tasks.",
    responses={
        **BAD_REQUEST_RESPONSE,
        **FORBIDDEN_RESPONSE,
        **NOT_FOUND_RESPONSE,
    },
)
async def remove_member(
    workspace_id: IdPath,
    member_user_id: IdPath,
    user: CurrentUser,
    service: WorkspaceServiceDep,
):
    await service.remove_member(workspace_id, member_user_id, user)
