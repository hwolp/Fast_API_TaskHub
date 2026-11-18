from typing import Annotated

from fastapi import APIRouter, Query

from app.api.v1.params import IdPath
from app.api.v1.responses import (
    BAD_REQUEST_RESPONSE,
    FORBIDDEN_RESPONSE,
    NOT_FOUND_RESPONSE,
)
from app.dependencies import CommentServiceDep, CurrentUser
from app.schemas.comment import CommentCreate, CommentResponse, CommentUpdate
from app.schemas.pagination import PaginatedResponse, PaginationDep

router = APIRouter()


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
    comment = await service.create_comment(data, user)
    return CommentResponse.model_validate(comment)


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
        pagination=pagination,
        task_id=task_id,
    )
    return PaginatedResponse(
        items=[CommentResponse.model_validate(item) for item in items],
        total=total,
    )


@router.get(
    "/{comment_id}",
    response_model=CommentResponse,
    summary="Get comment details by ID",
    responses=NOT_FOUND_RESPONSE,
)
async def get_comment(
    comment_id: IdPath, user: CurrentUser, service: CommentServiceDep
) -> CommentResponse:
    comment = await service.get_comment(comment_id, user)
    return CommentResponse.model_validate(comment)


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
    comment_id: IdPath,
    data: CommentUpdate,
    user: CurrentUser,
    service: CommentServiceDep,
) -> CommentResponse:
    updated = await service.update_comment(comment_id, data, user)
    return CommentResponse.model_validate(updated)


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
    comment_id: IdPath, user: CurrentUser, service: CommentServiceDep
) -> None:
    await service.delete_comment(comment_id, user)
