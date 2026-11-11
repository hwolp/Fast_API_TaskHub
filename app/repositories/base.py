from typing import Any, Generic, TypeVar

from sqlalchemy import func, inspect, select
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.database import Base

ModelT = TypeVar("ModelT", bound=Base)


class BaseRepository(Generic[ModelT]):
    def __init__(self, model: type[ModelT], session: AsyncSession) -> None:
        self.model = model
        self.session = session

    async def get(self, obj_id: int) -> ModelT | None:
        return await self.session.get(self.model, obj_id)

    async def get_multi(
        self, *, page: int = 1, limit: int = 20
    ) -> tuple[list[ModelT], int]:
        total = await self.session.scalar(select(func.count()).select_from(self.model))
        stmt = (
            select(self.model)
            .order_by(*inspect(self.model).primary_key)
            .offset((page - 1) * limit)
            .limit(limit)
        )
        result = await self.session.scalars(stmt)
        return list(result.all()), total or 0

    async def create(self, **data: Any) -> ModelT:
        obj = self.model(**data)
        self.session.add(obj)
        await self.session.flush()
        await self.session.refresh(obj)
        return obj

    async def update(self, obj: ModelT, data: dict[str, Any]) -> ModelT:
        for field, value in data.items():
            setattr(obj, field, value)
        await self.session.flush()
        await self.session.refresh(obj)
        return obj

    async def delete(self, obj: ModelT) -> None:
        await self.session.delete(obj)
        await self.session.flush()
