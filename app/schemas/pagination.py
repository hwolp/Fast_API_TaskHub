from typing import Annotated, Generic, TypeVar

from fastapi import Depends, Query
from pydantic import BaseModel

DEFAULT_PAGE = 1
DEFAULT_LIMIT = 20
MAX_LIMIT = 100

ItemT = TypeVar("ItemT")


class PaginationParams(BaseModel):
    page: int = DEFAULT_PAGE
    limit: int = DEFAULT_LIMIT


def get_pagination(
    page: Annotated[int, Query(ge=1)] = DEFAULT_PAGE,
    limit: Annotated[int, Query(ge=1, le=MAX_LIMIT)] = DEFAULT_LIMIT,
) -> PaginationParams:
    return PaginationParams(page=page, limit=limit)


PaginationDep = Annotated[PaginationParams, Depends(get_pagination)]


class PaginatedResponse(BaseModel, Generic[ItemT]):
    items: list[ItemT]
    total: int
