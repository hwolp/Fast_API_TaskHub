from contextlib import asynccontextmanager
import logging
import sys

from fastapi import FastAPI

from app.api.v1.endpoints.auth import jwks_router
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
from app.schemas.common import HEALTH_MESSAGE_OK, HEALTH_STATUS_OK, HealthResponse


def configure_logging() -> None:
    app_logger = logging.getLogger("app")
    app_logger.setLevel(logging.INFO)
    if not app_logger.handlers:
        handler = logging.StreamHandler(sys.stdout)
        handler.setFormatter(
            logging.Formatter("%(asctime)s %(levelname)s [%(name)s] %(message)s")
        )
        app_logger.addHandler(handler)
    app_logger.propagate = False


@asynccontextmanager
async def lifespan(app: FastAPI):
    configure_logging()
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
    configure_logging()
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
            status=HEALTH_STATUS_OK,
            message=HEALTH_MESSAGE_OK,
            version=API_VERSION,
        )

    return application


app = create_app()
