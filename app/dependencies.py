"""Shared dependencies: authentication (`CurrentUser`) and service wiring."""

from typing import Annotated

from fastapi import Depends
from fastapi.security import HTTPAuthorizationCredentials, HTTPBearer
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.database import get_db
from app.core.security import decode_token, unauthorized
from app.models import User
from app.repositories.auth import AuthRepository
from app.repositories.task import TaskRepository
from app.services.auth import AuthService
from app.services.task import TaskService

bearer = HTTPBearer(auto_error=False)

SessionDep = Annotated[AsyncSession, Depends(get_db)]


def get_auth_service(session: SessionDep) -> AuthService:
    return AuthService(AuthRepository(session))


def get_task_service(session: SessionDep) -> TaskService:
    return TaskService(TaskRepository(session))


async def get_current_user(
    credentials: Annotated[HTTPAuthorizationCredentials | None, Depends(bearer)],
    session: SessionDep,
) -> User:
    if credentials is None:
        raise unauthorized("token_missing")
    payload = decode_token(credentials.credentials, "access")
    user = await session.get(User, int(payload["sub"]))
    if user is None or not user.is_active:
        raise unauthorized("token_invalid")
    return user


CurrentUser = Annotated[User, Depends(get_current_user)]
