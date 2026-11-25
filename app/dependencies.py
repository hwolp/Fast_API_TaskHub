from typing import Annotated

from fastapi import Depends, Request
from fastapi.security import HTTPAuthorizationCredentials, HTTPBearer
from sqlalchemy.ext.asyncio import AsyncSession

from app.core import messages
from app.core.cache import RedisCache, TaskListCacheInvalidator
from app.core.database import get_db
from app.core.exceptions import UnauthorizedError
from app.core.security import decode_token
from app.models import User
from app.models.enums import TokenType
from app.repositories.auth import AuthRepository
from app.repositories.comment import CommentRepository
from app.repositories.label import LabelRepository
from app.repositories.project import ProjectRepository
from app.repositories.task import TaskRepository
from app.repositories.workspace import WorkspaceRepository
from app.services.auth import AuthService
from app.services.comment import CommentService
from app.services.label import LabelService
from app.services.project import ProjectService
from app.services.task import TaskService
from app.services.workspace import WorkspaceService

bearer = HTTPBearer(
    auto_error=False,
    bearerFormat="JWT",
    description="Paste the RS256 access_token obtained from POST /api/v1/auth/login.",
)
SessionDep = Annotated[AsyncSession, Depends(get_db)]


def get_auth_repository(session: SessionDep) -> AuthRepository:
    return AuthRepository(session)


def get_auth_service(
    repository: Annotated[AuthRepository, Depends(get_auth_repository)],
) -> AuthService:
    return AuthService(repository)


def get_task_cache(request: Request) -> RedisCache | None:
    return getattr(request.app.state, "cache", None)


TaskCacheDep = Annotated[RedisCache | None, Depends(get_task_cache)]


def get_task_list_invalidator(cache: TaskCacheDep) -> TaskListCacheInvalidator:
    return TaskListCacheInvalidator(cache)


TaskListInvalidatorDep = Annotated[
    TaskListCacheInvalidator, Depends(get_task_list_invalidator)
]


def get_task_service(
    session: SessionDep,
    cache: TaskCacheDep,
    invalidator: TaskListInvalidatorDep,
) -> TaskService:
    return TaskService(
        TaskRepository(session), cache=cache, task_cache_invalidator=invalidator
    )


def get_workspace_service(
    session: SessionDep, invalidator: TaskListInvalidatorDep
) -> WorkspaceService:
    return WorkspaceService(
        WorkspaceRepository(session), task_cache_invalidator=invalidator
    )


def get_project_service(
    session: SessionDep, invalidator: TaskListInvalidatorDep
) -> ProjectService:
    return ProjectService(
        ProjectRepository(session), task_cache_invalidator=invalidator
    )


def get_label_service(
    session: SessionDep, invalidator: TaskListInvalidatorDep
) -> LabelService:
    return LabelService(LabelRepository(session), task_cache_invalidator=invalidator)


def get_comment_service(session: SessionDep) -> CommentService:
    return CommentService(CommentRepository(session))


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
AuthServiceDep = Annotated[AuthService, Depends(get_auth_service)]
TaskServiceDep = Annotated[TaskService, Depends(get_task_service)]
WorkspaceServiceDep = Annotated[WorkspaceService, Depends(get_workspace_service)]
ProjectServiceDep = Annotated[ProjectService, Depends(get_project_service)]
LabelServiceDep = Annotated[LabelService, Depends(get_label_service)]
CommentServiceDep = Annotated[CommentService, Depends(get_comment_service)]
