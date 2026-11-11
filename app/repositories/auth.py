from datetime import datetime

from sqlalchemy import select, update
from sqlalchemy.ext.asyncio import AsyncSession

from app.models import RefreshToken, User


class AuthRepository:
    def __init__(self, session: AsyncSession) -> None:
        self.session = session

    async def get_user_by_id(self, user_id: int) -> User | None:
        return await self.session.get(User, user_id)

    async def by_email(self, email: str) -> User | None:
        return await self.session.scalar(select(User).where(User.email == email))

    async def lock_user(self, user_id: int) -> User | None:
        return await self.session.scalar(
            select(User).where(User.id == user_id).with_for_update()
        )

    async def get_refresh(self, hashed: str) -> RefreshToken | None:
        return await self.session.get(RefreshToken, hashed)

    async def revoke_family(self, family_id: str, now: datetime) -> None:
        await self.session.execute(
            update(RefreshToken)
            .where(
                RefreshToken.family_id == family_id,
                RefreshToken.revoked_at.is_(None),
            )
            .values(revoked_at=now)
        )

    async def consume(self, hashed: str, now: datetime) -> bool:
        result = await self.session.execute(
            update(RefreshToken)
            .where(
                RefreshToken.token_hash == hashed,
                RefreshToken.revoked_at.is_(None),
                RefreshToken.expires_at > now,
            )
            .values(revoked_at=now)
        )
        return result.rowcount == 1
