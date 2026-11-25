from contextlib import asynccontextmanager

from fastapi import FastAPI

from app.api.v1.endpoints.auth import jwks_router
from app.api.v1.responses import HealthResponse
from app.api.v1.router import api_router
from app.core.cache import RedisCache
from app.core.config import settings
from app.core.openapi import (
    API_VERSION,
    OPENAPI_DESCRIPTION,
    OPENAPI_TAGS,
    SWAGGER_UI_PARAMETERS,
)
from app.core.security import load_keys


@asynccontextmanager
async def lifespan(app: FastAPI):
    load_keys()
    cache = (
        RedisCache(
            settings.REDIS_URL,
            settings.TASK_LIST_CACHE_TTL_SECONDS,
            socket_timeout=settings.REDIS_SOCKET_TIMEOUT_SECONDS,
        )
        if settings.REDIS_URL
        else None
    )
    app.state.cache = cache
    try:
        yield
    finally:
        if cache is not None:
            await cache.close()


def create_app(*, enable_docs: bool | None = None) -> FastAPI:
    docs_enabled = settings.ENABLE_DOCS if enable_docs is None else enable_docs
    application = FastAPI(
        title=settings.PROJECT_NAME,
        description=OPENAPI_DESCRIPTION,
        version=API_VERSION,
        debug=settings.DEBUG,
        lifespan=lifespan,
        openapi_tags=OPENAPI_TAGS,
        docs_url="/docs" if docs_enabled else None,
        redoc_url="/redoc" if docs_enabled else None,
        openapi_url="/openapi.json" if docs_enabled else None,
        swagger_ui_parameters=SWAGGER_UI_PARAMETERS,
    )

    application.include_router(jwks_router)
    application.include_router(api_router, prefix=settings.API_V1_STR)

    @application.get(
        "/healthy",
        tags=["system"],
        response_model=HealthResponse,
        summary="Check service health",
        description="Returns service liveness status and API version.",
    )
    async def healthy_check() -> HealthResponse:
        return HealthResponse(
            status="Healthy",
            message="ok",
            version=API_VERSION,
        )

    return application


app = create_app()
