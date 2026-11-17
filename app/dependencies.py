from typing import Annotated

from fastapi import Depends
from fastapi.security import HTTPAuthorizationCredentials, HTTPBearer
from sqlalchemy.ext.asyncio import AsyncSession

from app.core import messages
from app.core.database import get_db
from app.core.exceptions import UnauthorizedError
from app.core.security import decode_token
from app.models import User
from app.models.enums import TokenType
from app.repositories.auth import AuthRepository
from app.repositories.project import ProjectRepository
from app.repositories.task import TaskRepository
from app.repositories.workspace import WorkspaceRepository
from app.services.auth import AuthService
from app.services.project import ProjectService
from app.services.task import TaskService
from app.services.workspace import WorkspaceService

bearer = HTTPBearer(auto_error=False)
SessionDep = Annotated[AsyncSession, Depends(get_db)]


def get_auth_repository(session: SessionDep) -> AuthRepository:
    return AuthRepository(session)


def get_auth_service(
    repository: Annotated[AuthRepository, Depends(get_auth_repository)],
) -> AuthService:
    return AuthService(repository)


def get_task_service(session: SessionDep) -> TaskService:
    return TaskService(TaskRepository(session))


def get_workspace_service(session: SessionDep) -> WorkspaceService:
    return WorkspaceService(WorkspaceRepository(session))


def get_project_service(session: SessionDep) -> ProjectService:
    return ProjectService(ProjectRepository(session))


async def get_current_user(
    credentials: Annotated[HTTPAuthorizationCredentials | None, Depends(bearer)],
    repository: Annotated[AuthRepository, Depends(get_auth_repository)],
) -> User:
    if credentials is None:
        raise UnauthorizedError(messages.TOKEN_MISSING)
    payload = decode_token(credentials.credentials, TokenType.ACCESS)
    user = await repository.get_user_by_id(int(payload["sub"]))
    if user is None or not user.is_active:
        raise UnauthorizedError(messages.TOKEN_INVALID)
    return user


CurrentUser = Annotated[User, Depends(get_current_user)]
