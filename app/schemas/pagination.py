from typing import Generic, TypeVar

from pydantic import BaseModel

ItemT = TypeVar("ItemT")


class PaginatedResponse(BaseModel, Generic[ItemT]):
    items: list[ItemT]
    total: int
