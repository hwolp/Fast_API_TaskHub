from fastapi import APIRouter, Response

from app.api.v1.responses import CONFLICT_RESPONSE, UNAUTHORIZED_RESPONSE
from app.core.security import get_public_jwk
from app.dependencies import AuthServiceDep, CurrentUser
from app.schemas.auth import (
    JWKSResponse,
    LoginRequest,
    RefreshRequest,
    RegisterRequest,
    TokenResponse,
    UserResponse,
)

router = APIRouter()
jwks_router = APIRouter(tags=["auth"])


@jwks_router.get(
    "/.well-known/jwks.json",
    response_model=JWKSResponse,
    summary="Get JSON Web Key Set",
    description="Returns the public RS256 signing keys used to verify access tokens.",
)
def jwks():
    return get_public_jwk()


@router.post(
    "/register",
    response_model=UserResponse,
    status_code=201,
    summary="Register a new user",
    description="Creates a new MEMBER account. Email is normalized to lowercase.",
    responses=CONFLICT_RESPONSE,
)
async def register(data: RegisterRequest, service: AuthServiceDep):
    return await service.register(data)


@router.post(
    "/login",
    response_model=TokenResponse,
    summary="Authenticate and issue JWT token pair",
    description="Validates email and password, returning an RS256 access token and rotating refresh token.",
    responses=UNAUTHORIZED_RESPONSE,
)
async def login(data: LoginRequest, service: AuthServiceDep, response: Response):
    response.headers["Cache-Control"] = "no-store"
    response.headers["Pragma"] = "no-cache"
    return await service.login(data.email, data.password)


@router.post(
    "/refresh",
    response_model=TokenResponse,
    summary="Rotate refresh token and issue new token pair",
    description="Consumes a valid refresh token and issues a new pair. Reusing a revoked token revokes the entire token family.",
    responses=UNAUTHORIZED_RESPONSE,
)
async def refresh(
    data: RefreshRequest, service: AuthServiceDep, response: Response
):
    response.headers["Cache-Control"] = "no-store"
    response.headers["Pragma"] = "no-cache"
    return await service.refresh(data.refresh_token)


@router.post(
    "/logout",
    status_code=204,
    summary="Revoke refresh token family",
    description="Revokes the refresh token family. Idempotent for already-revoked tokens belonging to the user.",
    responses=UNAUTHORIZED_RESPONSE,
)
async def logout(data: RefreshRequest, service: AuthServiceDep):
    await service.logout(data.refresh_token)
    return Response(status_code=204)


@router.get(
    "/me",
    response_model=UserResponse,
    summary="Get current authenticated user",
    description="Returns the profile of the authenticated user resolved from the Bearer access token.",
    responses=UNAUTHORIZED_RESPONSE,
)
async def me(user: CurrentUser):
    return user
