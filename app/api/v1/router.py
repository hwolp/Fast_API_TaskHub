from fastapi import APIRouter

from app.api.v1.endpoints import auth, project, task, workspace

api_router = APIRouter()
api_router.include_router(auth.router, prefix="/auth", tags=["auth"])
api_router.include_router(
    workspace.router, prefix="/workspaces", tags=["workspaces"]
)
api_router.include_router(
    project.router, prefix="/projects", tags=["projects"]
)
api_router.include_router(task.router, prefix="/tasks", tags=["tasks"])
