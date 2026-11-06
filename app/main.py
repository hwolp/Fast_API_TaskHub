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


@app.get("/.well-known/jwks.json", tags=["auth"])
def jwks():
    import json
    from cryptography.hazmat.primitives.serialization import load_pem_public_key
    from jwt.algorithms import RSAAlgorithm
    from app.core.security import read_key

    key = load_pem_public_key(read_key(settings.JWT_PUBLIC_KEY_PATH))
    public_jwk = json.loads(RSAAlgorithm.to_jwk(key))
    public_jwk.update(kid=settings.JWT_KEY_ID, use="sig", alg="RS256")
    return {"keys": [public_jwk]}


@app.get("/healthy", tags=["system"])
async def healthy_check():
    return {
        "status": "Healthy",
        "message": "ok",
        "version": "1.0.0",
    }
