from typing import Annotated

from fastapi import APIRouter, Query

from app.api.v1.params import IdPath
from app.api.v1.responses import (
    BAD_REQUEST_RESPONSE,
    CONFLICT_RESPONSE,
    FORBIDDEN_RESPONSE,
    NOT_FOUND_RESPONSE,
)
from app.dependencies import CurrentUser, LabelServiceDep
from app.schemas.label import LabelCreate, LabelResponse, LabelUpdate
from app.schemas.pagination import PaginatedResponse, PaginationDep

router = APIRouter()


@router.post(
    "/",
    response_model=LabelResponse,
    status_code=201,
    summary="Create a new label in a project",
    responses={
        **BAD_REQUEST_RESPONSE,
        **FORBIDDEN_RESPONSE,
        **NOT_FOUND_RESPONSE,
        **CONFLICT_RESPONSE,
    },
)
async def create_label(
    data: LabelCreate, user: CurrentUser, service: LabelServiceDep
) -> LabelResponse:
    label = await service.create_label(data, user)
    return LabelResponse.model_validate(label)


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
        pagination=pagination,
        project_id=project_id,
    )
    return PaginatedResponse(
        items=[LabelResponse.model_validate(item) for item in items],
        total=total,
    )


@router.get(
    "/{label_id}",
    response_model=LabelResponse,
    summary="Get label details by ID",
    responses=NOT_FOUND_RESPONSE,
)
async def get_label(
    label_id: IdPath, user: CurrentUser, service: LabelServiceDep
) -> LabelResponse:
    label = await service.get_label(label_id, user)
    return LabelResponse.model_validate(label)


@router.patch(
    "/{label_id}",
    response_model=LabelResponse,
    summary="Update label name or color",
    responses={
        **BAD_REQUEST_RESPONSE,
        **FORBIDDEN_RESPONSE,
        **NOT_FOUND_RESPONSE,
        **CONFLICT_RESPONSE,
    },
)
async def update_label(
    label_id: IdPath,
    data: LabelUpdate,
    user: CurrentUser,
    service: LabelServiceDep,
) -> LabelResponse:
    updated = await service.update_label(label_id, data, user)
    return LabelResponse.model_validate(updated)


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
    label_id: IdPath, user: CurrentUser, service: LabelServiceDep
) -> None:
    await service.delete_label(label_id, user)
