from typing import Annotated

from fastapi import APIRouter, Depends, Response

from app.core.security import get_public_jwk
from app.dependencies import get_auth_service, get_current_user
from app.models import User
from app.schemas.auth import (
    LoginRequest,
    RefreshRequest,
    RegisterRequest,
    TokenResponse,
    UserResponse,
)
from app.services.auth import AuthService

router = APIRouter()
jwks_router = APIRouter(tags=["auth"])
AuthServiceDep = Annotated[AuthService, Depends(get_auth_service)]


@jwks_router.get("/.well-known/jwks.json")
def jwks():
    return get_public_jwk()


@router.post("/register", response_model=UserResponse, status_code=201)
async def register(data: RegisterRequest, service: AuthServiceDep):
    return await service.register(data)


@router.post("/login", response_model=TokenResponse)
async def login(data: LoginRequest, service: AuthServiceDep, response: Response):
    response.headers["Cache-Control"] = "no-store"
    response.headers["Pragma"] = "no-cache"
    return await service.login(data.email, data.password)


@router.post("/refresh", response_model=TokenResponse)
async def refresh(
    data: RefreshRequest, service: AuthServiceDep, response: Response
):
    response.headers["Cache-Control"] = "no-store"
    response.headers["Pragma"] = "no-cache"
    return await service.refresh(data.refresh_token)


@router.post("/logout", status_code=204)
async def logout(data: RefreshRequest, service: AuthServiceDep):
    await service.logout(data.refresh_token)
    return Response(status_code=204)


@router.get("/me", response_model=UserResponse)
async def me(user: Annotated[User, Depends(get_current_user)]):
    return user
