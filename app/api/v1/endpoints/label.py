from typing import Annotated

from fastapi import APIRouter, Depends, Query

from app.dependencies import CurrentUser, get_label_service
from app.schemas.label import LabelCreate, LabelResponse, LabelUpdate
from app.schemas.pagination import PaginatedResponse, PaginationDep
from app.services.label import LabelService

router = APIRouter()
LabelServiceDep = Annotated[LabelService, Depends(get_label_service)]

BAD_REQUEST_RESPONSE = {400: {"description": "Archived project"}}
FORBIDDEN_RESPONSE = {403: {"description": "Forbidden"}}
NOT_FOUND_RESPONSE = {404: {"description": "Label or project not found"}}


@router.post(
    "/",
    response_model=LabelResponse,
    status_code=201,
    summary="Create a new label in a project",
    responses={
        **BAD_REQUEST_RESPONSE,
        **FORBIDDEN_RESPONSE,
        **NOT_FOUND_RESPONSE,
    },
)
async def create_label(
    data: LabelCreate, user: CurrentUser, service: LabelServiceDep
) -> LabelResponse:
    return await service.create_label(data, user)


@router.get(
    "/",
    response_model=PaginatedResponse[LabelResponse],
    summary="List visible labels with pagination",
)
async def list_labels(
    user: CurrentUser,
    service: LabelServiceDep,
    pagination: PaginationDep,
    project_id: Annotated[
        int | None, Query(ge=1, description="Lọc theo ID dự án")
    ] = None,
) -> PaginatedResponse[LabelResponse]:
    items, total = await service.list_labels(
        user,
        project_id=project_id,
        page=pagination.page,
        limit=pagination.limit,
    )
    return PaginatedResponse(items=items, total=total)


@router.get(
    "/{label_id}",
    response_model=LabelResponse,
    summary="Get label details by ID",
    responses=NOT_FOUND_RESPONSE,
)
async def get_label(
    label_id: int, user: CurrentUser, service: LabelServiceDep
) -> LabelResponse:
    return await service.get_label(label_id, user)


@router.patch(
    "/{label_id}",
    response_model=LabelResponse,
    summary="Update label name or color",
    responses={
        **BAD_REQUEST_RESPONSE,
        **FORBIDDEN_RESPONSE,
        **NOT_FOUND_RESPONSE,
    },
)
async def update_label(
    label_id: int,
    data: LabelUpdate,
    user: CurrentUser,
    service: LabelServiceDep,
) -> LabelResponse:
    return await service.update_label(label_id, data, user)


@router.delete(
    "/{label_id}",
    status_code=204,
    summary="Delete a label by ID",
    responses={
        **BAD_REQUEST_RESPONSE,
        **FORBIDDEN_RESPONSE,
        **NOT_FOUND_RESPONSE,
    },
)
async def delete_label(
    label_id: int, user: CurrentUser, service: LabelServiceDep
) -> None:
    await service.delete_label(label_id, user)
