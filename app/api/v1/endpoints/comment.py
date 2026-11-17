from typing import Annotated

from fastapi import APIRouter, Depends, Query

from app.dependencies import CurrentUser, get_comment_service
from app.schemas.comment import CommentCreate, CommentResponse, CommentUpdate
from app.schemas.pagination import PaginatedResponse, PaginationDep
from app.services.comment import CommentService

router = APIRouter()
CommentServiceDep = Annotated[CommentService, Depends(get_comment_service)]

BAD_REQUEST_RESPONSE = {400: {"description": "Archived project"}}
FORBIDDEN_RESPONSE = {403: {"description": "Forbidden"}}
NOT_FOUND_RESPONSE = {404: {"description": "Comment or task not found"}}


@router.post(
    "/",
    response_model=CommentResponse,
    status_code=201,
    summary="Create a new comment on a task",
    responses={
        **BAD_REQUEST_RESPONSE,
        **FORBIDDEN_RESPONSE,
        **NOT_FOUND_RESPONSE,
    },
)
async def create_comment(
    data: CommentCreate, user: CurrentUser, service: CommentServiceDep
) -> CommentResponse:
    return await service.create_comment(data, user)


@router.get(
    "/",
    response_model=PaginatedResponse[CommentResponse],
    summary="List visible comments with pagination",
)
async def list_comments(
    user: CurrentUser,
    service: CommentServiceDep,
    pagination: PaginationDep,
    task_id: Annotated[
        int | None, Query(ge=1, description="Lọc theo ID task")
    ] = None,
) -> PaginatedResponse[CommentResponse]:
    items, total = await service.list_comments(
        user,
        task_id=task_id,
        page=pagination.page,
        limit=pagination.limit,
    )
    return PaginatedResponse(items=items, total=total)


@router.get(
    "/{comment_id}",
    response_model=CommentResponse,
    summary="Get comment details by ID",
    responses=NOT_FOUND_RESPONSE,
)
async def get_comment(
    comment_id: int, user: CurrentUser, service: CommentServiceDep
) -> CommentResponse:
    return await service.get_comment(comment_id, user)


@router.patch(
    "/{comment_id}",
    response_model=CommentResponse,
    summary="Update comment content",
    responses={
        **BAD_REQUEST_RESPONSE,
        **FORBIDDEN_RESPONSE,
        **NOT_FOUND_RESPONSE,
    },
)
async def update_comment(
    comment_id: int,
    data: CommentUpdate,
    user: CurrentUser,
    service: CommentServiceDep,
) -> CommentResponse:
    return await service.update_comment(comment_id, data, user)


@router.delete(
    "/{comment_id}",
    status_code=204,
    summary="Delete a comment by ID",
    responses={
        **BAD_REQUEST_RESPONSE,
        **FORBIDDEN_RESPONSE,
        **NOT_FOUND_RESPONSE,
    },
)
async def delete_comment(
    comment_id: int, user: CurrentUser, service: CommentServiceDep
) -> None:
    await service.delete_comment(comment_id, user)
