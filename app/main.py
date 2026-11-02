from contextlib import asynccontextmanager
from fastapi import FastAPI
from app.core.config import settings
from app.api.v1.router import api_router


@asynccontextmanager
async def lifespan(app: FastAPI):
    # Startup event
    print(f"Starting up {settings.PROJECT_NAME}...")
    yield
    # Shutdown event
    print(f"Shutting down {settings.PROJECT_NAME}...")


app = FastAPI(
    title=settings.PROJECT_NAME,
    description="TaskHub",
    version="1.0.0",
    debug=settings.DEBUG,
    lifespan=lifespan,
)

app.include_router(api_router, prefix=settings.API_V1_STR)


@app.get("/healthy", tags=["system"])
async def healthy_check():
    return {
        "status": "Healthy",
        "message": "ok",
        "version": "1.0.0",
    }
