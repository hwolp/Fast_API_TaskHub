from datetime import datetime, timezone
from uuid import uuid4

from sqlalchemy.exc import IntegrityError
from starlette.concurrency import run_in_threadpool

from app.core import messages
from app.core.config import settings
from app.core.exceptions import ConflictError, UnauthorizedError
from app.core.security import (
    DUMMY_HASH,
    create_token,
    decode_token,
    password_hash,
    token_hash,
    verify_password,
)
from app.models import RefreshToken, User
from app.models.enums import TokenType
from app.repositories.auth import AuthRepository
from app.schemas.auth import RegisterRequest, TokenResponse


class AuthService:
    def __init__(self, repository: AuthRepository) -> None:
        self.repository = repository
        self.session = repository.session

    async def register(self, data: RegisterRequest) -> User:
        if await self.repository.by_email(data.email):
            raise ConflictError(messages.EMAIL_ALREADY_REGISTERED)
        user = User(
            email=data.email,
            full_name=data.full_name,
            hashed_password=await run_in_threadpool(
                password_hash.hash, data.password
            ),
        )
        self.session.add(user)
        try:
            await self.session.commit()
        except IntegrityError:
            await self.session.rollback()
            raise ConflictError(messages.EMAIL_ALREADY_REGISTERED) from None
        await self.session.refresh(user)
        return user

    def issue_pair(
        self, user: User, family_id: str | None = None
    ) -> TokenResponse:
        access, _ = create_token(user.id, user.role.value, TokenType.ACCESS)
        refresh, expires = create_token(
            user.id, user.role.value, TokenType.REFRESH
        )
        self.session.add(
            RefreshToken(
                token_hash=token_hash(refresh),
                user_id=user.id,
                family_id=family_id or str(uuid4()),
                expires_at=expires.replace(tzinfo=None),
            )
        )
        return TokenResponse(
            access_token=access,
            refresh_token=refresh,
            expires_in=settings.ACCESS_TOKEN_EXPIRE_MINUTES * 60,
        )

    async def login(self, email: str, password: str) -> TokenResponse:
        user = await self.repository.by_email(email)
        valid = await run_in_threadpool(
            verify_password,
            password,
            user.hashed_password if user else DUMMY_HASH,
        )
        if not user or not valid or not user.is_active:
            raise UnauthorizedError(messages.INVALID_CREDENTIALS)
        pair = self.issue_pair(user)
        await self.session.commit()
        return pair

    async def refresh(self, raw: str) -> TokenResponse:
        payload = decode_token(raw, TokenType.REFRESH)
        user = await self.repository.lock_user(int(payload["sub"]))
        stored = await self.repository.get_refresh(token_hash(raw))
        now = datetime.now(timezone.utc).replace(tzinfo=None)
        if not user or not user.is_active or not stored or stored.user_id != user.id:
            raise UnauthorizedError(messages.TOKEN_INVALID)
        if stored.revoked_at is not None:
            await self.repository.revoke_family(stored.family_id, now)
            await self.session.commit()
            raise UnauthorizedError(messages.REFRESH_TOKEN_REUSED)
        if not await self.repository.consume(stored.token_hash, now):
            raise UnauthorizedError(messages.TOKEN_EXPIRED)
        pair = self.issue_pair(user, stored.family_id)
        await self.session.commit()
        return pair

    async def logout(self, raw: str) -> None:
        payload = decode_token(raw, TokenType.REFRESH)
        user = await self.repository.lock_user(int(payload["sub"]))
        stored = await self.repository.get_refresh(token_hash(raw))
        if not user or not stored or stored.user_id != user.id:
            raise UnauthorizedError(messages.TOKEN_INVALID)
        await self.repository.revoke_family(
            stored.family_id,
            datetime.now(timezone.utc).replace(tzinfo=None),
        )
        await self.session.commit()
