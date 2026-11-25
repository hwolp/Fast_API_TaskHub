from fastapi import APIRouter

from app.api.v1.endpoints import auth, comment, label, project, task, workspace
from app.api.v1.responses import UNAUTHORIZED_RESPONSE

api_router = APIRouter()
api_router.include_router(auth.router, prefix="/auth", tags=["auth"])
api_router.include_router(
    workspace.router,
    prefix="/workspaces",
    tags=["workspaces"],
    responses=UNAUTHORIZED_RESPONSE,
)
api_router.include_router(
    project.router,
    prefix="/projects",
    tags=["projects"],
    responses=UNAUTHORIZED_RESPONSE,
)
api_router.include_router(
    task.router,
    prefix="/tasks",
    tags=["tasks"],
    responses=UNAUTHORIZED_RESPONSE,
)
api_router.include_router(
    label.router,
    prefix="/labels",
    tags=["labels"],
    responses=UNAUTHORIZED_RESPONSE,
)
api_router.include_router(
    comment.router,
    prefix="/comments",
    tags=["comments"],
    responses=UNAUTHORIZED_RESPONSE,
)
