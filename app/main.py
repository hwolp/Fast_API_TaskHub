from contextlib import asynccontextmanager

from fastapi import FastAPI

from app.api.v1.endpoints.auth import jwks_router
from app.api.v1.router import api_router
from app.core.config import settings
from app.core.security import load_keys


@asynccontextmanager
async def lifespan(app: FastAPI):
    load_keys()
    yield


app = FastAPI(
    title=settings.PROJECT_NAME,
    description="TaskHub",
    version="1.0.0",
    debug=settings.DEBUG,
    lifespan=lifespan,
)

app.include_router(jwks_router)
app.include_router(api_router, prefix=settings.API_V1_STR)


@app.get("/healthy", tags=["system"])
async def healthy_check():
    return {
        "status": "Healthy",
        "message": "ok",
        "version": "1.0.0",
    }
